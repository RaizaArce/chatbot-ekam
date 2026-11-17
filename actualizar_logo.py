"""Toma el logo de imagenes/logo-ekam.png, guarda una version liviana para la web en la base de datos
(id 'logo-ekam', la que usan el portal y el chat) y muestra sus colores principales."""
import collections
import pathlib
import sys

import pymupdf

from leer_manuales import conectar, preparar_tablas

sys.stdout.reconfigure(encoding="utf-8")
origen = pathlib.Path(__file__).parent / "imagenes" / "logo-ekam.png"
pix = pymupdf.Pixmap(str(origen))
if pix.alpha or pix.n > 3:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
print(f"Logo original: {pix.width}x{pix.height}, {origen.stat().st_size // 1024} KB")

colores = collections.Counter()
for y in range(0, pix.height, 4):
    for x in range(0, pix.width, 4):
        r, g, b = pix.pixel(x, y)[:3]
        if min(r, g, b) > 215:
            continue
        colores[(r // 8 * 8, g // 8 * 8, b // 8 * 8)] += 1
for (r, g, b), n in colores.most_common(5):
    print(f"  #{r:02x}{g:02x}{b:02x}  ({n})")

# version web de 640 px de ancho
escala = 640 / pix.width
web = pymupdf.Pixmap(pix, int(pix.width * escala), int(pix.height * escala))
datos = web.tobytes("png")
con = conectar()
preparar_tablas(con)
con.execute("INSERT INTO imagenes (id, data) VALUES ('logo-ekam', %s) ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data", (datos,))
print(f"Versión web guardada: {web.width}x{web.height}, {len(datos) // 1024} KB (proporción {web.width / web.height:.2f})")
