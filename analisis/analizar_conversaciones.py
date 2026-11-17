"""Analiza las conversaciones reales del portal: volumen, temas y tipo de respuesta del asistente."""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from leer_manuales import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
SIN_INFO = re.compile(r"no (se encuentra|contienen|cuento|está disponible|incluye|detallan|dispongo|encuentro)|lamentablemente|lamento informar|ningún fragmento|ninguno de los", re.I)
con = conectar()

print("=== Volumen por usuario")
for u, conv, msgs, ultimo in con.execute("""
    SELECT u.usuario, count(DISTINCT c.id), count(m.id), max(m.creado)::date
    FROM usuarios u LEFT JOIN conversaciones c ON c.usuario_id = u.id LEFT JOIN mensajes m ON m.conversacion_id = c.id
    GROUP BY u.usuario ORDER BY 3 DESC"""):
    print(f"  {u:<16} chats={conv:<3} mensajes={msgs:<4} último={ultimo}")

filas = con.execute("""SELECT c.id, c.titulo, m.rol, m.texto FROM mensajes m JOIN conversaciones c ON c.id = m.conversacion_id
                       ORDER BY c.creado, m.id""").fetchall()
tipos = collections.Counter()
ejemplos = collections.defaultdict(list)
anterior = None
for cid, titulo, rol, texto in filas:
    if rol == "usuario":
        anterior = texto
        continue
    if "no pude responder" in texto:
        t = "error (no pudo responder)"
    elif "navasoft-pagina?id=" in texto:
        t = "con pasos del manual"
    elif SIN_INFO.search(texto):
        t = "sin información → soporte"
    elif texto.strip().endswith("?"):
        t = "pide aclaración / saludo"
    else:
        t = "otro"
    tipos[t] += 1
    ejemplos[t].append(anterior)
total = sum(tipos.values())
print(f"\n=== Tipo de respuesta ({total} respuestas del asistente)")
for t, n in tipos.most_common():
    print(f"  {t:<28} {n:>3}  ({n / total:.0%})")

print("\n=== Consultas sin información (lo que los manuales no cubren)")
for q in ejemplos["sin información → soporte"]:
    print("  -", (q or "")[:110])
print("\n=== Consultas con error")
for q in ejemplos["error (no pudo responder)"]:
    print("  -", (q or "")[:110])

print("\n=== Títulos de conversación (temas)")
for (t,) in con.execute("SELECT titulo FROM conversaciones ORDER BY creado"):
    print("  -", t)

largo = con.execute("SELECT avg(n)::numeric(4,1), max(n) FROM (SELECT count(*) n FROM mensajes GROUP BY conversacion_id) x").fetchone()
print(f"\nMensajes por conversación: promedio {largo[0]}, máximo {largo[1]}")
