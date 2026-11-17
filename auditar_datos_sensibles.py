"""Busca datos reales o sensibles en los manuales, antes de cargarlos o de enviarlos a una IA: RUC, razones
sociales, correos, telefonos, DNI, contrasenas, servidores. Lee cada pagina entera con OCR, asi que tambien ve
lo que esta dentro de las capturas de pantalla. No cambia ningun manual: solo deja un informe para revisar.
    .venv\\Scripts\\python.exe auditar_datos_sensibles.py            (todos)
    .venv\\Scripts\\python.exe auditar_datos_sensibles.py --solo caja
La lectura de cada manual (lenta) se guarda en auditoria\\ocr\\ con la posicion de cada linea: si se corta, sigue
donde quedo, y limpiar_manuales.py usa esas posiciones para tapar los datos. El informe queda en
auditoria\\hallazgos.csv. Toda la carpeta auditoria\\ esta fuera de git, porque copia los datos encontrados."""
import argparse
import csv
import hashlib
import json
import os
import pathlib
import re
import sys
from collections import Counter, defaultdict

import pymupdf

sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).parent
MANUALES = pathlib.Path(os.getenv("MANUALES_DIR", r"C:\PRÁCTICAS EKAM\Manuales NAVASOFT"))
DATOS = pathlib.Path(os.getenv("NAVASOFT_DATOS", str(BASE)))   # en el servidor, la carpeta de datos del procesador
CONVERTIDOS = DATOS / "manuales_convertidos"
SALIDA = DATOS / "auditoria"
CACHE = SALIDA / "ocr"
DPI = 130
MAX_LADO = 2000  # el OCR reduce las imagenes mas grandes que esto, asi que no sirve pasarle mas
VERSION = 3     # cambia cuando cambia la forma de leer: descarta las lecturas guardadas
EXCLUIR = ["CLUB DE CONVERSACI", "BACKUP", "MANUAL_CONTROL_FACTURACION_ELECTRONICA"]  # igual que leer_manuales.py

SOCIEDAD = r"(?:S\.?\s?A\.?\s?C|S\.?\s?A\.?\s?A|S\.?\s?A|E\.?\s?I\.?\s?R\.?\s?L|S\.?\s?R\.?\s?L|S\.?\s?C\.?\s?R\.?\s?L)\.?"
PATRONES = {
    "RUC": re.compile(r"(?<![\d/])(?:10|15|17|20)\d{9}(?!\d)"),  # no fechas pegadas (05/02/2026...)
    "Razon social": re.compile(rf"[A-ZÁÉÍÓÚÑ0-9&][A-ZÁÉÍÓÚÑ0-9&.,' -]{{3,60}}\s{SOCIEDAD}(?![A-Za-z])"
                               # con puntos, aunque el OCR lo pegue al nombre: "FERRETERIAS.A.C."
                               r"|[A-ZÁÉÍÓÚÑ0-9&][A-ZÁÉÍÓÚÑ0-9&.,' -]{3,60}(?:S\.A\.C|S\.A\.A|E\.I\.R\.L|S\.R\.L)\.?"
                               # "Mi Empresa de Ejemplo Sac" (el OCR suele quitar los espacios)
                               r"|[A-ZÁÉÍÓÚÑ][\wáéíóúñ ]{3,50}[a-záéíóúñ ](?:Sac|Saa|Eirl|Srl)\b"
                               r"|(?i:.{0,60}(?:SOCIEDAD\s*AN[OÓ]NIMA|EMPRESA\s*INDIVIDUAL\s*DE\s*RESP|"
                               r"SOCIEDAD\s*COMERCIAL\s*DE\s*RESP)\w*(?:\s*CERRADA|\s*ABIERTA)?)"),
    "Usuario": re.compile(r"(?i)\busuario\b\s*[:=]\s*\S+"),
    # direcciones: AV./CAL./JR./MZA./URB. con punto y seguidas de un nombre (no las etiquetas "Nro.")
    "Direccion": re.compile(r"(?i)\b(?:AV|CAL|JR|MZA?|URB|PJ|OTR)\.\s*[A-Z0-9ÁÉÍÓÚÑ]{2,}.*"),
    "Telefono": re.compile(r"(?i)tel[eé]f\w*\W{0,4}\(?0?\d{2}\)?[ -]?\d{6,7}|(?<![\d/-])0[1-9]\d{7}(?![\d/-])"),  # no los codigos de operacion (124014-000101001)
    "Proveedor": re.compile(r"(?i)\bproveedor\s*:\s*[A-Za-z0-9&.'][\w&.' -]{3,}"),
    "Cliente": re.compile(r"(?i)\bcliente\s*:\s*(?!venta contado)[A-Za-z0-9&.'][\w&.' -]{3,}"),
    "Correo": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "Celular": re.compile(r"(?<!\d)9\d{2}[ -]?\d{3}[ -]?\d{3}(?!\d)"),
    "DNI": re.compile(r"(?i)\bD\.?N\.?I\.?\b\W{0,6}\d{8}(?!\d)"),
    "Contrasena": re.compile(r"(?i)\b(?:contrase[ñn]a|password|clave|pwd)\b\s*[:=]\s*\S+"),
    "Servidor o IP": re.compile(r"\\\\[\w.-]{3,}|(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
    "Persona": re.compile(r"\b(?:Sr|Sra|Srta|Señor|Señora|SR|SRA)\b\.?\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)?"),
}
# datos de ejemplo o del propio producto que no hay que tapar
# los datos ficticios que limpiar_manuales.py escribe en lugar de los reales: DEMO, solo ceros, ********, 900 000 000
PERMITIDOS = re.compile(r"(?i)navasoft|ekam|sunat|20000000001|99999999999|ejemplo@|@ejemplo|127\.0\.0\.1|localhost|dem[o0]|^(?:\D*0)+\D*$|\*{4,}|[:=]\s*[*•·oO0]{3,}$|^900 ?000 ?000$"
                        r"|^\d(?:\.\d){3}$|^1\.400\.007\.90$")  # numeros de seccion (5.2.1.1) y un importe

_ocr = None


def manuales():
    return sorted(MANUALES.rglob("*.pdf")) + sorted(CONVERTIDOS.glob("*.pdf"))


def se_carga(pdf):
    return not any(x in pdf.name.upper() for x in EXCLUIR)


def leer_pagina(pagina):
    """Lineas de la pagina con su posicion en puntos del PDF: las del texto escrito y las que lee el OCR
    (que incluye lo que hay dentro de las capturas). Posicion = caja en la pagina tal como se ve."""
    global _ocr
    if _ocr is None:
        import numpy  # aqui: quien solo usa la lectura ya guardada no necesita cargar el OCR
        from rapidocr_onnxruntime import RapidOCR
        _ocr = (RapidOCR(), numpy)
    motor, np = _ocr
    lineas = []
    for bloque in pagina.get_text("dict")["blocks"]:
        for linea in bloque.get("lines", []):
            texto = "".join(s["text"] for s in linea["spans"]).strip()
            if texto:
                caja = pymupdf.Rect(linea["bbox"]) * pagina.rotation_matrix
                lineas.append({"t": texto, "b": [round(v, 1) for v in caja], "o": "texto"})
    # Cada captura se lee aparte y a su tamano real: leyendo la pagina entera, la letra pequena de las capturas
    # se pierde. Las paginas escaneadas son una sola imagen grande, asi que tambien quedan cubiertas.
    vista = pagina.rect
    zonas = [pymupdf.Rect(i["bbox"]) & vista for i in pagina.get_image_info()]
    zonas = [z for z in zonas if z.width >= 30 and z.height >= 12]
    if not zonas and not lineas:
        zonas = [vista]  # pagina sin texto ni imagenes (dibujo vectorial): se lee entera
    hechas = []
    for z in sorted(zonas, key=lambda r: -r.get_area()):
        if any(h.contains(z) for h in hechas):
            continue  # imagen dentro de otra ya leida
        hechas.append(z)
        info = next((i for i in pagina.get_image_info() if (pymupdf.Rect(i["bbox"]) & vista) == z), None)
        zoom = max(DPI / 72, (info["width"] / z.width) if info and z.width else 0)
        zoom = min(zoom, MAX_LADO / max(z.width, z.height), 6)
        pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=z, colorspace=pymupdf.csRGB, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        resultado, _ = motor(img)
        for puntos, texto, _ in resultado or []:
            xs, ys = [p[0] / zoom + z.x0 for p in puntos], [p[1] / zoom + z.y0 for p in puntos]
            lineas.append({"t": texto, "b": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
                           "o": "ocr"})
    # Segunda lectura, igual que la carga (leer_manuales.leer_captura): cada imagen a su tamano original. A otra
    # escala el OCR lee cosas distintas, y lo que la carga lee es lo que termina en la base y le llega al cliente.
    doc = pagina.parent
    for info in pagina.get_image_info(xrefs=True):
        caja = pymupdf.Rect(info["bbox"]) & vista
        if not info.get("xref") or caja.is_empty or caja.width < 30 or caja.height < 12:
            continue
        try:
            datos = doc.extract_image(info["xref"])["image"]
        except Exception:
            continue
        resultado, _ = motor(datos)
        ancho, alto = info.get("width") or 1, info.get("height") or 1
        bx = pymupdf.Rect(info["bbox"])
        for puntos, texto, _ in resultado or []:
            xs = [bx.x0 + p[0] * bx.width / ancho for p in puntos]
            ys = [bx.y0 + p[1] * bx.height / alto for p in puntos]
            lineas.append({"t": texto, "b": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
                           "o": "ocr2"})
    return lineas


def lectura(pdf, forzar=False):
    """Paginas del manual ya leidas: lista de listas de lineas. Se guarda por archivo y fecha de modificacion."""
    CACHE.mkdir(parents=True, exist_ok=True)
    marca = f"{pdf}|{pdf.stat().st_mtime_ns}|{pdf.stat().st_size}|{DPI}|{VERSION}"
    archivo = CACHE / (hashlib.md5(marca.encode()).hexdigest() + ".json")
    if archivo.exists() and not forzar:
        return json.loads(archivo.read_text(encoding="utf-8"))["paginas"]
    with pymupdf.open(pdf) as doc:
        paginas = [leer_pagina(p) for p in doc]
    archivo.write_text(json.dumps({"manual": str(pdf), "paginas": paginas}, ensure_ascii=False), encoding="utf-8")
    return paginas


def hallazgos_de(paginas):
    """(pagina, tipo, dato, linea, caja) de cada dato que coincide con un patron."""
    salida = []
    for n, lineas in enumerate(paginas, 1):
        for l in lineas:
            for tipo, patron in PATRONES.items():
                if tipo in ("Cliente", "Proveedor") and l["o"] == "texto":
                    continue  # en el texto del manual "del cliente: ..." es una explicacion, no un nombre
                for m in patron.finditer(l["t"]):
                    dato = " ".join(m.group().split())
                    # un correo de una persona se tapa aunque sea de NAVASOFT (solo se dejan los de ejemplo)
                    permitido = re.search(r"(?i)ejemplo", dato) if tipo == "Correo" else PERMITIDOS.search(dato)
                    if not permitido:
                        salida.append((n, tipo, dato, " ".join(l["t"].split())[:160], l["b"]))
    return salida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", help="revisar solo los manuales cuyo nombre contenga este texto")
    ap.add_argument("--de-nuevo", action="store_true", help="volver a leer los manuales aunque ya esten leidos")
    args = ap.parse_args()
    pdfs = [p for p in manuales() if not args.solo or args.solo.lower() in p.name.lower()]
    SALIDA.mkdir(exist_ok=True)
    filas, resumen = [], defaultdict(Counter)
    for i, pdf in enumerate(pdfs, 1):
        vistos = set()
        for pag, tipo, dato, linea, _ in hallazgos_de(lectura(pdf, args.de_nuevo)):
            if (pag, tipo, dato) not in vistos:
                vistos.add((pag, tipo, dato))
                filas.append([pdf.name, "si" if se_carga(pdf) else "no", pag, tipo, dato, linea])
                resumen[pdf.name][tipo] += 1
        print(f"[{i}/{len(pdfs)}] {pdf.name}: {len(vistos)} hallazgos" + ("" if se_carga(pdf) else " (no se carga)"), flush=True)
    nombre = "hallazgos.csv" if not args.solo else f"hallazgos_{re.sub(r'[^a-z0-9]+', '_', args.solo.lower())}.csv"
    with open(SALIDA / nombre, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Manual", "Se carga al asistente", "Pagina", "Tipo", "Dato", "Linea donde aparece"])
        w.writerows(filas)
    print("\nRESUMEN (hallazgos por manual)")
    for manual, c in sorted(resumen.items(), key=lambda x: -sum(x[1].values())):
        print(f"{sum(c.values()):5d}  {manual}  |  " + ", ".join(f"{t}: {k}" for t, k in c.most_common()))
    print(f"\nInforme: {SALIDA / nombre}")


if __name__ == "__main__":
    main()
