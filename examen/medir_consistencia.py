"""Mide que tan parejas son las respuestas: hace la misma pregunta varias veces y cuenta los pasos.
(A cada repeticion se le agrega '(vez N)' para que no se use la respuesta guardada.)"""
import pathlib
import re
import statistics
import sys
import uuid

import requests

sys.stdout.reconfigure(encoding="utf-8")
ENV = dict(l.split("=", 1) for l in (pathlib.Path(__file__).parent.parent / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
CAB = {"X-Navasoft-Clave": ENV["ASISTENTE_CLAVE"].strip()}
PREGUNTAS = ["¿Cómo registro un comprobante de retención de un cliente agente de retención?",
             "¿Cómo hago el reembolso de la caja chica?",
             "¿Cómo emito una guía de remisión de transportista?"]
VECES = int(sys.argv[1]) if len(sys.argv) > 1 else 4

for q in PREGUNTAS:
    cuentas, paginas = [], []
    for n in range(VECES):
        r = requests.post("http://localhost:5678/webhook/navasoft-asistente", headers=CAB, timeout=180,
                          json={"sessionId": str(uuid.uuid4()), "chatInput": f"{q} (prueba {uuid.uuid4().hex[:6]})"}).json().get("output", "")
        cuentas.append(len(re.findall(r"(?m)^\s*\d+[.)]\s", r)))
        paginas.append(len(set(re.findall(r"navasoft-pagina\?id=([0-9a-f]{12})", r))))
    print(f"{q[:60]:<60} pasos={cuentas}  mínimo={min(cuentas)}  máximo={max(cuentas)}  "
          f"variación={max(cuentas) - min(cuentas)}  páginas citadas={paginas}")
