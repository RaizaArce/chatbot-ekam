"""Guarda en la base las formas en que un cliente pide cada tema (alias_secciones.json), como fragmentos tipo
"alias" pegados a la pagina del manual donde empieza ese tema. La busqueda los usa para encontrar la pagina
aunque el cliente no use los nombres del manual ("crear un producto" -> Mantenimiento al padron de items);
a la IA nunca le llegan: recibe las paginas reales del manual.
Se corre solo al final de leer_manuales.py --sincronizar (cargar un manual borra sus alias).
    .venv\\Scripts\\python.exe alias_secciones.py"""
import json
import pathlib
import re
import sys
import unicodedata

from leer_manuales import MODELOS, conectar, vectorizar

sys.stdout.reconfigure(encoding="utf-8")
ARCHIVO = pathlib.Path(__file__).parent / "alias_secciones.json"


def normal(texto):
    """'2. Notas de ingreso > 2.2 Nuevo' -> 'notas de ingreso > nuevo' (sin numeros, tildes ni mayusculas)."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    partes = [re.sub(r"^[\d.\s]+", "", p).strip(" .") for p in t.split(">")]
    return " > ".join(re.sub(r"\s+", " ", p) for p in partes)


def normal_numeros(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip(" .")


def main():
    datos = {k: v for k, v in json.loads(ARCHIVO.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    con = conectar()
    tabla = next(iter(MODELOS.values()))[0]
    nuevos, faltan = [], []
    for archivo, temas in datos.items():
        # secciones del manual, en orden de pagina: [(nombre sin numeros, metadata del primer fragmento de la seccion)]
        secciones = []
        for md0, in con.execute(f"""SELECT DISTINCT ON (metadata->>'seccion') metadata FROM {tabla}
                WHERE metadata->>'archivo' = %s AND coalesce(metadata->>'tipo', '') NOT IN ('captura', 'alias')
                  AND metadata->>'pagina' IS NOT NULL
                ORDER BY metadata->>'seccion', (metadata->>'pagina')::int, id""", (archivo,)):
            secciones.append((normal(md0.get("seccion") or ""), md0))
        for seccion, tema, frases in temas:
            # la seccion cuyo nombre termina igual ("notas de ingreso > nuevo"); si hay varias, la de pagina mas baja
            buscada = normal(seccion)
            # con numero ("6.2 Crear") se compara con el nombre tal cual: sirve cuando el nombre se repite en el manual
            con_numero = seccion[:1].isdigit()
            coincide = lambda s, md0: (normal_numeros(md0.get("seccion") or "").endswith(normal_numeros(seccion)) if con_numero
                                       else s == buscada or s.endswith("> " + buscada))
            hallada = sorted((md0 for s, md0 in secciones if coincide(s, md0)),
                             key=lambda m: int(m["pagina"]))
            if not hallada:
                faltan.append(f"{archivo.split(chr(92))[-1]}: {seccion}")
                continue
            # se copia la metadata del fragmento real (seccion, pagina, enlace), asi la busqueda arma el procedimiento
            md = {k: hallada[0].get(k) for k in ("manual", "archivo", "pagina", "seccion", "pagina_url")}
            md.update({"tipo": "alias", "tema": tema, "imagenes": [], "imagenes_url": []})
            for f in frases:
                nuevos.append((f"{f} ({tema})", md))
    for modelo, (t, _) in MODELOS.items():
        con.execute(f"DELETE FROM {t} WHERE metadata->>'tipo' = 'alias'")
        for i in range(0, len(nuevos), 32):
            lote = nuevos[i:i + 32]
            vecs = vectorizar(modelo, [x[0] for x in lote])
            with con.cursor() as cur:
                cur.executemany(f"INSERT INTO {t} (text, metadata, embedding) VALUES (%s, %s, %s::vector)",
                                [(x[0], json.dumps(x[1], ensure_ascii=False), str(v)) for x, v in zip(lote, vecs)])
    con.execute("TRUNCATE respuestas_cache")
    print(f"Alias cargados: {len(nuevos)}" + (f" | sin pagina en la base: {faltan}" if faltan else ""))


if __name__ == "__main__":
    main()
