"""Compara dos formas de obtener el indice de un manual: marcadores del PDF y titulos numerados del texto."""
import re
import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8")
TITULO = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,/()\-–.]{3,80})\s*$")
for ruta in [r"C:\chatbot-navasoft\manuales_convertidos\Manual de Ventas_V5.pdf",
             r"C:\PRÁCTICAS EKAM\Manuales NAVASOFT\manuales v5\Manual de caja chica V5.pdf"]:
    doc = pymupdf.open(ruta)
    print(f"\n=== {ruta.split(chr(92))[-1]}: marcadores del PDF = {len(doc.get_toc())}")
    vistos, titulos = set(), []
    for page in doc:
        if page.number < 2:  # portada e indice general
            continue
        for linea in page.get_text().splitlines():
            m = TITULO.match(linea)
            if m and m.group(1) not in vistos and not m.group(2).strip().endswith("."):
                vistos.add(m.group(1))
                titulos.append((m.group(1), m.group(2).strip(), page.number + 1))
    print(f"títulos numerados encontrados: {len(titulos)}")
    for n, t, p in titulos[:25]:
        print(f"  {n:<6} {t[:60]:<60} p.{p}")
