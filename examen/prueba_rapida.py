"""Prueba automatica de calidad del Asistente NAVASOFT (correrla despues de cada cambio).

Revisa: procedimientos completos, seguimiento sin repetir, consultas ambiguas, temas sin informacion,
temas ajenos, respuestas guardadas, enlaces e imagenes validos y que el asistente no este abierto al publico.

Uso:  .venv\\Scripts\\python.exe examen\\prueba_rapida.py
Por defecto prueba la laptop. Para la nube (gasta cuota de IA):  set NAVASOFT_URL=https://n8n.srv2106635.hstgr.cloud
"""
import os
import pathlib
import re
import sys
import time
import uuid

import requests

sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).parent.parent
ENV = dict(l.split("=", 1) for l in (BASE / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
URL = os.getenv("NAVASOFT_URL", "http://localhost:5678").rstrip("/")
ASISTENTE = f"{URL}/webhook/navasoft-asistente"
PORTAL_API = f"{URL}/webhook/navasoft-api"
CABECERA = {"X-Navasoft-Clave": ENV["ASISTENTE_CLAVE"].strip()}
URL_RE = re.compile(re.escape(URL) + r"/webhook/navasoft-(?:img|pagina)\?id=[0-9a-f]{12}")
SIN_INFO = re.compile(r"no (se encuentra|contienen|cuento|está disponible|incluye|detallan|dispongo|encuentro)|lamentablemente|lamento|ningún fragmento|ninguno de los|soporte de EKAM", re.I)
resultados = []


def preguntar(texto, sesion=None):
    t0 = time.time()
    r = requests.post(ASISTENTE, json={"sessionId": sesion or str(uuid.uuid4()), "chatInput": texto}, headers=CABECERA, timeout=180)
    r.raise_for_status()
    return r.json().get("output", ""), time.time() - t0


def revisar(nombre, ok, detalle=""):
    resultados.append(ok)
    print(f"  {'PASA ' if ok else 'FALLA'}  {nombre}" + (f"  ({detalle})" if detalle else ""))


def pasos(texto):
    return len(re.findall(r"(?m)^\s*\d+[.)]\s", texto))


print("\n=== Respuestas de una sola pregunta")
r, s = preguntar("¿Cómo abro una nueva caja chica?")
revisar("Caja chica: cita el manual correcto", "caja chica" in r.lower() and "navasoft-pagina?id=" in r, f"{s:.1f} s")
revisar("Caja chica: incluye captura de pantalla", "![" in r)
r, _ = preguntar("¿Cómo registro un comprobante de retención de un cliente agente de retención?")
revisar("Procedimiento completo (agente de retención): 3 o más pasos", pasos(r) >= 3, f"{pasos(r)} pasos")
r, _ = preguntar("tengo problemas con una boleta")
revisar("Consulta ambigua: pide aclaración sin citar fuentes", "?" in r and "navasoft-pagina" not in r)
r, _ = preguntar("No le cuadra el sistema con respecto al SIRE")
# ante un problema puede dar pasos de revision del manual, pero siempre debe derivar a soporte
revisar("Reporte de problema (SIRE): deriva a soporte", bool(SIN_INFO.search(r)) or "hablar con soporte" in r.lower())
r, _ = preguntar("¿Cuál es la capital de Francia?")
revisar("Tema ajeno: no responde con manuales", "navasoft-pagina" not in r and "parís" not in r.lower())
r, _ = preguntar("Hola")
revisar("Saludo: breve y sin fuentes", "navasoft-pagina" not in r and len(r) < 400)

print("\n=== Enlaces e imágenes")
r, _ = preguntar("¿Cómo emito una guía de remisión de transportista?")
urls = URL_RE.findall(r)
rotas = [u for u in urls if requests.get(u, timeout=30).status_code != 200]
revisar("Todas las capturas y páginas citadas existen", bool(urls) and not rotas, f"{len(urls)} enlaces, {len(rotas)} rotos")
revisar("Máximo 2 capturas por respuesta", r.count("![") <= 2, f"{r.count('![')} capturas")

print("\n=== Respuestas guardadas")
q = f"¿Cómo hago el reembolso de la caja chica? (prueba {uuid.uuid4().hex[:6]})"  # pregunta nueva cada vez: aun no guardada
r1, s1 = preguntar(q)
r2, s2 = preguntar(q)
revisar("La segunda vez responde la respuesta guardada", r1 == r2 and s2 < s1, f"1.ª {s1:.1f} s, 2.ª {s2:.1f} s")

print("\n=== Índice de temas de un manual")
r, s = preguntar("muéstrame los temas del manual de Ventas")
revisar("Índice: elige el manual principal (Ventas V5)", "Temas del Manual de Ventas V5" in r, f"{s:.1f} s")
revisar("Índice: cada tema enlaza a su página", len(URL_RE.findall(r)) >= 10, f"{len(URL_RE.findall(r))} enlaces")
r, _ = preguntar("¿qué manuales hay?")
revisar("Índice: lista los manuales disponibles", "caja chica" in r.lower() and "ventas" in r.lower())

print("\n=== Portal: modo guía y dictado por voz")
html_portal = requests.get(f"{URL}/webhook/navasoft-portal", timeout=30).text
# el JavaScript del portal no debe tener errores de sintaxis (una pagina en blanco no la detecta nada mas)
import shutil, subprocess, tempfile
if shutil.which("node"):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(re.findall(r"<script>(.*?)</script>", html_portal, re.S)[-1])
    chequeo = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    revisar("El JavaScript del portal no tiene errores de sintaxis", chequeo.returncode == 0, chequeo.stderr.strip()[:200])
revisar("El portal incluye el modo guía paso a paso", "Listo, siguiente paso" in html_portal and "function pasosDe" in html_portal)
revisar("El portal incluye el botón de dictado por voz", 'id="b-microfono"' in html_portal and "navasoft-voz" in html_portal)

print("\n=== Conversación por el portal (seguimiento)")
# la contraseña de la cuenta de prueba esta en examen/cuenta_prueba.txt (fuera del historial de git), asi se puede
# borrar portal/credenciales_iniciales.txt despues de cambiar las contraseñas de las cuentas reales
clave = [l.strip() for l in (BASE / "examen" / "cuenta_prueba.txt").read_text(encoding="utf-8").splitlines()
         if l.strip() and not l.startswith("#")][0]
tok = requests.post(PORTAL_API, json={"accion": "login", "usuario": "cliente.prueba", "clave": clave}).json().get("token")
if not tok:
    revisar("Inicio de sesión de la cuenta de prueba", False, "la cuenta cliente.prueba no pudo entrar")
else:
    conv, respuestas = None, []
    for texto in ["¿Cómo registro un comprobante de retención de un cliente agente de retención?", "y luego", "ya lo hice, ¿qué sigue?"]:
        j = requests.post(PORTAL_API, json={"accion": "nueva_pregunta", "token": tok, "conversacion_id": conv, "texto": texto}, timeout=200).json()
        conv = j.get("conversacion_id", conv)
        respuestas.append(j.get("respuesta", ""))
    limpio = lambda t: re.sub(r"\(http[^)]+\)|\[\[sugerencias:[^\]]*\]\]|!\[[^\]]*\]", "", t)
    revisar("Seguimiento: no repite la respuesta anterior", limpio(respuestas[1]) != limpio(respuestas[0]))
    revisar("Seguimiento: no dice 'no tengo información' de un proceso ya explicado",
            not re.search(r"no (cuento|tengo|dispongo|se encuentra)", respuestas[2], re.I))
    revisar("Respuestas con pasos traen sugerencias de siguiente pregunta", "[[sugerencias:" in respuestas[0])
    m = requests.post(PORTAL_API, json={"accion": "mensajes", "token": tok, "conversacion_id": conv}).json()
    ultimo = [x for x in m.get("mensajes", []) if x["rol"] == "bot"][-1]
    v = requests.post(PORTAL_API, json={"accion": "valorar", "token": tok, "mensaje_id": ultimo["id"], "valor": 1}).json()
    revisar("Valoración 👍/👎 se guarda", v.get("ok") is True)
    requests.post(PORTAL_API, json={"accion": "borrar_conversacion", "token": tok, "conversacion_id": conv})
    # la respuesta guardada de esta prueba se quita con 👎, para no dejar basura en respuestas_cache
    j = requests.post(PORTAL_API, json={"accion": "nueva_pregunta", "token": tok, "conversacion_id": None, "texto": q}, timeout=200).json()
    requests.post(PORTAL_API, json={"accion": "valorar", "token": tok, "mensaje_id": j.get("mensaje_id"), "valor": -1})
    requests.post(PORTAL_API, json={"accion": "borrar_conversacion", "token": tok, "conversacion_id": j.get("conversacion_id")})
    requests.post(PORTAL_API, json={"accion": "logout", "token": tok})

print("\n=== Seguridad")
revisar("El asistente rechaza pedidos sin la clave interna",
        requests.post(ASISTENTE, json={"chatInput": "hola"}, timeout=30).status_code == 403)
revisar("El chat público antiguo ya no existe",
        requests.get(f"{URL}/webhook/0f6f2a43-7c1e-4b55-9d3a-6c1a2f0e9b11/chat", timeout=30).status_code == 404)
revisar("El portal rechaza acciones sin sesión",
        requests.post(PORTAL_API, json={"accion": "conversaciones", "token": "x"}).json().get("sesion") is False)
revisar("El generador de títulos rechaza pedidos sin la clave interna",
        requests.post(f"{URL}/webhook/navasoft-titulo", json={"conversacion_id": "x"}, timeout=30).status_code == 403)
revisar("El portal verifica sus librerías externas", html_portal.count('integrity="sha384-') == 2)
revisar("Hablar con soporte abre WhatsApp con el resumen", "https://wa.me/${r.whatsapp}?text=" in html_portal)
if tok:
    tok = requests.post(PORTAL_API, json={"accion": "login", "usuario": "cliente.prueba", "clave": clave}).json().get("token")
    llamar = lambda **d: requests.post(PORTAL_API, json={"token": tok, **d}, timeout=30).json()
    revisar("Un cliente no puede escribir mensajes del asistente",
            llamar(accion="guardar_respuesta", conversacion_id=str(uuid.uuid4()), texto="x").get("ok") is False)
    revisar("Un cliente no puede usar funciones de administrador", llamar(accion="admin_usuarios").get("ok") is False)
    revisar("Un dato numérico enorme se rechaza sin error", llamar(accion="valorar", mensaje_id="9" * 25, valor=1).get("ok") is False)
    llamar(accion="logout")

total, pasan = len(resultados), sum(resultados)
print(f"\nResultado: {pasan} de {total} pruebas pasan" + ("  ✅" if pasan == total else "  ⚠️  revisar las que fallan"))
sys.exit(0 if pasan == total else 1)
