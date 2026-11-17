"""Examen del chatbot con las consultas reales del registro de soporte.
Solo se envia el texto de la consulta (sin nombre, telefono ni empresa del cliente).
Guarda cada respuesta en examen/resultados.json para revisarlas."""
import json
import pathlib
import re
import sys
import time
import uuid

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
AQUI = pathlib.Path(__file__).parent
EXCEL = r"C:\PRÁCTICAS EKAM\Manuales NAVASOFT\Registro_Soporte_EKAM_Peru.xlsx"
# el asistente solo responde con la clave interna (la misma que usa el portal)
CHAT = "http://localhost:5678/webhook/navasoft-asistente"
CLAVE = next(l.split("=", 1)[1].strip() for l in open(r"C:\chatbot-navasoft\.env", encoding="utf-8") if l.startswith("ASISTENTE_CLAVE="))
CABECERA = {"X-Navasoft-Clave": CLAVE}
PAUSA = 6  # segundos entre preguntas, para no pasar el limite gratuito por minuto

df = pd.read_excel(EXCEL, sheet_name="Registro de Soporte")
df = df[df["Consulta / Incidencia"].notna()].reset_index(drop=True)

salida = AQUI / "resultados.json"
resultados = json.loads(salida.read_text(encoding="utf-8")) if salida.exists() else []
hechos = {r["fila"] for r in resultados if "fila" in r}

for i, fila in df.iterrows():
    n = int(fila["N.º"])
    if i in hechos:  # se usa la fila del Excel: el N.º de caso se repite en algunos registros
        continue
    consulta = str(fila["Consulta / Incidencia"]).strip()
    t0 = time.time()
    try:
        r = requests.post(CHAT, json={"sessionId": str(uuid.uuid4()), "chatInput": consulta}, headers=CABECERA, timeout=180)
        respuesta = r.json().get("output", r.text) if r.ok else f"ERROR HTTP {r.status_code}"
    except Exception as e:
        respuesta = f"ERROR {e}"
    resultados.append({
        "fila": i,
        "n": n,
        "modulo": str(fila["Módulo"]).strip(),
        "consulta": consulta,
        "solucion_excel": None if pd.isna(fila["Solución / Respuesta"]) else str(fila["Solución / Respuesta"]).strip(),
        "observacion_excel": None if pd.isna(fila["Detalle / Observaciones"]) else str(fila["Detalle / Observaciones"]).strip(),
        "respuesta_bot": respuesta,
        "segundos": round(time.time() - t0, 1),
        "cita_manual": "navasoft-pagina?id=" in respuesta,
        "capturas": len(re.findall(r"!\[", respuesta)),
    })
    salida.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{len(resultados)}/{len(df)}] n={n} {resultados[-1]['segundos']}s cita={resultados[-1]['cita_manual']}", flush=True)
    time.sleep(PAUSA)

print("Examen terminado:", len(resultados), "consultas")
