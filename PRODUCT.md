# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Clientes de EKAM PERÚ que usan el ERP NAVASOFT (contadores, asistentes contables, cajeros, almaceneros y personal de ventas de empresas peruanas), además del personal de soporte de EKAM. Lo abren al lado de NAVASOFT cuando no saben cómo hacer un proceso (registrar una factura, abrir una caja chica, emitir una guía de remisión) o desde el celular para una consulta rápida. Lo usan por igual en computadora y celular.

## Product Purpose
Portal del Asistente NAVASOFT: un chat que responde, paso a paso y con capturas, cómo hacer cada proceso del ERP, citando el manual y la página exacta. Existe para que el cliente resuelva solo lo que está en los manuales y llegue a soporte humano solo cuando hace falta. Éxito: el cliente sigue los pasos y termina su tarea en NAVASOFT sin llamar a soporte.

## Positioning
Responde únicamente con los manuales oficiales de NAVASOFT de EKAM, cita la fuente (manual y página) y muestra las capturas reales de la pantalla del sistema; cuando no está en los manuales lo dice y deriva a soporte.

## Operating Context
- Cuentas creadas por EKAM (usuario y contraseña, cambio obligatorio la primera vez); roles cliente y administrador.
- Pantallas: inicio de sesión, cambio de contraseña, chat con lista de conversaciones (buscar, nueva, renombrar, borrar), modo guía paso a paso, visor de capturas, dictado por voz, valoración 👍/👎, botón "Hablar con soporte" (tickets).
- Zona de administración: tickets de soporte, panel de calidad (conversaciones y valoraciones), usuarios (crear cuentas, generar claves).
- Se sirve como una sola página HTML desde un webhook de n8n (portal/portal.html, publicado con portal/publicar_portal.py).

## Capabilities and Constraints
- Página única sin framework: HTML, CSS y JavaScript en un archivo; librerías por CDN (marked, DOMPurify).
- Las respuestas llegan en Markdown con pasos numerados, imágenes de capturas, enlaces a la fuente y sugerencias de siguiente pregunta.
- Funciona en escritorio y celular.

## Brand Commitments
- Marca: EKAM PERÚ; producto: NAVASOFT. Colores de EKAM obligatorios: azul marino #001858 (con #13307e y #24459f) y naranja #f58a00. El usuario pidió mantener estos colores y cambiar el diseño.
- Sensación pedida: sobria y profesional. Lo que no le gusta del diseño anterior: se ve genérico, recargado y anticuado.
- Voz: español de Perú, trato de "tú", claro y directo.

## Evidence on Hand
- Logo de EKAM ya incrustado en el portal.
- Manuales oficiales de NAVASOFT cargados en la base (no inventar módulos, clientes ni cifras).

## Product Principles
1. La respuesta del manual es el centro: los pasos y capturas deben leerse sin esfuerzo.
2. Siempre mostrar de dónde sale la respuesta (manual y página).
3. Sobrio y confiable, como el software contable que acompaña.
4. Igual de usable en celular que en computadora.
5. Llevar a soporte humano sin fricción cuando el manual no alcanza.
