"""Corrige la "Sección" de cada fragmento usando el indice real de cada manual (tabla manual_indice).

Al leer los PDF, a veces el encabezado de una tabla ("Nº AREA/USUARIO MODO", "ATRIBUTO DESCRIPCION") o una frase
se tomaba como titulo, y muchas paginas quedaban con una seccion equivocada. Aqui, para cada fragmento:
  1. se ubica su texto dentro de la pagina del PDF,
  2. se busca el ultimo titulo del indice que aparece antes de ese texto (en esa pagina o en las anteriores),
  3. se guarda la ruta completa, por ejemplo "1. Cobranzas > 1.5 Grupos del panel > 1.5.3 Transferencia a bancos".
Tambien quita de la busqueda los fragmentos del INDICE GENERAL (lineas de titulos con puntos "......"), que
no explican nada y confundian a la IA. Al terminar vuelve a vectorizar los fragmentos cambiados.

Uso:  .venv\\Scripts\\python.exe corregir_secciones.py [--solo "caja y bancos"] [--prueba]
"""
import argparse
import json
import re
import sys

import pymupdf

from leer_manuales import LIMPIOS, MODELOS, conectar, vectorizar

sys.stdout.reconfigure(encoding="utf-8")
PUNTOS = re.compile(r"\.{5,}")


def normal(t):
    t = t.lower()
    for a, b in zip("áéíóúñ", "aeioun"):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def es_indice(texto):
    """Fragmento del indice general: varias lineas de titulo terminadas en puntos y numero de pagina."""
    return len(PUNTOS.findall(texto)) >= 3


def ruta_pdf(archivo):
    return LIMPIOS / archivo  # la copia con los datos de clientes tapados (misma ruta relativa que el original)


def rutas_de_titulos(entradas):
    """numero -> titulo, para armar "1. Cobranzas > 1.5 Grupos > 1.5.3 Transferencia"."""
    por_numero = {e["numero"]: e["titulo"] for e in entradas if e["numero"]}
    for e in entradas:
        if e["numero"]:
            partes = e["numero"].split(".")
            camino = [f"{'.'.join(partes[:i])}{'.' if i == 1 else ''} {por_numero['.'.join(partes[:i])]}"
                      for i in range(1, len(partes) + 1) if '.'.join(partes[:i]) in por_numero]
            e["ruta"] = " > ".join(camino) or f"{e['numero']} {e['titulo']}"
        else:
            e["ruta"] = e["titulo"]
    return entradas


def cuerpo(texto):
    """Texto del fragmento sin el encabezado, sin capturas ni descripciones (lo que realmente esta en la pagina)."""
    lineas = texto.split("\n")[1:]
    t = " ".join(l for l in lineas if not l.startswith("[Captura") and not l.startswith("[Descripción"))
    return normal(t)


def main(solo=None, prueba=False):
    args = argparse.Namespace(solo=solo, prueba=prueba)
    con = conectar()
    tabla = next(iter(MODELOS.values()))[0]
    indice = {}
    for manual, archivo, orden, numero, titulo, pagina in con.execute(
            "SELECT manual, archivo, orden, numero, titulo, pagina FROM manual_indice ORDER BY archivo, orden"):
        indice.setdefault(archivo, []).append({"numero": numero, "titulo": titulo, "pagina": pagina})
    total_cambios, total_indice = 0, 0
    for archivo, entradas in indice.items():
        if args.solo and args.solo.lower() not in archivo.lower():
            continue
        pdf = ruta_pdf(archivo)
        if not pdf.exists():
            continue
        # solo manuales con titulos numerados: en las guias cortas el "indice" son lineas en mayusculas sueltas
        entradas = [e for e in entradas if e["numero"]]
        if len(entradas) < 3:
            continue
        entradas = rutas_de_titulos(entradas)
        doc = pymupdf.open(pdf)
        textos_pag = {}
        def pagina_normal(n):
            if n not in textos_pag:
                textos_pag[n] = normal(doc[n - 1].get_text()) if 1 <= n <= len(doc) else ""
            return textos_pag[n]
        # posicion de cada titulo dentro de su pagina
        for e in entradas:
            texto_pag = pagina_normal(e["pagina"])
            m = re.search(re.escape(normal(e["titulo"])), texto_pag) if e["titulo"] else None
            e["pos"] = m.start() if m else 0
        filas = con.execute(f"SELECT id, text, metadata FROM {tabla} WHERE metadata->>'archivo' = %s", (archivo,)).fetchall()
        cambios, borrar = [], []
        for fid, texto, md in filas:
            pag = md.get("pagina")
            if not pag:
                continue
            if es_indice(texto):
                borrar.append(fid)
                continue
            # posicion del fragmento en su pagina (con sus primeras palabras)
            palabras = cuerpo(texto).split()
            pos = None
            for inicio in range(0, min(len(palabras), 30), 5):
                trozo = " ".join(palabras[inicio:inicio + 6])
                if len(trozo) > 15:
                    i = pagina_normal(pag).find(trozo)
                    if i >= 0:
                        pos = i
                        break
            if pos is None:
                # no se ubico el texto en la pagina: solo se corrige si en esa pagina no empieza ningun titulo
                if any(e["pagina"] == pag for e in entradas):
                    continue
                pos = 0
            candidatos = [e for e in entradas if e["pagina"] < pag or (e["pagina"] == pag and e["pos"] <= pos + 5)]
            if not candidatos:
                continue
            nueva = candidatos[-1]["ruta"]
            if nueva != md.get("seccion"):
                cambios.append((fid, texto, md, nueva))
        print(f"{archivo}: {len(cambios)} secciones corregidas, {len(borrar)} fragmentos de índice general quitados")
        for fid, texto, md, nueva in cambios[:8] if args.prueba else []:
            print(f"   p{md['pagina']}: '{(md.get('seccion') or '')[:45]}'  ->  '{nueva[:80]}'")
        total_cambios += len(cambios); total_indice += len(borrar)
        if args.prueba:
            continue
        for modelo, (t, _) in MODELOS.items():
            for fid in borrar:
                con.execute(f"DELETE FROM {t} WHERE id = %s", (fid,))
            for i in range(0, len(cambios), 16):
                lote = cambios[i:i + 16]
                nuevos = []
                for fid, texto, md, nueva in lote:
                    primera, _, resto = texto.partition("\n")
                    primera = re.sub(r"\s*\|\s*Sección:.*$", "", primera) + f" | Sección: {nueva}"
                    md["seccion"] = nueva
                    nuevos.append((fid, primera + "\n" + resto, md))
                vecs = vectorizar(modelo, [x[1] for x in nuevos])
                for (fid, txt, md), v in zip(nuevos, vecs):
                    con.execute(f"UPDATE {t} SET text = %s, metadata = %s, embedding = %s::vector WHERE id = %s",
                                (txt, json.dumps(md, ensure_ascii=False), str(v), fid))
    if not args.prueba and (total_cambios or total_indice):
        con.execute("TRUNCATE respuestas_cache")
    print(f"Total: {total_cambios} secciones corregidas, {total_indice} fragmentos de índice quitados"
          + (" (prueba: no se guardó nada)" if args.prueba else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", help="solo manuales cuyo archivo contenga este texto")
    ap.add_argument("--prueba", action="store_true", help="solo mostrar los cambios, sin guardar")
    a = ap.parse_args()
    main(a.solo, a.prueba)
