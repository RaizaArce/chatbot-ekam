"""Lee los manuales de NAVASOFT (PDF y Word), incluidas sus capturas, y los guarda
en la base de datos para que el chatbot pueda buscar en ellos.

Uso:
  .venv\\Scripts\\python.exe leer_manuales.py                     (todos los manuales)
  .venv\\Scripts\\python.exe leer_manuales.py --solo "caja chica" (solo los que coincidan)
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

import psycopg
import pymupdf
import requests
from dotenv import load_dotenv
from rapidocr_onnxruntime import RapidOCR

sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).parent
load_dotenv(BASE / ".env")

MANUALES = pathlib.Path(os.getenv("MANUALES_DIR", r"C:\PRÁCTICAS EKAM\Manuales NAVASOFT"))
# en el servidor (procesador de manuales) las carpetas de datos van en NAVASOFT_DATOS; en la laptop, junto al codigo
DATOS = pathlib.Path(os.getenv("NAVASOFT_DATOS", str(BASE)))
CONVERTIDOS = DATOS / "manuales_convertidos"  # manuales Word pasados a PDF para tener paginas
LIMPIOS = DATOS / "manuales_limpios"  # copias con los datos de clientes tapados: lo unico que se carga
IMAGENES = DATOS / "imagenes"
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
# Direccion desde la que el chat del cliente pide las imagenes (cambiar al subirlo a un servidor)
URL_PUBLICA = os.getenv("URL_PUBLICA", "http://localhost:5678/webhook").rstrip("/")
EXCLUIR = ["CLUB DE CONVERSACI", "BACKUP", "MANUAL_CONTROL_FACTURACION_ELECTRONICA"]  # material que no es de NAVASOFT o que trae
# datos de otros clientes (de facturacion electronica se carga la copia de anonimizar_facturacion.py)
# bge-m3 gano la comparacion con nomic-embed-text en preguntas reales (ver comparar_busqueda.py)
MODELOS = {"bge-m3": ("chunks_bge_m3", 1024)}
MAX_CHARS = 1500
MIN_IMG_PX = 120 * 120

ocr = RapidOCR()


# ---------------------------------------------------------------- utilidades
def slug(texto):
    t = texto.lower()
    for a, b in zip("áéíóúñ", "aeioun"):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def titulo_manual(path):
    import limpiar_manuales  # aqui: limpiar_manuales importa la auditoria y no hace falta para otras tareas
    t = re.sub(r"[_\-]+", " ", path.stem)
    return limpiar_manuales.titulo_limpio(re.sub(r"\s+", " ", t).strip())


def leer_captura(data):
    res, _ = ocr(data)
    return " | ".join(r[1] for r in (res or []) if r[2] > 0.5)


def guardar_png(data, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    pix = pymupdf.Pixmap(data)
    if pix.alpha or pix.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    pix.save(destino)


def es_titulo(linea):
    s = linea.strip()
    if not 3 <= len(s) <= 80 or s.endswith(":"):
        return False
    if re.match(r"^\d+(\.\d+)*\.?\s+\S", s):
        return True
    letras = [c for c in s if c.isalpha()]
    return len(letras) >= 4 and sum(c.isupper() for c in letras) / len(letras) > 0.85


# ---------------------------------------------------------------- PDF
def segmentos_pdf(path, carpeta_img):
    """Devuelve una lista de segmentos (pagina, seccion, texto, imagen|None) en orden de lectura."""
    doc = pymupdf.open(path)
    paginas = []
    usos = collections.Counter()
    lineas_por_pag = collections.Counter()
    for page in doc:
        bloques = sorted(page.get_text("dict")["blocks"], key=lambda b: (round(b["bbox"][1]), b["bbox"][0]))
        paginas.append(bloques)
        vistas = set()
        for b in bloques:
            if b["type"] == 1:
                usos[hashlib.md5(b["image"]).hexdigest()] += 1
            else:
                for ln in b["lines"]:
                    vistas.add("".join(s["text"] for s in ln["spans"]).strip())
        lineas_por_pag.update(vistas)
    # encabezados y pies de pagina: lineas que se repiten en muchas paginas
    repetidas = {l for l, c in lineas_por_pag.items() if len(doc) > 3 and c > len(doc) * 0.4}

    segs, seccion = [], ""
    for num, bloques in enumerate(paginas, start=1):
        n_img = 0
        for b in bloques:
            if b["type"] == 1:
                h = hashlib.md5(b["image"]).hexdigest()
                if usos[h] > 2 or b["width"] * b["height"] < MIN_IMG_PX:
                    continue  # logos repetidos e iconos
                n_img += 1
                destino = carpeta_img / f"p{num:03d}_{n_img}.png"
                guardar_png(b["image"], destino)
                texto = leer_captura(b["image"])
                segs.append((num, seccion, f"[Captura de pantalla: {texto}]" if texto else "[Captura de pantalla]", destino))
                continue
            lineas = []
            for ln in b["lines"]:
                l = "".join(s["text"] for s in ln["spans"]).strip()
                if not l or l in repetidas or re.match(r"^P[áa]gina\s+\d+$", l, re.I):
                    continue
                lineas.append(l)
            if not lineas:
                continue
            if es_titulo(lineas[0]):
                seccion = lineas[0]
            segs.append((num, seccion, " ".join(lineas), None))
    return segs, len(doc)


# ---------------------------------------------------------------- Word
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def segmentos_docx(path, carpeta_img):
    with zipfile.ZipFile(path) as z:
        rels = ET.fromstring(z.read("word/_rels/document.xml.rels"))
        destino_rel = {r.get("Id"): "word/" + r.get("Target").lstrip("/").replace("word/", "") for r in rels.findall("rel:Relationship", NS)}
        cuerpo = ET.fromstring(z.read("word/document.xml")).find("w:body", NS)
        usos = collections.Counter(n for n in z.namelist() if n.startswith("word/media/"))
        conteo_ref = collections.Counter()
        for blip in cuerpo.iter(f"{{{NS['a']}}}blip"):
            conteo_ref[destino_rel.get(blip.get(f"{{{NS['r']}}}embed"))] += 1

        segs, seccion, n_img = [], "", 0
        for p in cuerpo.iter(f"{{{NS['w']}}}p"):
            estilo = p.find("w:pPr/w:pStyle", NS)
            estilo = estilo.get(f"{{{NS['w']}}}val", "") if estilo is not None else ""
            texto = "".join(t.text or "" for t in p.iter(f"{{{NS['w']}}}t")).strip()
            if texto:
                if re.search(r"heading|t[ií]tulo|ttulo", estilo, re.I) or es_titulo(texto):
                    seccion = texto
                segs.append((None, seccion, texto, None))
            for blip in p.iter(f"{{{NS['a']}}}blip"):
                media = destino_rel.get(blip.get(f"{{{NS['r']}}}embed"))
                if not media or media not in usos or conteo_ref[media] > 2:
                    continue
                data = z.read(media)
                try:
                    pix = pymupdf.Pixmap(data)
                except Exception:
                    continue  # formatos que no son imagen (emf, wmf)
                if pix.width * pix.height < MIN_IMG_PX:
                    continue
                n_img += 1
                destino = carpeta_img / f"img_{n_img:03d}.png"
                guardar_png(data, destino)
                t = leer_captura(data)
                segs.append((None, seccion, f"[Captura de pantalla: {t}]" if t else "[Captura de pantalla]", destino))
    return segs, None


# ---------------------------------------------------------------- trozos
def armar_trozos(segs, titulo, archivo):
    """Agrupa los segmentos en trozos de hasta MAX_CHARS, sin mezclar paginas (PDF) ni secciones (Word)."""
    trozos, actual = [], None

    def cerrar():
        # las paginas del indice general (titulos con "......") no explican nada: no se guardan
        if actual and actual["partes"] and len(re.findall(r"\.{5,}", " ".join(actual["partes"]))) < 3:
            ubic = f"Página: {actual['pagina']}" if actual["pagina"] else f"Sección: {actual['seccion']}"
            encabezado = f"Manual: {titulo} | {ubic}" + (f" | Sección: {actual['seccion']}" if actual["pagina"] and actual["seccion"] else "")
            trozos.append({
                "text": encabezado + "\n" + "\n".join(actual["partes"]),
                "metadata": {
                    "manual": titulo,
                    "archivo": archivo,
                    "pagina": actual["pagina"],
                    "seccion": actual["seccion"],
                    "imagenes": [str(p.relative_to(IMAGENES)).replace("\\", "/") for p in actual["imagenes"]],
                },
            })

    for pagina, seccion, texto, imagen in segs:
        clave = pagina if pagina else seccion
        largo = sum(len(x) for x in actual["partes"]) if actual else 0
        if actual is None or clave != actual["clave"] or largo + len(texto) > MAX_CHARS:
            cerrar()
            actual = {"clave": clave, "pagina": pagina, "seccion": seccion, "partes": [], "imagenes": []}
        actual["partes"].append(texto)
        if imagen:
            actual["imagenes"].append(imagen)
    cerrar()
    return trozos


# ---------------------------------------------------------------- base de datos
def conectar():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"), port=int(os.getenv("POSTGRES_PORT", "5432")), dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"), password=os.getenv("POSTGRES_PASSWORD"), autocommit=True,
    )


def preparar_tablas(con):
    con.execute("CREATE EXTENSION IF NOT EXISTS vector")
    con.execute("CREATE TABLE IF NOT EXISTS imagenes (id text PRIMARY KEY, data bytea NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS paginas (id text PRIMARY KEY, data bytea NOT NULL)")
    for tabla, dim in MODELOS.values():
        con.execute(f"""CREATE TABLE IF NOT EXISTS {tabla} (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            text text, metadata jsonb, embedding vector({dim}))""")


def id_corto(texto):
    return hashlib.md5(texto.encode("utf-8")).hexdigest()[:12]


def guardar_imagenes(con, trozos, pdf_path):
    """Guarda las capturas y la imagen de cada pagina en la base de datos y agrega
    a cada trozo las direcciones (URL) con las que el chat puede mostrarlas."""
    doc = pymupdf.open(pdf_path)
    paginas_hechas = set()
    for t in trozos:
        md = t["metadata"]
        urls = []
        for rel in md.get("imagenes", []):
            iid = id_corto(rel)
            con.execute(
                "INSERT INTO imagenes (id, data) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (iid, (IMAGENES / rel).read_bytes()),
            )
            urls.append(f"{URL_PUBLICA}/navasoft-img?id={iid}")
        md["imagenes_url"] = urls
        if md.get("pagina"):
            pid = id_corto(f"{md['archivo']}#{md['pagina']}")
            if pid not in paginas_hechas:
                png = doc[md["pagina"] - 1].get_pixmap(dpi=110).tobytes("png")
                con.execute(
                    "INSERT INTO paginas (id, data) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                    (pid, png),
                )
                paginas_hechas.add(pid)
            md["pagina_url"] = f"{URL_PUBLICA}/navasoft-pagina?id={pid}"


def completar_imagenes(con):
    """Para manuales ya cargados antes de esta funcion: agrega imagenes sin volver a leerlos (sin OCR)."""
    for tabla, _ in MODELOS.values():
        filas = con.execute(f"SELECT id, metadata FROM {tabla} WHERE NOT metadata ? 'pagina_url'").fetchall()
        por_archivo = collections.defaultdict(list)
        for fid, md in filas:
            por_archivo[md["archivo"]].append((fid, md))
        for archivo, items in por_archivo.items():
            pdf = LIMPIOS / archivo
            trozos = [{"metadata": md} for _, md in items]
            guardar_imagenes(con, trozos, pdf)
            for (fid, _), t in zip(items, trozos):
                con.execute(f"UPDATE {tabla} SET metadata = %s WHERE id = %s", (json.dumps(t["metadata"], ensure_ascii=False), fid))
            print(f"  ✓ imágenes agregadas: {archivo} ({len(items)} trozos)")


def vectorizar(modelo, textos):
    r = requests.post(f"{OLLAMA}/api/embed", json={"model": modelo, "input": textos}, timeout=600)
    r.raise_for_status()
    return r.json()["embeddings"]


def agregar_descripciones(con, trozos):
    """Si las capturas ya fueron descritas con IA de vision (describir_capturas.py), al volver a cargar
    el manual se agregan otra vez esas descripciones, para no tener que describirlas de nuevo."""
    if not con.execute("SELECT to_regclass('capturas_descripcion')").fetchone()[0]:
        return
    import limpiar_manuales
    descs = dict(con.execute("SELECT imagen_id, descripcion FROM capturas_descripcion WHERE descripcion IS NOT NULL").fetchall())
    # las descripciones se hicieron sobre las capturas sin tapar: las que nombran datos reales no se usan
    descs = {k: v for k, v in descs.items() if not limpiar_manuales.tiene_datos_reales(v)}
    for t in trozos:
        ids = [id_corto(r) for r in t["metadata"].get("imagenes", [])]
        t["text"] += "".join(f"\n[Descripción de la captura: {descs[i]}]" for i in ids if i in descs)


def guardar(con, trozos, archivo):
    agregar_descripciones(con, trozos)
    for modelo, (tabla, _) in MODELOS.items():
        con.execute(f"DELETE FROM {tabla} WHERE metadata->>'archivo' = %s", (archivo,))
        for i in range(0, len(trozos), 16):
            lote = trozos[i:i + 16]
            vecs = vectorizar(modelo, [t["text"] for t in lote])
            with con.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {tabla} (text, metadata, embedding) VALUES (%s, %s, %s::vector)",
                    [(t["text"], json.dumps(t["metadata"], ensure_ascii=False), str(v)) for t, v in zip(lote, vecs)],
                )


# ---------------------------------------------------------------- principal
def elegir_archivos(solo):
    vistos, elegidos = set(), []
    todos = sorted(p for p in MANUALES.rglob("*") if p.suffix.lower() in (".pdf", ".docx"))
    todos += sorted(CONVERTIDOS.glob("*.pdf")) if CONVERTIDOS.exists() else []
    pdf_stems = {re.sub(r"[^a-z0-9]", "", p.stem.lower()) for p in todos if p.suffix.lower() == ".pdf"}
    for p in todos:
        if any(x in p.name.upper() for x in EXCLUIR):
            continue
        if solo and solo.lower() not in p.name.lower():
            continue
        h = hashlib.md5(p.read_bytes()).hexdigest()
        if h in vistos:
            continue  # copia exacta de otro archivo
        if p.suffix.lower() == ".docx" and re.sub(r"[^a-z0-9]", "", p.stem.lower()) in pdf_stems:
            continue  # ya existe la version PDF, que trae numeros de pagina
        vistos.add(h)
        elegidos.append(p)
    return [copia_limpia(p) for p in elegidos]


def copia_limpia(p):
    """Los manuales traen datos reales de clientes en sus capturas: al asistente solo se carga la copia con esos
    datos tapados que deja limpiar_manuales.py. Si falta o es mas vieja que el original, no se carga nada."""
    copia = LIMPIOS / (p.relative_to(MANUALES) if p.is_relative_to(MANUALES) else pathlib.Path("convertidos") / p.name)
    if p.suffix.lower() != ".pdf":
        sys.exit(f"'{p.name}' no tiene version PDF: no se puede limpiar. Convertirlo a PDF antes de cargarlo.")
    if not copia.exists() or copia.stat().st_mtime < p.stat().st_mtime:
        sys.exit(f"Falta la copia limpia de '{p.name}' o el original cambio despues. "
                 "Correr auditar_datos_sensibles.py y limpiar_manuales.py antes de cargar.")
    return copia


def nombre_archivo(path):
    """Nombre con el que se guarda el manual en la base de datos (el mismo para el original y su copia limpia)."""
    for raiz in (LIMPIOS, MANUALES):
        if path.is_relative_to(raiz):
            return str(path.relative_to(raiz))
    return f"convertidos\\{path.name}"


def procesar(con, path):
    t0 = time.time()
    archivo = nombre_archivo(path)
    carpeta_img = IMAGENES / slug(path.stem)
    leer = segmentos_pdf if path.suffix.lower() == ".pdf" else segmentos_docx
    segs, paginas = leer(path, carpeta_img)
    trozos = armar_trozos(segs, titulo_manual(path), archivo)
    if path.suffix.lower() == ".pdf":
        guardar_imagenes(con, trozos, path)
    guardar(con, trozos, archivo)
    n_img = sum(1 for s in segs if s[3])
    print(f"  ✓ {archivo}: {paginas or '-'} págs, {n_img} capturas, {len(trozos)} trozos ({time.time() - t0:.0f}s)")


def sincronizar(con):
    """Deja la base de datos igual a la carpeta de manuales: carga los manuales nuevos o modificados
    y quita los que se borraron. Lo usa vigilar_manuales.ps1 cada vez que la carpeta cambia."""
    con.execute("CREATE TABLE IF NOT EXISTS manuales_cargados (archivo text PRIMARY KEY, hash text, fecha timestamptz DEFAULT now())")
    actuales = {nombre_archivo(p): (p, hashlib.md5(p.read_bytes()).hexdigest()) for p in elegir_archivos(None)}
    if not actuales:
        # carpeta vacia o disco desconectado: no se interpreta como que todos los manuales se borraron
        sys.exit(f"No se encontraron manuales en {MANUALES}: no se cambia nada.")
    tabla = next(iter(MODELOS.values()))[0]
    if not con.execute("SELECT 1 FROM manuales_cargados LIMIT 1").fetchone():
        # primera vez: los manuales que ya estan en la base se registran tal como estan, sin volver a leerlos
        en_base = {r[0] for r in con.execute(f"SELECT DISTINCT metadata->>'archivo' FROM {tabla}")}
        with con.cursor() as cur:
            cur.executemany("INSERT INTO manuales_cargados (archivo, hash) VALUES (%s, %s)",
                            [(a, h) for a, (_, h) in actuales.items() if a in en_base])
    registrados = dict(con.execute("SELECT archivo, hash FROM manuales_cargados").fetchall())
    nuevos = [a for a, (_, h) in actuales.items() if registrados.get(a) != h]
    # los manuales subidos desde el portal (portal/...) no estan en la carpeta de la laptop: no se tocan aqui
    borrados = [a for a in registrados if a not in actuales and not a.startswith("portal/")]
    for a in nuevos:
        print(("  + nuevo: " if a not in registrados else "  ~ modificado: ") + a)
        procesar(con, actuales[a][0])
        con.execute("INSERT INTO manuales_cargados (archivo, hash) VALUES (%s, %s) "
                    "ON CONFLICT (archivo) DO UPDATE SET hash = EXCLUDED.hash, fecha = now()", (a, actuales[a][1]))
    for a in borrados:
        print(f"  - quitado: {a}")
        for t, _ in MODELOS.values():
            con.execute(f"DELETE FROM {t} WHERE metadata->>'archivo' = %s", (a,))
        con.execute("DELETE FROM manuales_cargados WHERE archivo = %s", (a,))
    if nuevos or borrados:
        import crear_indice  # aqui y no arriba: crear_indice importa este archivo
        import corregir_secciones
        import fragmentos_capturas
        crear_indice.main()
        for a in nuevos:  # secciones segun el indice real del manual y fragmentos propios de sus capturas
            corregir_secciones.main(solo=pathlib.Path(a).name)
        fragmentos_capturas.main()
        import alias_secciones  # cargar un manual borra sus alias: se vuelven a poner
        alias_secciones.main()
        con.execute("TRUNCATE respuestas_cache")  # las respuestas guardadas podian venir del manual anterior
        print(f"Sincronizado: {len(nuevos)} cargados, {len(borrados)} quitados.")
    else:
        print("Sin cambios: la base de datos ya coincide con la carpeta de manuales.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", help="procesar solo los archivos cuyo nombre contenga este texto")
    ap.add_argument("--solo-imagenes", action="store_true", help="solo agregar imagenes a manuales ya cargados")
    ap.add_argument("--omitir-cargados", action="store_true", help="saltar manuales que ya estan en la base de datos")
    ap.add_argument("--sincronizar", action="store_true", help="cargar solo lo nuevo o modificado y quitar lo borrado")
    args = ap.parse_args()

    con = conectar()
    preparar_tablas(con)
    if args.solo_imagenes:
        completar_imagenes(con)
        print("Listo.")
        return
    if args.sincronizar:
        sincronizar(con)
        return

    archivos = elegir_archivos(args.solo)
    if args.omitir_cargados:
        tabla = next(iter(MODELOS.values()))[0]
        cargados = {r[0] for r in con.execute(f"SELECT DISTINCT metadata->>'archivo' FROM {tabla}")}
        archivos = [p for p in archivos if nombre_archivo(p) not in cargados]
    print(f"Manuales a procesar: {len(archivos)}")
    for path in archivos:
        procesar(con, path)
    if archivos:
        import crear_indice
        import corregir_secciones
        import fragmentos_capturas
        crear_indice.main()
        for path in archivos:
            corregir_secciones.main(solo=path.name)
        fragmentos_capturas.main()
    print("Listo.")


if __name__ == "__main__":
    main()
