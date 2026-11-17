"""Lista las ultimas ejecuciones con error del chatbot y muestra el mensaje de error de cada nodo."""
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")
KEY = next(l.split("=", 1)[1].strip() for l in open(r"C:\mcp-n8n\.env", encoding="utf-8") if l.startswith("N8N_API_KEY="))
H = {"X-N8N-API-KEY": KEY}
API = "http://localhost:5678/api/v1"
WF = sys.argv[1] if len(sys.argv) > 1 else "uGhzLlnotxpTwlfy"

exs = requests.get(f"{API}/executions", params={"workflowId": WF, "status": "error", "limit": 5}, headers=H).json()["data"]
for ex in exs:
    d = requests.get(f"{API}/executions/{ex['id']}", params={"includeData": "true"}, headers=H).json()
    rd = d["data"]["resultData"]
    print(f"\n=== ejecución {ex['id']}  {ex['startedAt']}")
    chat = rd["runData"].get("Chat del cliente", [{}])[0].get("data", {}).get("main", [[{}]])[0][0].get("json", {})
    print("  pregunta:", chat.get("chatInput"))
    err = rd.get("error") or {}
    print("  error general:", err.get("message"), "| nodo:", (err.get("node") or {}).get("name"))
    print("  detalle:", str(err.get("description"))[:400])
    for nombre, runs in rd["runData"].items():
        for run in runs:
            if run.get("error"):
                print(f"  - {nombre}: {str(run['error'].get('message'))[:200]}")
