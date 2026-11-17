"""Mide la busqueda de produccion (sin IA) contra la base y el Ollama de la nube, y prueba una ventaja para el
fragmento cuyo titulo de seccion aparece completo en la pregunta. Lo lanza analisis/evaluar_nube.ps1.
Compara el peso h: 0 es la busqueda actual."""
import os
import pathlib
import sys

import requests

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(BASE), str(BASE / "examen"), str(BASE / "n8n")]
from leer_manuales import conectar  # noqa: E402
from examen_noche import elegir_temas  # noqa: E402
from publicar_chatbot import BUSCAR_SQL_BASE, PESO_MANUAL  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OLLAMA = os.environ["OLLAMA_URL"]
con = conectar()

corte = BUSCAR_SQL_BASE.index("), principales AS")
SQL = (BUSCAR_SQL_BASE[:corte].replace("PESO_MANUAL", str(PESO_MANUAL)).replace("%", "%%")
       .replace("$1", "%(v)s").replace("$3", "%(q)s").replace("PESO_SECCION", "%(h)s")
       + ") SELECT metadata->>'archivo', (metadata->>'pagina')::int FROM parecidos WHERE metadata->>'pagina' IS NOT NULL ORDER BY puntaje DESC")

temas = elegir_temas(con, 120)
vec = {}
for t in temas:
    vec[t["pregunta"]] = str(requests.post(f"{OLLAMA}/api/embed", json={"model": "bge-m3", "input": t["pregunta"]}, timeout=120).json()["embeddings"][0])

base = {}
for h in (0, 0.004, 0.008, 0.012, 0.02):
    top1 = top6 = 0
    fallos = []
    for t in temas:
        filas = con.execute(SQL, {"v": vec[t["pregunta"]], "q": t["pregunta"], "h": h}).fetchall()
        dentro = lambda f: f[0] == t["archivo"] and t["pagina"] - 1 <= f[1] <= t["pagina"] + 4
        a, b = bool(filas) and dentro(filas[0]), any(dentro(f) for f in filas)
        top1 += a
        top6 += b
        fallos.append((t["pregunta"], a))
    if h == 0:
        base = dict(fallos)
    empeoran = [q[:70] for q, a in fallos if base[q] and not a]
    mejoran = sum(1 for q, a in fallos if a and not base[q])
    print(f"h={h:<6} 1.º correcto {top1}/{len(temas)}  entre 6 {top6}/{len(temas)}  mejoran {mejoran}  empeoran {len(empeoran)} {empeoran[:6]}", flush=True)
