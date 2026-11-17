# Plan de traspaso del Asistente NAVASOFT

La practicante que construyó el asistente termina su práctica en unas semanas. Hoy varias piezas dependen de su
laptop y de sus cuentas personales. Este plan dice qué hay que pasar a EKAM, quién lo hace y cómo comprobarlo.
**Nada de este documento lleva contraseñas ni claves**: cada una se entrega en persona o se crea de nuevo.

## 1. Dónde vive cada cosa hoy

| Pieza | Dónde está | Depende de la practicante |
|---|---|---|
| Portal y asistente | `https://chatbot-ekam.ekamperu.com` (VPS de Hostinger, n8n + base + Ollama + procesador) | No |
| Dominio y DNS | cPanel de Datec (ekamperu.com), registro A `chatbot-ekam` → 179.66.128.21 | No (cuenta de EKAM) |
| Respaldo diario | En el VPS a las 03:00 de Lima, 7 días (`/docker/navasoft/respaldos`) | No |
| Copia fuera del VPS | FTP cifrado al cPanel de Datec, 5 días. **Falta crear la cuenta FTP** (sección 3) | No, una vez creada |
| Acceso al VPS por SSH | Una sola llave, `navasoft-migracion`, guardada **solo en su laptop** | **Sí** |
| Terminal del navegador de Hostinger | Panel de Hostinger (entra con la contraseña de root) | Según quién tenga la cuenta de Hostinger |
| Código | GitHub `RaizaArce/chatbot-ekam` (público), rama `main` | **Sí: cuenta personal** |
| Historial completo del código | Rama `master` en su laptop (trae datos de clientes: **no subirla al repositorio público**) | **Sí** |
| Clave de la API de n8n | `C:\mcp-n8n\.env` de su laptop; la usan los scripts de publicación | **Sí** |
| Claves de IA | Credenciales en n8n: "Gemini NAVASOFT", "Groq account", "OpenRouter NAVASOFT" | **A confirmar** de qué cuentas salieron |
| Manuales originales (con datos reales) | `C:\PRÁCTICAS EKAM\Manuales NAVASOFT` en su laptop (54 archivos, 67 MB) | **Sí** |
| Lista privada de nombres a ocultar | `auditoria\limpieza.json` en su laptop; copia en el volumen del procesador (`/data/auditoria/`) | En parte |
| Administrador del portal | Cuenta `prueba.admin` (la usa ella) | **Sí** |

## 2. Antes de que se vaya (en este orden)

### 2.1 Acceso al servidor para el ingeniero
1. El ingeniero crea su propia llave en su computadora: `ssh-keygen -t ed25519 -C "ingeniero-ekam"`.
2. Le envía a la practicante **solo la llave pública** (el archivo que termina en `.pub`; no es secreta).
3. Ella la agrega en el VPS: `ssh -i ~/.ssh/navasoft_hostinger root@srv2106635.hstgr.cloud` y pega la llave al final de
   `/root/.ssh/authorized_keys`.
4. El ingeniero prueba que entra: `ssh root@srv2106635.hstgr.cloud`.
5. **Recién entonces** se borra la línea `navasoft-migracion` de `/root/.ssh/authorized_keys`, y la practicante
   borra `navasoft_hostinger` y `navasoft_hostinger.pub` de su carpeta `.ssh`.

Desde internet el VPS solo acepta llaves (las contraseñas están desactivadas). La terminal del navegador de
Hostinger sigue entrando con la contraseña de root: es el acceso de emergencia si se pierde la llave.

### 2.2 Cuentas que deben ser de EKAM
- **Hostinger:** confirmar a nombre de quién está el VPS y quién paga. **El plan vence el 28/11/2026.**
- **n8n:** la cuenta dueña (owner) debe ser de EKAM. El ingeniero crea su propia clave de API en n8n
  (Settings → n8n API) para los scripts de publicación.
- **GitHub:** transferir el repositorio a una cuenta u organización de EKAM: en GitHub, Settings → General →
  Danger Zone → Transfer ownership. Es público: no subir la rama `master` ni archivos de `auditoria/`.
- **Claves de IA:** crear claves nuevas con cuentas de EKAM (Google AI Studio para Gemini, Groq y OpenRouter) y
  reemplazarlas en n8n → Credentials, editando "Gemini NAVASOFT", "Groq account" y "OpenRouter NAVASOFT". Después,
  borrar las claves viejas en cada servicio. Las tres se usan en el plan gratuito.
- **Portal:** el ingeniero se crea un administrador con su nombre (Administración → Usuarios). Al final se desactivan
  `prueba.admin` y la cuenta de cliente de la practicante (`raiza`).

### 2.3 Archivos que hay que guardar en EKAM
- **Manuales originales** (`C:\PRÁCTICAS EKAM\Manuales NAVASOFT`): traen datos reales de clientes. Guardarlos en un
  almacenamiento privado de EKAM, no en el repositorio.
- **`auditoria\limpieza.json`:** la lista de nombres de clientes que se reemplazan en las capturas. Sin ella, la
  limpieza solo encuentra los datos con forma reconocible (RUC, S.A.C., correos...). Guardarla junto a los manuales.
- **Rama `master`** (historial completo): archivarla en un lugar privado de EKAM (por ejemplo, un repositorio
  privado aparte) o descartarla. No es necesaria para operar.
- **`.env` de la laptop:** solo sirve para la instalación local de pruebas; en producción las claves están en n8n y
  en `/docker/navasoft/.env` del VPS.

## 3. Copia de respaldo fuera del servidor (falta un paso)

El VPS ya está preparado para enviar cada día su respaldo al hosting de EKAM en Datec por FTP cifrado. Falta la
cuenta FTP, que crea alguien con acceso al cPanel (la contraseña no pasa por nadie más):

1. cPanel de ekamperu.com → **Archivos → Cuentas de FTP → Agregar cuenta FTP**:
   - **Inicio de sesión:** `respaldos` (queda `respaldos@ekamperu.com`).
   - **Contraseña:** una fuerte (botón "Generador de contraseñas"); no hace falta anotarla.
   - **Directorio:** borrar lo que propone y escribir `respaldos_chatbot` (fuera de `public_html`: no se ve desde la web).
   - **Cuota:** 2000 MB.
2. Panel de Hostinger → VPS → **Terminal del navegador**, y ejecutar:
   `/docker/navasoft/guardar_clave_datec.sh`
   Pide el usuario y la contraseña de esa cuenta (no se ven al escribir), los guarda solo en el VPS y envía la
   primera copia. Debe terminar con "LISTO".

Desde entonces, cada día a las 03:00 (hora de Lima) el respaldo queda en el VPS y en Datec. El registro está en
`/docker/navasoft/respaldo.log`.

## 4. Cómo se opera sin la laptop de la practicante

| Tarea | Cómo |
|---|---|
| Subir un manual nuevo | Portal → Administración → **Manuales**: subir, descargar la copia sin datos reales, revisarla y **Publicar** |
| Crear usuarios | Portal → Administración → Usuarios (una cuenta o "Crear varias cuentas" con Excel) |
| Ver solicitudes de soporte y calidad | Portal → Administración |
| Cambiar el portal o los flujos | Editar el código del repositorio y correr `python migracion/publicar_nube.py`. Los scripts leen la clave de la API de n8n de `C:\mcp-n8n\.env` (ruta fija en `n8n/publicar_chatbot.py` y `portal/publicar_portal.py`): cambiar esa ruta en la computadora del ingeniero |
| Actualizar el procesador de manuales | `migracion/desplegar_procesador.ps1` (usa la llave SSH; cambiar `$Llave` por la del ingeniero) |
| Restaurar la base | `docker exec -i navasoft-db pg_restore -U navasoft -d navasoft --clean < respaldos/AAAA-MM-DD/navasoft.dump` (probar antes en una base temporal) |
| Revisar que todo esté en marcha | `docker ps` en el VPS: `navasoft-db`, `navasoft-ollama`, `navasoft-procesador`, `n8n-n8n-1`, `n8n-traefik-1` |

Las decisiones técnicas pendientes están en `migracion/PENDIENTES_INGENIERO.md`.

## 5. Lista de comprobación final

- [ ] El ingeniero entra al VPS con su llave y se quitó la llave `navasoft-migracion`.
- [ ] El VPS está renovado y a nombre de EKAM.
- [ ] La cuenta dueña de n8n es de EKAM y el ingeniero tiene su clave de API.
- [ ] El repositorio está transferido a EKAM.
- [ ] Las claves de Gemini, Groq y OpenRouter son de cuentas de EKAM y se borraron las viejas.
- [ ] La cuenta FTP de respaldos existe y `respaldo.log` dice "copia ... enviada a Datec".
- [ ] Los manuales originales y `limpieza.json` están guardados en EKAM.
- [ ] El ingeniero tiene su administrador del portal; se desactivaron `prueba.admin` y `raiza`.
- [ ] El ingeniero subió y publicó un manual de prueba desde el portal y luego lo descartó.
