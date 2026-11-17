# Asistente NAVASOFT: decisiones pendientes para el ingeniero

Estado al 01/11/2026: el asistente funciona en `https://n8n.srv2106635.hstgr.cloud/webhook/navasoft-portal`, en el
VPS compartido. La base y Ollama están en `/docker/navasoft`, sin puertos abiertos a internet. Hay respaldo diario en
el mismo servidor (08:00 UTC, 7 días); se comprobó restaurándolo en una base temporal.

## 1. Subdominio propio para el portal

**Hecho el 17/11/2026:** el portal está en `https://chatbot-ekam.ekamperu.com` (registro A en el cPanel de Datec
hacia 179.66.128.21). Las rutas de Traefik están en las etiquetas de `procesador/docker-compose.yml`, así que no se
tocó la configuración de n8n. Solo se publican `/webhook/navasoft-...` y `/navasoft-procesador`; el resto de n8n
da 404 en ese dominio. El portal lleva su propia `Content-Security-Policy` como cabecera, y la dirección vieja del
portal redirige a la nueva. Los enlaces guardados en la base ya apuntan al dominio nuevo.

**Hecho el 17/11/2026 (n8n reiniciado; copia del archivo anterior en `docker-compose.yml.antes-sandbox-2026-11-17`):** se quitó `N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX` de
`/docker/n8n/docker-compose.yml` y recrear el contenedor de n8n. El portal no lo necesita, porque su cabecera
reemplaza la de n8n, pero antes hay que confirmar que ningún otro flujo sirva páginas HTML que dependan de él.
Después, probar el micrófono en un celular real. Lo que sigue es el análisis original:

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

**Hecho (17/11):** límite de 60 pedidos por minuto por IP (ráfagas de 40) en Traefik, y el bloqueo por intentos fallidos ahora es por cuenta e IP (tabla `intentos_login`): quien se equivoca solo se bloquea a sí mismo; la cuenta entera se bloquea solo con 30 fallos desde varias IP.
puede bloquear una cuenta ajena 10 minutos con cinco intentos fallidos.

## 2. Otras decisiones

| Tema | Situación | Hay que decidir |
|---|---|---|
| Copia fuera del servidor | **Preparado (17/11):** el respaldo diario incluye los manuales del portal y se envía por FTP cifrado al cPanel de Datec (5 días). `migracion/traer_respaldo.ps1` queda solo para traer una copia a mano | Crear la cuenta FTP y guardar su clave: `migracion/PLAN_TRASPASO.md`, sección 3 |
| Firewall y SSH | **Hecho (17/11):** `ufw` activo (solo 22, 80, 443). Desde internet SSH solo con llave; la terminal del navegador de Hostinger (169.254.0.1) sigue con contraseña. Copias: `sshd_config.antes-2026-11-17` | Nada |
| Imágenes de los manuales | `navasoft-img` y `navasoft-pagina` se abren sin sesión con el enlace | Si es aceptable o deben exigir sesión |
| Traefik | Usa `traefik` sin versión | Fijar una versión probada |
| Carga de manuales | `migracion/sincronizar_nube.ps1` corre en la laptop con una llave de root sin frase de seguridad | Mover la carga al servidor o usar un acceso con menos permisos |
| WhatsApp de soporte | **Hecho (17/11):** número definitivo +51 949 882 756. El cliente pulsa enviar | Número definitivo; API de WhatsApp Business si se quieren avisos automáticos |
| Repositorio | Público en GitHub (RaizaArce/chatbot-ekam), una sola versión sin historial | El historial completo queda en la rama `master` local: no subirlo |
| Plan del VPS | Vence el 28/11/2026 | Confirmar la renovación |

## 3. Antes de abrirlo a clientes

- **Hecho (17/11):** `admin.ekam` desactivada (seguía con la clave inicial; se reactiva desde Administración → Usuarios) y borrado `portal/credenciales_iniciales.txt`. La cuenta de administración en uso es `prueba.admin`. Falta decidir si se quitan las cuentas de prueba (`cliente.prueba`, `mperez`) antes de abrir a clientes.
- Quitar la llave `navasoft-migracion` de `/root/.ssh/authorized_keys`, según lo que se decida sobre los manuales.
- Probar el reinicio del VPS y el uso con varias personas a la vez.
