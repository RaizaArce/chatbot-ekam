"""Revisa la base de la nube despues de la limpieza: titulos de manual con nombres de clientes y datos reales que
sigan en el texto de los fragmentos (con la misma lista que limpiar_manuales.py). Con --arreglar-titulos pone el
titulo limpio en los fragmentos e indice que aun tengan el viejo.
    powershell -ExecutionPolicy Bypass -File migracion\\con_tunel.ps1 migracion\\revisar_nube.py [--arreglar-titulos]"""
import collections
import json
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import limpiar_manuales as L  # noqa: E402
from leer_manuales import MODELOS, conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
reglas = L.cargar_reglas()
con = conectar()
tabla = next(iter(MODELOS.values()))[0]
arreglar = "--arreglar-titulos" in sys.argv

titulos = [r[0] for r in con.execute(f"SELECT DISTINCT metadata->>'manual' FROM {tabla}")]
for t in titulos:
    limpio = L.titulo_limpio(t, reglas) if t in reglas["titulos"] or L.tiene_datos_reales(t, reglas) else t
    if limpio != t:
        print(f"TITULO viejo: {t!r} -> {limpio!r}")
        if arreglar:
            con.execute(f"UPDATE {tabla} SET metadata = jsonb_set(metadata, '{{manual}}', to_jsonb(%s::text)) "
                        "WHERE metadata->>'manual' = %s", (limpio, t))
            con.execute("UPDATE manual_indice SET manual = %s WHERE manual = %s", (limpio, t))

por_manual = collections.Counter()
ejemplos = {}
for texto, md in con.execute(f"SELECT text, metadata FROM {tabla} WHERE coalesce(metadata->>'tipo', '') <> 'alias'"):
    for linea in texto.splitlines():
        if L.tiene_datos_reales(linea, reglas):
            por_manual[md.get("archivo")] += 1
            ejemplos.setdefault(md.get("archivo"), linea[:140])
print(f"\nFragmentos con datos reales en el texto: {sum(por_manual.values())}")
for a, n in por_manual.most_common():
    print(f"  {n:4d}  {a}  | ej: {ejemplos[a]}")
if arreglar:
    con.execute("TRUNCATE respuestas_cache")
print(json.dumps({"titulos": len(titulos)}))
