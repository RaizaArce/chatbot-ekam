# Corre un script de Python de este proyecto contra la base y el Ollama de la nube, por un tunel SSH temporal
# (igual que sincronizar_nube.ps1). Ejemplos:
#   powershell -ExecutionPolicy Bypass -File migracion\con_tunel.ps1 corregir_secciones.py
#   powershell -ExecutionPolicy Bypass -File migracion\con_tunel.ps1 analisis\evaluar_cliente.py
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Comando)

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
$env:URL_PUBLICA = "https://n8n.srv2106635.hstgr.cloud/webhook"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

$tunel = Start-Process ssh -PassThru -WindowStyle Hidden -ArgumentList "-i", $Llave, "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=10", "-N", "-L", "${PuertoLocal}:${ipBase}:5432", "-L", "${PuertoOllama}:${ipOllama}:11434", $Servidor
try {
    Start-Sleep -Seconds 4
    & (Join-Path $Base ".venv\Scripts\python.exe") (Join-Path $Base $Comando[0]) @($Comando | Select-Object -Skip 1)
    if ($LASTEXITCODE -ne 0) { throw "El script fallo (codigo $LASTEXITCODE)" }
} finally {
    Stop-Process -Id $tunel.Id -Force -ErrorAction SilentlyContinue
}
