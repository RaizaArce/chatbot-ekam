"""Verifica que los textos con tilde de la funcion del portal esten bien guardados
y corrige titulos que hayan quedado con acentos rotos (por ejemplo 'conversaciÃ³n')."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from leer_manuales import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
con = conectar()
error = con.execute("SELECT navasoft_api('yo', '{\"token\":\"x\"}')->>'error'").fetchone()[0]
print("Mensaje de la función:", error, "->", "OK" if error == "Tu sesión expiró. Vuelve a iniciar sesión." else "MAL")
rotos = con.execute("SELECT id, titulo FROM conversaciones WHERE titulo LIKE %s", ("%Ã%",)).fetchall()
for cid, titulo in rotos:
    bien = titulo.encode("latin-1").decode("utf-8")
    con.execute("UPDATE conversaciones SET titulo = %s WHERE id = %s", (bien, cid))
    print(f"Título corregido: {titulo!r} -> {bien!r}")
print("Títulos con acentos rotos corregidos:", len(rotos))
