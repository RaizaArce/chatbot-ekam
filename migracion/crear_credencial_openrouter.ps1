# Crea en el n8n de la nube la credencial de OpenRouter, que el asistente usa como respaldo gratuito cuando
# Gemini y Groq fallan (antes de Claude, que es de pago). La clave se escribe oculta y no se guarda aqui: en
# credenciales_nube.json solo queda el identificador (no es secreto). Despues hay que publicar:
#   python migracion\publicar_nube.py
# Uso:
#   powershell -ExecutionPolicy Bypass -File migracion\crear_credencial_openrouter.ps1
#
# Cuenta gratuita de OpenRouter (sin comprar creditos): 20 pedidos por minuto y 50 por dia entre todos los
# modelos gratuitos; sacar mas claves o cuentas no sube ese limite. Por eso OpenRouter queda de respaldo.
# Con la clave ya escrita, el script prueba los modelos candidatos con una pregunta de ejemplo (gasta 1 pedido
# por modelo) y deja las respuestas en migracion\prueba_openrouter.txt para elegir cual usar.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
# el primero es el que usa el flujo: el mismo de MODELO_OPENROUTER en n8n\publicar_chatbot.py
$Candidatos = @("google/gemma-4-31b-it:free", "nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3.5-lightning:free")
$Api = "https://n8n.srv2106635.hstgr.cloud/api/v1/credentials"
$ApiKey = ((Get-Content "C:\mcp-n8n\.env" -Encoding utf8 | Where-Object { $_ -like "N8N_API_KEY=*" }) -replace "^N8N_API_KEY=", "").Trim()
$salida = Join-Path $PSScriptRoot "credenciales_nube.json"
$ids = Get-Content $salida -Raw | ConvertFrom-Json
if ($ids.openrouter) { throw "Ya hay una credencial de OpenRouter ($($ids.openrouter)). Borra esa linea de credenciales_nube.json si quieres crear otra." }

$s = Read-Host "Pega la clave de OpenRouter (empieza con sk-or-, no se vera) y pulsa Enter" -AsSecureString
$p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
try { $clave = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p).Trim() }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
if (-not $clave) { throw "No se escribio ninguna clave; no se creo nada." }
$cab = @{ "Authorization" = "Bearer $clave" }

# Antes de guardarla: comprobar con OpenRouter que la clave sirve (consulta gratuita, no gasta pedidos).
try {
    $k = (Invoke-RestMethod -Uri "https://openrouter.ai/api/v1/key" -Headers $cab).data
    Write-Output "Clave valida. Cuenta gratuita: $($k.is_free_tier). Tope de gasto de la clave: $(if ($null -eq $k.limit) { 'sin tope' } else { $k.limit })"
} catch {
    throw "OpenRouter rechazo la clave: $($_.Exception.Message). No se creo nada."
}
$catalogo = (Invoke-RestMethod -Uri "https://openrouter.ai/api/v1/models").data.id
$Candidatos = @($Candidatos | Where-Object { $catalogo -contains $_ })
if (-not $Candidatos) { throw "Ninguno de los modelos candidatos sigue en el catalogo de OpenRouter. Actualiza la lista de este script. No se creo nada." }

# Prueba corta: la misma pregunta de ejemplo a cada candidato (texto en ASCII con \u para los acentos).
$sistema = 'Eres el asistente de soporte de EKAM PER\u00da para el ERP NAVASOFT. Responde en espa\u00f1ol de Per\u00fa, tratando de t\u00fa, SOLO con la informaci\u00f3n del fragmento del manual. Si es un procedimiento, usa pasos numerados. Termina con una l\u00ednea: Fuente: manual y p\u00e1gina. Si el fragmento no responde la pregunta, dilo y no inventes.'
$usuario = 'FRAGMENTO (Manual de caja chica V5, p\u00e1gina 12): Para aperturar una caja chica ingrese a Tesorer\u00eda, opci\u00f3n Caja chica, Apertura. Presione Nuevo, seleccione el responsable y registre el monto de apertura y la moneda. Seleccione la cuenta contable de origen y presione Grabar; el sistema asigna el n\u00famero de caja.\n\nPREGUNTA DEL CLIENTE: \u00bfC\u00f3mo abro una caja chica nueva? \u00bfY c\u00f3mo la cierro al final del mes?'
$informe = @("Prueba de modelos gratuitos de OpenRouter - $(Get-Date -Format 'yyyy-MM-dd HH:mm')", "")
foreach ($m in $Candidatos) {
    $json = '{"model":"' + $m + '","temperature":0.1,"max_tokens":500,"messages":[{"role":"system","content":"' + $sistema + '"},{"role":"user","content":"' + $usuario + '"}]}'
    $reloj = [Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Invoke-WebRequest -Method Post -Uri "https://openrouter.ai/api/v1/chat/completions" -Headers $cab -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($json)) -UseBasicParsing -TimeoutSec 90
        $texto = ([Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json).choices[0].message.content
        $estado = "respondio"
    } catch { $texto = "ERROR: $($_.Exception.Message)"; $estado = "FALLO" }
    $seg = [Math]::Round($reloj.Elapsed.TotalSeconds, 1)
    Write-Output "  $m : $estado en $seg s"
    $informe += @("===== $m ($seg s)", $texto, "")
}
$informe | Out-File (Join-Path $PSScriptRoot "prueba_openrouter.txt") -Encoding utf8

$cuerpo = @{ name = "OpenRouter NAVASOFT"; type = "openRouterApi"; data = @{ apiKey = $clave } } | ConvertTo-Json -Depth 5
$id = (Invoke-RestMethod -Method Post -Uri $Api -Headers @{ "X-N8N-API-KEY" = $ApiKey } -ContentType "application/json" -Body $cuerpo).id

$ids | Add-Member -NotePropertyName openrouter -NotePropertyValue $id -Force
$ids | ConvertTo-Json | Out-File $salida -Encoding ascii
Write-Output "CREDENCIAL_OPENROUTER_LISTA (respuestas de la prueba en migracion\prueba_openrouter.txt)"
