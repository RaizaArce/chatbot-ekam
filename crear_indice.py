"""Crea el indice (tabla de contenido) de cada manual a partir de sus titulos numerados
("2. COTIZACIONES", "2.2 NUEVO INGRESO DE UNA COTIZACION"...) y lo guarda en la tabla manual_indice.
El asistente lo usa cuando el cliente pide "muestrame los temas del manual de Ventas".
Se ejecuta solo al final de leer_manuales.py; tambien se puede ejecutar a mano."""
import re
import sys

import pymupdf

from leer_manuales import IMAGENES, MANUALES, URL_PUBLICA, conectar, elegir_archivos, id_corto, nombre_archivo, titulo_manual  # noqa: F401

sys.stdout.reconfigure(encoding="utf-8")
TITULO = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,/()\-–.]{3,80})\s*$")
MAYUSCULAS = re.compile(r"^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,/()\-–]{5,70}$")


SIGLAS = {"SIRE", "SUNAT", "ERCTA", "ERC", "IGV", "RUC", "TXT", "GRE", "RIC", "PLE", "NC", "ND", "OC", "OP", "CxP", "CXP"}


def bonito(t):
    """'NUEVO INGRESO DE UNA COTIZACION' -> 'Nuevo ingreso de una cotizacion' (conserva solo siglas conocidas)."""
    t = re.sub(r"\s+", " ", t).strip(" .-–")
    palabras = t.split(" ")
    salida = [p if p.strip("(),.") in SIGLAS else p.lower() for p in palabras]
    texto = " ".join(salida)
    return texto[:1].upper() + texto[1:]


def titulos_de(ruta):
    doc = pymupdf.open(ruta)
    vistos, titulos = set(), []
    for page in doc:
        if page.number < 2 and len(doc) > 6:  # portada e indice general de los manuales largos
            continue
        for linea in page.get_text().splitlines():
            m = TITULO.match(linea)
            # "...... 84" = renglon del indice general del PDF, no un titulo real
            if m and m.group(1) not in vistos and not m.group(2).strip().endswith(".") and "..." not in m.group(2):
                vistos.add(m.group(1))
                titulos.append((m.group(1), bonito(m.group(2)), page.number + 1))
    if len(titulos) >= 2:
        return titulos
    # guias cortas sin titulos numerados: titulos en mayusculas de cada pagina
    vistos, titulos = set(), []
    for page in doc:
        for linea in page.get_text().splitlines():
            s = linea.strip()
            if MAYUSCULAS.match(s) and s not in vistos and "[" not in s:
                vistos.add(s)
                titulos.append(("", bonito(s), page.number + 1))
    return titulos[:15]


def main():
    con = conectar()
    con.execute("""CREATE TABLE IF NOT EXISTS manual_indice (
        manual text, archivo text, orden int, numero text, titulo text, pagina int, pagina_url text)""")
    # los manuales subidos desde el portal (portal/...) los indexa el procesador del servidor: no se borran aqui
    con.execute("DELETE FROM manual_indice WHERE archivo NOT LIKE 'portal/%'")
    paginas_guardadas = {r[0] for r in con.execute("SELECT id FROM paginas")}
    for ruta in elegir_archivos(None):
        if ruta.suffix.lower() != ".pdf":
            continue
        archivo = nombre_archivo(ruta)
        titulo = titulo_manual(ruta)
        filas = []
        for orden, (num, t, pag) in enumerate(titulos_de(ruta)):
            pid = id_corto(f"{archivo}#{pag}")
            url = f"{URL_PUBLICA}/navasoft-pagina?id={pid}" if pid in paginas_guardadas else None
            filas.append((titulo, archivo, orden, num, t, pag, url))
        with con.cursor() as cur:
            cur.executemany("INSERT INTO manual_indice VALUES (%s, %s, %s, %s, %s, %s, %s)", filas)
        print(f"  {titulo:<50} {len(filas):>3} temas")


if __name__ == "__main__":
    main()
