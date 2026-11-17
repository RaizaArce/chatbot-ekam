"""Saca el logo de EKAM PERU (la imagen que se repite en el encabezado de los manuales),
lo guarda en la base de datos con id 'logo-ekam' y muestra sus colores principales."""
import collections
import pathlib
import sys

import pymupdf

from leer_manuales import MANUALES, conectar, preparar_tablas

sys.stdout.reconfigure(encoding="utf-8")
pdf = next(MANUALES.rglob("Manual de caja chica V5.pdf"))
doc = pymupdf.open(pdf)
usos = collections.Counter(img[0] for page in doc for img in page.get_images(full=True))
xref = max((x for x, c in usos.items() if c >= len(doc) * 0.6), key=lambda x: doc.extract_image(x)["width"])
pix = pymupdf.Pixmap(doc, xref)
if pix.alpha or pix.n > 3:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
destino = pathlib.Path(__file__).parent / "imagenes" / "logo-ekam.png"
pix.save(destino)
print(f"Logo: {pix.width}x{pix.height} -> {destino}")

# colores principales (ignorando blanco y casi blanco)
colores = collections.Counter()
for y in range(0, pix.height, 2):
    for x in range(0, pix.width, 2):
        r, g, b = pix.pixel(x, y)[:3]
        if min(r, g, b) > 225:
            continue
        colores[(r // 16 * 16, g // 16 * 16, b // 16 * 16)] += 1
for (r, g, b), n in colores.most_common(6):
    print(f"  #{r:02x}{g:02x}{b:02x}  ({n} px)")

con = conectar()
preparar_tablas(con)
con.execute("INSERT INTO imagenes (id, data) VALUES ('logo-ekam', %s) ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data", (destino.read_bytes(),))
print("Guardado en la base de datos como 'logo-ekam'")
