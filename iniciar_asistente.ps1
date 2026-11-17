# Prepara todo lo que necesita el Asistente NAVASOFT antes de encender n8n:
# Docker (base de datos navasoft-db) y Ollama (busqueda con bge-m3).
# Lo llama INICIAR-ASISTENTE.bat; no hace falta ejecutarlo a mano.
# Con -SinNavegador (lo usa guardian_asistente.ps1) solo prepara Docker y Ollama.
param([switch]$SinNavegador)

function Paso($texto) { Write-Host "  - $texto" }
function Listo($texto) { Write-Host "  [OK] $texto" -ForegroundColor Green }

Write-Host ""
Write-Host "Preparando el Asistente NAVASOFT..." -ForegroundColor Cyan

# 1. Docker Desktop y la base de datos
docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Paso "Encendiendo Docker Desktop (puede tardar 1 o 2 minutos)..."
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
}
$lista = $false
for ($i = 0; $i -lt 60; $i++) {
    docker exec navasoft-db pg_isready -U postgres 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $lista = $true; break }
    if ($i -eq 6) { docker start navasoft-db 2>$null | Out-Null }
    Start-Sleep -Seconds 5
}
if ($lista) { Listo "Base de datos lista" } else { Write-Host "  [!] La base de datos no respondio. Abre Docker Desktop y revisa el contenedor navasoft-db." -ForegroundColor Yellow }

# 2. Ollama (busqueda por significado)
if (-not (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)) {
    Paso "Encendiendo Ollama..."
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
    if (Test-Path $ollama) { Start-Process $ollama } else { Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden }
    for ($i = 0; $i -lt 24 -and -not (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 5 }
}
Listo "Ollama listo"

# 2b. Cargar el modelo de busqueda en memoria ahora, para que la primera pregunta no demore
try {
    Invoke-RestMethod "http://127.0.0.1:11434/api/embed" -Method Post -ContentType "application/json" -TimeoutSec 120 `
        -Body '{"model":"bge-m3","input":"caja chica","keep_alive":"3h"}' | Out-Null
    Listo "Modelo de búsqueda cargado"
} catch { Paso "El modelo de búsqueda se cargará con la primera pregunta." }

if ($SinNavegador) { exit }   # el guardian enciende n8n y el vigilante por su cuenta

# 3. Abrir el portal en el navegador apenas n8n responda (en segundo plano)
$abrir = @'
for ($i = 0; $i -lt 90; $i++) {
    try { Invoke-WebRequest "http://localhost:5678/webhook/navasoft-portal" -UseBasicParsing -TimeoutSec 5 | Out-Null; Start-Process "http://localhost:5678/webhook/navasoft-portal"; break } catch { Start-Sleep -Seconds 4 }
}
'@
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command", $abrir
Paso "El portal se abrira en el navegador cuando n8n este listo."

# 4. Vigilante de la carpeta de manuales: carga solo los manuales nuevos o modificados
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSScriptRoot\vigilar_manuales.ps1`""
Listo "Vigilante de manuales encendido (ver registro_vigilancia.txt)"
Write-Host ""
