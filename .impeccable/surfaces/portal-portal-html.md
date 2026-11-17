---
version: 1
slug: "portal-portal-html"
primary_target: "portal/portal.html"
related_targets: []
---

# Portal del Asistente NAVASOFT

Scope: portal/portal.html (login, cambio de clave, chat, guía paso a paso, visor, zona admin). Mode: Operate. Escritorio y celular por igual.
Audiencia: clientes de EKAM que usan NAVASOFT; tarea: preguntar y seguir pasos con capturas, ver la fuente, pasar a soporte.
Constraints: colores EKAM (#001858, #13307e, #24459f, #f58a00); conservar todo el HTML, ids y JavaScript; sin framework.

## Direction contract

THESIS: Cada respuesta del asistente se entrega como un voucher: un comprobante blanco con pasos en casillas numeradas y la fuente sellada como referencia. Rechaza el chat genérico de burbujas grises con sombras y degradados.

OWN-WORLD: Barra lateral y cabecera de acceso en azul marino #001858 sólido; papel blanco con filete fino; neutros de una sola rampa del azul; naranja #f58a00 solo para la acción principal, el sello de la fuente y el paso actual. Public Sans para todo; JetBrains Mono solo para números de paso y referencias. Esquinas de 4–6 px, sin degradados ni sombras decorativas, retícula de 8 px. Trama fina de seguridad solo en la franja superior del voucher.

STORY: El cliente pregunta, recibe un comprobante que sabe leer: pasos numerados, capturas, de qué manual y página sale, y qué preguntar después. Si no basta, pasa a soporte en un clic.

FIRST VIEWPORT: Barra lateral azul de 280 px (logo EKAM, Nueva consulta naranja, buscador, conversaciones, usuario abajo); cabecera blanca de 64 px con el título y Hablar con soporte; hilo centrado a 880 px máx.; pregunta del cliente como bloque azul a la derecha; respuesta como voucher con franja de cabecera (hora + sello VENTAS · PÁG. 78), cuerpo a 68ch, pie con sugerencias; caja de texto fija abajo con Enviar azul.

FORM: Voucher bancario, posición 5 de 7 en mi lista; seed: b3ff47a94d325f2f

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
