# Crea en el n8n de la nube la credencial de Claude (Anthropic), que el asistente usa solo como ultimo respaldo
# cuando Gemini y Groq fallan. La clave se escribe oculta y no se guarda aqui: en credenciales_nube.json solo
# queda el identificador (no es secreto). Despues hay que publicar: python migracion\publicar_nube.py
#   powershell -ExecutionPolicy Bypass -File migracion\crear_credencial_claude.ps1

$ErrorActionPreference = "Stop"
$Modelo = "claude-haiku-5-5"   # el mismo de MODELO_CLAUDE en n8n\publicar_chatbot.py
$Api = "https://n8n.srv2106635.hstgr.cloud/api/v1/credentials"
$ApiKey = ((Get-Content "C:\mcp-n8n\.env" -Encoding utf8 | Where-Object { $_ -like "N8N_API_KEY=*" }) -replace "^N8N_API_KEY=", "").Trim()
$salida = Join-Path $PSScriptRoot "credenciales_nube.json"
$ids = Get-Content $salida -Raw | ConvertFrom-Json
if ($ids.claude) { throw "Ya hay una credencial de Claude ($($ids.claude)). Borra esa linea de credenciales_nube.json si quieres crear otra." }

$s = Read-Host "Pega la clave de Claude (empieza con sk-ant-, no se vera) y pulsa Enter" -AsSecureString
$p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
try { $clave = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p).Trim() }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
if (-not $clave) { throw "No se escribio ninguna clave; no se creo nada." }

# Antes de guardarla: comprobar con Anthropic que la clave sirve y que el modelo existe (consulta gratuita).
try {
    $m = Invoke-RestMethod -Uri "https://api.anthropic.com/v1/models/$Modelo" -Headers @{ "x-api-key" = $clave; "anthropic-version" = "2023-06-01" }
    Write-Output "Clave valida. Modelo: $($m.display_name)"
} catch {
    throw "Anthropic rechazo la clave o el modelo '$Modelo': $($_.Exception.Message). No se creo nada."
}

$cuerpo = @{ name = "Claude NAVASOFT"; type = "anthropicApi"; data = @{ apiKey = $clave; url = "https://api.anthropic.com"; header = $false } } | ConvertTo-Json -Depth 5
$id = (Invoke-RestMethod -Method Post -Uri $Api -Headers @{ "X-N8N-API-KEY" = $ApiKey } -ContentType "application/json" -Body $cuerpo).id

$ids | Add-Member -NotePropertyName claude -NotePropertyValue $id -Force
$ids | ConvertTo-Json | Out-File $salida -Encoding ascii
Write-Output "CREDENCIAL_CLAUDE_LISTA"
