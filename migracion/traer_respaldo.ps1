# Copia fuera del servidor: trae a esta laptop el ultimo respaldo diario del asistente (base de datos, flujos de n8n
# y manuales subidos desde el portal) y guarda los ultimos 14 dias en respaldos\servidor\.
# Para traer una copia a mano (la copia diaria fuera del servidor va al cPanel de Datec: ver migracion/PLAN_TRASPASO.md).
#   powershell -ExecutionPolicy Bypass -File migracion\traer_respaldo.ps1

$ErrorActionPreference = "Stop"
$Base = Split-Path $PSScriptRoot -Parent
$Llave = "$env:USERPROFILE\.ssh\navasoft_hostinger"
$Servidor = "root@srv2106635.hstgr.cloud"
$Destino = Join-Path $Base "respaldos\servidor"
$Registro = Join-Path $Base "registro_respaldo.txt"

function Anotar($texto) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm') $texto" | Out-File -Append -Encoding utf8 $Registro }

try {
    $ultimo = (ssh -i $Llave -o BatchMode=yes -o ConnectTimeout=20 $Servidor "ls -1 /docker/navasoft/respaldos | sort | tail -1").Trim()
    if ($ultimo -notmatch '^\d{4}-\d{2}-\d{2}$') { throw "No se encontro ningun respaldo en el servidor." }
    $carpeta = Join-Path $Destino $ultimo
    if (Test-Path (Join-Path $carpeta "navasoft.dump")) { Anotar "ya estaba: $ultimo"; exit 0 }
    New-Item -ItemType Directory -Force $carpeta | Out-Null
    scp -i $Llave -o BatchMode=yes -q "${Servidor}:/docker/navasoft/respaldos/$ultimo/*" "$carpeta\"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $carpeta "navasoft.dump"))) { throw "La copia de $ultimo no termino." }
    # se quedan los ultimos 14 dias
    Get-ChildItem $Destino -Directory | Sort-Object Name -Descending | Select-Object -Skip 14 | Remove-Item -Recurse -Force
    $mb = [math]::Round(((Get-ChildItem $carpeta | Measure-Object Length -Sum).Sum / 1MB), 1)
    Anotar "copiado: $ultimo ($mb MB)"
} catch {
    Anotar "ERROR: $($_.Exception.Message)"
    exit 1
}
