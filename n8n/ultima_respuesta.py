"""Muestra el texto exacto de la ultima respuesta del chatbot (desde el registro de ejecuciones de n8n)."""
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")
KEY = next(l.split("=", 1)[1].strip() for l in open(r"C:\mcp-n8n\.env", encoding="utf-8") if l.startswith("N8N_API_KEY="))
H = {"X-N8N-API-KEY": KEY}
API = "http://localhost:5678/api/v1"

ex = requests.get(f"{API}/executions", params={"workflowId": "uGhzLlnotxpTwlfy", "limit": 1}, headers=H).json()["data"][0]
d = requests.get(f"{API}/executions/{ex['id']}", params={"includeData": "true"}, headers=H).json()
salida = d["data"]["resultData"]["runData"]["Asistente NAVASOFT"][0]["data"]["main"][0][0]["json"]["output"]
print(salida)
print("\n--- contiene imágenes Markdown:", "![" in salida)
