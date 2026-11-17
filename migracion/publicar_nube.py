"""Publica en el n8n de la nube los 3 flujos del asistente (chatbot, portal e imagenes), usando los mismos
constructores que la laptop y cambiando solo lo que difiere en el servidor: credenciales, Ollama y keep_alive.
Las llamadas internas a http://localhost:5678 se dejan igual: dentro del contenedor, n8n se llama a si mismo.
No toca los flujos de la laptop ni los archivos .id locales."""
import json
import pathlib
import sys

import requests

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(BASE / "n8n"), str(BASE / "portal")]
import publicar_chatbot as chatbot
import publicar_portal as portal

sys.stdout.reconfigure(encoding="utf-8")
AQUI = pathlib.Path(__file__).parent
API = "https://n8n.srv2106635.hstgr.cloud/api/v1"
H = {"X-N8N-API-KEY": chatbot.API_KEY}
IDS = json.loads((AQUI / "credenciales_nube.json").read_text(encoding="utf-8"))
ARCHIVO_FLUJOS = AQUI / "flujos_nube.json"


def clave_interna():
    if "interna" not in IDS:
        clave = next(l.split("=", 1)[1].strip() for l in (BASE / ".env").read_text(encoding="utf-8").splitlines()
                     if l.startswith("ASISTENTE_CLAVE="))
        r = requests.post(f"{API}/credentials", headers=H, timeout=30, json={
            "name": "Clave interna NAVASOFT", "type": "httpHeaderAuth",
            "data": {"name": chatbot.CABECERA_CLAVE, "value": clave}})
        r.raise_for_status()
        IDS["interna"] = r.json()["id"]
        (AQUI / "credenciales_nube.json").write_text(json.dumps(IDS, indent=2), encoding="ascii")
    return {"httpHeaderAuth": {"id": IDS["interna"], "name": "Clave interna NAVASOFT"}}


def adaptar(wf, cred_interna):
    texto = json.dumps(wf, ensure_ascii=False)
    for viejo, nuevo in [(chatbot.CRED_PG["postgres"]["id"], IDS["postgres"]),
                         (chatbot.CRED_GEMINI["googlePalmApi"]["id"], IDS["gemini"]),
                         (chatbot.CRED_GROQ["groqApi"]["id"], IDS["groq"]),
                         ("http://127.0.0.1:11434", "http://navasoft-ollama:11434"),
                         ("keep_alive: '3h'", "keep_alive: '5m'")]:
        texto = texto.replace(viejo, nuevo)
    wf = json.loads(texto)
    for n in wf["nodes"]:
        c = n.get("credentials", {}).get("httpHeaderAuth")
        if c and c.get("name") == "Clave interna NAVASOFT":
            n["credentials"]["httpHeaderAuth"] = cred_interna["httpHeaderAuth"]
    return {k: wf[k] for k in ("name", "nodes", "connections")} | {"settings": wf.get("settings") or {"executionOrder": "v1"}}


def publicar(wf, flujos):
    wid = flujos.get(wf["name"])
    r = (requests.put(f"{API}/workflows/{wid}", json=wf, headers=H, timeout=180) if wid
         else requests.post(f"{API}/workflows", json=wf, headers=H, timeout=180))
    if not r.ok:
        sys.exit(f"Error al publicar {wf['name']}: {r.status_code} {r.text[:500]}")
    wid = r.json()["id"]
    flujos[wf["name"]] = wid
    ARCHIVO_FLUJOS.write_text(json.dumps(flujos, ensure_ascii=False, indent=2), encoding="utf-8")
    act = requests.post(f"{API}/workflows/{wid}/activate", json={}, headers=H, timeout=60)
    if not act.ok:
        sys.exit(f"Error al activar {wf['name']}: {act.status_code} {act.text[:500]}")
    print(f"{wf['name']} | id {wid} | activo: {act.json()['active']}")


def main():
    cred = clave_interna()
    flujos = json.loads(ARCHIVO_FLUJOS.read_text(encoding="utf-8")) if ARCHIVO_FLUJOS.exists() else {}
    imagenes = json.loads((BASE / "n8n" / "imagenes.json").read_text(encoding="utf-8"))
    # Claude es el ultimo respaldo y es opcional: solo se conecta si ya se creo su credencial
    # (migracion/crear_credencial_claude.ps1 guarda el identificador en credenciales_nube.json).
    claude = {"anthropicApi": {"id": IDS["claude"], "name": "Claude NAVASOFT"}} if IDS.get("claude") else None
    print("Claude de respaldo:", "conectado" if claude else "sin credencial (solo Gemini y Groq)")
    # OpenRouter (modelo gratuito) va antes que Claude; tambien es opcional (migracion/crear_credencial_openrouter.ps1).
    openrouter = {"openRouterApi": {"id": IDS["openrouter"], "name": "OpenRouter NAVASOFT"}} if IDS.get("openrouter") else None
    print("OpenRouter de respaldo:", f"conectado ({chatbot.MODELO_OPENROUTER})" if openrouter else "sin credencial")
    for wf in (imagenes, chatbot.construir(cred, claude, openrouter), portal.construir()):
        publicar(adaptar(wf, cred), flujos)


if __name__ == "__main__":
    main()
