"""Diagnostico: para cada pregunta que fallo en Caja y bancos, que fragmentos trae la busqueda y con que similitud,
y si la pagina del tema esta en la base y que texto tiene."""
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from leer_manuales import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
con = conectar()
vec = lambda q: str(requests.post("http://127.0.0.1:11434/api/embed", json={"model": "bge-m3", "input": q}).json()["embeddings"][0])
ARCHIVO = r"manuales v5\Manual de caja y bancos_V5.pdf"

print("Fragmentos del manual de caja y bancos por pagina (largo del texto):")
filas = con.execute("""SELECT (metadata->>'pagina')::int p, length(text), left(regexp_replace(text, '\\s+', ' ', 'g'), 120)
                       FROM chunks_bge_m3 WHERE metadata->>'archivo' = %s ORDER BY 1""", (ARCHIVO,)).fetchall()
for p, n, t in filas:
    print(f"  p{p:<3} {n:>5}  {t}")

for q, pag in [("¿Cómo hago una transferencia a bancos?", 19), ("¿Cómo funcionan los cheques en caja y bancos?", 23),
               ("¿Cómo registro el comprobante de detracción del cliente?", 21), ("reportes de cobranzas", 21)]:
    print(f"\n=== {q} (tema en pág. {pag})")
    for m, p, sim in con.execute("""SELECT metadata->>'manual', metadata->>'pagina', 1 - (embedding <=> %s::vector)
                                    FROM chunks_bge_m3 ORDER BY embedding <=> %s::vector LIMIT 6""", (vec(q), vec(q))):
        print(f"   {sim:.3f}  {m[:40]:<40} p{p}")
