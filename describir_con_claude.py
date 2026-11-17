"""Apoyo para que Claude describa las capturas mirandolas directamente (mas exacto que gemma3 local).

  pendientes N [--orden "caja chica,ventas"]   lista las siguientes N capturas por describir (ya sin las decorativas)
  guardar archivo.json                         guarda las descripciones escritas por Claude:
                                               { "imagen_id": "descripcion" | null }   (null = no es una pantalla)
Al guardar, la descripcion se agrega al fragmento del manual de esa captura y se vuelve a vectorizar,
igual que describir_capturas.py (mismas tablas y mismo formato)."""
import json
import pathlib
import sys

import describir_capturas as D
from leer_manuales import IMAGENES, MODELOS, conectar, id_corto

sys.stdout.reconfigure(encoding="utf-8")
MODELO = "claude"


def pendientes(con, n, orden):
    D.preparar(con)
    tabla = next(iter(MODELOS.values()))[0]
    lista, vistas = [], set()
    for archivo, rutas, pagina, texto in con.execute(f"""SELECT metadata->>'archivo', metadata->'imagenes', metadata->>'pagina', text FROM {tabla}
            WHERE jsonb_array_length(coalesce(metadata->'imagenes', '[]'::jsonb)) > 0
            ORDER BY metadata->>'archivo', (metadata->>'pagina')::int NULLS LAST"""):
        for ruta in rutas:
            iid = id_corto(ruta)
            if iid not in vistas:
                vistas.add(iid); lista.append((iid, archivo, ruta, pagina, D.MARCA.sub("", texto)))
    hechas = {r[0] for r in con.execute("SELECT imagen_id FROM capturas_descripcion")}
    faltan = [p for p in lista if p[0] not in hechas]
    prioridad = [x.strip().lower() for x in orden.split(",") if x.strip()]
    faltan.sort(key=lambda p: next((i for i, x in enumerate(prioridad) if x in p[1].lower()), len(prioridad)))
    salida = []
    for iid, archivo, ruta, pagina, texto in faltan:
        if len(salida) >= n:
            break
        fila = con.execute("SELECT data FROM imagenes WHERE id = %s", (iid,)).fetchone()
        if not fila:
            continue
        if D.es_decorativa(fila[0]):   # logos y franjas: se descartan sin mirarlas
            con.execute("INSERT INTO capturas_descripcion (imagen_id, archivo, ruta, descripcion, modelo, estado) VALUES (%s,%s,%s,NULL,%s,%s) "
                        "ON CONFLICT (imagen_id) DO NOTHING", (iid, archivo, ruta, MODELO, "descartada: imagen decorativa"))
            continue
        salida.append({"id": iid, "archivo": archivo, "pagina": pagina, "imagen": str(IMAGENES / ruta),
                       "texto_pagina": " ".join(texto.split())[:500]})
    print(f"Por describir: {len(faltan)} (antes de quitar decorativas)")
    print(json.dumps(salida, ensure_ascii=False, indent=1))


def guardar(con, ruta_json):
    datos = json.loads(pathlib.Path(ruta_json).read_text(encoding="utf-8"))
    rutas = dict(con.execute("SELECT id, NULL FROM imagenes WHERE false").fetchall())  # noqa: F841 (solo valida conexion)
    tabla = next(iter(MODELOS.values()))[0]
    # archivo y ruta de cada imagen, para la tabla de descripciones
    info = {}
    for archivo, lista in con.execute(f"SELECT metadata->>'archivo', metadata->'imagenes' FROM {tabla} WHERE metadata ? 'imagenes'"):
        for r in lista or []:
            info.setdefault(id_corto(r), (archivo, r))
    aceptadas = []
    for clave, desc in datos.items():
        # la clave puede ser el id de la imagen o su ruta ("manual-de-ventas-v5/p021_1.png")
        iid = id_corto(clave.replace("\\", "/")) if "/" in clave or "\\" in clave else clave
        archivo, ruta = info.get(iid, (None, None))
        if desc:
            desc = " ".join(str(desc).split()).replace("{", "(").replace("}", ")").replace("[", "(").replace("]", ")")
            estado = "aceptada: descrita por Claude mirando la imagen"
            aceptadas.append(iid)
        else:
            estado = "descartada: Claude indica que no es una pantalla del sistema"
        con.execute("INSERT INTO capturas_descripcion (imagen_id, archivo, ruta, descripcion, modelo, estado) VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (imagen_id) DO UPDATE SET descripcion = EXCLUDED.descripcion, modelo = EXCLUDED.modelo, "
                    "estado = EXCLUDED.estado, fecha = now()", (iid, archivo, ruta, desc or None, MODELO, estado))
    frag = D.actualizar_fragmentos(con, aceptadas) if aceptadas else 0
    con.execute("TRUNCATE respuestas_cache")
    total = con.execute("SELECT count(*) FILTER (WHERE descripcion IS NOT NULL), count(*) FROM capturas_descripcion").fetchone()
    print(f"Guardadas: {len(aceptadas)} descripciones, {len(datos) - len(aceptadas)} descartadas, {frag} fragmentos actualizados. "
          f"Total con descripción: {total[0]} (revisadas {total[1]}).")


if __name__ == "__main__":
    c = conectar()
    if sys.argv[1] == "pendientes":
        orden = sys.argv[sys.argv.index("--orden") + 1] if "--orden" in sys.argv else ""
        pendientes(c, int(sys.argv[2]), orden)
    elif sys.argv[1] == "guardar":
        guardar(c, sys.argv[2])
