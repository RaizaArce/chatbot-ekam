"""Crea un fragmento propio para cada captura descrita (tabla capturas_descripcion), ademas de la descripcion
que ya va dentro del fragmento de su pagina. Asi una pregunta sobre un campo, casilla o boton que solo se ve
en una pantalla ("¿donde marco que el cliente es agente retenedor?") encuentra esa pantalla directamente, en
vez de quedar escondida dentro de un fragmento largo sobre otro tema.

Los fragmentos llevan metadata tipo = "captura" y la misma pagina, seccion e imagen que su fragmento original.
Se pueden regenerar cuando se quiera (primero borra los anteriores).
Uso:  .venv\\Scripts\\python.exe fragmentos_capturas.py [--solo "caja y bancos"]
"""
import argparse
import json
import sys

from leer_manuales import MODELOS, URL_PUBLICA, conectar, id_corto, vectorizar

sys.stdout.reconfigure(encoding="utf-8")


def main(solo=None):
    con = conectar()
    tabla = next(iter(MODELOS.values()))[0]
    filtro = "AND metadata->>'archivo' ILIKE %s" if solo else ""
    params = (f"%{solo}%",) if solo else ()
    for t, _ in MODELOS.values():
        con.execute(f"DELETE FROM {t} WHERE metadata->>'tipo' = 'captura' {filtro}", params)
    import limpiar_manuales
    descs = dict(con.execute("SELECT imagen_id, descripcion FROM capturas_descripcion WHERE descripcion IS NOT NULL").fetchall())
    # descripciones hechas sobre las capturas sin tapar: las que nombran datos reales no se usan
    descs = {k: v for k, v in descs.items() if not limpiar_manuales.tiene_datos_reales(v)}
    nuevos, vistos = [], set()
    for md, in con.execute(f"""SELECT metadata FROM {tabla}
            WHERE coalesce(metadata->>'tipo', '') <> 'captura' AND jsonb_array_length(coalesce(metadata->'imagenes', '[]'::jsonb)) > 0 {filtro}
            ORDER BY metadata->>'archivo', (metadata->>'pagina')::int NULLS LAST""", params):
        for ruta in md.get("imagenes", []):
            iid = id_corto(ruta)
            if iid not in descs or iid in vistos:
                continue
            vistos.add(iid)
            ubic = f"Página: {md['pagina']}" if md.get("pagina") else "Sección"
            texto = (f"Manual: {md['manual']} | {ubic}" + (f" | Sección: {md['seccion']}" if md.get("seccion") else "")
                     + f"\n[Descripción de la captura: {descs[iid]}]")
            meta = {k: md.get(k) for k in ("manual", "archivo", "pagina", "seccion", "pagina_url")}
            meta.update({"tipo": "captura", "imagenes": [ruta], "imagenes_url": [f"{URL_PUBLICA}/navasoft-img?id={iid}"]})
            nuevos.append((texto, meta))
    for modelo, (t, _) in MODELOS.items():
        for i in range(0, len(nuevos), 16):
            lote = nuevos[i:i + 16]
            vecs = vectorizar(modelo, [x[0] for x in lote])
            with con.cursor() as cur:
                cur.executemany(f"INSERT INTO {t} (text, metadata, embedding) VALUES (%s, %s, %s::vector)",
                                [(x[0], json.dumps(x[1], ensure_ascii=False), str(v)) for x, v in zip(lote, vecs)])
    con.execute("TRUNCATE respuestas_cache")
    print(f"Fragmentos de capturas creados: {len(nuevos)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo")
    main(ap.parse_args().solo)
