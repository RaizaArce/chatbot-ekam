"""Experimento: copia chunks_bge_m3 a la tabla chunks_exp quitando el texto OCR de las capturas
("[Captura de pantalla: Reto | 40 | 回 ...]"), que es ilegible y ensucia la busqueda. Las capturas ya tienen
su propio fragmento con descripcion, asi que no se pierde informacion. No toca la tabla que usa el asistente.

Uso:  .venv\\Scripts\\python.exe analisis\\experimento_sin_ocr.py
"""
import pathlib
import re
import sys

import requests
from psycopg.types.json import Jsonb

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from leer_manuales import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OCR = re.compile(r"\[Captura de pantalla: [^\]]*\]")

con = conectar()
con.execute("DROP TABLE IF EXISTS chunks_exp")
con.execute("CREATE TABLE chunks_exp (LIKE chunks_bge_m3 INCLUDING ALL)")
filas = con.execute("SELECT id, text, metadata, embedding::text FROM chunks_bge_m3").fetchall()
cambiados = 0
for i, (id_, texto, meta, emb) in enumerate(filas, 1):
    limpio = OCR.sub("[Captura de pantalla]", texto)
    if limpio != texto:
        cambiados += 1
        emb = str(requests.post("http://127.0.0.1:11434/api/embed",
                                json={"model": "bge-m3", "input": limpio, "keep_alive": "3h"}).json()["embeddings"][0])
    con.execute("INSERT INTO chunks_exp (id, text, metadata, embedding) VALUES (%s, %s, %s, %s::vector)", (id_, limpio, Jsonb(meta), emb))
    if i % 100 == 0:
        print(f"  {i}/{len(filas)}", flush=True)
print(f"Listo: {len(filas)} fragmentos copiados, {cambiados} limpiados y revectorizados.")
