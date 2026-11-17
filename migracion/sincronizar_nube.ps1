# Carga en la base de la nube los manuales nuevos o cambiados, desde esta laptop (usa Word local para los .docx).
# Abre un tunel SSH temporal a la base y al Ollama del servidor (no hace falta Docker en la laptop)
# y corre leer_manuales.py --sincronizar contra ellos.
#   powershell -ExecutionPolicy Bypass -File migracion\sincronizar_nube.ps1

$ErrorActionPreference = "Stop"
$Base = Split-Path $PSScriptRoot -Parent
$Llave = "$env:USERPROFILE\.ssh\navasoft_hostinger"
$Servidor = "root@srv2106635.hstgr.cloud"
$PuertoLocal = 15432
$PuertoOllama = 15434

$ipBase = (ssh -i $Llave -o BatchMode=yes $Servidor "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' navasoft-db").Trim()
$ipOllama = (ssh -i $Llave -o BatchMode=yes $Servidor "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' navasoft-ollama").Trim()
$env:OLLAMA_URL = "http://127.0.0.1:$PuertoOllama"
$env:POSTGRES_USER = "navasoft"
$env:POSTGRES_DB = "navasoft"
$env:POSTGRES_PORT = "$PuertoLocal"
$env:POSTGRES_PASSWORD = (ssh -i $Llave -o BatchMode=yes $Servidor "grep ^POSTGRES_PASSWORD= /docker/navasoft/.env | cut -d= -f2").Trim()
$env:URL_PUBLICA = "https://chatbot-ekam.ekamperu.com/webhook"
$env:PYTHONIOENCODING = "utf-8"

$tunel = Start-Process ssh -PassThru -WindowStyle Hidden -ArgumentList "-i", $Llave, "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=10", "-o", "TCPKeepAlive=yes", "-N", "-L", "${PuertoLocal}:${ipBase}:5432", "-L", "${PuertoOllama}:${ipOllama}:11434", $Servidor
try {
    Start-Sleep -Seconds 4
    & (Join-Path $Base ".venv\Scripts\python.exe") (Join-Path $Base "leer_manuales.py") --sincronizar
    if ($LASTEXITCODE -ne 0) { throw "La carga de manuales fallo (codigo $LASTEXITCODE)" }
} finally {
    Stop-Process -Id $tunel.Id -Force -ErrorAction SilentlyContinue
}
