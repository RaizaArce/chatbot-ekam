# Respaldo completo del Asistente NAVASOFT en respaldos\automaticos\AAAA-MM-DD_HHMM\:
#  - navasoft.dump : toda la base de datos (manuales, imagenes, paginas, usuarios, conversaciones)
#  - flujos\*.json : los flujos de n8n (chatbot, portal y los demas), tal como estan publicados
# Se guardan los ultimos 7 respaldos. Lo llama el guardian una vez al dia; tambien se puede correr a mano:
#   powershell -ExecutionPolicy Bypass -File respaldar.ps1
# Este mismo respaldo es el que se sube al servidor de Hostinger (ver MIGRACION_HOSTINGER.md).

$ErrorActionPreference = "Stop"
$Base = $PSScriptRoot
$Raiz = Join-Path $Base "respaldos\automaticos"
$Destino = Join-Path $Raiz (Get-Date -Format "yyyy-MM-dd_HHmm")
New-Item -ItemType Directory -Force (Join-Path $Destino "flujos") | Out-Null
$env_ = @{}; Get-Content (Join-Path $Base ".env") -Encoding utf8 | Where-Object { $_ -match "^[^#].*=" } | ForEach-Object { $k, $v = $_ -split "=", 2; $env_[$k.Trim()] = $v.Trim() }

# 1. Base de datos (formato comprimido de PostgreSQL; se restaura con pg_restore)
docker exec navasoft-db pg_dump -U $env_["POSTGRES_USER"] -d $env_["POSTGRES_DB"] -Fc -f /tmp/navasoft.dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump fallo" }
docker cp navasoft-db:/tmp/navasoft.dump (Join-Path $Destino "navasoft.dump") | Out-Null
docker exec navasoft-db rm -f /tmp/navasoft.dump | Out-Null

# 2. Flujos de n8n por su API
# la clave del n8n de la laptop quedo en esta copia: C:\mcp-n8n\.env ahora apunta a la nube
$clave = (Get-Content "C:\mcp-n8n\.env.bak-local" -Encoding utf8 | Where-Object { $_ -like "N8N_API_KEY=*" }) -replace "^N8N_API_KEY=", ""
$flujos = (Invoke-RestMethod "http://localhost:5678/api/v1/workflows?limit=100" -Headers @{ "X-N8N-API-KEY" = $clave.Trim() }).data
foreach ($f in $flujos) {
    $nombre = ($f.name -replace '[\\/:*?"<>|]', '_')
    $f | ConvertTo-Json -Depth 100 | Out-File (Join-Path $Destino "flujos\$nombre.json") -Encoding utf8
}

# 3. Se conservan solo los 7 mas recientes
Get-ChildItem $Raiz -Directory | Sort-Object Name -Descending | Select-Object -Skip 7 | Remove-Item -Recurse -Force
$mb = [math]::Round((Get-ChildItem $Destino -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Output "Respaldo listo: $Destino ($mb MB, $($flujos.Count) flujos)"
