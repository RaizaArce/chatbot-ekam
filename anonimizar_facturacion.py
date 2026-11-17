"""Copia del manual de control de facturacion electronica con los datos de empresas de sus capturas reemplazados
por datos FICTICIOS (nombre de la empresa del usuario, clientes y montos), escritos con el fondo, el color y el
tamano de letra de la captura, para que el asistente lo pueda mostrar a cualquier cliente.
El original queda sin cambios y se excluye de la carga (leer_manuales.EXCLUIR).
    .venv\\Scripts\\python.exe anonimizar_facturacion.py"""
import io
import itertools
import pathlib
import re

import pymupdf
from PIL import Image, ImageDraw

import auditar_datos_sensibles as auditoria
from limpiar_manuales import colores, escribir

ORIGINAL = pathlib.Path(r"C:\PRÁCTICAS EKAM\Manuales NAVASOFT\facturacion eletronica"
                        r"\Manual_Control_Facturacion_Electronica_NavaSoft version 2.pdf")
COPIA = pathlib.Path(__file__).parent / "manuales_convertidos" / "Control de facturacion electronica eNavaSoft.pdf"
# zonas a reemplazar por imagen del PDF (xref), en pixeles de la imagen, y que tipo de dato hay en cada una
ZONAS = {
    5: [((300, 6, 575, 30), "titulo"), ((80, 172, 262, 194), "panel"),    # Imagen 1: empresa en la barra y en el panel
        ((86, 197, 205, 252), "logo")],                                   # y su logo (las etiquetas de la derecha quedan)
    7: [((82, 56, 247, 121), "logo")],                                     # Imagen 2: nombre y logo de la empresa
    9: [((162, 160, 376, 502), "cliente"), ((376, 160, 448, 502), "total")],   # Imagen 3: columnas Cliente y Total
    11: [((163, 160, 338, 506), "cliente"), ((338, 160, 406, 506), "total")],  # Imagen 4: columnas Cliente y Total
}
CLIENTES = ["CLIENTE DEMO S.A.C.", "COMERCIAL DEMO E.I.R.L.", "DISTRIBUIDORA DEMO S.A.", "SERVICIOS DEMO S.A.C.",
            "INVERSIONES DEMO S.R.L."]
MONTOS = ["1,180.00", "2,360.00", "590.00", "4,720.00", "354.00", "11,800.00", "236.00"]
MONTO = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}")


def texto_ficticio(tipo, linea, n, clientes, montos):
    """Que se escribe en la parte de 'linea' que cae dentro de una zona ('' = solo se borra)."""
    if tipo == "titulo":
        return "EMPRESA DEMO S.A.C. (20000000001)"
    if tipo == "panel":
        return "EMPRESA DEMO S.A.C."
    if tipo == "cliente":
        return next(clientes)
    if tipo == "total":
        m = MONTO.search(linea)
        moneda = re.search(r"S/\.?|US\$", linea)
        monto = "0.00" if m and m.group() == "0.00" else next(montos)
        return (moneda.group() + " " if moneda else "") + monto
    return ""   # logo


def main():
    doc = pymupdf.open(ORIGINAL)
    paginas = auditoria.lectura(ORIGINAL)
    hechas = set()
    clientes, montos = itertools.cycle(CLIENTES), itertools.cycle(MONTOS)
    for num, pagina in enumerate(doc, 1):
        for info in pagina.get_image_info(xrefs=True):
            xref = info["xref"]
            if xref not in ZONAS or xref in hechas:
                continue
            bbox = pymupdf.Rect(info["bbox"])
            img = Image.open(io.BytesIO(doc.extract_image(xref)["image"])).convert("RGB")
            fx, fy = img.width / bbox.width, img.height / bbox.height
            # lineas del OCR (una sola lectura, para no escribir dos veces) dentro de la imagen, en pixeles
            lineas = []
            for l in paginas[num - 1]:
                r = pymupdf.Rect(l["b"])
                if l["o"] == "ocr" and bbox.intersects(r):
                    lineas.append(((int((r.x0 - bbox.x0) * fx), int((r.y0 - bbox.y0) * fy),
                                    int((r.x1 - bbox.x0) * fx) + 1, int((r.y1 - bbox.y0) * fy) + 1), l["t"]))
            # filas de la captura: las alturas de todas las lineas del OCR (de cualquier columna), agrupadas. Asi se
            # escribe en cada fila aunque el OCR no haya leido justo la parte de la zona
            alto = sorted(c[3] - c[1] for c, _ in lineas)[len(lineas) // 2] if lineas else 12
            filas = []
            for c, _ in sorted(lineas, key=lambda ct: (ct[0][1] + ct[0][3]) / 2):
                centro = (c[1] + c[3]) / 2
                if filas and abs(centro - filas[-1][-1]) < alto * 0.6:
                    filas[-1].append(centro)
                else:
                    filas.append([centro])
            centros = [sum(f) / len(f) for f in filas]
            dibujo = ImageDraw.Draw(img)
            for zona, tipo in ZONAS[xref]:
                zx0, zy0, zx1, zy1 = zona
                if tipo in ("logo", "panel", "titulo"):
                    # no es una tabla: se borra la zona entera con el color de alrededor y se escribe por linea
                    fondo = colores(img, zona)
                    dentro = sorted(((c, t) for c, t in lineas if min(c[2], zx1) - max(c[0], zx0) > 4
                                     and min(c[3], zy1) - max(c[1], zy0) > 2), key=lambda ct: (ct[0][1], ct[0][0]))
                    tonos = [colores(img, (max(c[0], zx0), max(c[1], zy0), min(c[2], zx1), min(c[3], zy1))) for c, _ in dentro]
                    dibujo.rectangle(zona, fill=fondo[0])
                    for n, ((c, t), (_, letra)) in enumerate(zip(dentro, tonos)):
                        texto = texto_ficticio(tipo, t, n, clientes, montos)
                        if texto:
                            escribir(dibujo, (max(c[0], zx0) + 2, c[1], zx1 - 2, c[3]), texto, letra)
                    continue
                # columna de una tabla: una linea ficticia por fila, todas del mismo tamano
                trabajos = []
                for centro in centros:
                    if not zy0 <= centro <= zy1:
                        continue
                    banda = (zx0, int(centro - alto / 2), zx1, int(centro + alto / 2) + 1)
                    leida = next((t for c, t in lineas if min(c[2], zx1) - max(c[0], zx0) > 4
                                  and c[1] <= centro <= c[3]), "")
                    texto = texto_ficticio(tipo, leida, 0, clientes, montos)
                    trabajos.append((banda, texto, colores(img, banda)))
                for (x0, y0, x1, y1), _, (fondo, _) in trabajos:
                    dibujo.rectangle((x0, y0 - 1, x1, y1 + 1), fill=fondo)
                for (x0, y0, x1, y1), texto, (_, letra) in trabajos:
                    if texto:   # la caja del OCR es mas alta que la letra de la tabla: se escribe al 75 %
                        escribir(dibujo, (x0 + 3, y0, x1 - 4, y1), texto, letra, tope=alto * 0.75, derecha=tipo == "total")
            salida = io.BytesIO()
            img.save(salida, "PNG")
            pagina.replace_image(xref, stream=salida.getvalue())
            hechas.add(xref)
    faltan = set(ZONAS) - hechas
    if faltan:
        raise SystemExit(f"No se encontraron las imagenes {faltan}: el PDF cambio, revisar ZONAS.")
    doc.save(COPIA, garbage=4, deflate=True)
    print(f"Copia guardada: {COPIA}")


if __name__ == "__main__":
    main()
