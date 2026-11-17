@echo off
title Asistente NAVASOFT - EKAM PERU (no cerrar esta ventana)
rem Enciende todo con un solo clic: Docker (base de datos), Ollama (busqueda), n8n (asistente y portal)
rem y abre el portal en el navegador. Mientras uses el chat, deja esta ventana abierta.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar_asistente.ps1"
call "%~dp0INICIAR-N8N.bat"
