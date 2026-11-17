# Trabajo de la noche del Asistente NAVASOFT (dura como maximo 4 h 45 min y se detiene solo):
#   1. Examen automatico: 120 preguntas sacadas del indice de los manuales (unos 80 minutos) -> Excel en examen\resultados
#   2. Descripcion de capturas con IA de vision (gemma3), empezando por los manuales mas consultados
#   3. Cada 15 minutos revisa que n8n, la base de datos y Ollama respondan
# Todo queda anotado en registro_noche.txt y el resumen final en resumen_noche.txt.
# Uso:  powershell -ExecutionPolicy Bypass -File trabajo_noche.ps1 [-Minutos 285] [-Preguntas 120]
param([int]$Minutos = 285, [int]$Preguntas = 120, [int]$MinutosExamen = 85, [switch]$SinCapturas)

[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUNBUFFERED = "1"
$Base = $PSScriptRoot
$Python = Join-Path $Base ".venv\Scripts\python.exe"
$RegistroNoche = Join-Path $Base "registro_noche.txt"
$ResumenNoche = Join-Path $Base "resumen_noche.txt"
$HoraInicio = Get-Date
$HoraFin = $HoraInicio.AddMinutes($Minutos)

# mientras este script corre, Windows no suspende la laptop por inactividad (como hace un reproductor de video).
# No cambia ninguna configuracion: al terminar el script todo vuelve a la normalidad. La tapa cerrada igual la suspende.
Add-Type -Namespace Navasoft -Name Energia -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[void][Navasoft.Energia]::SetThreadExecutionState([uint32]"0x80000001")   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

function Anotar($texto) { Add-Content -Path $RegistroNoche -Value "$(Get-Date -Format 'HH:mm:ss')  $texto" -Encoding utf8 }
function MinutosRestantes { [math]::Floor(($HoraFin - (Get-Date)).TotalMinutes) }
function Ejecutar($nombre, [string[]]$argumentos) {
    & $Python @argumentos 2>&1 | ForEach-Object { $linea = "$_"; if ($linea.Trim()) { Anotar "[$nombre] $linea" } }
}

Set-Content -Path $RegistroNoche -Value "=== Trabajo de la noche: $($HoraInicio.ToString('dd/MM/yyyy HH:mm')) — termina a mas tardar a las $($HoraFin.ToString('HH:mm')) ===" -Encoding utf8

# ---- revision de salud cada 15 minutos (en segundo plano)
$revision = Start-Job -ArgumentList $RegistroNoche, $HoraFin -ScriptBlock {
    param($archivoRegistro, $finTrabajo)
    while ((Get-Date) -lt $finTrabajo) {
        $estado = @()
        foreach ($p in @(@("n8n", "http://127.0.0.1:5678/healthz"), @("Ollama", "http://127.0.0.1:11434/api/tags"))) {
            $t0 = Get-Date
            try { Invoke-WebRequest $p[1] -UseBasicParsing -TimeoutSec 20 | Out-Null; $estado += "$($p[0]) OK ($([int]((Get-Date) - $t0).TotalMilliseconds) ms)" }
            catch { $estado += "$($p[0]) NO RESPONDE" }
        }
        docker exec navasoft-db pg_isready -U postgres 2>$null | Out-Null
        $estado += $(if ($LASTEXITCODE -eq 0) { "Base de datos OK" } else { "Base de datos NO RESPONDE" })
        $libre = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
        Add-Content -Path $archivoRegistro -Value "$(Get-Date -Format 'HH:mm:ss')  [salud] $($estado -join ' · ') · RAM libre $libre GB" -Encoding utf8
        Start-Sleep -Seconds 900
    }
}

# ---- 1. examen automatico (necesita n8n encendido)
$n8nListo = $false
for ($i = 0; $i -lt 10 -and -not $n8nListo; $i++) {
    try { Invoke-WebRequest "http://127.0.0.1:5678/healthz" -UseBasicParsing -TimeoutSec 10 | Out-Null; $n8nListo = $true } catch { Start-Sleep -Seconds 30 }
}
$t0 = Get-Date
if ($n8nListo) {
    Anotar "1. Examen automatico: $Preguntas preguntas (maximo $MinutosExamen minutos)"
    Ejecutar "examen" @((Join-Path $Base "examen\examen_noche.py"), "--max", "$Preguntas", "--espera", "40", "--minutos", "$MinutosExamen")
} else {
    Anotar "1. Examen OMITIDO: n8n no respondio. Se sigue con las capturas."
}
$duracionExamen = [int]((Get-Date) - $t0).TotalMinutes

# ---- 2. descripcion de capturas con el tiempo que quede
$t1 = Get-Date
$minCapturas = (MinutosRestantes) - 8
if ($SinCapturas) {
    Anotar "2. Capturas: no se usa gemma3 esta vez (las describe Claude por separado)."
} elseif ($minCapturas -gt 5) {
    Anotar "2. Descripcion de capturas: $minCapturas minutos"
    Ejecutar "capturas" @((Join-Path $Base "describir_capturas.py"), "--max", "2000", "--minutos", "$minCapturas",
                           "--orden", "caja chica,ventas,inventarios,cuentas por pagar,caja y bancos,contabilidad")
}
$duracionCapturas = [int]((Get-Date) - $t1).TotalMinutes
# libera la memoria del modelo de vision
try { Invoke-RestMethod "http://127.0.0.1:11434/api/generate" -Method Post -ContentType "application/json" -Body '{"model":"gemma3:4b","keep_alive":0}' -TimeoutSec 30 | Out-Null } catch {}

# ---- resumen
Stop-Job $revision -ErrorAction SilentlyContinue; Remove-Job $revision -Force -ErrorAction SilentlyContinue
$lineasExamen = Select-String -Path $RegistroNoche -Pattern "Examen terminado:" -Encoding utf8 | Select-Object -Last 1
$conteo = docker exec navasoft-db psql -U postgres -d navasoft -tAc "SELECT count(*) FILTER (WHERE descripcion IS NOT NULL), count(*) FILTER (WHERE descripcion IS NULL), count(*) FILTER (WHERE fecha >= now() - interval '$Minutos minutes') FROM capturas_descripcion"
$partes = "$conteo".Trim() -split '\|'
$errores = (Select-String -Path $RegistroNoche -Pattern "NO RESPONDE|Traceback|ERROR|⚠️ error" -Encoding utf8).Count
$resumen = @(
    "RESUMEN DEL TRABAJO DE LA NOCHE"
    "Inicio: $($HoraInicio.ToString('dd/MM/yyyy HH:mm'))   Fin: $((Get-Date).ToString('HH:mm'))   Duración: $([int]((Get-Date) - $HoraInicio).TotalMinutes) min"
    ""
    "1. Examen automático ($duracionExamen min): " + $(if ($lineasExamen) { ($lineasExamen.Line -replace '^\S+\s+\[examen\]\s*', '') } else { "no se completó (revisar registro_noche.txt)" })
    "2. Capturas ($duracionCapturas min): procesadas esta noche $($partes[2]) · total con descripción aceptada $($partes[0]) · descartadas (decorativas o no comprobadas) $($partes[1])"
    "3. Avisos o errores anotados: $errores (detalle en registro_noche.txt)"
)
Set-Content -Path $ResumenNoche -Value $resumen -Encoding utf8
Anotar "Trabajo de la noche terminado."
[void][Navasoft.Energia]::SetThreadExecutionState([uint32]"0x80000000")   # la laptop ya puede suspenderse normalmente
