"""Carga al chatbot SOLO las preguntas frecuentes que una ingeniera marco como 'Validado = SI'
y cuyo publico es 'Cliente'. Si la ingeniera escribio una respuesta corregida, se usa esa.

Uso:  .venv\\Scripts\\python.exe faq\\cargar_faq.py
(vuelve a ejecutarlo cada vez que se validen o corrijan preguntas: reemplaza la carga anterior)"""
import json
import pathlib
import sys

from openpyxl import load_workbook

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from leer_manuales import MODELOS, conectar, preparar_tablas, vectorizar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
EXCEL = pathlib.Path(__file__).parent / "Borrador_Preguntas_Frecuentes_NAVASOFT.xlsx"
ARCHIVO = "faq\\Preguntas frecuentes validadas"
TITULO = "Preguntas frecuentes de soporte EKAM PERÚ"

ws = load_workbook(EXCEL, data_only=True)["Borrador FAQ"]
cab = [c.value for c in ws[1]]
col = {nombre: i for i, nombre in enumerate(cab)}
trozos, omitidas = [], 0
for fila in ws.iter_rows(min_row=2, values_only=True):
    if not fila[col["Pregunta del cliente"]]:
        continue
    validado = str(fila[col["Validado (SI/NO)"]] or "").strip().upper() == "SI"
    publico = str(fila[col["Público"]] or "").strip().lower() == "cliente"
    if not (validado and publico):
        omitidas += 1
        continue
    respuesta = (fila[col["Respuesta corregida por la ingeniera"]] or fila[col["Respuesta propuesta"]]).strip()
    pregunta = fila[col["Pregunta del cliente"]].strip()
    trozos.append({
        "text": f"Manual: {TITULO} | Sección: {fila[col['Módulo']]}\nPregunta: {pregunta}\nRespuesta validada por soporte: {respuesta}",
        "metadata": {"manual": TITULO, "archivo": ARCHIVO, "pagina": None, "seccion": str(fila[col["Módulo"]]),
                     "imagenes": [], "imagenes_url": [],
                     "validado_por": fila[col["Validado por"]], "fecha_validacion": str(fila[col["Fecha"]] or "")},
    })

con = conectar()
preparar_tablas(con)
for modelo, (tabla, _) in MODELOS.items():
    con.execute(f"DELETE FROM {tabla} WHERE metadata->>'archivo' = %s", (ARCHIVO,))
    if trozos:
        vecs = vectorizar(modelo, [t["text"] for t in trozos])
        with con.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {tabla} (text, metadata, embedding) VALUES (%s, %s, %s::vector)",
                [(t["text"], json.dumps(t["metadata"], ensure_ascii=False), str(v)) for t, v in zip(trozos, vecs)],
            )
print(f"Preguntas cargadas al chatbot: {len(trozos)} | sin validar u omitidas: {omitidas}")
