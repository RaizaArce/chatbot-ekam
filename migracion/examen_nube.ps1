# Corre el examen de calidad contra la nube, leyendo los temas de la base del servidor por un tunel SSH temporal.
# Al terminar quita de respuestas_cache las respuestas que dejo el examen.
#   powershell -ExecutionPolicy Bypass -File migracion\examen_nube.ps1 -Max 100 -Espera 25 -Minutos 60

param([int]$Max = 100, [int]$Espera = 25, [int]$Minutos = 60)

$Base = Split-Path $PSScriptRoot -Parent
$Llave = "$env:USERPROFILE\.ssh\navasoft_hostinger"
$Servidor = "root@srv2106635.hstgr.cloud"
$PuertoLocal = 15432

$ipBase = (ssh -i $Llave -o BatchMode=yes $Servidor "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' navasoft-db").Trim()
$env:POSTGRES_USER = "navasoft"
$env:POSTGRES_DB = "navasoft"
$env:POSTGRES_PORT = "$PuertoLocal"
$env:POSTGRES_PASSWORD = (ssh -i $Llave -o BatchMode=yes $Servidor "grep ^POSTGRES_PASSWORD= /docker/navasoft/.env | cut -d= -f2").Trim()
$env:NAVASOFT_URL = "https://chatbot-ekam.ekamperu.com"
$env:PYTHONIOENCODING = "utf-8"

$tunel = Start-Process ssh -PassThru -WindowStyle Hidden -ArgumentList "-i", $Llave, "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "-N", "-L", "${PuertoLocal}:${ipBase}:5432", $Servidor
try {
    Start-Sleep -Seconds 4
    & (Join-Path $Base ".venv\Scripts\python.exe") (Join-Path $Base "examen\examen_noche.py") --max $Max --espera $Espera --minutos $Minutos 2>&1 | ForEach-Object { "$_" }
} finally {
    Stop-Process -Id $tunel.Id -Force -ErrorAction SilentlyContinue
    $orden = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("docker exec navasoft-db psql -U navasoft -d navasoft -At -c `"delete from respuestas_cache where clave like '%examen %'`""))
    ssh -i $Llave -o BatchMode=yes $Servidor "echo $orden | base64 -d | bash"
}
