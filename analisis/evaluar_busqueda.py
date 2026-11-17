"""Mide solo la BUSQUEDA (sin la IA, gratis y en segundos) con las mismas preguntas del examen nocturno.

Para cada pregunta revisa si el fragmento mas parecido (el que decide que procedimiento se lee) cae en la
pagina del tema (pag-1 .. pag+4, igual que el examen) y si la pagina aparece entre los 6 primeros.
Compara la busqueda actual (solo por significado) con la busqueda mixta (significado + palabras + manual).

Uso:  .venv\\Scripts\\python.exe analisis\\evaluar_busqueda.py [--detalle]
"""
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "examen"))
from leer_manuales import conectar  # noqa: E402
from examen_noche import elegir_temas  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
con = conectar()
_vectores = {}


def vec(q):
    if q not in _vectores:
        _vectores[q] = str(requests.post("http://127.0.0.1:11434/api/embed", json={"model": "bge-m3", "input": q, "keep_alive": "3h"}).json()["embeddings"][0])
    return _vectores[q]


PESOS = {"ps": 1.0, "pt": 0.5, "pm": 0.012}   # titulo de seccion, texto, nombre del manual

SOLO_VECTOR = """SELECT metadata->>'archivo', (metadata->>'pagina')::int FROM chunks_bge_m3
                 WHERE metadata->>'pagina' IS NOT NULL ORDER BY embedding <=> %(v)s::vector LIMIT 6"""

# Busqueda mixta: une por "rango reciproco" (RRF) tres listas: parecido de significado, coincidencia de palabras
# en el texto y en el titulo de la seccion, y le da ventaja a los fragmentos del manual que nombra la pregunta.
MIXTA = open(pathlib.Path(__file__).parent / "busqueda_mixta.sql", encoding="utf-8").read()


def evaluar(nombre, sql, temas, detalle, pesos=PESOS):
    top1 = top6 = 0
    for t in temas:
        filas = con.execute(sql, {"v": vec(t["pregunta"]), "q": t["pregunta"], **pesos}).fetchall()
        dentro = lambda f: f[0] == t["archivo"] and t["pagina"] - 1 <= f[1] <= t["pagina"] + 4
        a, b = bool(filas) and dentro(filas[0]), any(dentro(f) for f in filas)
        top1 += a; top6 += b
        if detalle and not a:
            print(f"   {'·' if b else '✗'} {t['pregunta'][:70]:<70} tema p{t['pagina']} -> {[f'{x[0][-25:]} p{x[1]}' for x in filas[:3]]}")
    n = len(temas)
    if nombre is None:
        return top1, top6
    print(f"{nombre:<14} 1.º correcto: {top1}/{n} ({top1 / n:.0%})   entre los 6: {top6}/{n} ({top6 / n:.0%})", flush=True)


if __name__ == "__main__":
    temas = elegir_temas(con, 120)
    detalle = "--detalle" in sys.argv
    if "--solo-mixta" not in sys.argv:
        evaluar("Actual", SOLO_VECTOR, temas, detalle)
    if "--ajustar" in sys.argv:
        prueba = [(evaluar(None, MIXTA, temas, False, {"ps": a, "pt": b, "pm": c}), a, b, c)
                  for a in (0.5, 1, 2) for b in (0, 0.5, 1) for c in (0, 0.012, 0.03)]
        for (t1, t6), a, b, c in sorted(prueba, reverse=True)[:6]:
            print(f"  seccion {a}  texto {b}  manual {c}:  1.º {t1}   entre 6 {t6}")
    else:
        evaluar("Mixta", MIXTA, temas, detalle)
