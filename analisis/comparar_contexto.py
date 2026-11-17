"""Compara, sin la IA, si la pagina del tema llega en lo que se le pasa al asistente (todas las filas de la busqueda),
con la busqueda publicada y con la variante "segunda principal = la mas parecida por significado".
Uso: .venv\Scripts\python.exe analisis\comparar_contexto.py"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "n8n"))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from evaluar_busqueda import con, vec, elegir_temas  # noqa: E402
from publicar_chatbot import BUSCAR_SQL  # noqa: E402

ANTES_P = """), principales AS (
  SELECT metadata->>'archivo' AS archivo, (metadata->>'pagina')::int AS pagina, metadata->>'seccion' AS seccion,
         row_number() OVER (ORDER BY puntaje DESC) AS rn
  -- con el mismo minimo de parecido que usa "Armar consulta": una palabra suelta ("capital") no arma un procedimiento
  FROM parecidos WHERE metadata->>'pagina' IS NOT NULL AND sim >= 0.45 ORDER BY puntaje DESC LIMIT 2
)"""
NUEVA_P = """), mas_parecido AS (
  -- el fragmento mas parecido por significado (aunque las palabras lo dejen fuera de los 6)
  SELECT metadata, 1 - dist AS sim FROM base ORDER BY dist LIMIT 1
), principales AS (
  SELECT * FROM (SELECT metadata->>'archivo' AS archivo, (metadata->>'pagina')::int AS pagina, metadata->>'seccion' AS seccion, 1 AS rn
    -- con el mismo minimo de parecido que usa "Armar consulta": una palabra suelta ("capital") no arma un procedimiento
    FROM parecidos WHERE metadata->>'pagina' IS NOT NULL AND sim >= 0.45 ORDER BY puntaje DESC LIMIT 1) p1
  UNION ALL
  -- la segunda: la mas parecida por significado, si es otra pagina; se le pasan esa pagina y la siguiente
  SELECT metadata->>'archivo', (metadata->>'pagina')::int, metadata->>'seccion', 2 FROM mas_parecido
  WHERE metadata->>'pagina' IS NOT NULL AND sim >= 0.45
)"""
ANTES_V = "AND (c.metadata->>'pagina')::int = x.pagina + 1\n), citadas"
NUEVA_V = "AND (c.metadata->>'pagina')::int BETWEEN x.pagina AND x.pagina + 1\n), citadas"
assert ANTES_P in BUSCAR_SQL and ANTES_V in BUSCAR_SQL and "base AS (" in BUSCAR_SQL
VARIANTE = BUSCAR_SQL.replace(ANTES_P, NUEVA_P).replace(ANTES_V, NUEVA_V)

def prep(s):
    return s.replace("%", "%%").replace("$1", "%(v)s").replace("$2", "''").replace("$3", "%(q)s")

if __name__ == "__main__":
    temas = elegir_temas(con, 120)
    res = {}
    for nombre, sql in {"publicada": prep(BUSCAR_SQL), "variante": prep(VARIANTE)}.items():
        res[nombre] = []
        for t in temas:
            filas = con.execute(sql, {"v": vec(t["pregunta"]), "q": t["pregunta"]}).fetchall()
            ok = [f for f in filas if f[1].get("archivo") == t["archivo"] and f[4] is not None and t["pagina"] - 1 <= f[4] <= t["pagina"] + 4]
            res[nombre].append((bool(ok), len(filas)))
        print(f"{nombre:<10} la pagina del tema llega al asistente: {sum(x for x, _ in res[nombre])}/120   fragmentos promedio: {sum(n for _, n in res[nombre]) / 120:.1f}")
    for t, (a, _), (b, _) in zip(temas, res["publicada"], res["variante"]):
        if a != b:
            print("  ", "gana  " if b else "pierde", t["pregunta"][:80])
    q = "¿Cuál es la capital de Francia?"
    print("Capital de Francia, fragmentos:", len(con.execute(prep(VARIANTE), {"v": vec(q), "q": q}).fetchall()))
