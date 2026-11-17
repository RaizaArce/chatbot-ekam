"""Describe las capturas de los manuales con IA de vision (gemma3:4b en Ollama, gratis y local) y agrega
la descripcion al texto del fragmento al que pertenece cada captura, para que el asistente tambien
encuentre respuestas que solo estan "dibujadas" en la pantalla (nombres de botones, columnas, pestanas).

Es lento en esta laptop (1 a 3 minutos por captura), por eso se hace de a poco y retoma donde se quedo:
  .venv\\Scripts\\python.exe describir_capturas.py --max 10                 (10 capturas)
  .venv\\Scripts\\python.exe describir_capturas.py --max 40 --solo "caja chica"
  .venv\\Scripts\\python.exe describir_capturas.py --estado                 (cuantas faltan)
Conviene dejarlo corriendo de noche, no durante una presentacion (usa mucha memoria)."""
import argparse
import base64
import re
import sys
import time

import requests

from leer_manuales import MODELOS, OLLAMA, conectar, id_corto, vectorizar

sys.stdout.reconfigure(encoding="utf-8")
MODELO_VISION = "gemma3:4b"
PROMPT = ("Imagen tomada de un manual del sistema contable/ERP NAVASOFT. Si NO es una ventana o pantalla del sistema con textos legibles "
          "(por ejemplo un logo, una franja decorativa, una portada o un dibujo), responde solamente: NO_ES_PANTALLA. "
          "Si es una pantalla, describe en español, en 2 a 4 frases, qué pantalla es y qué botones, campos, pestañas o columnas se ven, "
          "copiando los nombres exactos que aparecen escritos. No inventes nada que no esté escrito en la imagen.")
MARCA = re.compile(r"\n\[Descripción de la captura: [^\]]*\]")
# palabras que no prueban nada al comparar la descripcion con el texto leido de la pagina
COMUNES = {"pantalla", "captura", "navasoft", "sistema", "muestra", "permite", "utiliza", "botones", "campos", "columnas", "pestañas",
           "imagen", "registro", "información", "datos", "donde", "cuales", "cuenta", "botón", "campo", "columna", "pestaña", "ventana"}


def preparar(con):
    con.execute("""CREATE TABLE IF NOT EXISTS capturas_descripcion (
        imagen_id text PRIMARY KEY, archivo text, ruta text, descripcion text, modelo text, fecha timestamptz DEFAULT now())""")
    con.execute("ALTER TABLE capturas_descripcion ADD COLUMN IF NOT EXISTS estado text")


def normal(t):
    t = t.lower()
    for a, b in zip("áéíóú", "aeiou"):
        t = t.replace(a, b)
    return t


def es_decorativa(data):
    """Logos, franjas de portada e iconos: no son pantallas del sistema."""
    import io
    import PIL.Image
    an, al = PIL.Image.open(io.BytesIO(bytes(data))).size
    return an * al < 250 * 180 or an / al > 4 or al / an > 4


def comprobar(desc, texto_pagina):
    """La descripcion se acepta solo si nombra cosas que de verdad estan escritas en la pagina (texto + OCR)."""
    pagina = normal(texto_pagina)
    palabras = {w for w in re.findall(r"[a-záéíóúñ]{5,}", desc.lower()) if w not in COMUNES}
    coinciden = {w for w in palabras if normal(w) in pagina}
    return len(coinciden) >= 4, len(coinciden)


def describir(data):
    r = requests.post(f"{OLLAMA}/api/generate", timeout=900, json={
        "model": MODELO_VISION, "prompt": PROMPT, "images": [base64.b64encode(bytes(data)).decode()], "stream": False,
        "keep_alive": "5m", "options": {"temperature": 0.1, "num_predict": 220}})
    r.raise_for_status()
    texto = re.sub(r"\s+", " ", r.json()["response"]).strip()
    return texto.replace("{", "(").replace("}", ")").replace("[", "(").replace("]", ")")  # n8n no acepta llaves


def texto_con_descripciones(con, texto, rutas):
    """Texto original del fragmento + la descripcion de cada una de sus capturas (sin repetirlas)."""
    base = MARCA.sub("", texto)
    ids = [id_corto(r) for r in rutas]
    descs = dict(con.execute("SELECT imagen_id, descripcion FROM capturas_descripcion WHERE imagen_id = ANY(%s) AND descripcion IS NOT NULL", (ids,)).fetchall())
    return base + "".join(f"\n[Descripción de la captura: {descs[i]}]" for i in ids if i in descs)


def actualizar_fragmentos(con, imagen_ids):
    filas = []
    for modelo, (tabla, _) in MODELOS.items():
        filas = con.execute(f"""SELECT id, text, metadata->'imagenes' FROM {tabla}
            WHERE EXISTS (SELECT 1 FROM jsonb_array_elements_text(coalesce(metadata->'imagenes', '[]'::jsonb)) r
                          WHERE substr(md5(r), 1, 12) = ANY(%s))""", (list(imagen_ids),)).fetchall()
        for fid, texto, rutas in filas:
            nuevo = texto_con_descripciones(con, texto, rutas)
            if nuevo != texto:
                con.execute(f"UPDATE {tabla} SET text = %s, embedding = %s::vector WHERE id = %s",
                            (nuevo, str(vectorizar(modelo, [nuevo])[0]), fid))
    return len(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=10, help="cuantas capturas describir en esta vuelta")
    ap.add_argument("--solo", help="solo capturas de manuales cuyo nombre contenga este texto")
    ap.add_argument("--estado", action="store_true", help="solo mostrar cuantas capturas faltan")
    ap.add_argument("--orden", help="manuales a describir primero, separados por comas (ej. \"caja chica,ventas\")")
    ap.add_argument("--minutos", type=float, default=0, help="detenerse despues de estos minutos (0 = sin limite)")
    args = ap.parse_args()
    con = conectar()
    preparar(con)
    tabla = next(iter(MODELOS.values()))[0]
    pendientes, vistas = [], set()
    for archivo, rutas, texto in con.execute(f"""SELECT metadata->>'archivo', metadata->'imagenes', text FROM {tabla}
            WHERE jsonb_array_length(coalesce(metadata->'imagenes', '[]'::jsonb)) > 0
            ORDER BY metadata->>'archivo', (metadata->>'pagina')::int NULLS LAST"""):
        for ruta in rutas:
            iid = id_corto(ruta)
            if iid not in vistas:
                vistas.add(iid)
                pendientes.append((iid, archivo, ruta, MARCA.sub("", texto)))
    hechas = {r[0] for r in con.execute("SELECT imagen_id FROM capturas_descripcion")}
    faltan = [p for p in pendientes if p[0] not in hechas]
    print(f"Capturas: {len(pendientes)} en total, {len(pendientes) - len(faltan)} descritas, {len(faltan)} por describir.")
    if args.estado:
        return
    if args.solo:
        faltan = [p for p in faltan if args.solo.lower() in p[1].lower()]
    if args.orden:
        # primero los manuales de la lista, en ese orden; luego el resto
        prioridad = [x.strip().lower() for x in args.orden.split(",") if x.strip()]
        rango = lambda p: next((i for i, x in enumerate(prioridad) if x in p[1].lower()), len(prioridad))
        faltan.sort(key=rango)
    limite = time.time() + args.minutos * 60 if args.minutos else None

    def anotar(iid, archivo, ruta, desc, estado):
        con.execute("INSERT INTO capturas_descripcion (imagen_id, archivo, ruta, descripcion, modelo, estado) VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (imagen_id) DO UPDATE SET descripcion = EXCLUDED.descripcion, estado = EXCLUDED.estado, fecha = now()",
                    (iid, archivo, ruta, desc, MODELO_VISION, estado))

    for n, (iid, archivo, ruta, texto_pagina) in enumerate(faltan[:args.max], 1):
        if limite and time.time() > limite:
            print("Tiempo terminado: se detiene aquí (lo avanzado queda guardado).")
            break
        fila = con.execute("SELECT data FROM imagenes WHERE id = %s", (iid,)).fetchone()
        if not fila:
            continue
        if es_decorativa(fila[0]):
            anotar(iid, archivo, ruta, None, "descartada: imagen decorativa")
            print(f"  [{n}] {ruta}: descartada (logo o franja decorativa, sin usar la IA)")
            continue
        t0 = time.time()
        try:
            desc = describir(fila[0])
        except Exception as e:  # noqa: BLE001 - se sigue con la siguiente captura
            print(f"  ! {ruta}: {e}")
            continue
        if "NO_ES_PANTALLA" in desc:
            anotar(iid, archivo, ruta, None, "descartada: la IA dice que no es una pantalla")
            print(f"  [{n}] {ruta}: descartada (no es una pantalla del sistema, {time.time() - t0:.0f}s)")
            continue
        ok, coinciden = comprobar(desc, texto_pagina)
        if not ok:
            anotar(iid, archivo, ruta, None, f"descartada: solo {coinciden} nombres coinciden con la página")
            print(f"  [{n}] {ruta}: descartada (no se pudo comprobar con el texto de la página: {coinciden} coincidencias)\n      {desc[:160]}")
            continue
        anotar(iid, archivo, ruta, desc, f"aceptada: {coinciden} nombres comprobados")
        frag = actualizar_fragmentos(con, [iid])
        print(f"  [{n}] {ruta} ({time.time() - t0:.0f}s, {coinciden} nombres comprobados, {frag} fragmento/s actualizado/s)\n      {desc[:200]}")
    if faltan[:args.max]:
        con.execute("TRUNCATE respuestas_cache")  # las respuestas guardadas no conocian las descripciones nuevas
    print("Listo.")


if __name__ == "__main__":
    main()
