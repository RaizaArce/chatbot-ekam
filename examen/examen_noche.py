"""Examen automatico del asistente con preguntas sacadas del indice de los manuales (tabla manual_indice).

Para cada tema arma una pregunta como la haria un cliente, se la hace al asistente y revisa si cito el
manual correcto y una pagina cercana a la del tema. Va despacio (una pregunta cada --espera segundos)
para no gastar los limites gratuitos de Gemini y Groq. Guarda un Excel con el resumen y el detalle.

Uso:  .venv\\Scripts\\python.exe examen\\examen_noche.py --max 120 --espera 40
"""
import argparse
import datetime
import itertools
import os
import pathlib
import re
import sys
import time
import uuid

import openpyxl
import requests
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from leer_manuales import conectar, id_corto  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).parent.parent
ENV = dict(l.split("=", 1) for l in (BASE / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
ASISTENTE = os.getenv("NAVASOFT_URL", "http://localhost:5678").rstrip("/") + "/webhook/navasoft-asistente"
CABECERA = {"X-Navasoft-Clave": ENV["ASISTENTE_CLAVE"].strip()}
SIN_INFO = re.compile(r"no (se encuentra|contienen|cuento|está disponible|incluye|detallan|dispongo|encuentro)|lamentablemente|lamento|hablar con soporte", re.I)
SALTAR = re.compile(r"^(introducci[oó]n|consideraciones|objetivo|alcance|índice|indice)", re.I)


def modulo(manual):
    """'Manual de caja chica V5' -> 'caja chica'."""
    return re.sub(r"(?i)^manual de |\s*v\d+$|^guia |^procedimiento ", "", manual).strip().lower()


def pregunta(titulo, padre, manual):
    t, p = titulo.strip().rstrip("."), (padre or "").strip()
    tl = t.lower()
    if p:
        if tl.startswith("crear") or tl.startswith("nuevo"):
            return f"En {p} de NAVASOFT, ¿cómo creo uno nuevo?"
        if tl.startswith("modificar"):
            return f"En {p} de NAVASOFT, ¿cómo modifico un registro?"
        if tl.startswith("anular"):
            return f"En {p} de NAVASOFT, ¿cómo anulo un registro?"
        if tl.startswith("descripci"):
            return f"¿Qué opciones tiene la pantalla de {p} en NAVASOFT?"
        if tl.startswith("impresi"):
            return f"¿Cómo imprimo el formato de {p}?"
    return f"¿Cómo funciona {tl} en el módulo de {modulo(manual)} de NAVASOFT?"


def elegir_temas(con, maximo):
    filas = con.execute("SELECT manual, archivo, orden, numero, titulo, pagina FROM manual_indice ORDER BY manual, orden").fetchall()
    por_manual, padres = {}, {}
    for manual, archivo, orden, numero, titulo, pagina in filas:
        if not numero:
            # guia corta sin temas numerados: una sola pregunta general sobre la guia, en su primera pagina
            if manual not in por_manual:
                por_manual[manual] = [{"manual": manual, "archivo": archivo, "numero": "", "titulo": "(guía completa)", "pagina": 1,
                                       "pregunta": f"¿Cómo hago {modulo(manual)} en NAVASOFT?"}]
            continue
        if "." not in numero:
            padres[(archivo, numero)] = titulo
        if SALTAR.match(titulo or "") or modulo(manual) in titulo.lower() or len(titulo) < 5:
            continue
        padre = padres.get((archivo, numero.split(".")[0])) if numero and "." in numero else None
        por_manual.setdefault(manual, []).append(
            {"manual": manual, "archivo": archivo, "numero": numero, "titulo": titulo, "pagina": pagina,
             "pregunta": pregunta(titulo, padre, manual)})
    # se reparte entre todos los manuales (uno de cada uno por vuelta), sin repetir preguntas
    elegidos, vistas = [], set()
    for grupo in itertools.zip_longest(*por_manual.values()):
        for t in grupo:
            if t and t["pregunta"] not in vistas and len(elegidos) < maximo:
                vistas.add(t["pregunta"]); elegidos.append(t)
    return elegidos


def calificar(tema, respuesta):
    citadas = set(re.findall(r"navasoft-pagina\?id=([0-9a-f]{12})", respuesta))
    cerca = {id_corto(f"{tema['archivo']}#{p}") for p in range(max(1, tema["pagina"] - 1), tema["pagina"] + 5)}
    mismo = {id_corto(f"{tema['archivo']}#{p}") for p in range(1, 400)}
    if citadas & cerca:
        return "✅ página correcta"
    if citadas & mismo:
        return "🟡 manual correcto, otra página"
    if citadas:
        return "❌ citó otro manual"
    if SIN_INFO.search(respuesta):
        return "⚪ dijo que no tiene la información"
    return "⚪ respondió sin citar fuente"


def guardar_excel(resultados, ruta, inicio):
    wb = openpyxl.Workbook()
    hoja = wb.active; hoja.title = "Resumen"
    total = len(resultados)
    cuenta = {}
    for r in resultados:
        cuenta[r["resultado"]] = cuenta.get(r["resultado"], 0) + 1
    hoja.append(["Examen automático del Asistente NAVASOFT (EKAM PERÚ)"]); hoja["A1"].font = Font(bold=True, size=14)
    hoja.append([f"Fecha: {inicio:%d/%m/%Y %H:%M}   ·   Preguntas: {total}"])
    hoja.append([])
    hoja.append(["Resultado", "Cantidad", "%"])
    for c in hoja[4]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="001858")
    for k in ["✅ página correcta", "🟡 manual correcto, otra página", "❌ citó otro manual",
              "⚪ dijo que no tiene la información", "⚪ respondió sin citar fuente", "⚠️ error"]:
        n = cuenta.get(k, 0)
        hoja.append([k, n, f"{(n / total * 100 if total else 0):.0f}%"])
    tiempos = [r["segundos"] for r in resultados if r["segundos"]]
    hoja.append([])
    hoja.append(["Tiempo promedio de respuesta", f"{(sum(tiempos) / len(tiempos) if tiempos else 0):.1f} s"])
    hoja.append(["Manual correcto (página exacta o cercana + otra página)",
                 f"{((cuenta.get('✅ página correcta', 0) + cuenta.get('🟡 manual correcto, otra página', 0)) / total * 100 if total else 0):.0f}%"])
    hoja.append([])
    hoja.append(["Por manual", "Preguntas", "Página correcta", "%"])
    for c in hoja[hoja.max_row]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="001858")
    manuales = {}
    for r in resultados:
        m = manuales.setdefault(r["manual"], [0, 0]); m[0] += 1; m[1] += r["resultado"].startswith("✅")
    for m, (n, ok) in sorted(manuales.items(), key=lambda x: x[1][1] / x[1][0]):
        hoja.append([m, n, ok, f"{ok / n * 100:.0f}%"])
    hoja.column_dimensions["A"].width = 58; hoja.column_dimensions["B"].width = 14; hoja.column_dimensions["C"].width = 16

    det = wb.create_sheet("Detalle")
    det.append(["#", "Manual", "Tema (índice)", "Pág. del tema", "Pregunta hecha", "Resultado", "Segundos", "Pasos", "Capturas", "Respuesta del asistente"])
    for c in det[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="001858")
    for i, r in enumerate(resultados, 1):
        limpia = re.sub(r"\(http[^)]+\)", "", r["respuesta"]).replace("[[", "[")
        det.append([i, r["manual"], f"{r['numero']} {r['titulo']}".strip(), r["pagina"], r["pregunta"], r["resultado"],
                    round(r["segundos"] or 0, 1), r["pasos"], r["capturas"], limpia[:3000]])
    for col, ancho in zip("ABCDEFGHIJ", [5, 30, 36, 8, 48, 30, 9, 7, 9, 90]):
        det.column_dimensions[col].width = ancho
    for fila in det.iter_rows(min_row=2):
        for c in fila:
            c.alignment = Alignment(vertical="top", wrap_text=c.column_letter in "CEJ")
    det.freeze_panes = "A2"; det.auto_filter.ref = det.dimensions
    wb.save(ruta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=120)
    ap.add_argument("--espera", type=float, default=40, help="segundos entre preguntas")
    ap.add_argument("--minutos", type=float, default=0, help="detenerse despues de estos minutos (0 = sin limite)")
    args = ap.parse_args()
    inicio = datetime.datetime.now()
    limite = time.time() + args.minutos * 60 if args.minutos else None
    temas = elegir_temas(conectar(), args.max)
    carpeta = BASE / "examen" / "resultados"; carpeta.mkdir(exist_ok=True)
    ruta = carpeta / f"examen_noche_{inicio:%Y%m%d_%H%M}.xlsx"
    print(f"Examen: {len(temas)} preguntas, una cada {args.espera:.0f} s. Reporte: {ruta}", flush=True)
    resultados = []
    for i, t in enumerate(temas, 1):
        if limite and time.time() > limite:
            print("Tiempo del examen terminado.", flush=True); break
        t0 = time.time()
        try:
            # cada pregunta en una conversacion nueva y con marca unica para no usar respuestas guardadas
            r = requests.post(ASISTENTE, headers=CABECERA, timeout=180,
                              json={"sessionId": str(uuid.uuid4()), "chatInput": f"{t['pregunta']} (examen {uuid.uuid4().hex[:5]})"})
            respuesta = r.json().get("output", "") if r.ok else ""
            resultado = calificar(t, respuesta) if respuesta else "⚠️ error"
        except Exception as e:  # noqa: BLE001 - se anota y se sigue con la siguiente
            respuesta, resultado = f"ERROR: {e}", "⚠️ error"
        seg = time.time() - t0
        resultados.append({**t, "respuesta": respuesta, "resultado": resultado, "segundos": seg,
                           "pasos": len(re.findall(r"(?m)^\s*\d+[.)]\s", respuesta)), "capturas": respuesta.count("![")})
        print(f"  [{i}/{len(temas)}] {resultado:<36} {seg:4.1f}s  {t['pregunta'][:80]}", flush=True)
        if i % 10 == 0:
            guardar_excel(resultados, ruta, inicio)   # se guarda de a poco por si se apaga la laptop
        time.sleep(max(0, args.espera - seg))
    guardar_excel(resultados, ruta, inicio)
    ok = sum(r["resultado"].startswith("✅") for r in resultados)
    print(f"Examen terminado: {ok}/{len(resultados)} con página correcta. Reporte: {ruta}", flush=True)


if __name__ == "__main__":
    main()
