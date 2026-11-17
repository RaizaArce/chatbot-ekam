# Crea en el n8n de la nube las credenciales de Gemini y Groq. Las claves se escriben ocultas y no se guardan aqui.
# En credenciales_nube.json solo quedan los identificadores (no son secretos); los usa la publicacion de los flujos.
#   powershell -ExecutionPolicy Bypass -File migracion\crear_credenciales_ia.ps1

$ErrorActionPreference = "Stop"
$Api = "https://n8n.srv2106635.hstgr.cloud/api/v1/credentials"
$ApiKey = ((Get-Content "C:\mcp-n8n\.env" -Encoding utf8 | Where-Object { $_ -like "N8N_API_KEY=*" }) -replace "^N8N_API_KEY=", "").Trim()

function Leer-Clave($texto) {
    $s = Read-Host $texto -AsSecureString
    $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}

function Crear($nombre, $tipo, $datos) {
    $cuerpo = @{ name = $nombre; type = $tipo; data = $datos } | ConvertTo-Json -Depth 5
    return (Invoke-RestMethod -Method Post -Uri $Api -Headers @{ "X-N8N-API-KEY" = $ApiKey } -ContentType "application/json" -Body $cuerpo).id
}

$gemini = Leer-Clave "Pega la clave de Gemini (no se vera) y pulsa Enter"
$groq = Leer-Clave "Pega la clave de Groq (no se vera) y pulsa Enter"
if (-not $gemini -or -not $groq) { throw "Falta una de las claves; no se creo nada." }

$idGemini = Crear "Gemini NAVASOFT" "googlePalmApi" @{ host = "https://generativelanguage.googleapis.com"; apiKey = $gemini }
$idGroq = Crear "Groq account" "groqApi" @{ apiKey = $groq }

$salida = Join-Path $PSScriptRoot "credenciales_nube.json"
@{ postgres = "u2HUHvYtmdPfTQV2"; gemini = $idGemini; groq = $idGroq } | ConvertTo-Json | Out-File $salida -Encoding ascii
Write-Output "CREDENCIALES_LISTAS"
