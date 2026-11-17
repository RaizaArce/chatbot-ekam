@echo off
title n8n - Asistente NAVASOFT (no cerrar esta ventana)
echo ================================================
echo   n8n para el Asistente NAVASOFT - EKAM PERU
echo   No cierres esta ventana mientras uses el chat.
echo ================================================
echo.

rem Permite que el portal (pagina creada en n8n) use la API, el logo y la sesion guardada.
rem Sin esto, n8n "aisla" las paginas de los webhooks y el portal no puede funcionar.
set N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX=true

rem Limpieza automatica del historial de ejecuciones: cada respuesta del chatbot se guarda
rem con todo su detalle y el historial crecia sin limite (lento al abrir n8n).
rem Se conservan las ultimas 300 ejecuciones y como maximo las de los ultimos 7 dias (168 horas).
set EXECUTIONS_DATA_PRUNE=true
set EXECUTIONS_DATA_MAX_AGE=168
set EXECUTIONS_DATA_PRUNE_MAX_COUNT=300

rem Arranque mas rapido: n8n no consulta servicios de internet que el asistente no usa
rem (estadisticas, avisos de version, plantillas, encuesta de personalizacion).
set N8N_DIAGNOSTICS_ENABLED=false
set N8N_VERSION_NOTIFICATIONS_ENABLED=false
set N8N_TEMPLATES_ENABLED=false
set N8N_PERSONALIZATION_ENABLED=false

n8n start
pause
