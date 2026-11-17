"""Prueba la lectura de capturas: inicia sesion con la cuenta de prueba, envia una imagen a /navasoft-captura
y luego hace la pregunta con la descripcion, igual que el portal. Uso: python examen/probar_captura.py <imagen> ["pregunta"]"""
import base64, pathlib, sys, time
import requests
sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).parent
API = "http://localhost:5678/webhook/navasoft-api"
clave = [l.strip() for l in (BASE / "cuenta_prueba.txt").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")][0]
tok = requests.post(API, json={"accion": "login", "usuario": "cliente.prueba", "clave": clave}, timeout=30).json()["token"]
img = pathlib.Path(sys.argv[1])
dato = f"data:image/{img.suffix[1:].replace('jpg', 'jpeg')};base64," + base64.b64encode(img.read_bytes()).decode()
t = time.time()
c = requests.post("http://localhost:5678/webhook/navasoft-captura", json={"token": tok, "imagen": dato}, timeout=90).json()
print(f"Captura ({time.time() - t:.1f}s):", c)
if c.get("ok"):
    pregunta = (sys.argv[2] if len(sys.argv) > 2 else "Tengo este problema en NAVASOFT, ¿qué hago?") + "\n\n[Captura adjunta] " + c["descripcion"]
    r = requests.post(API, json={"accion": "nueva_pregunta", "token": tok, "conversacion_id": None, "texto": pregunta}, timeout=200).json()
    print("\nRespuesta:\n", (r.get("respuesta") or r)[:1500] if isinstance(r.get("respuesta"), str) else r)
    requests.post(API, json={"accion": "borrar_conversacion", "token": tok, "conversacion_id": r.get("conversacion_id")})
requests.post(API, json={"accion": "logout", "token": tok})
