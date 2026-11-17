"""Compara, sin la IA, que pagina elige el asistente como "procedimiento completo" con cada variante de la busqueda.
Usa las mismas 120 preguntas del examen. Uso: .venv\Scripts\python.exe analisis\comparar_principal.py"""
import pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "n8n"))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from evaluar_busqueda import con, vec, elegir_temas  # noqa: E402
from publicar_chatbot import BUSCAR_SQL  # noqa: E402

base = BUSCAR_SQL.split("), procedimiento AS")[0].replace("%", "%%")
base = base.replace("$1", "%(v)s").replace("$2", "''").replace("$3", "%(q)s")
ACTUAL = re.search(r"principales AS \(.*", base, re.S).group(0)
VARIANTES = {
    "antes (sim, sin piso)": ACTUAL.replace("ORDER BY puntaje DESC) AS rn", "ORDER BY sim DESC) AS rn")
                                     .replace(" AND sim >= 0.45 ORDER BY puntaje DESC", " ORDER BY sim DESC"),
    "actual (puntaje, piso)": ACTUAL,
    "sim + piso": ACTUAL.replace("ORDER BY puntaje DESC) AS rn", "ORDER BY sim DESC) AS rn")
                        .replace("ORDER BY puntaje DESC LIMIT 2", "ORDER BY sim DESC LIMIT 2"),
}
temas = elegir_temas(con, 120)
res = {}
for nombre, princ in VARIANTES.items():
    sql = base.replace(ACTUAL, princ) + ") SELECT archivo, pagina FROM principales ORDER BY rn LIMIT 1"
    res[nombre] = []
    for t in temas:
        f = con.execute(sql, {"v": vec(t["pregunta"]), "q": t["pregunta"]}).fetchone()
        res[nombre].append(bool(f) and f[0] == t["archivo"] and t["pagina"] - 1 <= f[1] <= t["pagina"] + 4)
    print(f"{nombre:<24} procedimiento en la pagina correcta: {sum(res[nombre])}/120")
a, b = list(res.values())[:2]
for t, x, y in zip(temas, a, b):
    if x != y:
        print("  ", "pierde" if x else "gana  ", t["pregunta"][:80])
