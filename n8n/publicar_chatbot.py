"""Construye y publica en n8n el workflow del Asistente NAVASOFT.

Funcionamiento (busqueda primero, una sola llamada a la IA por pregunta):
  Consulta interna (solo el portal, con clave) -> historial de la conversacion -> preparar busqueda
    -> si es la primera pregunta y ya se respondio antes: respuesta guardada (sin gastar IA)
    -> si no: vectorizar con bge-m3 -> buscar fragmentos + paginas siguientes del mismo manual
       -> armar consulta -> IA (Gemini, con Groq de respaldo; en la nube, Claude si fallan los dos)
       -> agregar capturas de las paginas citadas (max. 2) y sugerencias -> guardar respuesta reutilizable
"""
import json
import pathlib
import secrets
import sys

import psycopg
import requests

sys.stdout.reconfigure(encoding="utf-8")
AQUI = pathlib.Path(__file__).parent
BASE = AQUI.parent
WORKFLOW_ID = "uGhzLlnotxpTwlfy"
API = "http://localhost:5678/api/v1"
API_KEY = next(l.split("=", 1)[1].strip() for l in open(r"C:\mcp-n8n\.env", encoding="utf-8") if l.startswith("N8N_API_KEY="))
H = {"X-N8N-API-KEY": API_KEY}
CRED_PG = {"postgres": {"id": "SqW5cZj7KdT9Lbyu", "name": "Base de datos NAVASOFT"}}
CRED_GEMINI = {"googlePalmApi": {"id": "YbrX4mPubLFww3W5", "name": "Gemini NAVASOFT"}}
CRED_GROQ = {"groqApi": {"id": "F1zpkcgXPrBt9cVH", "name": "Groq account"}}
# Claude solo entra si Gemini y Groq fallan los dos (ultimo respaldo, de pago). La credencial vive solo en la nube:
# la crea migracion/crear_credencial_claude.ps1 y publicar_nube.py la pasa a construir().
MODELO_CLAUDE = "claude-haiku-5-5"
# OpenRouter (modelo gratuito) entra antes que Claude cuando Gemini y Groq fallan. La cuenta gratuita permite solo
# 50 pedidos por dia, por eso es respaldo y no el modelo principal. La credencial la crea
# migracion/crear_credencial_openrouter.ps1 (el modelo debe ser el primero de su lista de candidatos).
MODELO_OPENROUTER = "google/gemma-4-31b-it:free"
CABECERA_CLAVE = "X-Navasoft-Clave"

MANUALES = """Caja chica, Caja y bancos, Contabilidad general, Cuentas por pagar, Entregas a rendir cuenta (ERCTA),
Inventarios, Ventas, Asiento de cierre y apertura, Configurar diseño de libros contables, Costo de ventas,
Depósitos en efectivo, Emisión de guías de remisión de transportista (GRE), Ventas con transferencia gratuita y su
cancelación, Agente de retención (cliente), Compra diferida y TXT del balance de comprobación"""

# Sin llaves { } en este texto: n8n lo procesa como plantilla.
REGLAS = f"""Eres el asistente virtual de soporte de EKAM PERÚ. EKAM PERÚ es la empresa que brinda el soporte; NAVASOFT es el sistema (ERP) que usan sus clientes. Hablas en nombre de EKAM PERÚ y ayudas a los clientes con el uso de NAVASOFT.

En cada mensaje recibes: la CONVERSACIÓN PREVIA, los FRAGMENTOS DE LOS MANUALES encontrados para la consulta y la NUEVA CONSULTA DEL CLIENTE.

REGLAS:
1. Responde SOLO con información de los FRAGMENTOS. Nunca inventes menús, botones, campos ni pasos. Usa la CONVERSACIÓN PREVIA para entender a qué se refiere el cliente (por ejemplo "¿y después qué hago?").
2. Los fragmentos se buscan automáticamente y muchos solo se PARECEN a la consulta sin responderla. Antes de usar un fragmento comprueba que trate EXACTAMENTE la misma acción o problema que plantea el cliente:
   - Si el cliente quiere EMITIR o REGISTRAR algo y el fragmento explica cómo ANULARLO o MODIFICARLO (o al revés), no sirve.
   - Si el cliente reporta un ERROR o mensaje específico y el fragmento solo describe el uso normal de esa pantalla, no sirve: no lo presentes como solución.
   - Si la consulta es comercial o administrativa (cotizaciones de servicios, licencias, instalaciones, accesos, capacitaciones) y el fragmento trata de una función del sistema con nombre parecido, no sirve.
   Si ningún fragmento responde exactamente, aplica la regla 7 (o la 8 si la consulta es ambigua). Es mejor derivar a soporte que dar pasos de otro tema.
3. Explica en pasos numerados, claros y cortos. Escribe los nombres de menús, ventanas, botones y campos en negrita, tal como aparecen en el fragmento (ejemplo: **Administrativo → Egresos → Caja chica → Movimientos**).
4. Escribe solo rutas de menú, ventanas y botones que aparezcan textualmente en los fragmentos. Nunca escribas rutas aproximadas como "por ejemplo Ventas" o "según la ruta de tu empresa"; si el fragmento no trae la ruta, dilo.
5. Indica la fuente UNA sola vez, al final de la respuesta (nunca después de cada paso), con un enlace a cada página usada y la dirección del campo pagina_url escrita tal cual (sin signos < >): 📄 Fuente: [Nombre del manual, página N](DIRECCION), [página M](DIRECCION)
6. IMÁGENES: si explicas cómo usar una pantalla y el fragmento usado trae direcciones en imagenes_url, incluye 1 o 2 capturas (nunca más de 2), cada una en su propia línea justo después del paso al que corresponde: ![Pantalla de NAVASOFT](DIRECCION). Copia las direcciones exactamente; nunca inventes una.
7. SIN INFORMACIÓN: el cliente no conoce los nombres del sistema y usa sus propias palabras. Antes de decir que no hay información, revisa si algún fragmento trata lo mismo con otro nombre (usa la lista TÉRMINOS EQUIVALENTES si viene: por ejemplo "crear un producto" es dar de alta un ítem en el **Padrón de ítems** de Inventarios). Si es así, responde con ese fragmento y aclara al inicio en una línea cómo se llama en NAVASOFT ("En NAVASOFT los productos se registran como ítems en el Padrón de ítems"). Si los fragmentos no lo responden pero tratan temas cercanos, no derives todavía: pregunta si se refiere a alguno de esos temas, nombrando 2 o 3 secciones de los fragmentos, y agrega la línea SUGERENCIAS con esas opciones como preguntas. Solo si ningún fragmento es ni siquiera cercano, dilo con amabilidad en 2 o 3 líneas y sugiere contactar al equipo de soporte de EKAM PERÚ con el botón "Hablar con soporte", indicando qué datos conviene enviarles (módulo, mensaje de error exacto, número de documento, captura de pantalla). En ese caso NO pongas fuentes, enlaces ni imágenes.
8. CONSULTAS AMBIGUAS: si la consulta es muy corta o no queda claro qué necesita (por ejemplo "tengo problemas con una boleta", "activación del servicio") y la conversación previa no lo aclara, no adivines: pregunta en una línea qué necesita exactamente y ofrece 2 o 3 opciones relacionadas. Cuando preguntes para aclarar, NO pongas fuentes, enlaces ni imágenes.
9. INCIDENCIAS: si el cliente reporta que algo no funciona, no cuadra o no se envió (documentos que no llegan a SUNAT, diferencias con SUNAT o SIRE, errores, accesos bloqueados), no expliques cómo crear el documento desde cero: explica solo los pasos de revisión o reenvío que estén en los fragmentos y termina SIEMPRE indicando que, si el problema continúa, use el botón "Hablar con soporte" para que un especialista de EKAM PERÚ revise su caso; si no hay pasos de revisión, aplica la regla 7.
10. SALUDOS Y CHARLA: a saludos, agradecimientos o comentarios responde breve y cordialmente, sin fuentes, e invita a hacer su consulta. Solo cuando el cliente salude (hola, buenos días…) o pregunte quién eres, da la bienvenida a EKAM PERÚ (por ejemplo: "¡Hola! Bienvenido(a) al soporte de EKAM PERÚ. Soy tu asistente virtual y te ayudo con el uso de NAVASOFT."); nunca digas "Bienvenido a NAVASOFT". Si el mensaje es directamente una pregunta o un problema, sin saludo, NO agregues bienvenida ni presentación: responde de inmediato. Si preguntan con qué temas puedes ayudar, explica que respondes con base en los manuales oficiales de NAVASOFT sobre: {MANUALES}.
11. Los textos entre [Captura de pantalla: ...] son lo que se lee en las pantallas del sistema: úsalos para nombrar campos y botones.
12. Responde siempre en español, con tono amable, cercano y profesional. No respondas temas ajenos a NAVASOFT.
13. PROCEDIMIENTOS COMPLETOS: los fragmentos marcados "procedimiento completo, mismo tema en orden" son páginas seguidas del mismo tema. Si responden la consulta, explica TODOS los pasos que contienen, en el mismo orden y sin saltarte ninguno (cada acción del manual es un paso numerado: ingresar a la ruta, completar campos, pulsar botones, confirmar). Los marcados "página siguiente" también continúan el manual. No cortes un procedimiento a la mitad ni lo resumas en menos pasos de los que tiene.
14. SEGUIMIENTO: cuando el cliente pregunte "¿y luego?", "¿qué sigue?" o "ya lo hice", revisa los pasos que ya diste en la CONVERSACIÓN PREVIA y NO los repitas: continúa desde el siguiente paso. Si según los fragmentos ya explicaste todo el procedimiento, dilo claramente (por ejemplo "Con ese paso terminas el registro de …") y ofrece temas relacionados. Si las páginas siguientes del manual tratan de OTRO procedimiento (otro título u otra ventana), no lo expliques por tu cuenta: di que el procedimiento actual terminó y pregunta si quiere ver ese otro tema, nombrándolo. Nunca digas que no tienes información de un proceso que ya explicaste completo.
15. SUGERENCIAS: al final de cada respuesta con pasos (y cuando preguntas a qué tema cercano se refiere, regla 7) agrega UNA última línea exacta con 2 o 3 preguntas cortas que el cliente podría hacer a continuación y que los fragmentos permitan responder, con este formato: SUGERENCIAS: ¿pregunta 1? | ¿pregunta 2? | ¿pregunta 3? No la agregues en saludos simples, en aclaraciones ni cuando derivas a soporte.
16. Las líneas "[Descripción de la captura: ...]" fueron escritas automáticamente por una IA que miró la imagen y pueden tener errores de lectura: úsalas solo para saber qué pantalla muestra la captura. Nunca copies de ellas números, códigos, montos ni nombres de ejemplo, y no las cites como si fueran texto del manual."""

HISTORIAL_SQL = """SELECT rol, texto FROM (
  SELECT id, rol, texto FROM mensajes WHERE conversacion_id = $1::uuid ORDER BY id DESC LIMIT 9
) t ORDER BY id"""

# Palabras del cliente -> nombre en NAVASOFT. "si" es una expresion regular sobre la consulta en minusculas y sin tildes;
# "buscar" se agrega a la busqueda; "nota" se le da a la IA. Para agregar terminos: una linea mas y publicar.
GLOSARIO = [
    {"si": r"\b(producto|productos|articulo|articulos|item|items|mercaderia|codigo de producto|sku)\b",
     "buscar": "mantenimiento al padrón de ítems kardex",
     "nota": "producto / artículo / mercadería = ítem del Padrón de ítems (Inventarios → Mantenimiento al padrón de ítems)"},
    {"si": r"\b(stock|existencia|existencias|cuanto (hay|tengo|queda))\b",
     "buscar": "movimientos del kardex visualizar el kardex de un ítem stock",
     "nota": "stock / existencias = Kardex del ítem (Inventarios → Movimientos del kardex)"},
    {"si": r"\b(entrada de mercaderia|ingreso de mercaderia|recibir mercaderia|ingresar mercaderia|ingreso al almacen)\b",
     "buscar": "notas de ingreso nuevo", "nota": "ingreso de mercadería al almacén = Nota de ingreso (Inventarios)"},
    {"si": r"\b(salida de mercaderia|sacar mercaderia|despachar|retirar del almacen|consumo interno)\b",
     "buscar": "notas de salida nuevo", "nota": "salida de mercadería del almacén = Nota de salida (Inventarios)"},
    {"si": r"\b(crea\w*|creo|nuev[oa]|registr\w*|agreg\w*|ingres\w*|dar de alta|alta de)\b.{0,25}\bcliente|\bcliente\w* nuev[oa]",
     "buscar": "catálogo de clientes datos generales del cliente nuevo",
     "nota": "crear un cliente = registrarlo en el padrón / catálogo de clientes (datos generales del cliente)"},
    {"si": r"\b(crea\w*|creo|nuev[oa]|registr\w*|agreg\w*|ingres\w*|dar de alta|alta de)\b.{0,25}\bproveedor|\bproveedor\w* nuev[oa]",
     "buscar": "proveedores operaciones de mantenimiento nuevo proveedor",
     "nota": "crear un proveedor = Nuevo proveedor (Cuentas por pagar → Proveedores → Operaciones de mantenimiento)"},
    {"si": r"\b(facturo|facturar|facturarle|le facturo|emitir (una )?factura|hacer (una )?factura)\b",
     "buscar": "factura de venta crear", "nota": "facturar = crear una Factura de venta (Ventas → Factura de venta → Crear)"},
    {"si": r"\b(sin ruc|consumidor final|persona natural|con dni|boletear|boleta)\b",
     "buscar": "boleta de venta crear", "nota": "venta a persona sin RUC = Boleta de venta (Ventas)"},
    {"si": r"\b(conte|contamos|lo contado|diferencia de stock|no cuadra el stock|ajuste de stock|ajustar (el )?stock)\b",
     "buscar": "registro y proceso de inventario periódico a la fecha toma de inventario",
     "nota": "ajustar el stock con un conteo = Registro y proceso de inventario periódico (Inventarios)"},
    {"si": r"\b(devol\w*|descuento posterior|anular una venta ya)",
     "buscar": "nota de crédito nuevo registro del documento",
     "nota": "devolución o descuento sobre una venta ya facturada = Nota de crédito (Ventas)"},
    {"si": r"\b(cobrar|cobro|cobranza|pago del cliente|me pagaron|abono del cliente)\b",
     "buscar": "cobranzas apertura de la planilla de cobranza edición de RIC amortización de documentos",
     "nota": "registrar lo que paga un cliente = Cobranzas: planilla de cobranza y RIC (Caja y bancos)"},
    {"si": r"\b(pagar a(l)? proveedor|pago a proveedor|pagar factura de compra|pagar una factura)\b",
     "buscar": "orden de pago crear egresos cheque pagos en efectivo",
     "nota": "pagar a un proveedor = Orden de pago (Cuentas por pagar) y egreso por cheque o efectivo (Caja y bancos)"},
    {"si": r"\b(gasto|gastos|recibo por honorarios|factura de servicio)\b",
     "buscar": "facturas gastos diversos crear",
     "nota": "registrar un gasto o servicio = Facturas gastos diversos (Cuentas por pagar); gastos menores = Caja chica"},
    {"si": r"\b(precio|precios|tarifa|cambiar el precio)\b",
     "buscar": "lista de precios actualizar lista de precios",
     "nota": "precios de venta = Lista de precios (Ventas)"},
    {"si": r"\b(proforma|presupuesto para el cliente|cotizar)\b",
     "buscar": "cotizaciones nuevo ingreso de una cotización", "nota": "proforma / presupuesto = Cotización (Ventas)"},
    {"si": r"\b(orden de venta|orden del cliente)\b",
     "buscar": "pedidos crear", "nota": "orden de venta = Pedido (Ventas)"},
    {"si": r"\b(guia|guias|traslado)\b",
     "buscar": "guía de remisión crear", "nota": "guía = Guía de remisión (Ventas) o GRE transportista"},
    {"si": r"\b(asiento|voucher contable|comprobante contable|partida)\b",
     "buscar": "comprobantes ingresar un nuevo comprobante",
     "nota": "asiento contable = Comprobante contable (Contabilidad → Movimientos, comprobantes contables)"},
    {"si": r"\b(cuenta contable|plan de cuentas|crear (una )?cuenta)\b",
     "buscar": "plan contable general", "nota": "cuentas contables = Plan contable general (Contabilidad → Maestros)"},
    {"si": r"\b(inventario fisico|contar (la )?mercaderia|conteo)\b",
     "buscar": "inventario periódico formato de toma de inventario",
     "nota": "conteo físico = Toma de inventario / inventario periódico (Inventarios)"},
    {"si": r"\b(fondo fijo|caja menuda|gastos menores|reponer caja)\b",
     "buscar": "caja chica apertura reembolso de caja chica",
     "nota": "fondo fijo / caja menuda = Caja chica; reponerla = Reembolso de caja chica"},
    {"si": r"\b(viaticos|adelanto a(l)? trabajador|rendicion de gastos|rendir)\b",
     "buscar": "entregas a rendir cuenta registro emisión liquidación de cuentas",
     "nota": "viáticos o adelantos al personal = Entregas a rendir cuenta (ERC)"},
    {"si": r"\b(conciliar|conciliacion|estado de cuenta del banco|extracto)\b",
     "buscar": "conciliación bancaria movimiento bancos",
     "nota": "cuadrar con el banco = Conciliación bancaria (Caja y bancos → Movimiento bancos)"},
]

PREPARAR_BUSQUEDA = r"""const consulta = $('Consulta interna').first().json.body || {};
const pregunta = String(consulta.chatInput || '').trim();
let hist = $input.all().map((i) => i.json).filter((m) => m && m.rol);
// el portal ya guardo la pregunta actual en el historial: se quita para no repetirla
const ultimo = hist[hist.length - 1];
if (ultimo && ultimo.rol === 'usuario' && ultimo.texto.trim() === pregunta) hist.pop();
hist = hist.slice(-8);
// si es una pregunta de seguimiento ("y luego?", "ya lo hice"), se busca junto con la anterior
const anteriores = hist.filter((m) => m.rol === 'usuario').map((m) => m.texto);
// una pregunta corta completa ("¿Cómo anulo una guía?") es un tema nuevo, salvo que se refiera a lo anterior ("¿cómo lo guardo?")
const preguntaNueva = /^¿?\s*(c[oó]mo|qu[eé]|d[oó]nde|cu[aá]l(es)?|cu[aá]nto|por qu[eé]|para qu[eé]|puedo|se puede)\b/i.test(pregunta)
  && !/\b(lo|la|los|las|eso|esto|esa|ese|ah[ií]|sigue|m[aá]s)\b/i.test(pregunta);
const seguimiento = hist.length > 0 && ((pregunta.length < 25 && !preguntaNueva) ||
  /^(¿?\s*y\b|entonces|luego|despu[eé]s|eso|esa|ese|esto|ok|vale|bien|listo|ya\b|contin|sigue|siguiente|qu[eé] (m[aá]s|sigue|procede)|y\s+si)/i.test(pregunta));
let busqueda = seguimiento && anteriores.length ? anteriores[anteriores.length - 1] + ' ' + pregunta : pregunta;
// GLOSARIO: el cliente usa sus palabras ("crear un producto") y el manual las de NAVASOFT ("padrón de ítems").
// Si la consulta trae una de esas palabras, se agrega a la búsqueda el nombre del manual y se avisa a la IA.
const sinTildes = (t) => t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const GLOSARIO = GLOSARIO_JSON;
const textoGlosario = sinTildes(busqueda);
const equivalencias = GLOSARIO.filter((g) => new RegExp(g.si, 'i').test(textoGlosario));
if (equivalencias.length) busqueda += ' ' + equivalencias.map((g) => g.buscar).join(' ');
const glosario = equivalencias.map((g) => g.nota).join('\n');
// todas las paginas que ya se citaron en la conversacion: en un seguimiento se leen las que siguen
const urlsPagina = (t) => t.match(/https?:\/\/[^\s)>]+\/navasoft-pagina\?id=[0-9a-f]{12}/g) || [];
const citadas = seguimiento ? [...new Set(hist.filter((m) => m.rol === 'bot').flatMap((m) => urlsPagina(m.texto)))] : [];
const limpiar = (t, n) => t.replace(/!\[[^\]]*\]\([^)]+\)/g, '').replace(/\]\([^)]+\)/g, ']')
  .replace(/\[\[sugerencias:[^\]]*\]\]/g, '').replace(/\s+/g, ' ').slice(0, n);
// la ultima respuesta va casi completa: asi la IA sabe que pasos ya dio y no los repite
const ultimaBot = hist.map((m) => m.rol).lastIndexOf('bot');
const historial = hist.map((m, i) => (m.rol === 'usuario' ? 'Cliente: ' + limpiar(m.texto, 400)
  : 'Asistente: ' + limpiar(m.texto, i === ultimaBot ? 2000 : 600))).join('\n');
// clave para respuestas guardadas: pregunta en minusculas, sin tildes ni signos
const clave = pregunta.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9ñ ]/g, ' ').replace(/\s+/g, ' ').trim();
// ¿pide el indice de un manual o la lista de manuales? ("muestrame los temas de Ventas", "que manuales hay")
const pideIndice = (/\b(temas|indice|contenido|secciones|capitulos)\b/.test(clave) && /\b(manual|manuales|guia|temas de|temas del|que temas|cuales temas)\b|temas d/.test(clave))
  || /\b(que|cuales) manuales\b|\blista de manuales\b|\bmanuales (hay|tienes|disponibles)\b/.test(clave);
const VACIAS = new Set(['manual', 'manuales', 'temas', 'tema', 'indice', 'contenido', 'muestrame', 'mostrar', 'muestra', 'cuales',
  'tiene', 'tienes', 'trae', 'incluye', 'guia', 'sobre', 'quiero', 'puedes', 'lista', 'secciones', 'capitulos', 'dame', 'dime',
  'hay', 'disponibles', 'para', 'este', 'esta', 'todos', 'todas', 'ensename', 'conocer', 'saber']);
const palabras = clave.split(' ').filter((w) => w.length >= 4 && !VACIAS.has(w)).join(' ');
return [{ json: { pregunta, busqueda, historial, glosario, citadas: citadas.join(',') || 'ninguna', clave: clave || 'vacia',
  primera: hist.length === 0 ? 'si' : 'no', indice: pideIndice ? 'si' : 'no', palabras: palabras || 'ninguna' } }];"""

# indice de un manual: el manual cuyo nombre coincide con mas palabras de la consulta; si ninguno coincide, lista de manuales
INDICE_SQL = """WITH q AS (
  SELECT w FROM unnest(string_to_array($1, ' ')) AS w WHERE length(w) >= 4
), m AS (
  SELECT metadata->>'manual' AS manual, metadata->>'archivo' AS archivo FROM chunks_bge_m3
  WHERE metadata->>'pagina' IS NOT NULL GROUP BY 1, 2
), puntaje AS (
  SELECT m.manual, m.archivo, count(q.w) AS p FROM m
  JOIN q ON translate(lower(m.manual), 'áéíóúñ', 'aeioun') LIKE '%' || q.w || '%' GROUP BY 1, 2
), mejor AS (
  -- ante un empate se prefiere el manual principal ("Manual de Ventas" antes que la guia "Costo de ventas")
  SELECT manual, archivo FROM puntaje ORDER BY p DESC, (manual ILIKE 'Manual de%') DESC, length(manual) LIMIT 1
)
SELECT 'elegido' AS tipo, mejor.manual, NULL AS numero, NULL AS titulo, NULL::int AS pagina,
       (SELECT c.metadata->>'pagina_url' FROM chunks_bge_m3 c WHERE c.metadata->>'archivo' = mejor.archivo
         AND c.metadata->>'pagina' IS NOT NULL ORDER BY (c.metadata->>'pagina')::int LIMIT 1) AS pagina_url, -1 AS orden
  FROM mejor
UNION ALL
SELECT 'tema', i.manual, i.numero, i.titulo, i.pagina, i.pagina_url, i.orden
  FROM manual_indice i JOIN mejor ON i.archivo = mejor.archivo
UNION ALL
SELECT 'manual', m.manual, NULL, NULL, NULL, NULL, 0 FROM m WHERE NOT EXISTS (SELECT 1 FROM mejor)
ORDER BY orden, manual"""

RESPONDER_INDICE = r"""const filas = $input.all().map((i) => i.json).filter((f) => f && f.tipo);
const elegido = filas.find((f) => f.tipo === 'elegido');
let out = '', sug = [];
if (elegido) {
  const temas = filas.filter((f) => f.tipo === 'tema');
  out = `📚 **Temas del ${elegido.manual}**\n\n`;
  if (!temas.length) {
    out += `Esta guía trata un solo tema. Puedes verla desde su primera página: [${elegido.manual}](${elegido.pagina_url}).\n\nCuéntame qué necesitas hacer y te explico los pasos.`;
  } else {
    for (const t of temas) {
      const enlace = t.pagina_url ? `[${t.numero ? t.numero + ' ' : ''}${t.titulo}](${t.pagina_url}) · pág. ${t.pagina}` : `${t.numero} ${t.titulo}`;
      out += (!t.numero || !t.numero.includes('.')) ? `\n**${t.numero ? t.numero + '. ' : ''}${t.titulo}** · [pág. ${t.pagina}](${t.pagina_url})\n` : `- ${enlace}\n`;
    }
    out += '\nEscríbeme el tema que te interesa y te explico los pasos.';
    const corto = elegido.manual.replace(/^(Manual de|guia)\s+/i, '').replace(/\s+V5$/i, '');
    sug = temas.filter((t) => t.numero && t.numero.includes('.') && !/interfaz/i.test(t.titulo)).slice(0, 3)
      .map((t) => `Explícame: ${t.titulo} (${corto})`);
  }
} else {
  const manuales = filas.filter((f) => f.tipo === 'manual').map((f) => f.manual);
  out = '📚 **Manuales disponibles**\n\n' + manuales.map((m) => `- ${m}`).join('\n') + '\n\n¿De cuál quieres ver los temas?';
  sug = ['Temas del Manual de Ventas V5', 'Temas del Manual de caja chica V5', 'Temas del Manual de Inventarios V5'];
}
if (sug.length) out += `\n\n[[sugerencias: ${sug.join(' | ')}]]`;
return [{ json: { output: out } }];"""

USAR_GUARDADA_SQL = """UPDATE respuestas_cache SET usos = usos + 1
WHERE clave = $1 AND $2 = 'si' RETURNING respuesta AS output"""

# $1 = vector de la consulta; $2 = paginas ya citadas en la conversacion (solo en preguntas de seguimiento);
# $3 = texto de la busqueda.
# Busqueda mixta (ver analisis/evaluar_busqueda.py): une por rango reciproco (RRF) el parecido de significado,
# las palabras en el titulo de la seccion y en el texto, con una pequena ventaja al manual que nombra la pregunta.
# En el examen de 120 temas subio la pagina correcta en 1.er lugar de 62 a 80 y entre los 6 primeros de 84 a 112.
BUSCAR_SQL_BASE = """WITH q AS (
  -- cualquier palabra cuenta (OR); las palabras de relleno de las preguntas no suman
  SELECT replace(plainto_tsquery('spanish', regexp_replace(translate(lower($3), 'áéíóúü', 'aeiouu'),
           '\\m(navasoft|modulo|funciona|como|hago|pantalla|opciones|tiene|registro|nuevo|creo|uno)\\M', ' ', 'g'))::text,
           '&', '|')::tsquery AS ts,
         tsvector_to_array(to_tsvector('spanish', translate(lower($3), 'áéíóúü', 'aeiouu'))) AS lex
), base AS (
  SELECT id, text, metadata, embedding <=> $1::vector AS dist,
         to_tsvector('spanish', translate(lower(coalesce(metadata->>'seccion', '')), 'áéíóúü', 'aeiouu')) AS ts_sec,
         to_tsvector('spanish', translate(lower(text), 'áéíóúü', 'aeiouu')) AS ts_txt
  FROM chunks_bge_m3
), vector AS (
  SELECT id, row_number() OVER (ORDER BY dist) AS r FROM base ORDER BY dist LIMIT 40
), en_seccion AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(ts_sec, q.ts, 1) DESC, dist) AS r
  FROM base, q WHERE ts_sec @@ q.ts ORDER BY r LIMIT 40
), en_texto AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(ts_txt, q.ts, 1) DESC) AS r
  FROM base, q WHERE ts_txt @@ q.ts ORDER BY r LIMIT 40
), alias AS (
  -- frases de cliente (alias_secciones.py): las 3 secciones cuyas frases mas se parecen a la consulta. No son
  -- resultados: solo empujan las paginas reales de esa seccion, y solo si el parecido pasa del umbral
  SELECT metadata->>'archivo' AS archivo, metadata->>'seccion' AS seccion, max(1 - dist) AS sim
  FROM base WHERE metadata->>'tipo' = 'alias' GROUP BY 1, 2 ORDER BY sim DESC LIMIT 3
), en_alias AS (
  -- la primera pagina de la mejor seccion, aunque la busqueda normal no la haya traido
  SELECT DISTINCT ON (b.metadata->>'seccion') b.id FROM base b JOIN alias a
    ON b.metadata->>'archivo' = a.archivo AND b.metadata->>'seccion' = a.seccion
  WHERE coalesce(b.metadata->>'tipo', '') NOT IN ('alias', 'captura') AND a.sim >= UMBRAL_ALIAS
  ORDER BY b.metadata->>'seccion', (b.metadata->>'pagina')::int
), manual AS (
  -- cuantas palabras del nombre del manual aparecen en la pregunta, comparando raices
  -- ("transportista" = "TRANSPORTISTAS"), sin contar las genericas
  SELECT m, count(*) AS n FROM (SELECT DISTINCT metadata->>'manual' AS m FROM base) x,
    unnest(tsvector_to_array(to_tsvector('spanish', translate(lower(x.m), 'áéíóúü', 'aeiouu')))) AS p, q
  WHERE length(p) >= 3 AND p NOT IN ('manual', 'guia', 'proced', 'navasoft', 'v5') AND p = ANY(q.lex)
  GROUP BY m
), parecidos AS (
  -- sim sigue siendo el parecido de significado (la IA lo ve y se filtra el ruido); el orden lo da el puntaje mixto
  SELECT b.text, b.metadata, round((1 - b.dist)::numeric, 3) AS sim,
         coalesce(1.0 / (60 + v.r), 0) + 0.5 * coalesce(1.0 / (60 + s.r), 0) + 0.5 * coalesce(1.0 / (60 + t.r), 0)
         + PESO_ALIAS * greatest(coalesce(al.sim, 0) - UMBRAL_ALIAS, 0)
         + PESO_MANUAL * coalesce(m.n, 0) / greatest((SELECT max(n) FROM manual), 1)
         -- ventaja si la pregunta nombra completo el titulo de la seccion ("otros ingresos" -> 1.5.1 Otros ingresos)
         + PESO_SECCION * (SELECT CASE WHEN cardinality(a) > 0 AND a <@ q.lex THEN cardinality(a) ELSE 0 END FROM q,
             tsvector_to_array(to_tsvector('spanish', translate(lower(regexp_replace(regexp_replace(coalesce(b.metadata->>'seccion', ''),
             '^.*>\\s*', ''), '^[0-9. ]+', '')), 'áéíóúü', 'aeiouu'))) AS a) AS puntaje
  FROM base b LEFT JOIN vector v USING (id) LEFT JOIN en_seccion s USING (id) LEFT JOIN en_texto t USING (id)
  LEFT JOIN alias al ON al.archivo = b.metadata->>'archivo' AND al.seccion = b.metadata->>'seccion'
  LEFT JOIN manual m ON m.m = b.metadata->>'manual'
  WHERE coalesce(b.metadata->>'tipo', '') <> 'alias'
    AND (v.id IS NOT NULL OR s.id IS NOT NULL OR t.id IS NOT NULL OR b.id IN (SELECT id FROM en_alias))
  ORDER BY puntaje DESC LIMIT 8
), principales AS (
  SELECT metadata->>'archivo' AS archivo, (metadata->>'pagina')::int AS pagina, metadata->>'seccion' AS seccion,
         row_number() OVER (ORDER BY puntaje DESC) AS rn
  -- con el mismo minimo de parecido que usa "Armar consulta": una palabra suelta ("capital") no arma un procedimiento
  FROM parecidos WHERE metadata->>'pagina' IS NOT NULL AND sim >= 0.45 ORDER BY puntaje DESC LIMIT 2
), procedimiento AS (
  -- el procedimiento completo del fragmento mas parecido: su pagina, hasta 5 anteriores de la misma seccion
  -- (si cae a mitad de un procedimiento, se lee desde su inicio)
  -- y hasta 3 paginas siguientes de la misma seccion (la inmediata siguiente siempre, por si cambia el titulo).
  -- la inmediata anterior tambien: una seccion que empieza a media pagina queda etiquetada con la seccion previa
  -- (los pasos 1 y 2 de "2.4 Anular" de Cotizaciones estan en la pagina 28, marcada como "2.3 Modificar")
  SELECT c.text, c.metadata, 'procedimiento completo, mismo tema en orden' AS similitud, 1 AS orden, (c.metadata->>'pagina')::int AS pag
  FROM chunks_bge_m3 c JOIN principales x ON x.rn = 1 AND c.metadata->>'archivo' = x.archivo AND coalesce(c.metadata->>'tipo', '') NOT IN ('captura', 'alias')
   AND (((c.metadata->>'pagina')::int BETWEEN x.pagina - 5 AND x.pagina + 3 AND c.metadata->>'seccion' = x.seccion)
        OR (c.metadata->>'pagina')::int BETWEEN x.pagina - 1 AND x.pagina + 1)
), vecinas AS (
  SELECT c.text, c.metadata, 'página siguiente del mismo manual' AS similitud, 3 AS orden, (c.metadata->>'pagina')::int AS pag
  FROM chunks_bge_m3 c JOIN principales x ON x.rn = 2 AND c.metadata->>'archivo' = x.archivo AND coalesce(c.metadata->>'tipo', '') NOT IN ('captura', 'alias')
   AND (c.metadata->>'pagina')::int = x.pagina + 1
), citadas AS (
  SELECT metadata->>'archivo' AS archivo, max((metadata->>'pagina')::int) AS pagina
  FROM chunks_bge_m3 WHERE metadata->>'pagina_url' = ANY(string_to_array($2, ',')) GROUP BY 1
), siguientes AS (
  SELECT c.text, c.metadata, 'página siguiente a lo ya explicado' AS similitud, 1 AS orden, (c.metadata->>'pagina')::int AS pag
  FROM chunks_bge_m3 c JOIN citadas x ON c.metadata->>'archivo' = x.archivo AND coalesce(c.metadata->>'tipo', '') NOT IN ('captura', 'alias')
   AND (c.metadata->>'pagina')::int BETWEEN x.pagina AND x.pagina + 2
)
SELECT text, metadata, similitud, 0 AS orden, pag FROM siguientes
UNION ALL SELECT text, metadata, similitud, orden, pag FROM procedimiento
-- los alias (frases de cliente) solo sirven para ubicar la pagina: a la IA le llegan las paginas reales
UNION ALL SELECT text, metadata, sim::text, 2, (metadata->>'pagina')::int FROM parecidos WHERE coalesce(metadata->>'tipo', '') <> 'alias'
UNION ALL SELECT text, metadata, similitud, orden, pag FROM vecinas
ORDER BY orden, pag"""
PESO_MANUAL = 0.012
PESO_SECCION = 0.012  # en 120 temas subio la pagina correcta en 1.er lugar de 80 a 89 (analisis/evaluar_nube.py)
# Empujon a la seccion cuyas frases de cliente se parecen a la consulta. Medido en la nube (11/11/2026):
# preguntas de cliente 1.er lugar 11 -> 25 de 40 (analisis/evaluar_cliente.py); preguntas con nombres del manual
# 88 -> 94 de 120 (analisis/evaluar_alias_regresion.py). Con peso 0.5 o mas, las preguntas normales empeoran.
PESO_ALIAS = 0.3
UMBRAL_ALIAS = 0.55  # parecido minimo con una frase de cliente para que empuje
BUSCAR_SQL = (BUSCAR_SQL_BASE.replace("PESO_MANUAL", str(PESO_MANUAL)).replace("PESO_SECCION", str(PESO_SECCION))
              .replace("PESO_ALIAS", str(PESO_ALIAS)).replace("UMBRAL_ALIAS", str(UMBRAL_ALIAS)))

ARMAR_CONSULTA = r"""const b = $('Preparar búsqueda').first().json;
// se descartan fragmentos repetidos y los de parecido muy bajo (ruido); maximo 10 fragmentos
const MINIMO = 0.45, MAXIMO = 10;
const vistos = new Set();
// si la busqueda salio debil y se reformulo la pregunta, se usan los resultados de la segunda busqueda
const segunda = $('Buscar de nuevo').isExecuted;
const fuente = segunda ? $('Buscar de nuevo').all() : $('Buscar en manuales').all();
const tema = segunda ? $('Nueva búsqueda').first().json.tema : '';
const frags = fuente.map((i) => i.json).filter((f) => {
  if (!f || !f.text || vistos.has(f.text)) return false;
  const s = parseFloat(f.similitud);
  if (!isNaN(s) && s < MINIMO) return false;
  vistos.add(f.text);
  return true;
}).slice(0, MAXIMO);
const meta = (f) => (typeof f.metadata === 'string' ? JSON.parse(f.metadata) : (f.metadata || {}));
// en un seguimiento, la primera pagina de continuacion es la ultima ya explicada: su seccion es el tema actual.
// las paginas siguientes de OTRA seccion se marcan como otro tema, para que la IA lo ofrezca en vez de explicarlo.
const CONT = 'página siguiente a lo ya explicado';
const actual = frags.find((f) => f.similitud === CONT);
const seccionActual = actual ? (meta(actual).seccion || '') : '';
const paginaActual = actual ? Number(meta(actual).pagina) : null;
const bloques = frags.map((f, i) => {
  const md = meta(f);
  const tipo = isNaN(parseFloat(f.similitud)) ? f.similitud : `parecido ${f.similitud}`;
  const otroTema = f.similitud === CONT && seccionActual && md.seccion && md.seccion !== seccionActual && Number(md.pagina) > paginaActual;
  return [
    `### Fragmento ${i + 1} (${tipo})`,
    ...(otroTema ? [`AVISO: este fragmento es de la sección "${md.seccion}", distinta de la que se venía explicando ("${seccionActual}"). Es OTRO tema: no lo expliques; di que el procedimiento actual terminó y ofrécelo nombrándolo.`] : []),
    `Manual: ${md.manual}`,
    `Sección: ${md.seccion || 'sin sección'}`,
    `Página: ${md.pagina ?? 'sin página'}`,
    `pagina_url: ${md.pagina_url || 'ninguna'}`,
    `imagenes_url: ${(md.imagenes_url || []).join(' ') || 'ninguna'}`,
    'Contenido:',
    f.text,
  ].join('\n');
}).join('\n\n');
const prompt = 'CONVERSACIÓN PREVIA:\n' + (b.historial || '(es el primer mensaje)') +
  ((b.glosario || tema) ? '\n\nTÉRMINOS EQUIVALENTES (palabras del cliente y su nombre en NAVASOFT):\n' +
    [b.glosario, tema ? 'Según el índice de los manuales, el cliente probablemente se refiere a: ' + tema : ''].filter(Boolean).join('\n') : '') +
  '\n\nFRAGMENTOS DE LOS MANUALES ENCONTRADOS PARA ESTA CONSULTA:\n' + (bloques || '(ninguno)') +
  '\n\nNUEVA CONSULTA DEL CLIENTE:\n' + b.pregunta;
// n8n procesa el texto como plantilla: se quitan las llaves para que no lo confunda
return [{ json: { prompt: prompt.replace(/[{}]/g, '') } }];"""

# Pasos finales: la IA a veces omite las capturas o pone demasiadas. Se buscan las capturas
# de las paginas que cito la respuesta y se dejan como maximo 2.
PREPARAR_RESPUESTA = r"""const output = String($input.first().json.text || $input.first().json.output || '').trim();
const paginas = [...new Set(output.match(/https?:\/\/[^\s)>]+\/navasoft-pagina\?id=[0-9a-f]{12}/g) || [])];
// n8n no acepta un parametro vacio en la consulta: 'ninguna' no coincide con ninguna pagina
return [{ json: { output, paginas: paginas.join(',') || 'ninguna' } }];"""

CAPTURAS_SQL = """SELECT u.url
FROM chunks_bge_m3 c, jsonb_array_elements_text(c.metadata->'imagenes_url') WITH ORDINALITY AS u(url, n)
WHERE c.metadata->>'pagina_url' = ANY(string_to_array($1, ','))
ORDER BY (c.metadata->>'pagina')::int, u.n
LIMIT 4"""

RESPUESTA_FINAL = r"""const MAX = 2;
let output = $('Preparar respuesta').first().json.output.replace(/\]\(<([^>]+)>\)/g, ']($1)');
// la bienvenida es solo para quien saluda o pregunta quien es el asistente (regla 10); a veces la IA la agrega igual
if (!/^\s*¡?\s*(hola|buen[oa]s|saludos|qui[eé]n eres|qu[eé] eres)/i.test($('Preparar búsqueda').first().json.pregunta)) {
  output = output.replace(/^\s*¡?hola!?[,.]?\s*(bienvenid[^.\n]*\.\s*)?(soy tu asistente[^.\n]*\.\s*)?/i, '');
}
const urls = $input.all().map((i) => i.json.url).filter(Boolean);
// las sugerencias de la IA se separan y se agregan al final como marca que el portal convierte en botones
let sugerencias = [];
output = output.replace(/^\s*\**SUGERENCIAS:?\**\s*(.+)$/im, (_, s) => {
  sugerencias = s.split('|').map((x) => x.replace(/[*_]/g, '').trim()).filter((x) => x.length > 3 && x.length < 120).slice(0, 3);
  return '';
}).trim();
// si la respuesta solo pide una aclaracion (termina en pregunta y no trae pasos), va sin fuentes ni capturas
const cuerpo = output.split('📄')[0].replace(/!\[[^\]]*\]\([^)]+\)/g, '').trim();
const soloPregunta = /\?\s*$/.test(cuerpo) && !/\*\*[^*\n]+\s(→|–|-)\s[^*\n]+\*\*/.test(cuerpo);
if (soloPregunta) { output = cuerpo; sugerencias = []; }
let vistas = 0;
output = output.replace(/!\[[^\]]*\]\([^)]+\)\n?/g, (img) => (++vistas <= MAX ? img : ''));
// si la respuesta dice que los manuales no tienen la informacion, no se agregan capturas
// las mismas frases que admin_calidad en portal/esquema.sql: si se cambia una, cambiar la otra
const sinInfo = /no (se encuentra|contienen|cuento|está disponible|detallan|dispongo|encuentro)|lamentablemente|lamento informar|ningún fragmento|ninguno de los/i.test(output);
if (sinInfo) sugerencias = [];
if (vistas === 0 && urls.length && !sinInfo && !soloPregunta) {
  const bloque = urls.slice(0, MAX).map((u) => `![Pantalla de NAVASOFT](${u})`).join('\n\n');
  const fuente = output.search(/\n[^\n]*📄/);
  output = fuente >= 0 ? output.slice(0, fuente) + '\n\n' + bloque + '\n' + output.slice(fuente) : output + '\n\n' + bloque;
}
if (!output) output = 'Lo siento, en este momento no pude responder. Intenta nuevamente en unos segundos.';
output = output.replace(/\n{3,}/g, '\n\n');
if (sugerencias.length) output += `\n\n[[sugerencias: ${sugerencias.join(' | ')}]]`;
// solo se guarda para reutilizar una primera pregunta de tipo "como / que / donde" respondida con pasos de los
// manuales; los reportes de problemas ("no me cuadra", "no se envio") dependen de cada caso y no se guardan
const b = $('Preparar búsqueda').first().json;
const esConsultaDeUso = /^\s*¿?\s*(c[oó]mo|qu[eé]|d[oó]nde|cu[aá]l(es)?|para qu[eé]|puedo|se puede)\b/i.test(b.pregunta);
const guardar = b.primera === 'si' && esConsultaDeUso && output.includes('navasoft-pagina?id=') && !sinInfo && !soloPregunta;
return [{ json: { output, guardar: guardar ? 'si' : 'no', clave: b.clave } }];"""

GUARDAR_SQL = """WITH g AS (
  INSERT INTO respuestas_cache (clave, respuesta) SELECT $1, $2 WHERE $3 = 'si'
  ON CONFLICT (clave) DO UPDATE SET respuesta = EXCLUDED.respuesta, creado = now()
  RETURNING 1
)
SELECT $2::text AS output"""


# Red de seguridad: si la busqueda sale debil (nada parecido y sin termino del glosario), una llamada corta a la IA
# barata traduce la pregunta al tema del manual con la lista de temas, y se busca otra vez. Solo en esos casos.
UMBRAL_DEBIL = 0.62

MEDIR_BUSQUEDA = r"""const b = $('Preparar búsqueda').first().json;
const sims = $input.all().map((i) => parseFloat(i.json.similitud)).filter((s) => !isNaN(s));
const mejor = sims.length ? Math.max(...sims) : 0;
// un saludo o una palabra suelta no se reformula
const corta = b.pregunta.split(/\s+/).length < 2;
return [{ json: { debil: !b.glosario && !corta && mejor < UMBRAL, mejor } }];"""

REFORMULAR = """Eres un clasificador. Un cliente de NAVASOFT (un ERP) escribió una consulta con sus propias palabras. Indica a qué tema de los manuales se refiere, eligiendo de esta lista:
TEMAS_LISTA

Responde SOLO con una línea: hasta 2 temas de la lista, copiados exactamente (solo el nombre del tema, sin el ejemplo) y separados por " | ". Si la consulta no corresponde a ningún tema (saludo, otro asunto), responde NINGUNO."""

NUEVA_BUSQUEDA = r"""const b = $('Preparar búsqueda').first().json;
const r = String($input.first().json.text || '').trim().split('\n')[0];
const tema = (!r || /ningun/i.test(r)) ? '' : r.replace(/["*]/g, '').slice(0, 200);
return [{ json: { tema, busqueda: tema ? b.busqueda + ' ' + tema.replace(/\|/g, ' ') : b.busqueda } }];"""


def temas_para_reformular():
    """Lista de temas de los manuales (de alias_secciones.json) con un ejemplo de como lo pide un cliente."""
    datos = json.loads((BASE / "alias_secciones.json").read_text(encoding="utf-8"))
    lineas = []
    for archivo, temas in datos.items():
        if archivo.startswith("_"):
            continue
        manual = archivo.split("\\")[-1].replace("Manual de ", "").replace("_V5.pdf", "").replace(" V5.pdf", "")
        lineas += [f"- {tema} ({manual}): ej. {frases[0]}" for _, tema, frases in temas]
    return "\n".join(lineas)


def nodo(id_, nombre, tipo, version, pos, params, **extra):
    return {"id": id_, "name": nombre, "type": tipo, "typeVersion": version, "position": pos, "parameters": params, **extra}


def asegurar_credencial_interna():
    """Clave compartida entre el portal y el asistente: sin ella nadie mas puede usar el asistente."""
    env = BASE / ".env"
    lineas = env.read_text(encoding="utf-8").splitlines()
    clave = next((l.split("=", 1)[1] for l in lineas if l.startswith("ASISTENTE_CLAVE=")), None)
    if not clave:
        clave = secrets.token_urlsafe(32)
        env.write_text("\n".join(lineas + [f"ASISTENTE_CLAVE={clave}"]) + "\n", encoding="utf-8")
    archivo_id = AQUI / "credencial_interna.id"
    if archivo_id.exists():
        return {"httpHeaderAuth": {"id": archivo_id.read_text().strip(), "name": "Clave interna NAVASOFT"}}
    r = requests.post(f"{API}/credentials", headers=H, timeout=30, json={
        "name": "Clave interna NAVASOFT", "type": "httpHeaderAuth", "data": {"name": CABECERA_CLAVE, "value": clave}})
    r.raise_for_status()
    archivo_id.write_text(r.json()["id"])
    return {"httpHeaderAuth": {"id": r.json()["id"], "name": "Clave interna NAVASOFT"}}


def construir(cred_interna, cred_claude=None, cred_openrouter=None):
    """cred_openrouter y cred_claude: credenciales en n8n de los respaldos (en ese orden: primero el gratuito).
    Si no se pasa ninguna, el flujo queda solo con Gemini y Groq."""
    reintentos = {"retryOnFail": True, "maxTries": 2, "waitBetweenTries": 2000}
    pg = lambda id_, nombre, pos, sql, params: nodo(id_, nombre, "n8n-nodes-base.postgres", 2.5, pos, {
        "operation": "executeQuery", "query": sql, "options": {"queryReplacement": params}}, credentials=CRED_PG, alwaysOutputData=True)
    nodes = [
        nodo("a1", "Consulta interna", "n8n-nodes-base.webhook", 2, [0, 0], {
            "httpMethod": "POST", "path": "navasoft-asistente", "authentication": "headerAuth",
            "responseMode": "lastNode", "options": {}}, credentials=cred_interna,
             webhookId="4e8b2c71-9a3d-4f60-b5e2-7c1d0a9f3e58"),
        pg("b1", "Historial reciente", [220, 0], HISTORIAL_SQL, "={{ [ String($json.body.sessionId || '') ] }}"),
        nodo("b2", "Preparar búsqueda", "n8n-nodes-base.code", 2, [440, 0], {"jsCode": PREPARAR_BUSQUEDA.replace("GLOSARIO_JSON", json.dumps(GLOSARIO, ensure_ascii=False))}),
        nodo("d1", "¿Pide el índice?", "n8n-nodes-base.if", 2, [560, 0], {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                           "conditions": [{"id": "i1", "leftValue": "={{ $json.indice }}", "rightValue": "si",
                                           "operator": {"type": "string", "operation": "equals"}}],
                           "combinator": "and"}, "options": {}}),
        pg("d2", "Índice del manual", [760, -320], INDICE_SQL, "={{ [ $json.palabras ] }}"),
        nodo("d3", "Responder índice", "n8n-nodes-base.code", 2, [980, -320], {"jsCode": RESPONDER_INDICE}),
        pg("c1", "Buscar respuesta guardada", [660, 0], USAR_GUARDADA_SQL, "={{ [ $json.clave, $json.primera ] }}"),
        nodo("c2", "¿Ya estaba respondida?", "n8n-nodes-base.if", 2, [880, 0], {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                           "conditions": [{"id": "g1", "leftValue": "={{ $json.output }}", "rightValue": "",
                                           "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}}],
                           "combinator": "and"}, "options": {}}),
        nodo("c3", "Respuesta guardada", "n8n-nodes-base.code", 2, [1100, -160],
             {"jsCode": "return [{ json: { output: $input.first().json.output } }];"}),
        nodo("b3", "Vectorizar consulta", "n8n-nodes-base.httpRequest", 4.2, [1100, 0], {
            "method": "POST", "url": "http://127.0.0.1:11434/api/embed", "sendBody": True, "specifyBody": "json",
            # keep_alive: el modelo de busqueda queda cargado 3 horas (si no, Ollama lo descarga a los 5 minutos)
            "jsonBody": "={{ JSON.stringify({ model: 'bge-m3', input: $('Preparar búsqueda').first().json.busqueda, keep_alive: '3h' }) }}",
            "options": {"timeout": 60000}}, **reintentos),
        pg("b4", "Buscar en manuales", [1320, 0], BUSCAR_SQL,
           "={{ [ JSON.stringify($json.embeddings[0]), $('Preparar búsqueda').first().json.citadas, $('Preparar búsqueda').first().json.busqueda ] }}"),
        nodo("r1", "Medir búsqueda", "n8n-nodes-base.code", 2, [1430, 160],
             {"jsCode": MEDIR_BUSQUEDA.replace("UMBRAL", str(UMBRAL_DEBIL))}),
        nodo("r2", "¿Búsqueda débil?", "n8n-nodes-base.if", 2, [1430, 320], {
            "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                           "conditions": [{"id": "w1", "leftValue": "={{ $json.debil }}", "rightValue": True,
                                           "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                           "combinator": "and"}, "options": {}}),
        # sin reintentos y sin detener el flujo: si la IA barata falla, se responde con la primera busqueda
        nodo("r3", "Reformular consulta", "@n8n/n8n-nodes-langchain.chainLlm", 1.7, [1430, 500], {
            "promptType": "define", "text": "={{ 'Consulta del cliente: ' + $('Preparar búsqueda').first().json.busqueda }}",
            "hasOutputParser": False,
            "messages": {"messageValues": [{"type": "SystemMessagePromptTemplate",
                                            "message": REFORMULAR.replace("TEMAS_LISTA", temas_para_reformular())}]}},
             onError="continueRegularOutput"),
        nodo("r4", "Gemini reformular", "@n8n/n8n-nodes-langchain.lmChatGoogleGemini", 1, [1430, 700], {
            "modelName": "models/gemini-3.5-flash-lite", "options": {"temperature": 0, "maxOutputTokens": 60}},
             credentials=CRED_GEMINI),
        nodo("r5", "Nueva búsqueda", "n8n-nodes-base.code", 2, [1650, 500], {"jsCode": NUEVA_BUSQUEDA}),
        nodo("r6", "Vectorizar de nuevo", "n8n-nodes-base.httpRequest", 4.2, [1650, 700], {
            "method": "POST", "url": "http://127.0.0.1:11434/api/embed", "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ model: 'bge-m3', input: $json.busqueda, keep_alive: '3h' }) }}",
            "options": {"timeout": 60000}}, **reintentos),
        pg("r7", "Buscar de nuevo", [1650, 900], BUSCAR_SQL,
           "={{ [ JSON.stringify($json.embeddings[0]), $('Preparar búsqueda').first().json.citadas, $('Nueva búsqueda').first().json.busqueda ] }}"),
        nodo("b5", "Armar consulta para la IA", "n8n-nodes-base.code", 2, [1540, 0], {"jsCode": ARMAR_CONSULTA}),
        nodo("a2", "Asistente NAVASOFT", "@n8n/n8n-nodes-langchain.chainLlm", 1.7, [1760, 0], {
            "promptType": "define", "text": "={{ $json.prompt }}", "hasOutputParser": False, "needsFallback": True,
            "messages": {"messageValues": [{"type": "SystemMessagePromptTemplate", "message": REGLAS}]}},
             **reintentos),
        nodo("a3", "Gemini", "@n8n/n8n-nodes-langchain.lmChatGoogleGemini", 1, [1680, 220], {
            "modelName": "models/gemini-3.5-flash-lite", "options": {"temperature": 0.1}},
             credentials=CRED_GEMINI, **reintentos),
        nodo("a7", "Groq respaldo", "@n8n/n8n-nodes-langchain.lmChatGroq", 1, [1840, 220], {
            "model": "openai/gpt-oss-120b", "options": {"temperature": 0.1}},
             credentials=CRED_GROQ, **reintentos),
        nodo("f1", "Preparar respuesta", "n8n-nodes-base.code", 2, [2000, 0], {"jsCode": PREPARAR_RESPUESTA}),
        # como lista: si se pasa el texto suelto, n8n lo parte por las comas y solo usa la primera pagina
        pg("f2", "Capturas de páginas citadas", [2220, 0], CAPTURAS_SQL, "={{ [ $json.paginas ] }}"),
        nodo("f3", "Respuesta final", "n8n-nodes-base.code", 2, [2440, 0], {"jsCode": RESPUESTA_FINAL}),
        pg("f4", "Guardar para reutilizar", [2660, 0], GUARDAR_SQL, "={{ [ $json.clave, $json.output, $json.guardar ] }}"),
    ]
    # Respaldos en cadena: si Gemini y Groq fallan, el asistente sale por su salida de error y el siguiente
    # modelo redacta con la misma consulta; si ese tambien falla, pasa al que sigue.
    respaldos = []
    if cred_openrouter:
        respaldos.append(("OpenRouter", nodo("a11", "OpenRouter respaldo", "@n8n/n8n-nodes-langchain.lmChatOpenRouter", 1, [0, 0], {
            "model": MODELO_OPENROUTER, "options": {"temperature": 0.1}}, credentials=cred_openrouter, **reintentos)))
    if cred_claude:
        respaldos.append(("Claude", nodo("a9", "Claude respaldo", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, [0, 0], {
            "model": {"__rl": True, "mode": "id", "value": MODELO_CLAUDE}, "options": {}},
             credentials=cred_claude, **reintentos)))
    cadena = ["Asistente NAVASOFT"] + [f"Asistente NAVASOFT ({nombre})" for nombre, _ in respaldos]
    for i, (nombre, modelo) in enumerate(respaldos):
        next(n for n in nodes if n["name"] == cadena[i])["onError"] = "continueErrorOutput"
        modelo["position"] = [1760 + 240 * i, 660]
        nodes += [
            nodo("a8" if nombre == "Claude" else "a10", cadena[i + 1], "@n8n/n8n-nodes-langchain.chainLlm", 1.7, [1760 + 240 * i, 440], {
                "promptType": "define", "text": "={{ $('Armar consulta para la IA').first().json.prompt }}",
                "hasOutputParser": False,
                "messages": {"messageValues": [{"type": "SystemMessagePromptTemplate", "message": REGLAS}]}},
                 **reintentos),
            modelo,
        ]
    a = lambda *destinos: {"main": [[{"node": d, "type": "main", "index": 0}] for d in destinos]}
    connections = {
        "Consulta interna": a("Historial reciente"),
        "Historial reciente": a("Preparar búsqueda"),
        "Preparar búsqueda": a("¿Pide el índice?"),
        "¿Pide el índice?": a("Índice del manual", "Buscar respuesta guardada"),
        "Índice del manual": a("Responder índice"),
        "Buscar respuesta guardada": a("¿Ya estaba respondida?"),
        "¿Ya estaba respondida?": a("Respuesta guardada", "Vectorizar consulta"),
        "Vectorizar consulta": a("Buscar en manuales"),
        "Buscar en manuales": a("Medir búsqueda"),
        "Medir búsqueda": a("¿Búsqueda débil?"),
        "¿Búsqueda débil?": a("Reformular consulta", "Armar consulta para la IA"),
        "Gemini reformular": {"ai_languageModel": [[{"node": "Reformular consulta", "type": "ai_languageModel", "index": 0}]]},
        "Reformular consulta": a("Nueva búsqueda"),
        "Nueva búsqueda": a("Vectorizar de nuevo"),
        "Vectorizar de nuevo": a("Buscar de nuevo"),
        "Buscar de nuevo": a("Armar consulta para la IA"),
        "Armar consulta para la IA": a("Asistente NAVASOFT"),
        "Gemini": {"ai_languageModel": [[{"node": "Asistente NAVASOFT", "type": "ai_languageModel", "index": 0}]]},
        "Groq respaldo": {"ai_languageModel": [[{"node": "Asistente NAVASOFT", "type": "ai_languageModel", "index": 1}]]},
        "Asistente NAVASOFT": a("Preparar respuesta"),
        "Preparar respuesta": a("Capturas de páginas citadas"),
        "Capturas de páginas citadas": a("Respuesta final"),
        "Respuesta final": a("Guardar para reutilizar"),
    }
    for i, (nombre, modelo) in enumerate(respaldos):
        connections[cadena[i]] = a("Preparar respuesta", cadena[i + 1])
        connections[cadena[i + 1]] = a("Preparar respuesta")
        connections[modelo["name"]] = {"ai_languageModel": [[
            {"node": cadena[i + 1], "type": "ai_languageModel", "index": 0}]]}
    return {"name": "NAVASOFT - Chatbot de ayuda", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}}


def vaciar_respuestas_guardadas():
    """Al cambiar las reglas, las respuestas guardadas se descartan para que se generen con las reglas nuevas."""
    env = dict(l.split("=", 1) for l in (BASE / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
    with psycopg.connect(host="127.0.0.1", port=5432, dbname=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
                         password=env["POSTGRES_PASSWORD"], autocommit=True) as con:
        con.execute("TRUNCATE respuestas_cache")


def main():
    sys.exit("El asistente ahora esta en la nube: publica con migracion/publicar_nube.py")
    wf = construir(asegurar_credencial_interna())
    (AQUI / "chatbot.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    r = requests.put(f"{API}/workflows/{WORKFLOW_ID}", json=wf, headers=H, timeout=180)
    r.raise_for_status()
    vaciar_respuestas_guardadas()
    print("Publicado:", r.json()["name"], "| activo:", r.json()["active"], "| respuestas guardadas vaciadas")


if __name__ == "__main__":
    main()
