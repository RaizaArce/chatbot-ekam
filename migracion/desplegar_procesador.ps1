# Instala o actualiza en el servidor el procesador de manuales (procesador\app.py): copia el codigo, construye el
# contenedor y le pasa la lista privada de nombres a reemplazar (auditoria\limpieza.json, que no esta en git).
#   powershell -ExecutionPolicy Bypass -File migracion\desplegar_procesador.ps1

$ErrorActionPreference = "Stop"
$Base = Split-Path $PSScriptRoot -Parent
$Llave = "$env:USERPROFILE\.ssh\navasoft_hostinger"
$Servidor = "root@srv2106635.hstgr.cloud"
$Destino = "/docker/navasoft/procesador"

ssh -i $Llave -o BatchMode=yes $Servidor "mkdir -p $Destino"
$archivos = @("procesador\app.py", "procesador\Dockerfile", "procesador\requirements.txt", "procesador\docker-compose.yml",
              "leer_manuales.py", "auditar_datos_sensibles.py", "limpiar_manuales.py", "crear_indice.py", "corregir_secciones.py")
foreach ($a in $archivos) { scp -i $Llave -o BatchMode=yes -q (Join-Path $Base $a) "${Servidor}:$Destino/" }
ssh -i $Llave -o BatchMode=yes $Servidor "cd $Destino && docker compose up -d --build 2>&1 | tail -5"
if ($LASTEXITCODE -ne 0) { throw "No se pudo construir el procesador" }

# reglas de limpieza (nombres de clientes): directo al volumen de datos del contenedor
scp -i $Llave -o BatchMode=yes -q (Join-Path $Base "auditoria\limpieza.json") "${Servidor}:/tmp/limpieza.json"
ssh -i $Llave -o BatchMode=yes $Servidor "docker exec navasoft-procesador mkdir -p /data/auditoria && docker cp /tmp/limpieza.json navasoft-procesador:/data/auditoria/limpieza.json && rm -f /tmp/limpieza.json"
Write-Output "PROCESADOR_LISTO"
