"""Muestra, para la ultima ejecucion del chatbot, la salida de cada paso final (para depurar capturas)."""
import json
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")
KEY = next(l.split("=", 1)[1].strip() for l in open(r"C:\mcp-n8n\.env", encoding="utf-8") if l.startswith("N8N_API_KEY="))
H = {"X-N8N-API-KEY": KEY}
API = "http://localhost:5678/api/v1"
ex = requests.get(f"{API}/executions", params={"workflowId": "uGhzLlnotxpTwlfy", "limit": 1}, headers=H).json()["data"][0]
rd = requests.get(f"{API}/executions/{ex['id']}", params={"includeData": "true"}, headers=H).json()["data"]["resultData"]["runData"]
for paso in ["Preparar respuesta", "Capturas de páginas citadas", "Respuesta final"]:
    items = rd.get(paso, [{}])[0].get("data", {}).get("main", [[]])[0]
    print(f"\n=== {paso} ({len(items)} items)")
    for it in items[:4]:
        print(json.dumps(it.get("json"), ensure_ascii=False)[:500])
