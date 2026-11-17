"""Crea o actualiza en n8n el workflow del portal con inicio de sesion:
  GET  /webhook/navasoft-portal  -> la pagina (portal.html)
  POST /webhook/navasoft-api     -> acciones (login, conversaciones, preguntas, administracion)
Toda la logica de usuarios esta en la funcion navasoft_api de PostgreSQL (esquema.sql)."""
import json
import pathlib
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8")
AQUI = pathlib.Path(__file__).parent
API_N8N = "http://localhost:5678/api/v1"
KEY = next(l.split("=", 1)[1].strip() for l in open(r"C:\mcp-n8n\.env", encoding="utf-8") if l.startswith("N8N_API_KEY="))
H = {"X-N8N-API-KEY": KEY}
ID_ARCHIVO = AQUI / "portal.id"
# el asistente solo acepta pedidos que traigan la clave interna (credencial creada por n8n/publicar_chatbot.py)
CHAT_INTERNO = "http://localhost:5678/webhook/navasoft-asistente"
_ID_CRED = (AQUI.parent / "n8n" / "credencial_interna.id")
CRED_INTERNA = {"httpHeaderAuth": {"id": _ID_CRED.read_text().strip() if _ID_CRED.exists() else "", "name": "Clave interna NAVASOFT"}}
CRED_PG = {"postgres": {"id": "SqW5cZj7KdT9Lbyu", "name": "Base de datos NAVASOFT"}}

# lo que la pagina puede cargar y a donde puede enviar datos: limita el dano si algo malicioso llegara a ejecutarse
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; media-src 'self' blob:; worker-src 'self' blob:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
# el historial de n8n no guarda los datos de este flujo: traen contrasenas, tokens, audios y capturas
SIN_HISTORIAL = {"executionOrder": "v1", "saveDataSuccessExecution": "none", "saveDataErrorExecution": "none",
                 "saveManualExecutions": False, "saveExecutionProgress": False}

SQL_API = "SELECT navasoft_api(($1::jsonb)->>'accion', $1::jsonb) AS r"
CRED_GEMINI = {"googlePalmApi": {"id": "YbrX4mPubLFww3W5", "name": "Gemini NAVASOFT"}}
CRED_GROQ = {"groqApi": {"id": "F1zpkcgXPrBt9cVH", "name": "Groq account"}}
URL_TITULO = "http://localhost:5678/webhook/navasoft-titulo"

# Titulos de conversacion: se generan con IA despues de responder, hasta que el chat tenga un tema claro.
DATOS_CHAT_SQL = """SELECT c.titulo_fijo,
       coalesce(string_agg(left(m.texto, 300), ' | ' ORDER BY m.id) FILTER (WHERE m.rol = 'usuario'), '') AS preguntas
FROM conversaciones c LEFT JOIN mensajes m ON m.conversacion_id = c.id
WHERE c.id = $1::uuid
GROUP BY c.id, c.titulo_fijo"""

PROMPT_TITULO = """Escribe un título corto (de 2 a 6 palabras) en español que resuma el tema principal de esta conversación de soporte del sistema NAVASOFT, para que el cliente la reconozca rápido en su historial.
Ejemplos de buenos títulos: Apertura de caja chica / Registro de factura de venta / Envío de boletas a SUNAT / Reembolso de caja chica.
Si el cliente solo saludó o todavía no planteó ningún tema, responde exactamente: Nueva conversación
Responde solo con el título, sin comillas, sin punto final y sin explicaciones.

Mensajes del cliente en orden:
"""

LIMPIAR_TITULO = r"""let t = String($input.first().json.text || '').split('\n').map((s) => s.trim()).filter(Boolean)[0] || '';
t = t.replace(/^(t[ií]tulo\s*:\s*)/i, '').replace(/^["'«“*]+|["'»”*.]+$/g, '').trim();
if (!t || t.length > 70) t = 'Nueva conversación';
t = t.charAt(0).toUpperCase() + t.slice(1);
return [{ json: { titulo: t, fijo: !/^nueva conversaci[oó]n$/i.test(t) } }];"""

PROMPT_SUGERENCIAS = """Un cliente del sistema NAVASOFT va a pedir ayuda a un especialista de soporte de EKAM PERÚ por WhatsApp.
Según su conversación con el asistente virtual, escribe 3 mensajes distintos que el cliente podría enviar, en primera persona,
breves (máximo 110 caracteres cada uno) y concretos: menciona el módulo, la pantalla, el mensaje de error o el documento si aparecen.
Uno debe decir qué intentó hacer y qué no funcionó. No inventes datos que no estén en la conversación.
Responde solo con los 3 mensajes, uno por línea, sin numeración, sin comillas y sin explicaciones.

Conversación:
"""

LIMPIAR_SUGERENCIAS = r"""const lineas = String($input.first().json.text || '').split('\n')
  .map((s) => s.replace(/^\s*([-*•]|\d+[.)])\s*/, '').replace(/^["'«“]+|["'»”]+$/g, '').trim())
  .filter((s) => s.length >= 8 && s.length <= 160);
return [{ json: { ok: true, sugerencias: [...new Set(lineas)].slice(0, 3) } }];"""

GUARDAR_TITULO_SQL = """UPDATE conversaciones SET titulo = $2, titulo_fijo = ($3)::boolean
WHERE id::text = $1 AND NOT titulo_fijo"""

# Dictado por voz: el portal graba el audio (funciona en cualquier navegador) y aqui se pasa a texto con
# Whisper de Groq (gratis). Solo para usuarios con sesion iniciada.
URL_WHISPER = "https://api.groq.com/openai/v1/audio/transcriptions"
# Sin "prompt" de pista: con silencios, Whisper repetia la frase de pista como si el cliente la hubiera dicho.
# Los silencios ademas se quitan en el portal antes de enviar el audio.
# Whisper marca cada tramo con la probabilidad de que NO sea voz; los tramos de ruido o voces de fondo se descartan
RESPUESTA_VOZ = """={{ (() => {
  if ($json.text === undefined) {
    const m = JSON.stringify($json.error || $json);
    return { ok: false, limite: /429|rate.?limit/i.test(m), error: 'No se pudo pasar la voz a texto. Intenta de nuevo.' };
  }
  const tramos = $json.segments || [];
  const texto = tramos.length
    ? tramos.filter((s) => !(s.no_speech_prob > 0.6 && s.avg_logprob < -0.7)).map((s) => s.text).join('')
    : String($json.text);
  return { ok: true, texto: texto.replace(/\\s+/g, ' ').trim() };
})() }}"""

# Captura del cliente: el portal envia la imagen de su pantalla y Gemini (que entiende imagenes) la describe en
# texto; esa descripcion viaja con la pregunta para buscar en los manuales. La imagen no se guarda en ningun lado.
URL_GEMINI_VISION = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
# si el modelo ligero esta saturado (error 503) o falla, se prueba con el completo
URL_GEMINI_VISION_2 = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"
PROMPT_CAPTURA = """Eres soporte del ERP peruano NAVASOFT. El cliente envió esta captura de su pantalla.
Descríbela en español, en máximo 70 palabras y con este formato exacto:
Pantalla: <módulo y nombre de la ventana o formulario que se ve, por ejemplo Ventas > Factura de venta>
Mensaje: <texto exacto de cualquier error, advertencia o aviso visible; "ninguno" si no hay>
Situación: <qué estaba haciendo el cliente o qué botón o campo parece relevante>
No inventes nada que no se vea. No copies RUC, montos, nombres de clientes ni otros datos de la empresa.
Si la imagen no es una pantalla de NAVASOFT ni de un sistema, responde solo: No es una pantalla del sistema."""
RESPUESTA_CAPTURA = r"""={{ (() => {
  const t = (((($json.candidates || [])[0] || {}).content || {}).parts || []).map((p) => p.text || '').join('').trim();
  if (!t) {
    const m = JSON.stringify($json.error || $json);
    return { ok: false, limite: /429|quota|rate.?limit/i.test(m), error: 'No se pudo leer la captura. Escribe el mensaje de error que ves en pantalla.' };
  }
  return { ok: true, descripcion: t.replace(/\s*\n\s*/g, ' · ').replace(/\s+/g, ' ').slice(0, 600) };
})() }}"""

# Pagina del caso para la consultora (enlace del mensaje de WhatsApp): conversacion completa con capturas.
# Todo el texto se escapa; la pagina no carga nada externo ni ejecuta scripts (ver CSP_CASO).
CSP_CASO = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
PAGINA_CASO = r"""const c = $input.first().json.r || {};
const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (x) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[x]));
const fecha = (iso) => new Date(iso).toLocaleString('es-PE', { timeZone: 'America/Lima', dateStyle: 'short', timeStyle: 'short' });
// el texto del asistente viene en Markdown: se dejan solo negritas y saltos de linea
const bot = (t) => esc(String(t).replace(/!\[[^\]]*\]\([^)]+\)/g, '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
  .replace(/\[\[sugerencias:[^\]]*\]\]/g, '').trim()).replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>');
const usuario = (t) => {
  const [propio, desc] = String(t).split('[Captura adjunta]');
  return esc(propio.trim()).replace(/\n/g, '<br>') + (desc ? `<div class="desc">Lectura automática de la captura: ${esc(desc.trim())}</div>` : '');
};
let cuerpo;
if (!c.ok) {
  cuerpo = '<section class="vacio"><h1>Enlace no válido o vencido</h1><p>Los casos de soporte se pueden ver durante 30 días después de la solicitud. Pide al cliente su número de solicitud.</p></section>';
} else {
  const capturas = (c.mensajes || []).filter((m) => m.captura).length;
  const msgs = (c.mensajes || []).map((m) => `<div class="m ${m.rol === 'bot' ? 'b' : 'u'}"><div class="quien">${m.rol === 'bot' ? 'Asistente' : 'Cliente'}<span>${fecha(m.creado)}</span></div>`
    + (m.captura && /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(m.captura) ? `<a class="cap" href="${m.captura}" target="_blank" title="Abrir en tamaño completo"><img src="${m.captura}" alt="Captura del cliente"></a>` : '')
    + `<div class="t">${m.rol === 'bot' ? bot(m.texto) : usuario(m.texto)}</div></div>`).join('');
  cuerpo = `<header class="cab"><div class="logo" role="img" aria-label="EKAM PERÚ"></div>
<span class="estado ${c.estado === 'atendido' ? 'ok' : ''}">${c.estado === 'atendido' ? 'Atendida' : 'Abierta'}</span></header>
<div class="caso"><aside class="ficha"><p class="sup">Solicitud de soporte</p><h1>N.º ${esc(c.ticket)}</h1>
<dl><div><dt>Cliente</dt><dd>${esc(c.nombre)}</dd></div>${c.empresa ? `<div><dt>Empresa</dt><dd>${esc(c.empresa)}</dd></div>` : ''}
<div><dt>Fecha</dt><dd>${fecha(c.creado)}</dd></div><div><dt>Capturas</dt><dd>${capturas}</dd></div></dl>
<div class="necesita"><p class="sup">Qué necesita</p><p>${esc(c.detalle).replace(/\n/g, '<br>')}</p></div></aside>
<section class="chat"><h2>Conversación con el asistente</h2>${msgs || '<p class="nota">El cliente pidió soporte sin conversación previa.</p>'}
<p class="pie">🔒 Enlace privado: no lo reenvíes. Vence 30 días después de la solicitud.</p></section></div>`;
}
const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><meta http-equiv="Content-Security-Policy" content="CSP_META"><title>Solicitud de soporte · EKAM PERÚ</title><style>
:root{--azul:#001858;--azul-2:#13307e;--dorado:#f58a00;--dorado-2:#fff3e3;--fondo:#f3f2f7;--texto:#111a33;--suave:#5e6680;--verde:#1f8f4e;--verde-2:#e5f6ec;
--sombra:0 1px 2px rgba(17,26,51,.04),0 2px 8px rgba(17,26,51,.05)}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--texto);-webkit-font-smoothing:antialiased;
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:max(16px,env(safe-area-inset-top)) max(16px,env(safe-area-inset-right)) 48px max(16px,env(safe-area-inset-left))}
.cab{display:flex;align-items:center;justify-content:space-between;margin:4px 0 16px}
.logo{width:132px;height:52px;background:#fff url('/webhook/navasoft-img?id=logo-ekam&v=2') center/contain no-repeat;background-origin:content-box;padding:6px 10px;border-radius:14px;box-shadow:var(--sombra)}
.estado{font-size:.8rem;font-weight:600;padding:5px 12px;border-radius:999px;background:var(--dorado-2);color:#a85400}.estado.ok{background:var(--verde-2);color:var(--verde)}
.ficha{background:linear-gradient(160deg,#13307e 0%,#001858 100%);color:#fff;border-radius:22px;padding:20px 20px 18px;box-shadow:0 12px 32px rgba(0,24,88,.22)}
.sup{margin:0;font-size:.75rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;opacity:.7}
h1{margin:2px 0 14px;font-size:clamp(1.35rem,1rem + 2vw,1.9rem);letter-spacing:-.02em}
dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(130px,100%),1fr));gap:10px 16px;margin:0 0 16px}dt{font-size:.75rem;opacity:.65}dd{margin:0;font-weight:600;overflow-wrap:anywhere}
.necesita{background:rgba(255,255,255,.1);border-left:3px solid var(--dorado);border-radius:12px;padding:10px 14px}.necesita p:last-child{margin:4px 0 0}
h2{font-size:1rem;margin:28px 4px 12px;color:var(--suave);font-weight:600}
.m{max-width:88%;margin:0 0 12px;padding:12px 16px;overflow-wrap:anywhere;box-shadow:var(--sombra)}
.m.b{background:#fff;border-radius:6px 22px 22px 22px}
.m.u{margin-left:auto;background:linear-gradient(180deg,#13307e 0%,#001858 100%);color:#fff;border-radius:22px 22px 6px 22px}
.quien{display:flex;gap:8px;align-items:baseline;font-size:.78rem;font-weight:600;margin-bottom:4px}.m.b .quien{color:#a85400}
.quien span{font-weight:400;opacity:.65}
.cap img{display:block;max-width:100%;max-height:440px;border-radius:12px;margin:6px 0 8px;background:#fff;cursor:zoom-in}
.desc{margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,.2);font-size:.8rem;opacity:.75}
.nota{color:var(--suave)}.pie{margin:28px 0 0;text-align:center;font-size:.8rem;color:var(--suave)}
.vacio{background:#fff;border-radius:22px;padding:28px 22px;text-align:center;box-shadow:var(--sombra);margin-top:12vh}.vacio h1{font-size:1.3rem}.vacio p{color:var(--suave);margin:0}
@media (max-width:520px){.m{max-width:96%;padding:11px 14px}.ficha{padding:18px 16px 16px;border-radius:20px}.logo{width:112px;height:46px}}
/* tablet horizontal y PC: ficha fija a la izquierda y conversacion a la derecha */
@media (min-width:900px){main{max-width:1180px;padding:24px 32px 56px}
  .caso{display:grid;grid-template-columns:minmax(300px,360px) minmax(0,1fr);gap:32px;align-items:start}
  .ficha{position:sticky;top:24px}.chat h2{margin-top:4px}.m{max-width:80%}.cap img{max-height:520px}}
@media (min-width:1600px){main{max-width:1320px}body{font-size:16px}}
@media print{body{background:#fff}.ficha{position:static;box-shadow:none}.m{box-shadow:none;border:1px solid #ddd;break-inside:avoid}}
</style></head><body><main>${cuerpo}</main></body></html>`;
return [{ json: { html, estado: c.ok ? 200 : 404 } }];"""



def meta_csp(csp):
    return "; ".join(x for x in csp.split("; ") if not x.startswith("frame-ancestors"))


PAGINA_CASO = PAGINA_CASO.replace("CSP_META", meta_csp(CSP_CASO))


def nodo(id_, nombre, tipo, version, pos, params, **extra):
    return {"id": id_, "name": nombre, "type": tipo, "typeVersion": version, "position": pos, "parameters": params, **extra}


def construir():
    # n8n descarta la cabecera Content-Security-Policy de los webhooks: la politica va tambien dentro del HTML
    # (frame-ancestors no vale en una etiqueta meta y el navegador lo ignora ahi)
    pagina = (AQUI / "portal.html").read_text(encoding="utf-8").replace(
        '<meta charset="utf-8">', f'<meta charset="utf-8">\n<meta http-equiv="Content-Security-Policy" content="{meta_csp(CSP)}">', 1)
    nodes = [
        nodo("p1", "Página del portal", "n8n-nodes-base.webhook", 2, [0, -220],
             {"httpMethod": "GET", "path": "navasoft-portal", "responseMode": "responseNode", "options": {}},
             webhookId="5c0e7a3d-2f61-4a8e-b1d4-7e9a0c3f5b21"),
        nodo("p2", "Enviar página", "n8n-nodes-base.respondToWebhook", 1.1, [240, -220],
             {"respondWith": "text", "responseBody": pagina,
              "options": {"responseHeaders": {"entries": [
                  {"name": "Content-Type", "value": "text/html; charset=utf-8"},
                  {"name": "Cache-Control", "value": "no-cache"},
                  {"name": "Content-Security-Policy", "value": CSP}]}}}),

        nodo("p3", "Portal API", "n8n-nodes-base.webhook", 2, [0, 0],
             {"httpMethod": "POST", "path": "navasoft-api", "responseMode": "responseNode", "options": {}},
             webhookId="9a4d2b6e-8c13-4f77-a5e0-3b1f6d9c2e48"),
        nodo("p4", "Ejecutar acción", "n8n-nodes-base.postgres", 2.5, [220, 0],
             {"operation": "executeQuery", "query": SQL_API,
              "options": {"queryReplacement": "={{ [ JSON.stringify($json.body || {}) ] }}"}},
             credentials=CRED_PG),
        nodo("p5", "¿Es una pregunta para el bot?", "n8n-nodes-base.if", 2, [440, 0], {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [
                    {"id": "c1", "leftValue": "={{ $('Portal API').first().json.body.accion }}", "rightValue": "nueva_pregunta",
                     "operator": {"type": "string", "operation": "equals"}},
                    {"id": "c2", "leftValue": "={{ $json.r.ok }}", "rightValue": True,
                     "operator": {"type": "boolean", "operation": "true", "singleValue": True}},
                ],
                "combinator": "and"},
            "options": {}}),
        nodo("p6", "Preguntar al asistente", "n8n-nodes-base.httpRequest", 4.2, [660, -100], {
            "method": "POST", "url": CHAT_INTERNO, "sendBody": True, "specifyBody": "json",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "jsonBody": "={{ JSON.stringify({ sessionId: $json.r.conversacion_id, chatInput: $json.r.texto }) }}",
            "options": {"timeout": 150000}},
             credentials=CRED_INTERNA, onError="continueRegularOutput"),
        nodo("p7", "Guardar respuesta", "n8n-nodes-base.postgres", 2.5, [880, -100], {
            "operation": "executeQuery", "query": "SELECT navasoft_guardar_respuesta($1::uuid, $2) AS r",
            "options": {"queryReplacement": (
                "={{ [ $('Ejecutar acción').first().json.r.conversacion_id, $json.output || '' ] }}")}},
             credentials=CRED_PG),
        nodo("p8", "Responder con la respuesta", "n8n-nodes-base.respondToWebhook", 1.1, [1100, -100],
             {"respondWith": "json", "responseBody": "={{ $json.r }}", "options": {}}),
        nodo("p9", "Responder", "n8n-nodes-base.respondToWebhook", 1.1, [660, 120],
             {"respondWith": "json", "responseBody": "={{ $json.r }}", "options": {}}),
        # despues de responder al cliente, se pide (sin esperar) que se actualice el titulo del chat
        nodo("p10", "Pedir título del chat", "n8n-nodes-base.httpRequest", 4.2, [1320, -100], {
            "method": "POST", "url": URL_TITULO, "sendBody": True, "specifyBody": "json",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "jsonBody": "={{ JSON.stringify({ conversacion_id: $('Ejecutar acción').first().json.r.conversacion_id }) }}",
            "options": {"timeout": 60000}}, credentials=CRED_INTERNA, onError="continueRegularOutput"),

        # ---- generador de titulos (tambien se usa para titular chats antiguos)
        nodo("t1", "Pedido de título", "n8n-nodes-base.webhook", 2, [0, 360],
             {"httpMethod": "POST", "path": "navasoft-titulo", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
             credentials=CRED_INTERNA, webhookId="c3e1b7a2-4d59-4f0b-9a86-2e7f5d1c8b37"),
        nodo("t2", "Datos del chat", "n8n-nodes-base.postgres", 2.5, [220, 360], {
            "operation": "executeQuery", "query": DATOS_CHAT_SQL,
            "options": {"queryReplacement": "={{ [ String($json.body.conversacion_id || '') ] }}"}},
             credentials=CRED_PG, alwaysOutputData=True),
        nodo("t3", "¿Necesita título?", "n8n-nodes-base.if", 2, [440, 360], {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [
                    {"id": "t1", "leftValue": "={{ $json.titulo_fijo }}", "rightValue": False,
                     "operator": {"type": "boolean", "operation": "false", "singleValue": True}},
                    {"id": "t2", "leftValue": "={{ $json.preguntas }}", "rightValue": "",
                     "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}},
                ],
                "combinator": "and"},
            "options": {}}),
        nodo("t4", "Crear título", "@n8n/n8n-nodes-langchain.chainLlm", 1.7, [660, 360], {
            "promptType": "define", "hasOutputParser": False, "needsFallback": True,
            "text": "=" + PROMPT_TITULO + "{{ String($json.preguntas).replace(/[{}]/g, '') }}"},
             retryOnFail=True, maxTries=2, waitBetweenTries=1500),
        nodo("t5", "Groq títulos", "@n8n/n8n-nodes-langchain.lmChatGroq", 1, [600, 560],
             {"model": "openai/gpt-oss-120b", "options": {"temperature": 0.2}}, credentials=CRED_GROQ),
        nodo("t6", "Gemini títulos", "@n8n/n8n-nodes-langchain.lmChatGoogleGemini", 1, [740, 560],
             {"modelName": "models/gemini-3.5-flash-lite", "options": {"temperature": 0.2}}, credentials=CRED_GEMINI),
        nodo("t7", "Limpiar título", "n8n-nodes-base.code", 2, [880, 360], {"jsCode": LIMPIAR_TITULO}),
        nodo("t8", "Guardar título", "n8n-nodes-base.postgres", 2.5, [1100, 360], {
            "operation": "executeQuery", "query": GUARDAR_TITULO_SQL,
            "options": {"queryReplacement": (
                "={{ [ String($('Pedido de título').first().json.body.conversacion_id), $json.titulo, String($json.fijo) ] }}")}},
             credentials=CRED_PG, alwaysOutputData=True),

        # ---- sugerencias para el mensaje a soporte (segun el chat)
        nodo("g1", "Pedido de sugerencias", "n8n-nodes-base.webhook", 2, [0, 1700],
             {"httpMethod": "POST", "path": "navasoft-sugerencias", "responseMode": "responseNode", "options": {}},
             webhookId="d2a6c9e4-5b17-4f3a-8e60-1c9b7f4a2d35"),
        nodo("g2", "Contexto del chat", "n8n-nodes-base.postgres", 2.5, [220, 1700], {
            "operation": "executeQuery", "query": "SELECT navasoft_api('sugerir_soporte', $1::jsonb) AS r",
            "options": {"queryReplacement": "={{ [ JSON.stringify({ token: $json.body.token || '', conversacion_id: $json.body.conversacion_id || '' }) ] }}"}},
             credentials=CRED_PG),
        nodo("g3", "¿Hay contexto?", "n8n-nodes-base.if", 2, [440, 1700], {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [
                    {"id": "g1", "leftValue": "={{ $json.r.ok }}", "rightValue": True,
                     "operator": {"type": "boolean", "operation": "true", "singleValue": True}},
                    {"id": "g2", "leftValue": "={{ $json.r.contexto }}", "rightValue": "",
                     "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}},
                ],
                "combinator": "and"},
            "options": {}}),
        nodo("g4", "Crear sugerencias", "@n8n/n8n-nodes-langchain.chainLlm", 1.7, [660, 1640], {
            "promptType": "define", "hasOutputParser": False, "needsFallback": True,
            "text": "=" + PROMPT_SUGERENCIAS + "{{ String($json.r.contexto).replace(/[{}]/g, '') }}"},
             retryOnFail=True, maxTries=2, waitBetweenTries=1000, onError="continueRegularOutput"),
        nodo("g5", "Gemini sugerencias", "@n8n/n8n-nodes-langchain.lmChatGoogleGemini", 1, [600, 1840],
             {"modelName": "models/gemini-3.5-flash-lite", "options": {"temperature": 0.4}}, credentials=CRED_GEMINI),
        nodo("g6", "Groq sugerencias", "@n8n/n8n-nodes-langchain.lmChatGroq", 1, [740, 1840],
             {"model": "openai/gpt-oss-120b", "options": {"temperature": 0.4}}, credentials=CRED_GROQ),
        nodo("g7", "Limpiar sugerencias", "n8n-nodes-base.code", 2, [880, 1640], {"jsCode": LIMPIAR_SUGERENCIAS}),
        nodo("g8", "Enviar sugerencias", "n8n-nodes-base.respondToWebhook", 1.1, [1100, 1640],
             {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}}),
        nodo("g9", "Sin sugerencias", "n8n-nodes-base.respondToWebhook", 1.1, [660, 1800], {
            "respondWith": "json",
            "responseBody": "={{ { ok: false, sesion: $json.r.sesion, error: $json.r.error || 'Sin conversación' } }}",
            "options": {}}),

        # ---- dictado por voz
        nodo("v1", "Audio dictado", "n8n-nodes-base.webhook", 2, [0, 760],
             {"httpMethod": "POST", "path": "navasoft-voz", "responseMode": "responseNode", "options": {}},
             webhookId="e7b4c2d9-1a6f-4c38-8e52-9d0f3a7b6c14"),
        nodo("v2", "Revisar sesión", "n8n-nodes-base.postgres", 2.5, [220, 760], {
            "operation": "executeQuery", "query": "SELECT navasoft_api('usar_ia', $1::jsonb) AS r",
            "options": {"queryReplacement": "={{ [ JSON.stringify({ token: $json.body.token || '' }) ] }}"}},
             credentials=CRED_PG),
        nodo("v3", "¿Sesión válida y con audio?", "n8n-nodes-base.if", 2, [440, 760], {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [
                    {"id": "v1", "leftValue": "={{ $json.r.ok }}", "rightValue": True,
                     "operator": {"type": "boolean", "operation": "true", "singleValue": True}},
                    {"id": "v2", "leftValue": "={{ $('Audio dictado').first().json.body.audio }}", "rightValue": "",
                     "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}},
                ],
                "combinator": "and"},
            "options": {}}),
        nodo("v8", "Tomar audio", "n8n-nodes-base.code", 2, [600, 640], {"jsCode": (
            "const b = $('Audio dictado').first().json.body;\n"
            "return [{ json: { audio: String(b.audio).replace(/^data:[^,]*,/, ''), tipo: String(b.tipo || 'audio/webm').split(';')[0] } }];")}),
        nodo("v4", "Preparar audio", "n8n-nodes-base.convertToFile", 1.1, [760, 700], {
            "operation": "toBinary", "sourceProperty": "audio",
            "options": {"fileName": "={{ 'dictado.' + ({ 'audio/ogg': 'ogg', 'audio/mp4': 'mp4', 'audio/wav': 'wav', 'audio/mpeg': 'mp3' }[$json.tipo] || 'webm') }}",
                        "mimeType": "={{ $json.tipo }}"}}),
        nodo("v5", "Pasar voz a texto", "n8n-nodes-base.httpRequest", 4.2, [880, 700], {
            "method": "POST", "url": URL_WHISPER,
            "authentication": "predefinedCredentialType", "nodeCredentialType": "groqApi",
            "sendBody": True, "contentType": "multipart-form-data",
            "bodyParameters": {"parameters": [
                {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "data"},
                {"name": "model", "value": "whisper-large-v3-turbo"},
                {"name": "language", "value": "es"},
                {"name": "temperature", "value": "0"},
                {"name": "response_format", "value": "verbose_json"}]},
            "options": {"timeout": 60000}},
             credentials=CRED_GROQ, onError="continueRegularOutput"),
        nodo("v6", "Enviar texto dictado", "n8n-nodes-base.respondToWebhook", 1.1, [1100, 700], {
            "respondWith": "json",
            "responseBody": RESPUESTA_VOZ,
            "options": {}}),
        nodo("v7", "Rechazar dictado", "n8n-nodes-base.respondToWebhook", 1.1, [660, 880], {
            "respondWith": "json",
            "responseBody": "={{ $json.r.ok ? { ok: false, error: 'No llegó el audio.' } : $json.r.sesion === false ? { ok: false, sesion: false, error: 'Tu sesión terminó. Vuelve a ingresar.' } : { ok: false, error: $json.r.error } }}",
            "options": {}}),

        # ---- captura de pantalla del cliente
        nodo("k1", "Captura del cliente", "n8n-nodes-base.webhook", 2, [0, 1080],
             {"httpMethod": "POST", "path": "navasoft-captura", "responseMode": "responseNode", "options": {}},
             webhookId="4f2a9c61-7d3e-4b85-a0c2-6e1d8b5f9a73"),
        nodo("k2", "Revisar sesión (captura)", "n8n-nodes-base.postgres", 2.5, [220, 1080], {
            "operation": "executeQuery", "query": "SELECT navasoft_api('usar_ia', $1::jsonb) AS r",
            "options": {"queryReplacement": "={{ [ JSON.stringify({ token: $json.body.token || '' }) ] }}"}},
             credentials=CRED_PG),
        nodo("k3", "¿Sesión válida y con imagen?", "n8n-nodes-base.if", 2, [440, 1080], {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [
                    {"id": "k1", "leftValue": "={{ $json.r.ok }}", "rightValue": True,
                     "operator": {"type": "boolean", "operation": "true", "singleValue": True}},
                    {"id": "k2", "leftValue": "={{ $('Captura del cliente').first().json.body.imagen }}", "rightValue": "",
                     "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}},
                ],
                "combinator": "and"},
            "options": {}}),
        nodo("k4", "Leer captura", "n8n-nodes-base.httpRequest", 4.2, [660, 1020], {
            "method": "POST", "url": URL_GEMINI_VISION,
            "authentication": "predefinedCredentialType", "nodeCredentialType": "googlePalmApi",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": ("={{ JSON.stringify({ contents: [{ parts: [ { text: " + json.dumps(PROMPT_CAPTURA) + " }, "
                         "{ inline_data: { mime_type: (String($('Captura del cliente').first().json.body.imagen).match(/^data:([^;,]+)/) || [])[1] || 'image/jpeg', "
                         "data: String($('Captura del cliente').first().json.body.imagen).replace(/^data:[^,]*,/, '') } } ] }], "
                         "generationConfig: { temperature: 0.1, maxOutputTokens: 400 } }) }}"),
            "options": {"timeout": 25000}},
             credentials=CRED_GEMINI, onError="continueErrorOutput", retryOnFail=True, maxTries=2, waitBetweenTries=1000),
        nodo("k7", "Leer captura (respaldo)", "n8n-nodes-base.httpRequest", 4.2, [780, 1140], {
            "method": "POST", "url": URL_GEMINI_VISION_2,
            "authentication": "predefinedCredentialType", "nodeCredentialType": "googlePalmApi",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": ("={{ JSON.stringify({ contents: [{ parts: [ { text: " + json.dumps(PROMPT_CAPTURA) + " }, "
                         "{ inline_data: { mime_type: (String($('Captura del cliente').first().json.body.imagen).match(/^data:([^;,]+)/) || [])[1] || 'image/jpeg', "
                         "data: String($('Captura del cliente').first().json.body.imagen).replace(/^data:[^,]*,/, '') } } ] }], "
                         "generationConfig: { temperature: 0.1, maxOutputTokens: 400 } }) }}"),
            "options": {"timeout": 25000}},
             credentials=CRED_GEMINI, onError="continueRegularOutput", retryOnFail=True, maxTries=2, waitBetweenTries=1000),
        nodo("k5", "Enviar descripción", "n8n-nodes-base.respondToWebhook", 1.1, [880, 1020],
             {"respondWith": "json", "responseBody": RESPUESTA_CAPTURA, "options": {}}),
        nodo("k6", "Rechazar captura", "n8n-nodes-base.respondToWebhook", 1.1, [660, 1180], {
            "respondWith": "json",
            "responseBody": "={{ $json.r.ok ? { ok: false, error: 'No llegó la imagen.' } : $json.r.sesion === false ? { ok: false, sesion: false, error: 'Tu sesión terminó. Vuelve a ingresar.' } : { ok: false, error: $json.r.error } }}",
            "options": {}}),

        # ---- caso de soporte para la consultora (enlace privado del mensaje de WhatsApp)
        nodo("s1", "Caso de soporte", "n8n-nodes-base.webhook", 2, [0, 1400],
             {"httpMethod": "GET", "path": "navasoft-caso", "responseMode": "responseNode", "options": {}},
             webhookId="b8d3f1a7-2c64-4e9b-9f05-7a1c3e6d2b84"),
        nodo("s2", "Datos del caso", "n8n-nodes-base.postgres", 2.5, [220, 1400], {
            "operation": "executeQuery", "query": "SELECT navasoft_caso($1) AS r",
            "options": {"queryReplacement": "={{ [ String($json.query.id || '') ] }}"}},
             credentials=CRED_PG),
        nodo("s3", "Armar página del caso", "n8n-nodes-base.code", 2, [440, 1400], {"jsCode": PAGINA_CASO}),
        nodo("s4", "Enviar caso", "n8n-nodes-base.respondToWebhook", 1.1, [660, 1400],
             {"respondWith": "text", "responseBody": "={{ $json.html }}",
              "options": {"responseCode": "={{ $json.estado }}", "responseHeaders": {"entries": [
                  {"name": "Content-Type", "value": "text/html; charset=utf-8"},
                  {"name": "Cache-Control", "value": "no-store"},
                  {"name": "X-Robots-Tag", "value": "noindex, nofollow"},
                  {"name": "Referrer-Policy", "value": "no-referrer"},
                  {"name": "Content-Security-Policy", "value": CSP_CASO}]}}}),
    ]
    a = lambda destino, i=0: {"node": destino, "type": "main", "index": i}
    connections = {
        "Página del portal": {"main": [[a("Enviar página")]]},
        "Portal API": {"main": [[a("Ejecutar acción")]]},
        "Ejecutar acción": {"main": [[a("¿Es una pregunta para el bot?")]]},
        "¿Es una pregunta para el bot?": {"main": [[a("Preguntar al asistente")], [a("Responder")]]},
        "Preguntar al asistente": {"main": [[a("Guardar respuesta")]]},
        "Guardar respuesta": {"main": [[a("Responder con la respuesta")]]},
        "Responder con la respuesta": {"main": [[a("Pedir título del chat")]]},
        "Pedido de título": {"main": [[a("Datos del chat")]]},
        "Datos del chat": {"main": [[a("¿Necesita título?")]]},
        "¿Necesita título?": {"main": [[a("Crear título")], []]},
        "Groq títulos": {"ai_languageModel": [[{"node": "Crear título", "type": "ai_languageModel", "index": 0}]]},
        "Gemini títulos": {"ai_languageModel": [[{"node": "Crear título", "type": "ai_languageModel", "index": 1}]]},
        "Crear título": {"main": [[a("Limpiar título")]]},
        "Limpiar título": {"main": [[a("Guardar título")]]},
        "Pedido de sugerencias": {"main": [[a("Contexto del chat")]]},
        "Contexto del chat": {"main": [[a("¿Hay contexto?")]]},
        "¿Hay contexto?": {"main": [[a("Crear sugerencias")], [a("Sin sugerencias")]]},
        "Gemini sugerencias": {"ai_languageModel": [[{"node": "Crear sugerencias", "type": "ai_languageModel", "index": 0}]]},
        "Groq sugerencias": {"ai_languageModel": [[{"node": "Crear sugerencias", "type": "ai_languageModel", "index": 1}]]},
        "Crear sugerencias": {"main": [[a("Limpiar sugerencias")]]},
        "Limpiar sugerencias": {"main": [[a("Enviar sugerencias")]]},
        "Audio dictado": {"main": [[a("Revisar sesión")]]},
        "Revisar sesión": {"main": [[a("¿Sesión válida y con audio?")]]},
        "¿Sesión válida y con audio?": {"main": [[a("Tomar audio")], [a("Rechazar dictado")]]},
        "Tomar audio": {"main": [[a("Preparar audio")]]},
        "Preparar audio": {"main": [[a("Pasar voz a texto")]]},
        "Pasar voz a texto": {"main": [[a("Enviar texto dictado")]]},
        "Captura del cliente": {"main": [[a("Revisar sesión (captura)")]]},
        "Revisar sesión (captura)": {"main": [[a("¿Sesión válida y con imagen?")]]},
        "¿Sesión válida y con imagen?": {"main": [[a("Leer captura")], [a("Rechazar captura")]]},
        "Leer captura": {"main": [[a("Enviar descripción")], [a("Leer captura (respaldo)")]]},
        "Leer captura (respaldo)": {"main": [[a("Enviar descripción")]]},
        "Caso de soporte": {"main": [[a("Datos del caso")]]},
        "Datos del caso": {"main": [[a("Armar página del caso")]]},
        "Armar página del caso": {"main": [[a("Enviar caso")]]},
    }
    return {"name": "NAVASOFT - Portal con inicio de sesión", "nodes": nodes, "connections": connections,
            "settings": SIN_HISTORIAL}


def main():
    sys.exit("El asistente ahora esta en la nube: publica con migracion/publicar_nube.py")
    wf = construir()
    (AQUI / "portal_workflow.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    if ID_ARCHIVO.exists():
        wid = ID_ARCHIVO.read_text().strip()
        r = requests.put(f"{API_N8N}/workflows/{wid}", json=wf, headers=H, timeout=30)
    else:
        r = requests.post(f"{API_N8N}/workflows", json=wf, headers=H, timeout=30)
    r.raise_for_status()
    wid = r.json()["id"]
    ID_ARCHIVO.write_text(wid)
    act = requests.post(f"{API_N8N}/workflows/{wid}/activate", json={}, headers=H, timeout=30)
    act.raise_for_status()
    print(f"Portal publicado (id {wid}), activo: {act.json()['active']}")
    print("Abrir: http://localhost:5678/webhook/navasoft-portal")


if __name__ == "__main__":
    main()
