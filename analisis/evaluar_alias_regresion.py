"""Comprueba que el peso de las frases de cliente (PESO_ALIAS) no empeore las preguntas escritas con los nombres
del manual (los 120 temas del examen de la noche). Corre con migracion/con_tunel.ps1."""
import os, pathlib, sys
import requests
BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(BASE), str(BASE / "examen"), str(BASE / "n8n")]
from leer_manuales import conectar  # noqa: E402
from examen_noche import elegir_temas  # noqa: E402
from publicar_chatbot import BUSCAR_SQL_BASE, PESO_MANUAL, PESO_SECCION  # noqa: E402
sys.stdout.reconfigure(encoding="utf-8")
OLLAMA = os.environ["OLLAMA_URL"]
con = conectar()
corte = BUSCAR_SQL_BASE.index("), principales AS")
SQL = (BUSCAR_SQL_BASE[:corte].replace("PESO_MANUAL", str(PESO_MANUAL)).replace("PESO_SECCION", str(PESO_SECCION)).replace("%", "%%")
       .replace("$1", "%(v)s").replace("$3", "%(q)s").replace("PESO_ALIAS", "%(pa)s").replace("UMBRAL_ALIAS", "%(ua)s")
       + ") SELECT metadata->>'archivo', (metadata->>'pagina')::int FROM parecidos WHERE metadata->>'pagina' IS NOT NULL ORDER BY puntaje DESC")
temas = elegir_temas(con, 120)
vec = {t["pregunta"]: str(requests.post(f"{OLLAMA}/api/embed", json={"model": "bge-m3", "input": t["pregunta"]}, timeout=120).json()["embeddings"][0]) for t in temas}
for pa, ua in [(0, 1)] + [(pa, ua) for ua in (0.5, 0.55) for pa in (0.2, 0.3, 0.5)]:
    top1 = top6 = 0
    for t in temas:
        filas = con.execute(SQL, {"v": vec[t["pregunta"]], "q": t["pregunta"], "pa": pa, "ua": ua}).fetchall()
        dentro = lambda f: f[0] == t["archivo"] and t["pagina"] - 1 <= f[1] <= t["pagina"] + 4
        top1 += bool(filas) and dentro(filas[0]); top6 += any(dentro(f) for f in filas)
    print(f"peso {pa} umbral {ua}: 1.º correcto {top1}/{len(temas)} | entre los primeros {top6}/{len(temas)}", flush=True)
