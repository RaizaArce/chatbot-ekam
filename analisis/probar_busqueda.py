"""Prueba dos puntos debiles de la busqueda:
1) siglas y terminos exactos (SIRE, ERCTA, kardex, RIC, detraccion)
2) cuantas paginas ocupa un procedimiento (si una sola pagina basta para responderlo completo)."""
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from leer_manuales import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
con = conectar()
vec = lambda q: str(requests.post("http://127.0.0.1:11434/api/embed", json={"model": "bge-m3", "input": q}).json()["embeddings"][0])

print("=== 1) Siglas: ¿el fragmento mas parecido contiene la palabra buscada?")
for termino, consulta in [("SIRE", "SIRE"), ("ERCTA", "ERCTA devolución"), ("RIC", "editar un RIC"),
                          ("kárdex", "kárdex centralizado"), ("detracci", "detracciones"), ("TXT", "TXT balance")]:
    filas = con.execute("""SELECT metadata->>'manual', metadata->>'pagina', text FROM chunks_bge_m3
                           ORDER BY embedding <=> %s::vector LIMIT 5""", (vec(consulta),)).fetchall()
    hits = sum(1 for _, _, t in filas if termino.lower() in t.lower())
    exactos = con.execute("SELECT count(*) FROM chunks_bge_m3 WHERE text ILIKE %s", (f"%{termino}%",)).fetchone()[0]
    print(f"  '{consulta}': {hits}/5 de los resultados contienen '{termino}' | fragmentos que la contienen en toda la base: {exactos}")

print("\n=== 2) Tamaño de los fragmentos (¿cabe un procedimiento completo?)")
r = con.execute("""SELECT count(*), avg(length(text))::int, percentile_cont(0.5) WITHIN GROUP (ORDER BY length(text))::int,
                   count(*) FILTER (WHERE length(text) < 400) FROM chunks_bge_m3""").fetchone()
print(f"  fragmentos: {r[0]} | largo promedio: {r[1]} caracteres | mediana: {r[2]} | muy cortos (<400): {r[3]}")
for consulta in ["registrar comprobante de retención de cliente agente retenedor", "movimientos del kárdex"]:
    filas = con.execute("""SELECT metadata->>'manual', (metadata->>'pagina')::int, length(text) FROM chunks_bge_m3
                           ORDER BY embedding <=> %s::vector LIMIT 3""", (vec(consulta),)).fetchall()
    print(f"  '{consulta}': " + " | ".join(f"{m[:25]} p{p} ({l} car.)" for m, p, l in filas))
