# Guardian del Asistente NAVASOFT: lo mantiene encendido solo, sin ventanas y sin que nadie haga nada.
#  - Al iniciar sesion en Windows enciende Docker (base de datos), Ollama, n8n y el vigilante de manuales.
#  - Cada 2 minutos revisa que todo responda; si algo se cayo, lo vuelve a encender.
#  - Una vez al dia (despues de las 8:00) corre la prueba rapida de calidad, anota el resultado y hace el
#    respaldo de la base de datos y de los flujos (respaldar.ps1).
#  - Todo queda anotado en registro_guardian.txt (y lo que dice n8n en registro_n8n.txt).
# Lo enciende la tarea programada "Asistente NAVASOFT" (ver instalar_guardian.ps1).

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Base = $PSScriptRoot
$Registro = Join-Path $Base "registro_guardian.txt"
$RegistroN8n = Join-Path $Base "registro_n8n.txt"
$Python = Join-Path $Base ".venv\Scripts\python.exe"
$MarcaPrueba = Join-Path $Base "examen\ultima_prueba_diaria.txt"

function Anotar($texto) { Add-Content -Path $Registro -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $texto" -Encoding utf8 }

# aviso en la esquina de Windows (y tambien queda en el registro); el mismo aviso no se repite en 30 minutos
$ultimosAvisos = @{}
function Avisar($texto) {
    Anotar "AVISO: $texto"
    if ($ultimosAvisos[$texto] -and ((Get-Date) - $ultimosAvisos[$texto]).TotalMinutes -lt 30) { return }
    $ultimosAvisos[$texto] = Get-Date
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $seguro = [Security.SecurityElement]::Escape($texto)
        $xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>Asistente NAVASOFT</text><text>$seguro</text></binding></visual></toast>")
        $app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
    } catch { Anotar "No se pudo mostrar el aviso: $($_.Exception.Message)" }
}

# una sola copia a la vez
$candado = New-Object System.Threading.Mutex($false, "Global\GuardianAsistenteNavasoft")
if (-not $candado.WaitOne(0)) { exit }

# las mismas opciones que INICIAR-N8N.bat
$env:N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX = "true"
$env:EXECUTIONS_DATA_PRUNE = "true"; $env:EXECUTIONS_DATA_MAX_AGE = "168"; $env:EXECUTIONS_DATA_PRUNE_MAX_COUNT = "300"
$env:N8N_DIAGNOSTICS_ENABLED = "false"; $env:N8N_VERSION_NOTIFICATIONS_ENABLED = "false"
$env:N8N_TEMPLATES_ENABLED = "false"; $env:N8N_PERSONALIZATION_ENABLED = "false"

function Puerto($n) { [bool](Get-NetTCPConnection -LocalPort $n -State Listen -ErrorAction SilentlyContinue) }
function BaseLista { docker exec navasoft-db pg_isready -U postgres 2>$null | Out-Null; $LASTEXITCODE -eq 0 }
function OllamaListo { try { Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 10 | Out-Null; $true } catch { $false } }
function AsistenteListo {
    # sin la clave interna el asistente debe responder 403: prueba que n8n y el flujo del chatbot estan activos (sin gastar IA)
    try { Invoke-WebRequest "http://localhost:5678/webhook/navasoft-asistente" -Method Post -Body '{}' -ContentType "application/json" -UseBasicParsing -TimeoutSec 20 | Out-Null; $false }
    catch { $_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 403 }
}
function PortalListo { try { (Invoke-WebRequest "http://localhost:5678/webhook/navasoft-portal" -UseBasicParsing -TimeoutSec 20).StatusCode -eq 200 } catch { $false } }
function VigilanteEncendido {
    [bool](Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*vigilar_manuales.ps1*" })
}

function EncenderN8n {
    Anotar "Encendiendo n8n..."
    Start-Process cmd.exe -WindowStyle Hidden -ArgumentList "/c", "n8n start >> `"$RegistroN8n`" 2>&1"
}
function ApagarN8n {
    $conexion = Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conexion) { Stop-Process -Id $conexion.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 5 }
}
function EncenderVigilante {
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$Base\vigilar_manuales.ps1`""
    Anotar "Vigilante de manuales encendido"
}

function Preparar {
    # Docker y Ollama; la salida pasa por Anotar para que el registro quede en un solo formato (UTF-8)
    & (Join-Path $Base "iniciar_asistente.ps1") -SinNavegador *>&1 | ForEach-Object { "$_".Trim() } | Where-Object { $_ } | ForEach-Object { Anotar $_ }
}

function PruebaDiaria {
    $hoy = Get-Date -Format "yyyy-MM-dd"
    if ((Get-Date).Hour -lt 8 -or ((Test-Path $MarcaPrueba) -and (Get-Content $MarcaPrueba) -eq $hoy)) { return }
    Set-Content $MarcaPrueba $hoy
    $env:PYTHONIOENCODING = "utf-8"
    $salida = & $Python (Join-Path $Base "examen\prueba_rapida.py") 2>&1 | ForEach-Object { "$_" }
    $resumen = $salida | Where-Object { $_ -match "^Resultado:" } | Select-Object -Last 1
    Anotar "Prueba diaria de calidad: $resumen"
    $fallas = @($salida | Where-Object { $_ -match "FALLA" })
    foreach ($falla in $fallas) { Anotar "   $($falla.Trim())" }
    if ($fallas.Count -gt 0 -or -not $resumen) { Avisar "La prueba diaria de calidad encontró fallas: revisa registro_guardian.txt" }
    # y el respaldo diario de la base de datos y de los flujos (respaldar.ps1 guarda los ultimos 7)
    try { Anotar (& (Join-Path $Base "respaldar.ps1") | Select-Object -Last 1) } catch { Avisar "El respaldo diario falló: $($_.Exception.Message)" }
}

Anotar "Guardián encendido"
Preparar
$fallasN8n = 0; $esperaN8n = 0
while ($true) {
    if (-not (BaseLista)) {
        Avisar "La base de datos no responde: se vuelve a encender"
        Preparar
    }
    if (-not (OllamaListo)) {
        Avisar "Ollama no responde: se vuelve a encender"
        Preparar
    }

    if (-not (Puerto 5678)) {
        # n8n tarda 1 a 3 minutos en encender: no se lanza otra copia mientras arranca
        if ($esperaN8n -le 0) { EncenderN8n; $esperaN8n = 3 } else { $esperaN8n-- }
    } elseif ((AsistenteListo) -and (PortalListo)) {
        if ($fallasN8n -gt 0) { Anotar "El asistente volvió a responder" }
        $fallasN8n = 0; $esperaN8n = 0
    } elseif (++$fallasN8n -ge 3) {
        Avisar "El asistente o el portal no responden: se reinicia n8n"
        ApagarN8n; EncenderN8n; $fallasN8n = 0; $esperaN8n = 3
    }

    if ((Puerto 5678) -and -not (VigilanteEncendido)) { EncenderVigilante }
    if ($fallasN8n -eq 0 -and (Puerto 5678)) { PruebaDiaria }
    Start-Sleep -Seconds 120
}
