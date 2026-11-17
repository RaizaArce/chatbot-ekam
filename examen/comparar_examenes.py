"""Compara el examen antes y despues de las mejoras y clasifica cada respuesta."""
import json
import pathlib
import re
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")
AQUI = pathlib.Path(__file__).parent
SIN_INFO = re.compile(r"no (se encuentra|contienen|cuento|está disponible|incluye|detallan|tengo información)|lamentablemente|lamento informar", re.I)


def tipo(r):
    t = r["respuesta_bot"]
    if t.startswith("ERROR") or "no pude responder" in t:
        return "error"
    if r["cita_manual"]:
        return "con manual"
    if SIN_INFO.search(t):
        return "sin info → soporte"
    if t.strip().endswith("?") and len(t) < 600:
        return "pide aclaración / saludo"
    return "otro"


def resumen(nombre, datos):
    tipos = {}
    for r in datos:
        tipos.setdefault(tipo(r), []).append(r)
    segs = [r["segundos"] for r in datos if tipo(r) != "error"]
    print(f"\n=== {nombre}: {len(datos)} consultas | tiempo mediano {statistics.median(segs):.1f} s")
    for k in ["con manual", "sin info → soporte", "pide aclaración / saludo", "otro", "error"]:
        print(f"  {k:<26} {len(tipos.get(k, [])):>3}")
    return tipos


antes = json.loads((AQUI / "resultados_v1_antes_de_mejoras.json").read_text(encoding="utf-8"))
despues = json.loads((AQUI / "resultados.json").read_text(encoding="utf-8"))
resumen("ANTES", antes)
t = resumen("AHORA", despues)

limpio = lambda s: re.sub(r"\s+", " ", re.sub(r"\(http[^)]+\)", "", re.sub(r"!\[[^\]]*\]\([^)]+\)", "[IMG]", s))).strip()
for k in ["con manual", "otro", "pide aclaración / saludo", "error"]:
    print(f"\n----- {k.upper()} -----")
    for r in t.get(k, []):
        print(f"#{r['n']} Q: {limpio(r['consulta'])[:120]}")
        print(f"   BOT: {limpio(r['respuesta_bot'])[:330]}")
