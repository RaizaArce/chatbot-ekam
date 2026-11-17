"""Envia preguntas al chatbot y verifica que las imagenes y enlaces que devuelve existan."""
import re
import sys
import time
import uuid

import requests

sys.stdout.reconfigure(encoding="utf-8")
# el asistente solo responde con la clave interna (la misma que usa el portal)
CHAT = "http://localhost:5678/webhook/navasoft-asistente"
CLAVE = next(l.split("=", 1)[1].strip() for l in open(r"C:\chatbot-navasoft\.env", encoding="utf-8") if l.startswith("ASISTENTE_CLAVE="))
CABECERA = {"X-Navasoft-Clave": CLAVE}
PREGUNTAS = sys.argv[1:] or ["¿Cómo abro una nueva caja chica?"]

for pregunta in PREGUNTAS:
    t0 = time.time()
    r = requests.post(CHAT, json={"sessionId": str(uuid.uuid4()), "chatInput": pregunta}, headers=CABECERA, timeout=180)
    texto = r.json().get("output", r.text)
    print(f"\n❓ {pregunta}  ({time.time() - t0:.1f} s)\n{texto}\n")
    urls = re.findall(r"http://localhost:5678/webhook/navasoft-(?:img|pagina)\?id=[0-9a-f]{12}", texto)
    imagenes = len(re.findall(r"!\[[^\]]*\]\(", texto))
    print(f"   → capturas en la respuesta: {imagenes} | enlaces totales: {len(urls)}")
    for u in urls:
        ok = requests.get(u, timeout=30).status_code
        print(f"   {'OK ' if ok == 200 else 'ROTA'} {ok} {u}")
