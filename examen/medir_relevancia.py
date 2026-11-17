"""Mide el parecido (similitud) de los fragmentos encontrados para consultas bien y mal respondidas,
para decidir un umbral minimo de relevancia."""
import sys

import requests

sys.path.insert(0, r"C:\chatbot-navasoft")
from leer_manuales import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
CASOS = {
    "BIEN": ["Orientacion como registrar inventario inicial de 02 insumos (maiz y soya)",
             "que se le libere una boleeta mal registrada", "¿Cómo abro una nueva caja chica?",
             "no podia emitir cotizaciones", "presentaba problemas con el detalle de detraccion",
             "le figura un mensaje importe depositado no es valido", "¿Cómo emito una guía de remisión de transportista?"],
    "MAL": ["tenia que hacer unas notas de credito a una boetas que hbaia anulado por que en sunt estban emitidas",
            "preguntaba sobre una cotización que se le envio / se solicito capacitacion en modulo de empleados",
            "Al intentar modificar el asiento de apertura que se genero automartico sale mensaje de error FOREN KEY CUENTA",
            "quiere cancelar por asienrto d ediario una boleta de venta que fue por comision",
            "Queria hacer una guia por devolución pero le referenciaba a una factura diferida",
            "No le cuadra el sistema con respecto al SIRE",
            "no salian los valores correctos en el monto total de detraciones puesto que salio con decimal"],
}
con = conectar()
for grupo, consultas in CASOS.items():
    print(f"\n=== {grupo}")
    for q in consultas:
        v = requests.post("http://127.0.0.1:11434/api/embed", json={"model": "bge-m3", "input": q}).json()["embeddings"][0]
        sims = [round(float(r[0]), 3) for r in con.execute(
            "SELECT 1 - (embedding <=> %s::vector) FROM chunks_bge_m3 ORDER BY embedding <=> %s::vector LIMIT 3",
            (str(v), str(v))).fetchall()]
        print(f"  {sims}  {q[:70]}")
