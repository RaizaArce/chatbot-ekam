"""Mide si la busqueda (sin IA) encuentra la pagina correcta para preguntas escritas como las escribe un cliente,
sin los nombres del manual (examen/preguntas_cliente.json). Compara: sin ayuda, con el glosario, y con los alias
(las frases de cliente cargadas por alias_secciones.py). Corre contra la base y el Ollama de la nube con
migracion/sincronizar_nube.ps1 abierto, o con las variables de conexion puestas a mano.
    .venv\\Scripts\\python.exe analisis\\evaluar_cliente.py"""
import json
import os
import pathlib
import re
import sys
import unicodedata

import requests

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(BASE), str(BASE / "n8n")]
from leer_manuales import conectar  # noqa: E402
from publicar_chatbot import BUSCAR_SQL_BASE, GLOSARIO, PESO_MANUAL, PESO_SECCION  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
con = conectar()
corte = BUSCAR_SQL_BASE.index("), principales AS")
SQL = (BUSCAR_SQL_BASE[:corte].replace("PESO_MANUAL", str(PESO_MANUAL)).replace("PESO_SECCION", str(PESO_SECCION))
       .replace("%", "%%").replace("$1", "%(v)s").replace("$3", "%(q)s").replace("PESO_ALIAS", "%(pa)s").replace("UMBRAL_ALIAS", "%(ua)s")
       + ") SELECT metadata->>'archivo', (metadata->>'pagina')::int, metadata->>'tipo', sim, metadata->>'seccion' FROM parecidos "
         "WHERE metadata->>'pagina' IS NOT NULL ORDER BY puntaje DESC")
SIN_ALIAS = SQL.replace("FROM chunks_bge_m3\n), vector", "FROM chunks_bge_m3 WHERE coalesce(metadata->>'tipo', '') <> 'alias'\n), vector")
assert SIN_ALIAS != SQL


def con_glosario(q):
    t = unicodedata.normalize("NFD", q.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    extra = [g["buscar"] for g in GLOSARIO if re.search(g["si"], t, re.I)]
    return " ".join([q] + extra)


def vector(texto):
    return str(requests.post(f"{OLLAMA}/api/embed", json={"model": "bge-m3", "input": texto}, timeout=120).json()["embeddings"][0])


from alias_secciones import normal, normal_numeros  # noqa: E402


preguntas = json.loads((BASE / "examen" / "preguntas_cliente.json").read_text(encoding="utf-8"))
modos = {"glosario": (SQL, con_glosario, 0, 1)}
modos |= {f"glosario + alias (peso {pa}, umbral {ua})": (SQL, con_glosario, pa, ua)
          for ua in (0.5, 0.55) for pa in (0.2, 0.3, 0.5)}
for modo, (sql, preparar, pa, ua) in modos.items():
    top1 = top3 = 0
    fallos, mejor_sims = [], []
    for q, archivo, sec in preguntas:
        b = preparar(q)
        filas = con.execute(sql, {"v": vector(b), "q": b, "pa": pa, "ua": ua}).fetchall()
        # acierta si es la seccion esperada del manual (un tema ocupa varias paginas)
        dentro = lambda f: f[0] == archivo and (normal_numeros(f[4] or "").endswith(normal_numeros(sec)) if sec[:1].isdigit()
                                                 else normal(f[4] or "") == normal(sec) or normal(f[4] or "").endswith("> " + normal(sec)))
        top1 += bool(filas) and dentro(filas[0])
        top3 += any(dentro(f) for f in filas[:3])
        mejor_sims.append(max((float(f[3]) for f in filas), default=0))
        if not (filas and dentro(filas[0])):
            fallos.append(f"{q}  -> {filas[0][0].split(chr(92))[-1]} p{filas[0][1]} [{filas[0][4]}] {filas[0][2] or ''} | esperado: {sec}" if filas else q)
    print(f"\n{modo}: 1.º correcto {top1}/{len(preguntas)} | entre los 3 primeros {top3}/{len(preguntas)}")
    if "--detalle" in sys.argv:
        for f in fallos:
            print("   x", f)
