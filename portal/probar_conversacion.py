"""Prueba una conversacion completa por el portal (como un cliente): inicia sesion con la cuenta
de prueba, hace varias preguntas seguidas en el mismo chat y muestra las respuestas y el titulo."""
import pathlib
import re
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")
API = "http://localhost:5678/webhook/navasoft-api"
cred = pathlib.Path(__file__).parent / "credenciales_iniciales.txt"
clave = re.search(r"cliente\.prueba\s+rol=cliente\s+contraseña=(\S+)", cred.read_text(encoding="utf-8")).group(1)

tok = requests.post(API, json={"accion": "login", "usuario": "cliente.prueba", "clave": clave}).json()["token"]
conv = None
for pregunta in sys.argv[1:]:
    t0 = time.time()
    r = requests.post(API, json={"accion": "nueva_pregunta", "token": tok, "conversacion_id": conv, "texto": pregunta}, timeout=200).json()
    conv = r.get("conversacion_id", conv)
    texto = re.sub(r"\(http[^)]+\)", "(url)", r.get("respuesta") or r.get("error", ""))
    print(f"\n❓ {pregunta}  ({time.time() - t0:.1f} s)\n{texto[:600]}")
time.sleep(6)  # el titulo se genera despues de responder
lista = requests.post(API, json={"accion": "conversaciones", "token": tok}).json()["conversaciones"]
print("\nTítulo del chat:", next((c["titulo"] for c in lista if c["id"] == conv), "?"))
