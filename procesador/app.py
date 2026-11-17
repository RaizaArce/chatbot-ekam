"""Procesador de manuales del servidor: recibe los manuales que un administrador sube desde el portal, los limpia
(datos reales -> ficticios) y, cuando el administrador lo pide, los carga para que el asistente los use.

Corre en el contenedor navasoft-procesador. Traefik le pasa lo que llega a
https://<servidor>/navasoft-procesador/... (mismo dominio que el portal, asi el navegador lo permite).

Estados de un manual (tabla manuales_subidos):
  en_cola -> limpiando -> revisar -> (publicar) publicando -> publicado
                                  -> (descartar) se borra
  cualquier paso puede terminar en 'error' (se ve el detalle en el portal).
El trabajo pesado (OCR, limpieza, vectores) lo hace un solo hilo, de a un manual, para no ahogar el servidor.
"""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pymupdf
from psycopg.rows import dict_row

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import auditar_datos_sensibles as auditoria  # noqa: E402
import leer_manuales  # noqa: E402
import limpiar_manuales  # noqa: E402

PREFIJO = "/navasoft-procesador"
DATOS = pathlib.Path(os.environ.get("NAVASOFT_DATOS", "/data"))
ORIGINALES = auditoria.MANUALES / "portal"          # lo que suben los administradores (ya en PDF)
MAX_BYTES = 80 * 1024 * 1024
CARPETA_TRABAJO = DATOS / "trabajo"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS manuales_subidos (
    id          bigserial PRIMARY KEY,
    archivo     text NOT NULL,              -- 'portal/<titulo>.pdf': el nombre con que queda en la base
    titulo      text NOT NULL,
    original    text NOT NULL,              -- nombre del archivo que se subio
    subido_por  text,
    estado      text NOT NULL DEFAULT 'en_cola',
    avance      text,
    error       text,
    paginas     int,
    paginas_cambiadas int[],
    zonas       int,
    creado      timestamptz NOT NULL DEFAULT now(),
    actualizado timestamptz NOT NULL DEFAULT now(),
    publicado   timestamptz
);
CREATE TABLE IF NOT EXISTS manuales_cargados (archivo text PRIMARY KEY, hash text, fecha timestamptz DEFAULT now());
"""


def con():
    return leer_manuales.conectar()


def actualizar(mid, **campos):
    sets = ", ".join(f"{k} = %s" for k in campos)
    with con() as c:
        c.execute(f"UPDATE manuales_subidos SET {sets}, actualizado = now() WHERE id = %s", (*campos.values(), mid))


def admin(token):
    """Nombre del administrador dueno de la sesion, o None si la sesion no es de un administrador."""
    if not token or not re.fullmatch(r"[0-9a-fA-F-]{36}", token):
        return None
    with con() as c:
        r = c.execute("SELECT navasoft_api('yo', jsonb_build_object('token', %s::text))", (token,)).fetchone()[0]
    return r.get("nombre") if r and r.get("ok") and r.get("rol") == "admin" else None


def nombre_seguro(titulo):
    """Titulo -> nombre de archivo: sin caracteres raros ni rutas (el titulo es como el cliente vera el manual)."""
    t = unicodedata.normalize("NFC", titulo).strip()
    t = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:120]


# ---------------------------------------------------------------- trabajo pesado (un solo hilo)
def convertir_a_pdf(origen):
    """Word -> PDF con LibreOffice (el PDF trae numeros de pagina, que el asistente cita)."""
    salida = CARPETA_TRABAJO / f"conv_{os.getpid()}_{int(time.time())}"
    salida.mkdir(parents=True, exist_ok=True)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(salida), str(origen)],
                   check=True, timeout=600, capture_output=True)
    pdf = next(salida.glob("*.pdf"))
    return pdf


def limpiar(fila):
    mid, archivo = fila["id"], fila["archivo"]
    original = ORIGINALES / pathlib.Path(archivo).name
    actualizar(mid, estado="limpiando", avance="Leyendo las capturas del manual (puede tardar varios minutos)…", error=None)
    reglas = limpiar_manuales.cargar_reglas()
    limpiar_manuales.titulo_limpio(original.stem, reglas)   # el titulo no puede nombrar a un cliente
    lectura = auditoria.lectura(original)
    cajas = limpiar_manuales.cajas_a_tapar(original, lectura, reglas)
    actualizar(mid, avance="Reemplazando los datos reales por datos ficticios…")
    zonas = limpiar_manuales.limpiar(original, reglas)
    with pymupdf.open(original) as d:
        paginas = len(d)
    actualizar(mid, estado="revisar", avance=None, paginas=paginas, paginas_cambiadas=sorted(cajas), zonas=zonas)


def publicar(fila):
    mid, archivo = fila["id"], fila["archivo"]
    original = ORIGINALES / pathlib.Path(archivo).name
    copia = limpiar_manuales.destino(original)
    if not copia.exists():
        raise RuntimeError("No se encontró la copia limpia del manual. Vuelve a subirlo.")
    actualizar(mid, estado="publicando", avance="Preparando el manual para el asistente (capturas, búsqueda e índice)…")
    c = con()
    leer_manuales.procesar(c, copia)
    # indice del manual (temas y paginas)
    from crear_indice import titulos_de
    titulo = leer_manuales.titulo_manual(copia)
    guardadas = {r[0] for r in c.execute("SELECT id FROM paginas")}
    c.execute("DELETE FROM manual_indice WHERE archivo = %s", (archivo,))
    filas = []
    for orden, (num, t, pag) in enumerate(titulos_de(copia)):
        pid = leer_manuales.id_corto(f"{archivo}#{pag}")
        url = f"{leer_manuales.URL_PUBLICA}/navasoft-pagina?id={pid}" if pid in guardadas else None
        filas.append((titulo, archivo, orden, num, t, pag, url))
    with c.cursor() as cur:
        cur.executemany("INSERT INTO manual_indice VALUES (%s, %s, %s, %s, %s, %s, %s)", filas)
    import corregir_secciones
    corregir_secciones.main(solo=archivo)
    c.execute("INSERT INTO manuales_cargados (archivo, hash) VALUES (%s, %s) "
              "ON CONFLICT (archivo) DO UPDATE SET hash = EXCLUDED.hash, fecha = now()",
              (archivo, hashlib.md5(copia.read_bytes()).hexdigest()))
    c.execute("TRUNCATE respuestas_cache")   # las respuestas guardadas no conocian este manual
    c.close()
    actualizar(mid, estado="publicado", avance=None, publicado=time.strftime("%Y-%m-%d %H:%M:%S%z"))


def trabajador():
    """Toma de la base el siguiente manual pendiente (por orden de llegada) y lo procesa."""
    with con() as c:   # lo que quedo a medias si el contenedor se reinicio
        c.execute("UPDATE manuales_subidos SET estado = 'en_cola' WHERE estado = 'limpiando'")
        c.execute("UPDATE manuales_subidos SET estado = 'publicar' WHERE estado = 'publicando'")
    while True:
        try:
            with con() as c:
                c.row_factory = dict_row
                fila = c.execute("SELECT * FROM manuales_subidos WHERE estado IN ('en_cola', 'publicar') "
                                 "ORDER BY actualizado LIMIT 1").fetchone()
            if not fila:
                time.sleep(5)
                continue
            try:
                (limpiar if fila["estado"] == "en_cola" else publicar)(fila)
            except BaseException as e:   # SystemExit incluido: lo usan los scripts para avisar problemas
                traceback.print_exc()
                mensaje = str(e) or e.__class__.__name__
                actualizar(fila["id"], estado="error", avance=None, error=mensaje[:500])
        except Exception:
            traceback.print_exc()
            time.sleep(15)


# ---------------------------------------------------------------- HTTP
class Manejador(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):   # sin datos de la sesion en el registro
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    def responder(self, codigo, cuerpo, tipo="application/json"):
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo, ensure_ascii=False, default=str).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(datos)

    def ruta(self):
        partes = urllib.parse.urlsplit(self.path)
        return partes.path.removeprefix(PREFIJO), dict(urllib.parse.parse_qsl(partes.query))

    def quien(self):
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        return admin(token)

    def do_GET(self):
        ruta, q = self.ruta()
        if ruta == "/salud":
            return self.responder(200, {"ok": True})
        if not self.quien():
            return self.responder(403, {"ok": False, "error": "Solo un administrador puede ver los manuales."})
        if ruta == "/lista":
            with con() as c:
                c.row_factory = dict_row
                filas = c.execute("""SELECT id, titulo, original, subido_por, estado, avance, error, paginas,
                                            coalesce(array_length(paginas_cambiadas, 1), 0) AS paginas_con_cambios,
                                            zonas, creado, actualizado, publicado
                                     FROM manuales_subidos ORDER BY creado DESC LIMIT 100""").fetchall()
            return self.responder(200, {"ok": True, "manuales": filas})
        if ruta == "/copia":
            with con() as c:
                fila = c.execute("SELECT archivo FROM manuales_subidos WHERE id = %s", (int(q.get("id", 0)),)).fetchone()
            copia = fila and limpiar_manuales.destino(ORIGINALES / pathlib.Path(fila[0]).name)
            if not copia or not copia.exists():
                return self.responder(404, {"ok": False, "error": "La copia limpia todavía no está lista."})
            return self.responder(200, copia.read_bytes(), "application/pdf")
        return self.responder(404, {"ok": False, "error": "No existe."})

    def do_POST(self):
        ruta, q = self.ruta()
        quien = self.quien()
        if not quien:
            return self.responder(403, {"ok": False, "error": "Solo un administrador puede subir manuales."})
        if ruta == "/subir":
            return self.subir(quien)
        if ruta in ("/publicar", "/descartar"):
            mid = int(q.get("id", 0))
            with con() as c:
                fila = c.execute("SELECT estado, archivo FROM manuales_subidos WHERE id = %s", (mid,)).fetchone()
                if not fila:
                    return self.responder(404, {"ok": False, "error": "No existe ese manual."})
                if ruta == "/publicar":
                    if fila[0] not in ("revisar", "error"):
                        return self.responder(409, {"ok": False, "error": "El manual todavía no está listo para publicar."})
                    if fila[0] == "error" and not limpiar_manuales.destino(ORIGINALES / pathlib.Path(fila[1]).name).exists():
                        return self.responder(409, {"ok": False, "error": "El manual falló antes de limpiarse: súbelo de nuevo."})
                    c.execute("UPDATE manuales_subidos SET estado = 'publicar', error = NULL, actualizado = now() WHERE id = %s", (mid,))
                    return self.responder(200, {"ok": True})
                if fila[0] in ("publicando", "publicado", "limpiando"):
                    return self.responder(409, {"ok": False, "error": "Ese manual no se puede descartar ahora."})
                c.execute("DELETE FROM manuales_subidos WHERE id = %s", (mid,))
            original = ORIGINALES / pathlib.Path(fila[1]).name
            for f in (original, limpiar_manuales.destino(original)):
                f.unlink(missing_ok=True)
            return self.responder(200, {"ok": True})
        return self.responder(404, {"ok": False, "error": "No existe."})

    def subir(self, quien):
        largo = int(self.headers.get("Content-Length") or 0)
        if not largo or largo > MAX_BYTES:
            return self.responder(413, {"ok": False, "error": "El archivo está vacío o pesa más de 80 MB."})
        original = urllib.parse.unquote(self.headers.get("X-Nombre-Archivo") or "")
        titulo = nombre_seguro(urllib.parse.unquote(self.headers.get("X-Titulo") or ""))
        extension = pathlib.Path(original).suffix.lower()
        if extension not in (".pdf", ".docx", ".doc"):
            return self.responder(400, {"ok": False, "error": "Sube el manual en PDF o Word (.docx)."})
        if len(titulo) < 4:
            return self.responder(400, {"ok": False, "error": "Escribe el título del manual (como lo verán los clientes)."})
        datos = self.rfile.read(largo)
        archivo = f"portal/{titulo}.pdf"
        with con() as c:
            ocupado = c.execute("SELECT 1 FROM manuales_subidos WHERE archivo = %s UNION "
                                "SELECT 1 FROM manuales_cargados WHERE archivo = %s", (archivo, archivo)).fetchone()
        if ocupado:
            return self.responder(409, {"ok": False, "error": "Ya hay un manual con ese título. Usa otro título."})
        ORIGINALES.mkdir(parents=True, exist_ok=True)
        CARPETA_TRABAJO.mkdir(parents=True, exist_ok=True)
        destino = ORIGINALES / f"{titulo}.pdf"
        try:
            if extension == ".pdf":
                if not datos.startswith(b"%PDF"):
                    return self.responder(400, {"ok": False, "error": "El archivo no es un PDF válido."})
                destino.write_bytes(datos)
            else:
                temporal = CARPETA_TRABAJO / f"subida_{int(time.time())}{extension}"
                temporal.write_bytes(datos)
                pdf = convertir_a_pdf(temporal)
                shutil.move(str(pdf), destino)
                temporal.unlink(missing_ok=True)
                shutil.rmtree(pdf.parent, ignore_errors=True)
            with pymupdf.open(destino) as d:
                if len(d) == 0:
                    raise ValueError("vacío")
        except Exception:
            destino.unlink(missing_ok=True)
            return self.responder(400, {"ok": False, "error": "No se pudo abrir el archivo. Revisa que el PDF o Word no esté dañado."})
        with con() as c:
            mid = c.execute("INSERT INTO manuales_subidos (archivo, titulo, original, subido_por, avance) "
                            "VALUES (%s, %s, %s, %s, 'En cola para procesar…') RETURNING id",
                            (archivo, titulo, original[:200], quien)).fetchone()[0]
        return self.responder(200, {"ok": True, "id": mid})


def main():
    with con() as c:
        c.execute(ESQUEMA)
    threading.Thread(target=trabajador, daemon=True).start()
    servidor = ThreadingHTTPServer(("0.0.0.0", 8080), Manejador)
    print("Procesador de manuales escuchando en el puerto 8080", flush=True)
    servidor.serve_forever()


if __name__ == "__main__":
    main()
