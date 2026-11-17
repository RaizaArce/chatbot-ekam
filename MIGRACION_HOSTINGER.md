# Pasar el Asistente NAVASOFT a Hostinger

**Estado (31/10/2026): ya migrado** a `https://n8n.srv2106635.hstgr.cloud/webhook/navasoft-portal`. Base y Ollama
en `/docker/navasoft`. Publicar flujos: `migracion/publicar_nube.py`. Cargar manuales desde la laptop:
`migracion/sincronizar_nube.ps1`. Este documento queda como referencia de lo que se hizo.

Guía para el ingeniero. Este documento dice qué piezas había en la laptop, qué se llevó al servidor y qué hubo
que cambiar.

## 1. Qué plan contratar

El asistente **no funciona en hosting compartido** ni en el "n8n en la nube" sin servidor propio: necesita
Docker, una base PostgreSQL con la extensión pgvector y Ollama con el modelo de búsqueda.

- **Hostinger VPS** (KVM), con la plantilla *Ubuntu 24.04 + n8n* (o Ubuntu con Docker).
- **Mínimo KVM 2 (8 GB de RAM, 2 vCPU)**. El modelo de búsqueda `bge-m3` ocupa ~2,5 GB de RAM, n8n ~1 GB y
  PostgreSQL ~0,5 GB. Con 4 GB funciona, pero lento y con riesgo de quedarse sin memoria.
- Disco: con 20 GB sobra (la base pesa ~160 MB hoy).
- Un dominio o subdominio (p. ej. `asistente.ekamperu.com`) para tener HTTPS.

## 2. Las piezas

| Pieza | Hoy (laptop) | En el servidor |
|---|---|---|
| Base de datos (manuales, imágenes, páginas, usuarios, conversaciones) | Docker `pgvector/pgvector:pg17`, contenedor `navasoft-db` | El mismo contenedor ([docker-compose.yml](docker-compose.yml)) |
| Búsqueda por significado | Ollama en Windows, modelo `bge-m3` | Contenedor `ollama/ollama` + `ollama pull bge-m3` |
| Chatbot, portal e imágenes | n8n en Windows (4 flujos) | n8n de la plantilla de Hostinger |
| IA que redacta | Gemini (principal) y Groq (respaldo), en internet | Igual; solo hay que volver a cargar las claves. Además, Claude como último respaldo si fallan los dos (`migracion/crear_credencial_claude.ps1`) |
| Carga de manuales | `migracion/sincronizar_nube.ps1` desde la laptop; indexa con el Ollama del servidor (Word local solo para .docx) | Ver punto 6 |
| Guardián, respaldo diario | `guardian_asistente.ps1`, `respaldar.ps1` (Windows) | Docker `restart: unless-stopped` + cron (punto 7) |

## 3. Llevar los datos

1. En la laptop, sacar un respaldo fresco (también se hace solo cada día):
   `powershell -ExecutionPolicy Bypass -File respaldar.ps1`
   Queda en `respaldos\automaticos\<fecha>\`: `navasoft.dump` (toda la base) y `flujos\*.json`.
2. Subir esa carpeta al servidor (`scp`).
3. En el servidor, levantar la base con el mismo `docker-compose.yml` y un `.env` con
   `POSTGRES_USER`, `POSTGRES_PASSWORD` (una **nueva** y fuerte) y `POSTGRES_DB`.
4. Restaurar:
   ```bash
   docker cp navasoft.dump navasoft-db:/tmp/
   docker exec navasoft-db pg_restore -U <usuario> -d <base> --no-owner /tmp/navasoft.dump
   ```

## 4. Cambiar las direcciones `localhost` (importante)

Los enlaces a páginas y capturas que cita el asistente están **guardados dentro de la base** con la dirección
de la laptop (`http://localhost:5678/webhook/...`) — en los 1 204 fragmentos. En el servidor hay que
reescribirlos al dominio nuevo, si no las respuestas traerán enlaces rotos:

```sql
UPDATE chunks_bge_m3
SET metadata = replace(metadata::text, 'http://localhost:5678', 'https://asistente.ekamperu.com')::jsonb
WHERE metadata::text LIKE '%localhost:5678%';
UPDATE manual_indice SET pagina_url = replace(pagina_url, 'http://localhost:5678', 'https://asistente.ekamperu.com');
TRUNCATE respuestas_cache;   -- las respuestas guardadas tienen los enlaces viejos
```

También tienen `localhost` fijo estos archivos, que hay que ajustar antes de publicar desde ahí:
- [n8n/publicar_chatbot.py](n8n/publicar_chatbot.py): la API de n8n (`API = ...`) y Ollama
  (`http://127.0.0.1:11434/api/embed`; en Docker será `http://ollama:11434/api/embed`).
- [portal/publicar_portal.py](portal/publicar_portal.py) y [leer_manuales.py](leer_manuales.py) (al generar los enlaces).
- Las pruebas en [examen/](examen/) usan `localhost:5678`.
- Ambos `publicar_*.py` leen la clave de la API de n8n desde `C:\mcp-n8n\.env`: en el servidor, crear una clave
  nueva en n8n (Settings → n8n API) y leerla de una variable de entorno.

## 5. Pasar los flujos de n8n

1. Importar los 4 archivos de `flujos\` en el n8n del servidor (o mejor: correr `publicar_chatbot.py` y
   `publicar_portal.py` apuntando al servidor, que los crean igual que en la laptop).
2. **Las credenciales no viajan en los JSON.** Crearlas otra vez en n8n y volver a asignarlas a los nodos:
   - PostgreSQL (host `navasoft-db` si están en la misma red de Docker, usuario y contraseña del `.env` nuevo).
   - Gemini (clave de Google AI Studio) y Groq.
   - La clave interna del asistente (`ASISTENTE_CLAVE` del `.env`; la crea `publicar_chatbot.py`).
   - Los IDs de credenciales están fijos en `publicar_chatbot.py` (`CRED_GEMINI`, `CRED_GROQ`): cambiarlos por los nuevos.
3. Variables de entorno de n8n (las mismas de [INICIAR-N8N.bat](INICIAR-N8N.bat)):
   `N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX=true` (sin esto el portal no funciona),
   `EXECUTIONS_DATA_PRUNE=true`, `EXECUTIONS_DATA_MAX_AGE=168`, `EXECUTIONS_DATA_PRUNE_MAX_COUNT=300`,
   y además `WEBHOOK_URL=https://asistente.ekamperu.com/`.
4. Activar los flujos y probar `https://asistente.ekamperu.com/webhook/navasoft-portal`.

## 6. Carga de manuales nuevos

El vigilante actual vigila una carpeta de Windows y usa Word para pasar los `.docx` a PDF: **no corre en Linux**.
Opciones, de la más simple a la más cómoda:

- **A (recomendada para empezar):** seguir cargando desde la laptop. `leer_manuales.py --sincronizar`
  apuntando a la base del servidor por un túnel SSH (`ssh -L 5432:localhost:5432 usuario@servidor`).
  Los manuales se siguen guardando en la misma carpeta de siempre.
- **B:** correr `leer_manuales.py` en el servidor (instalar Python y LibreOffice para los Word) y subir los
  manuales por SFTP o una carpeta compartida.

## 7. Que no se caiga y que haya respaldo

- En `docker-compose.yml`, `restart: unless-stopped` para base, Ollama y n8n: con eso se levantan solos
  si el servidor se reinicia (reemplaza al guardián de Windows).
- Respaldo diario por cron, con la misma idea que `respaldar.ps1`:
  `0 3 * * * docker exec navasoft-db pg_dump -U <usuario> -d <base> -Fc > /respaldos/navasoft_$(date +\%F).dump`
  y borrar los de más de 7 días. Activar también las copias del VPS de Hostinger.
- Prueba de calidad: `examen/prueba_rapida.py` (ajustando las direcciones) una vez al día.

## 8. Seguridad antes de abrirlo a clientes

- Contraseñas nuevas para la base y para las cuentas del portal; **no** subir
  `portal/credenciales_iniciales.txt` al servidor.
- PostgreSQL y Ollama **sin puertos abiertos a internet** (solo n8n detrás de HTTPS). En el compose actual la
  base escucha solo en `127.0.0.1`: mantenerlo así.
- Firewall del VPS: abrir solo 22 (SSH), 80 y 443.

## 9. Lista de verificación final

- [ ] El portal abre por HTTPS e inicia sesión.
- [ ] Una pregunta ("¿Cómo abro una nueva caja chica?") responde con enlace a la página y captura, y los enlaces abren.
- [ ] `prueba_rapida.py` contra el servidor: 22 de 22.
- [ ] Reiniciar el VPS: todo vuelve a responder solo.
- [ ] El respaldo de la noche aparece en `/respaldos`.
- [ ] Apagar el guardián de la laptop (`instalar_guardian.ps1 -Quitar`) cuando el servidor ya esté en uso.
