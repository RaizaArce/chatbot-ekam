"""Pasa por el asistente las preguntas reales de examen/preguntas_reales.txt y clasifica cada respuesta.
Uso: .venv\Scripts\python.exe examen\examen_reales.py"""
import pathlib, re, sys, time
import requests
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from examen_noche import ASISTENTE, CABECERA  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
SIN_INFO = re.compile(r"no (se encuentra|contienen|cuento|está disponible|incluye|detallan|dispongo|encuentro|tengo)|ninguno de los", re.I)
preguntas = [l.strip() for l in (pathlib.Path(__file__).parent / "preguntas_reales.txt").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
cuenta = {"con pasos y fuente": 0, "pide aclaración": 0, "sin información": 0, "error": 0}
for p in preguntas:
    try:
        r = requests.post(ASISTENTE, headers=CABECERA, json={"chatInput": p, "sessionId": f"reales-{time.time()}"}, timeout=180)
        r.raise_for_status(); t = r.json().get("output", "")
    except Exception as e:
        t = ""; print("   error:", e)
    tipo = ("error" if not t else "sin información" if SIN_INFO.search(t) else
            "con pasos y fuente" if "Fuente:" in t else "pide aclaración")
    cuenta[tipo] += 1
    fuente = re.search(r"Fuente: \[([^\]]+)\]", t)
    print(f"[{tipo}] {p}\n      -> {fuente.group(1) if fuente else t[:150].replace(chr(10), ' ')}", flush=True)
    time.sleep(20)
print("\nResumen:", ", ".join(f"{k}: {v}" for k, v in cuenta.items()), f"(de {len(preguntas)})")
