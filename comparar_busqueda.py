"""Hace las mismas preguntas a los dos modelos de busqueda y muestra que paginas encuentra cada uno."""
import sys

import requests

from leer_manuales import MODELOS, OLLAMA, conectar

sys.stdout.reconfigure(encoding="utf-8")

PREGUNTAS = [
    "¿Cómo abro una nueva caja chica?",
    "¿Qué datos necesito para aperturar una caja chica?",
    "¿Por qué menú entro a los movimientos de caja chica?",
    "¿Cómo registro un gasto pagado con caja chica?",
    "¿Cómo hago el reembolso de la caja chica?",
    "¿Dónde veo cuánto saldo le queda a la caja?",
    "¿Cómo se genera el asiento contable de un egreso?",
    "quiero imprimir el recibo de un egreso",
]

con = conectar()
for pregunta in PREGUNTAS:
    print(f"\n❓ {pregunta}")
    for modelo, (tabla, _) in MODELOS.items():
        vec = requests.post(f"{OLLAMA}/api/embed", json={"model": modelo, "input": [pregunta]}).json()["embeddings"][0]
        filas = con.execute(
            f"""SELECT metadata->>'pagina', 1 - (embedding <=> %s::vector), left(split_part(text, E'\\n', 2), 90)
                FROM {tabla} ORDER BY embedding <=> %s::vector LIMIT 3""",
            (str(vec), str(vec)),
        ).fetchall()
        print(f"   {modelo:<17} " + "  ".join(f"p{p} ({s:.2f})" for p, s, _ in filas))
        print(f"   {'':<17} → {filas[0][2]}")
