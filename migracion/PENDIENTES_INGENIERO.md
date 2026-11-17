# Asistente NAVASOFT: decisiones pendientes para el ingeniero

Estado al 01/11/2026: el asistente funciona en `https://n8n.srv2106635.hstgr.cloud/webhook/navasoft-portal`, en el
VPS compartido. La base y Ollama están en `/docker/navasoft`, sin puertos abiertos a internet. Hay respaldo diario en
el mismo servidor (08:00 UTC, 7 días); se comprobó restaurándolo en una base temporal.

## 1. Subdominio propio para el portal (crítico antes de abrir a clientes)

**Problema.** El portal comparte dirección con el panel de n8n y `N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX=true`
está activo en todo el n8n. Una página maliciosa servida por cualquier flujo podría actuar con la sesión de quien
tenga el panel abierto, incluida la cuenta owner. El ajuste es necesario hoy porque, sin él, el navegador bloquea el
micrófono y el guardado de la sesión.

**Propuesta (sin probar todavía).**
1. Crear un registro DNS, por ejemplo `asistente.ekamperu.com`, hacia la IP del VPS.
2. En `/docker/n8n/docker-compose.yml`, añadir a n8n un segundo router de Traefik para ese dominio, limitado a
   `PathPrefix(/webhook/navasoft-)`.
3. En ese router, reemplazar la cabecera `Content-Security-Policy` por la del portal (`CSP` en
   `portal/publicar_portal.py`), para quitar el aislamiento solo en el portal.
4. Quitar `N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX` y comprobar el micrófono en un celular real.
5. En la base, cambiar la dirección guardada en `chunks_bge_m3.metadata`, `manual_indice.pagina_url` y `mensajes`
   (igual que en `MIGRACION_HOSTINGER.md`, punto 4), vaciar `respuestas_cache` y actualizar `URL_PUBLICA`.

Con ese router también se puede poner un límite de pedidos por IP al inicio de sesión. Hoy no existe, y cualquiera
puede bloquear una cuenta ajena 10 minutos con cinco intentos fallidos.

## 2. Otras decisiones

| Tema | Situación | Hay que decidir |
|---|---|---|
| Copia fuera del servidor | Las copias diarias están en el mismo VPS | Dónde guardarlas; revisar también las copias semanales de Hostinger |
| Firewall y SSH | `ufw` inactivo; root entra por contraseña. Abiertos: 22, 80, 443 | Activar firewall y usar solo llaves. Hay riesgo de quedarse sin acceso: conservar la consola web |
| Imágenes de los manuales | `navasoft-img` y `navasoft-pagina` se abren sin sesión con el enlace | Si es aceptable o deben exigir sesión |
| Traefik | Usa `traefik` sin versión | Fijar una versión probada |
| Carga de manuales | `migracion/sincronizar_nube.ps1` corre en la laptop con una llave de root sin frase de seguridad | Mover la carga al servidor o usar un acceso con menos permisos |
| WhatsApp de soporte | El cliente pulsa enviar; el número 940455332 es de prueba | Número definitivo; API de WhatsApp Business si se quieren avisos automáticos |
| Repositorio | Git solo en la laptop | Crear un repositorio remoto privado |
| Plan del VPS | Vence el 28/11/2026 | Confirmar la renovación |

## 3. Antes de abrirlo a clientes

- Desactivar `prueba.admin`, cambiar las demás contraseñas y borrar `portal/credenciales_iniciales.txt`.
- Quitar la llave `navasoft-migracion` de `/root/.ssh/authorized_keys`, según lo que se decida sobre los manuales.
- Probar el reinicio del VPS y el uso con varias personas a la vez.
