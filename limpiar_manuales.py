"""Crea copias limpias de los manuales en manuales_limpios\\, con los datos reales tapados (RUC, razones sociales,
correos, claves, nombres de clientes...), tanto en el texto como dentro de las capturas. Los originales no se tocan.
El asistente carga SOLO las copias limpias (ver leer_manuales.py).
    .venv\\Scripts\\python.exe limpiar_manuales.py                (todos)
    .venv\\Scripts\\python.exe limpiar_manuales.py --solo caja
    .venv\\Scripts\\python.exe limpiar_manuales.py --comprobar    (vuelve a leer las copias y avisa si quedo algo)

Que se tapa:
  1. Lo que detecta auditar_datos_sensibles.py por su forma (RUC, S.A.C., correos, celulares, claves...).
  2. Las lineas que contienen alguno de los terminos de auditoria\\limpieza.json (nombres de empresas y personas
     que no se reconocen por su forma). Ese archivo esta fuera de git porque lista esos nombres:
       {"terminos": ["..."],                      se tapan en todos los manuales
        "permitir": ["..."],                      lineas que NO se tapan aunque coincidan (datos de ejemplo)
        "por_manual": {"archivo.pdf": {"terminos": ["..."], "zonas": {"3": [[x0, y0, x1, y1]]},
                                       "columnas": {"29": [[x0, y0, x1, y1], [x0, y0, x1, y1, "texto fijo"]]}}}}
     Las zonas van en puntos del PDF, por numero de pagina, para tapar algo que el OCR no lee (logos, firmas).
     Las columnas (tambien en puntos) son columnas de una tabla con nombres que el OCR no lee bien: se reescriben
     fila por fila con nombres ficticios del mismo tamano, y lo detectado dentro de ellas ya no se trata aparte.

Cada dato real se reemplaza por uno FICTICIO escrito con el mismo fondo, color y tamano de letra, para que la
captura se vea como la original: "Usuario: JPEREZ" queda "Usuario: DEMO01", una razon social queda
"EMPRESA DEMO S.A.C.", un RUC queda 20000000001 y una clave queda ********. Lo de abajo se borra (no se dibuja
encima), y si una linea reemplazada todavia trae algo real, se escribe solo el dato ficticio."""
import argparse
import io
import itertools
import json
import os
import pathlib
import re
import shutil
import sys
import unicodedata

import pymupdf
from PIL import Image, ImageDraw, ImageFont

import auditar_datos_sensibles as auditoria

sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).parent
LIMPIOS = auditoria.DATOS / "manuales_limpios"   # en la laptop, junto al codigo; en el servidor, en NAVASOFT_DATOS
REGLAS = auditoria.SALIDA / "limpieza.json"
MARGEN = 1.5  # puntos de mas alrededor de cada linea tapada
# la letra de las pantallas de Windows (NAVASOFT, SUNAT, SQL Server); en el servidor se indica con NAVASOFT_FUENTE
FUENTE = os.getenv("NAVASOFT_FUENTE", r"C:\Windows\Fonts\tahoma.ttf")
FUENTE_RESPALDO = os.getenv("NAVASOFT_FUENTE_RESPALDO", r"C:\Windows\Fonts\arial.ttf")
BORDE_PX = 2  # pixeles de mas alrededor de cada linea reemplazada (se borra el contorno suavizado de las letras)
# dato ficticio por tipo; todos los reconoce auditar_datos_sensibles.PERMITIDOS, asi la comprobacion no los marca
FALSO = {"RUC": "20000000001", "Razon social": "EMPRESA DEMO S.A.C.", "Usuario": "DEMO01", "Contrasena": "********",
         "Cliente": "EMPRESA DEMO S.A.C.", "Proveedor": "PROVEEDOR DEMO S.A.C.", "Correo": "usuario@ejemplo.com",
         "Celular": "900 000 000", "Telefono": "(01) 000-0000", "Direccion": "AV. DEMO 123 - LIMA", "DNI": "00000000",
         "Persona": "Sr. Demo", "Servidor o IP": "\\\\SERVIDOR-DEMO"}
NOMBRE_FALSO = "EMPRESA DEMO"
NOMBRES_TABLA = ["CLIENTE DEMO S.A.C.", "COMERCIAL DEMO E.I.R.L.", "DISTRIBUIDORA DEMO S.A.", "SERVICIOS DEMO S.A.C.",
                 "INVERSIONES DEMO S.R.L.", "TRANSPORTES DEMO S.A.C."]   # para las columnas de tablas   # para los nombres de la lista de terminos (empresas y personas)
# variantes cada vez mas cortas cuando el dato ficticio no cabe en el espacio del original
CORTOS = {"EMPRESA DEMO S.A.C.": ["EMPRESA DEMO SAC", "EMPRESA DEMO", "DEMO S.A.C.", "DEMO"],
          "PROVEEDOR DEMO S.A.C.": ["PROVEEDOR DEMO", "DEMO S.A.C.", "DEMO"], "EMPRESA DEMO": ["DEMO"],
          "AV. DEMO 123 - LIMA": ["AV. DEMO 123", "AV. DEMO"], "usuario@ejemplo.com": ["demo@ejemplo.com"]}


def normalizar(texto):
    """Para comparar nombres aunque el OCR los lea pegados o confunda 0/O y 1/I: solo letras y numeros."""
    t = unicodedata.normalize("NFD", texto.upper())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]", "", t).replace("0", "O").replace("1", "I")


def cargar_reglas():
    reglas = json.loads(REGLAS.read_text(encoding="utf-8")) if REGLAS.exists() else {}
    return {"terminos": reglas.get("terminos", []), "permitir": reglas.get("permitir", []),
            "por_manual": reglas.get("por_manual", {}), "titulos": reglas.get("titulos", {})}


def tiene_datos_reales(texto, reglas=None):
    """True si el texto trae algo que se tapa en los manuales (RUC, razon social, cliente, nombre de la lista...).
    Lo usan la carga y los fragmentos de capturas para descartar descripciones hechas sobre las capturas sin tapar."""
    reglas = reglas or cargar_reglas()
    if any(not auditoria.PERMITIDOS.search(m.group()) for p in auditoria.PATRONES.values() for m in p.finditer(texto)):
        return True
    n = normalizar(texto)
    return any(len(t) >= 4 and t in n for t in map(normalizar, reglas["terminos"]))


def titulo_limpio(titulo, reglas=None):
    """Titulo con que el asistente nombra al manual ante el cliente: sin nombres de clientes ni de personas.
    Usa "titulos" de limpieza.json ({"titulo original": "titulo nuevo"}); si no esta, quita lo que va tras "CASO"."""
    reglas = reglas or cargar_reglas()
    if titulo in reglas.get("titulos", {}):
        return reglas["titulos"][titulo]
    if tiene_datos_reales(titulo, reglas):
        raise SystemExit(f"El titulo '{titulo}' nombra a un cliente: agregarlo a 'titulos' en {REGLAS}.")
    return titulo


def destino(pdf):
    """Donde queda la copia limpia: misma ruta relativa que el original (o convertidos\\ para los Word)."""
    if pdf.is_relative_to(auditoria.MANUALES):
        return LIMPIOS / pdf.relative_to(auditoria.MANUALES)
    return LIMPIOS / "convertidos" / pdf.name


def ficticio(tipo, dato):
    """Dato ficticio para reemplazar 'dato'. Conserva la etiqueta ('Usuario: ', 'DNI ', 'Telef: ')."""
    if tipo == "Servidor o IP" and re.fullmatch(r"[\d.]+", dato):
        return "0.0.0.0"
    falso = FALSO.get(tipo, NOMBRE_FALSO)
    patron = {"DNI": r"(?i)D\.?N\.?I\.?\W{0,6}", "Telefono": r"(?i)tel[eé]f\w*\.?\s*[:=]?\s*"}.get(tipo, r"[^:=]{1,30}[:=]\s*")
    if tipo in ("Usuario", "Contrasena", "Cliente", "Proveedor", "DNI", "Telefono"):
        m = re.match(patron, dato)
        if m:
            return m.group().rstrip(" ") + " " + falso   # "Usuario:" -> "Usuario: DEMO01"
    return falso


def patron_termino(termino):
    """Regex que encuentra un nombre de la lista en el texto del OCR (pegado o con espacios, 0/O, 1/I, tildes)."""
    clases = {"O": "[O0ÓÒ]", "I": "[I1ÍÌ]", "A": "[AÁÀ]", "E": "[EÉÈ]", "U": "[UÚÜ]", "N": "[NÑ]"}
    return re.compile(r"[\W_]*".join(clases.get(c, re.escape(c)) for c in termino), re.I)


def cajas_a_tapar(pdf, paginas, reglas):
    """{numero de pagina: [(caja, texto original, texto nuevo con datos ficticios)]} de todo lo que hay que tapar.
    El texto nuevo es '' en las zonas fijas (solo se borran)."""
    propias = reglas["por_manual"].get(pdf.name, {})
    terminos = [normalizar(t) for t in reglas["terminos"] + propias.get("terminos", [])]
    terminos = [t for t in terminos if len(t) >= 4]
    permitir = [normalizar(t) for t in reglas["permitir"]]
    permitida = lambda linea: any(p and p in normalizar(linea) for p in permitir)
    texto_de = {(n, tuple(l["b"])): " ".join(l["t"].split()) for n, lineas in enumerate(paginas, 1) for l in lineas}
    # Cada linea con datos se reescribe con SOLO su etiqueta ("Usuario: ", "RUC: ") y los datos ficticios, en el
    # orden en que estaban. No se conserva el resto: en las tablas el OCR lee la fila entera como una linea y ahi
    # quedarian pedazos de nombres, direcciones o telefonos que no se reconocen como datos.
    datos = {}   # (pagina, caja) -> [(posicion en la linea, fin, dato ficticio)]
    for pag, tipo, dato, linea, caja in auditoria.hallazgos_de(paginas):
        if permitida(linea):
            continue
        clave = (pag, tuple(caja))
        original = texto_de.get(clave, linea)
        i = original.find(dato)
        datos.setdefault(clave, []).append((i if i >= 0 else 10 ** 6, i + len(dato) if i >= 0 else 10 ** 6,
                                            ficticio(tipo, dato)))
    for pag, ls in enumerate(paginas, 1):
        for l in ls:
            n = normalizar(l["t"])
            encontrados = [t for t in terminos if t in n]
            if not encontrados or permitida(l["t"]):
                continue
            clave = (pag, tuple(l["b"]))
            original = texto_de[clave]
            lista = datos.setdefault(clave, [])
            for t in encontrados:
                m = patron_termino(t).search(original)
                ini, fin = (m.start(), m.end()) if m else (10 ** 6, 10 ** 6)
                if not any(a <= ini < b or ini <= a < fin for a, b, _ in lista):   # no repetir lo de un patron
                    lista.append((ini, fin, NOMBRE_FALSO))
    cajas = {}
    for (pag, caja), lista in datos.items():
        original = texto_de.get((pag, caja), "")
        lista.sort()
        falsos = []
        for _, _, f in lista:
            if not falsos or falsos[-1] != f:
                falsos.append(f)
        # etiqueta antes del primer dato ("RuC:2048..." -> "RUC: "), si es corta y no trae numeros
        etiqueta = original[:lista[0][0]] if lista[0][0] < 10 ** 6 else ""
        etiqueta = etiqueta if re.fullmatch(r"[A-Za-zÁÉÍÓÚÑáéíóúñ .()*]{2,30}[:=]\s*", etiqueta) else ""
        etiqueta = re.sub(r"\bR[uU]C\b", "RUC", re.sub(r"[:=]\s*$", ": ", etiqueta)) if etiqueta else ""
        nuevo = etiqueta + "   ".join(falsos)
        if tiene_datos_reales(nuevo, reglas):   # seguridad: nunca se escribe algo que parezca real
            nuevo = NOMBRE_FALSO
        cajas.setdefault(pag, []).append((list(caja), original, nuevo))
    for pag, zonas in propias.get("zonas", {}).items():
        cajas.setdefault(int(pag), []).extend((z, "", "") for z in zonas)
    return cajas


def fuente(tamano):
    for archivo in (FUENTE, FUENTE_RESPALDO):
        try:
            return ImageFont.truetype(archivo, max(6, int(round(tamano))))
        except OSError:
            continue
    return ImageFont.load_default()


def colores(img, caja):
    """(fondo, letra) de una linea de la captura: el fondo es el color mas comun del borde de alrededor y la letra
    el promedio de los pixeles que mas se alejan del fondo."""
    x0, y0, x1, y1 = caja
    ancho, alto = img.size
    px = img.load()
    borde = []
    for x in range(max(0, x0 - 3), min(ancho, x1 + 3)):
        for y in (y0 - 3, y0 - 2, y1 + 1, y1 + 2):
            if 0 <= y < alto:
                borde.append(px[x, y])
    for y in range(max(0, y0), min(alto, y1)):
        for x in (x0 - 3, x0 - 2, x1 + 1, x1 + 2):
            if 0 <= x < ancho:
                borde.append(px[x, y])
    if not borde:
        return (255, 255, 255), (0, 0, 0)
    grupos = {}
    for c in borde:
        grupos.setdefault(tuple(v // 12 for v in c), []).append(c)
    comun = max(grupos.values(), key=len)
    fondo = tuple(sum(c[i] for c in comun) // len(comun) for i in range(3))
    dentro = [px[x, y] for x in range(max(0, x0), min(ancho, x1)) for y in range(max(0, y0), min(alto, y1))]
    dist = lambda c: sum((c[i] - fondo[i]) ** 2 for i in range(3))
    lejanos = sorted(dentro, key=dist, reverse=True)[:max(1, len(dentro) // 30)]   # el centro de las letras
    if not lejanos or dist(lejanos[0]) < 40 ** 2:
        oscuro = sum(fondo) / 3 > 128
        return fondo, (40, 40, 40) if oscuro else (235, 235, 235)
    letra = tuple(sum(c[i] for c in lejanos) // len(lejanos) for i in range(3))
    return fondo, letra


def escribir(dibujo, caja, texto, color, tope=None, derecha=False):
    """Escribe 'texto' centrado en la caja (a la izquierda, o a la derecha si derecha=True), del alto de la linea."""
    x0, y0, x1, y1 = caja
    alto, ancho = y1 - y0, x1 - x0
    tamano = alto * 0.95 if tope is None else min(alto * 0.95, tope)
    opciones = [texto] + CORTOS.get(texto, [])
    for opcion in opciones:   # primero achica la letra hasta un 75 %; si no cabe, prueba un texto mas corto
        t = tamano
        while t >= tamano * 0.75:
            f = fuente(t)
            if dibujo.textlength(opcion, font=f) <= ancho * 1.1 or opcion == opciones[-1] and t <= tamano * 0.76:
                caja_letra = f.getbbox(opcion)
                izquierda = x1 - caja_letra[2] if derecha else x0 - caja_letra[0]
                dibujo.text((izquierda, (y0 + y1) / 2 - (caja_letra[1] + caja_letra[3]) / 2),
                            opcion, font=f, fill=color)
                return
            t -= 0.5


def tapar_en_capturas(doc, pagina, lista, alto_fila=None):
    """Reemplaza dentro de las imagenes de la pagina (en sus pixeles) las lineas que caen sobre una captura: borra la
    linea con el color del fondo y escribe el texto con datos ficticios. Devuelve lo que NO pudo tratar asi (texto
    del manual, imagenes giradas): eso va por la redaccion normal."""
    imagenes = []
    for info in pagina.get_image_info(xrefs=True):
        a, b, c, d = info["transform"][:4]
        if info["xref"] and a > 0 and d > 0 and abs(b) < 1e-3 and abs(c) < 1e-3:   # solo imagenes derechas
            imagenes.append((pymupdf.Rect(info["bbox"]), info["xref"]))
    por_imagen, resto = {}, []
    for caja, original, nuevo in lista:
        destino = next(((bbox, xref) for bbox, xref in imagenes if bbox.contains(pymupdf.Rect(caja))), None)
        if destino:
            por_imagen.setdefault(destino[1], (destino[0], []))[1].append((pymupdf.Rect(caja), original, nuevo))
        else:
            resto.append((caja, original, nuevo))
    for xref, (bbox, zonas) in por_imagen.items():
        img = Image.open(io.BytesIO(doc.extract_image(xref)["image"])).convert("RGB")
        fx, fy = img.width / bbox.width, img.height / bbox.height
        # la misma linea suele llegar dos veces (dos lecturas del OCR, cajas casi iguales): se unen y se escribe una
        # sola vez, con el texto de la lectura mas larga
        unidas = []   # [caja en pixeles, texto original, texto nuevo, alto de la lectura mas baja]
        for r, original, nuevo in zonas:
            x0, y0 = int((r.x0 - bbox.x0) * fx), int((r.y0 - bbox.y0) * fy)
            x1, y1 = int((r.x1 - bbox.x0) * fx) + 1, int((r.y1 - bbox.y0) * fy) + 1
            for u in unidas:
                a0, b0, a1, b1 = u[0]
                comun = max(0, min(x1, a1) - max(x0, a0)) * max(0, min(y1, b1) - max(y0, b0))
                if comun > 0.5 * min((x1 - x0) * (y1 - y0), (a1 - a0) * (b1 - b0)):
                    mejor = (original, nuevo) if len(original) > len(u[1]) else (u[1], u[2])
                    u[:] = [(min(x0, a0), min(y0, b0), max(x1, a1), max(y1, b1)), *mejor, min(u[3], y1 - y0)]
                    break
            else:
                unidas.append([(x0, y0, x1, y1), original, nuevo, y1 - y0])
        # los colores se toman de la imagen original, antes de borrar nada
        tonos = [colores(img, u[0]) for u in unidas]
        dibujo = ImageDraw.Draw(img)
        for u, (fondo, _) in zip(unidas, tonos):
            x0, y0, x1, y1 = u[0]
            dibujo.rectangle((x0 - BORDE_PX, y0 - BORDE_PX, x1 + BORDE_PX, y1 + BORDE_PX), fill=fondo)
        # misma letra en toda la captura: la de una linea normal (la mediana), aunque alguna caja sea mas alta
        altos = sorted(u[3] for u in unidas if u[2])
        # solo en tablas (muchas lineas): en una captura con pocas lineas cada una conserva su propio tamano
        tope = altos[len(altos) // 2] * 0.95 * 1.1 if len(altos) >= 6 else None
        if alto_fila:   # la pagina tiene una columna reescrita: todo del mismo tamano que esas filas
            tope = alto_fila * fy * 0.75
        for u, (_, letra) in zip(unidas, tonos):
            if u[2]:
                x0, y0, x1, y1 = u[0]
                centro = (y0 + y1) / 2   # la caja de la lectura mas baja, centrada donde estaba la linea
                escribir(dibujo, (x0, centro - u[3] / 2, x1, centro + u[3] / 2), u[2], letra, tope)
        salida = io.BytesIO()
        img.save(salida, "PNG")
        pagina.replace_image(xref, stream=salida.getvalue())
    return resto


def columnas_ficticias(doc, pagina, lineas, columnas):
    """Reescribe fila por fila, con nombres ficticios, las columnas de tabla dadas (en puntos) dentro de las capturas.
    Las filas salen de todas las lineas del OCR de la captura, de cualquier columna. Devuelve el alto de una fila en
    puntos (para que lo demas de la pagina se escriba del mismo tamano) o None si no hizo nada."""
    nombres = itertools.cycle(NOMBRES_TABLA)
    alto_pts = None
    for info in pagina.get_image_info(xrefs=True):
        bbox = pymupdf.Rect(info["bbox"])
        propias = [pymupdf.Rect(c[:4]) for c in columnas if bbox.contains(pymupdf.Rect(c[:4]).tl) and info["xref"]]
        if not propias:
            continue
        img = Image.open(io.BytesIO(doc.extract_image(info["xref"])["image"])).convert("RGB")
        fx, fy = img.width / bbox.width, img.height / bbox.height
        cajas = [((r.x0 - bbox.x0) * fx, (r.y0 - bbox.y0) * fy, (r.x1 - bbox.x0) * fx, (r.y1 - bbox.y0) * fy)
                 for r in (pymupdf.Rect(l["b"]) for l in lineas if l["o"] == "ocr") if bbox.intersects(r)]
        if not cajas:
            continue
        alto = sorted(c[3] - c[1] for c in cajas)[len(cajas) // 2]
        alto_pts = alto / fy
        def filas_de(cajas_tabla, completar=True):
            """Centros de las filas de una tabla (solo con las lineas del OCR a la altura de esa tabla)."""
            filas = []
            for c in sorted(cajas_tabla, key=lambda c: (c[1] + c[3]) / 2):
                centro = (c[1] + c[3]) / 2
                if filas and abs(centro - filas[-1][-1]) < alto * 0.6:
                    filas[-1].append(centro)
                else:
                    filas.append([centro])
            centros = [sum(f) / len(f) for f in filas]
            # las filas de una tabla tienen la misma altura: con la distancia mas comun entre filas se completan las que
            # el OCR no leyo (filas anuladas en rojo, texto borroso)
            pasos = sorted(b - a for a, b in zip(centros, centros[1:]) if b - a > alto * 0.6)
            if pasos and completar:
                # recta que mejor pasa por las filas leidas (fila k = inicio + k * paso): la cuadricula completa, sin
                # filas de mas por lo que el OCR lee entre dos filas (numeros en circulos, flechas)
                paso = pasos[len(pasos) // 2]
                ks = [round((c - centros[0]) / paso) for c in centros]
                n = len(ks)
                mk, mc = sum(ks) / n, sum(centros) / n
                var = sum((k - mk) ** 2 for k in ks)
                b = sum((k - mk) * (c - mc) for k, c in zip(ks, centros)) / var if var else paso
                a = mc - b * mk
                centros = [a + b * k for k in range(int(-a // b), int((img.height - a) // b) + 1)]
            return centros

        dibujo = ImageDraw.Draw(img)
        for r in propias:
            zx0, zy0 = int((r.x0 - bbox.x0) * fx), int((r.y0 - bbox.y0) * fy)
            zx1, zy1 = int((r.x1 - bbox.x0) * fx), int((r.y1 - bbox.y0) * fy)
            trabajos = []
            spec = columnas[[pymupdf.Rect(c[:4]) for c in columnas].index(r)]
            texto_fijo = spec[4] if len(spec) > 4 else None
            # una columna de texto fijo (pocas filas, todas leidas) usa las filas tal como las leyo el OCR
            centros = filas_de([c for c in cajas if zy0 <= (c[1] + c[3]) / 2 <= zy1], completar=not texto_fijo)
            for centro in centros:
                if zy0 <= centro <= zy1:
                    banda = (zx0, int(centro - alto / 2), zx1, int(centro + alto / 2) + 1)
                    trabajos.append((banda, colores(img, banda)))
            for (x0, y0, x1, y1), (fondo, _) in trabajos:
                dibujo.rectangle((x0, y0, x1, y1), fill=fondo)
            for banda, (_, letra) in trabajos:
                escribir(dibujo, (banda[0] + 2, banda[1], banda[2] - 2, banda[3]), texto_fijo or next(nombres), letra,
                         tope=alto * 0.62)
        salida = io.BytesIO()
        img.save(salida, "PNG")
        pagina.replace_image(info["xref"], stream=salida.getvalue())
    return alto_pts


def limpiar(pdf, reglas):
    lectura = auditoria.lectura(pdf)
    cajas = cajas_a_tapar(pdf, lectura, reglas)
    columnas = {int(k): v for k, v in reglas["por_manual"].get(pdf.name, {}).get("columnas", {}).items()}
    salida = destino(pdf)
    salida.parent.mkdir(parents=True, exist_ok=True)
    if not cajas and not columnas:
        shutil.copyfile(pdf, salida)
        return 0
    with pymupdf.open(pdf) as doc:
        for pag in sorted(set(cajas) | set(columnas)):
            pagina = doc[pag - 1]
            lista = cajas.get(pag, [])
            alto_fila = None
            if pag in columnas:
                dentro = lambda caja: any(pymupdf.Rect(c[:4]).contains(pymupdf.Rect(caja).tl + (1, 1)) for c in columnas[pag])
                lista = [x for x in lista if not dentro(x[0])]   # lo de la columna ya se reescribe entero
                alto_fila = columnas_ficticias(doc, pagina, lectura[pag - 1], columnas[pag])
            for c, _, nuevo in tapar_en_capturas(doc, pagina, lista, alto_fila):
                r = pymupdf.Rect(c) + (-MARGEN, -MARGEN, MARGEN, MARGEN)
                # texto del manual: se borra y se escribe el dato ficticio en el mismo lugar
                tam = r.height * 0.8
                while nuevo and tam > 5 and pymupdf.get_text_length(nuevo, "helv", tam) > r.width * 1.05:
                    tam -= 0.5
                r.x1 = max(r.x1, r.x0 + pymupdf.get_text_length(nuevo, "helv", tam) + 2) if nuevo else r.x1
                pagina.add_redact_annot(r * pagina.derotation_matrix, text=nuevo or None, fontname="helv",
                                        fontsize=tam, fill=(1, 1, 1), text_color=(0, 0, 0))
            # borra el texto escrito y los pixeles de las capturas que quedan debajo: no basta con dibujar encima
            pagina.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        doc.save(salida, garbage=4, deflate=True)
    return sum(len(v) for v in cajas.values())


def fuera_de_columnas(pdf, reglas, cajas):
    """Quita de 'cajas' lo que cae en una columna reescrita entera: ahi solo hay nombres ficticios (en capturas
    borrosas el OCR los lee mal, por ejemplo DEMO como DENO, y parecerian datos)."""
    columnas = reglas["por_manual"].get(pdf.name, {}).get("columnas", {})
    dentro = lambda pag, caja: any(pymupdf.Rect(c[:4]).contains(pymupdf.Rect(caja).tl + (1, 1)) for c in columnas.get(str(pag), []))
    return {pag: v for pag, v in ((pag, [x for x in lista if not dentro(pag, x[0])]) for pag, lista in cajas.items()) if v}


def comprobar(pdfs, reglas):
    """Vuelve a leer con OCR las copias limpias y lista lo que todavia se detecta."""
    quedan = 0
    for pdf in pdfs:
        copia = destino(pdf)
        if not copia.exists():
            print(f"  FALTA la copia limpia: {pdf.name}")
            quedan += 1
            continue
        # las zonas fijas no se vuelven a contar: solo lo que el OCR todavia lee en la copia
        propios = reglas["por_manual"].get(pdf.name, {}).get("terminos", [])
        resto = cajas_a_tapar(pdf, auditoria.lectura(copia), reglas | {"por_manual": {pdf.name: {"terminos": propios}}})
        resto = fuera_de_columnas(pdf, reglas, resto)
        n = sum(len(v) for v in resto.values())
        quedan += n
        print(f"  {'OK   ' if not n else 'QUEDA'} {pdf.name}" + (f": {n} en paginas {sorted(resto)}" if n else ""), flush=True)
    print("\nTodo limpio." if not quedan else f"\nQuedan {quedan} datos por tapar.")
    return quedan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", help="solo los manuales cuyo nombre contenga este texto")
    ap.add_argument("--comprobar", action="store_true", help="volver a leer las copias limpias y avisar si quedo algo")
    args = ap.parse_args()
    reglas = cargar_reglas()
    pdfs = [p for p in auditoria.manuales() if auditoria.se_carga(p)
            and (not args.solo or args.solo.lower() in p.name.lower())]
    if args.comprobar:
        sys.exit(1 if comprobar(pdfs, reglas) else 0)
    total = 0
    for pdf in pdfs:
        n = limpiar(pdf, reglas)
        total += n
        print(f"  {n:4d} zonas tapadas  {pdf.name}", flush=True)
    print(f"\n{len(pdfs)} copias en {LIMPIOS} ({total} zonas tapadas). Comprobar: limpiar_manuales.py --comprobar")


if __name__ == "__main__":
    main()
