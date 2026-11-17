# Vigila la carpeta de manuales mientras el asistente esta encendido. Cuando alguien agrega, cambia o borra
# un manual (PDF o Word), lo carga solo en la base de datos o lo quita. Nadie tiene que ejecutar comandos.
#  - Los Word nuevos se pasan a PDF con Word (asi el asistente puede citar numeros de pagina).
#  - Lo que hace queda anotado en registro_vigilancia.txt.
# Lo enciende iniciar_asistente.ps1 en segundo plano y se apaga solo cuando n8n se cierra.

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8   # para que el registro guarde bien las tildes
$Base = $PSScriptRoot
$Manuales = if ($env:MANUALES_DIR) { $env:MANUALES_DIR } else { "C:\PRÁCTICAS EKAM\Manuales NAVASOFT" }
$Convertidos = Join-Path $Base "manuales_convertidos"
$ArchivoCreados = Join-Path $Convertidos "creados_por_vigilante.txt"   # solo estos PDF se pueden borrar automaticamente
$Registro = Join-Path $Base "registro_vigilancia.txt"
$Python = Join-Path $Base ".venv\Scripts\python.exe"

function Anotar($texto) { Add-Content -Path $Registro -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $texto" -Encoding utf8 }
function Clave($nombre) { ($nombre.ToLower() -creplace '[^a-z0-9]', '') }   # igual que en leer_manuales.py
function Manuales { Get-ChildItem -LiteralPath $Manuales -Recurse -File -Include *.pdf, *.docx -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike '~$*' } }
function Foto { (Manuales | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" } | Sort-Object) -join "`n" }
function N8nEncendido { [bool](Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue) }

# una sola copia a la vez
$candado = New-Object System.Threading.Mutex($false, "Global\VigilanteManualesNavasoft")
if (-not $candado.WaitOne(0)) { exit }

function ConvertirWord {
    $archivos = @(Manuales)
    $pdfs = @($archivos | Where-Object Extension -eq '.pdf') + @(Get-ChildItem -LiteralPath $Convertidos -Filter *.pdf -ErrorAction SilentlyContinue)
    $creados = @(if (Test-Path $ArchivoCreados) { Get-Content $ArchivoCreados -Encoding utf8 })
    foreach ($doc in ($archivos | Where-Object Extension -eq '.docx')) {
        $destino = [string](Join-Path $Convertidos ($doc.BaseName + ".pdf"))
        $hecho = $pdfs | Where-Object { (Clave $_.BaseName) -eq (Clave $doc.BaseName) } | Select-Object -First 1
        # se convierte si no tiene PDF, o si el Word es mas nuevo que el PDF que creo este vigilante
        $actualizar = $hecho -and ($creados -contains $hecho.Name) -and ($doc.LastWriteTime -gt $hecho.LastWriteTime)
        if ($hecho -and -not $actualizar) { continue }
        # Word se usa en un proceso aparte con tiempo limite: si se queda colgado, se cierra solo ese Word
        $antes = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object Id)
        $tarea = Start-Job -ArgumentList ([string]$doc.FullName), $destino -ScriptBlock {
            param($origen, $pdf)
            $w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0
            try { $d = $w.Documents.Open($origen, $false, $true); $d.ExportAsFixedFormat($pdf, 17); $d.Close($false); "ok" }
            catch { "error: $($_.Exception.Message)" }
            finally { $w.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($w) }
        }
        $resultado = if (Wait-Job $tarea -Timeout 120) { "$(Receive-Job $tarea)" } else { "error: Word no respondio en 2 minutos" }
        Remove-Job $tarea -Force
        Get-Process WINWORD -ErrorAction SilentlyContinue | Where-Object { $antes -notcontains $_.Id } | Stop-Process -Force
        if ($resultado -eq "ok" -and (Test-Path $destino)) {
            if ($creados -notcontains (Split-Path $destino -Leaf)) { Add-Content $ArchivoCreados (Split-Path $destino -Leaf) -Encoding utf8; $creados += (Split-Path $destino -Leaf) }
            Anotar "Word convertido a PDF: $($doc.Name)"
        } else { Anotar "No se pudo convertir $($doc.Name): $resultado" }
    }

    # si se borro el Word, se borra tambien el PDF que este vigilante habia creado para el
    $claves = @($archivos | Where-Object Extension -eq '.docx' | ForEach-Object { Clave $_.BaseName })
    foreach ($nombre in $creados) {
        $pdf = Join-Path $Convertidos $nombre
        if ((Test-Path $pdf) -and ($claves -notcontains (Clave ([IO.Path]::GetFileNameWithoutExtension($nombre))))) {
            Remove-Item -LiteralPath $pdf
            Set-Content $ArchivoCreados (@($creados | Where-Object { $_ -ne $nombre })) -Encoding utf8
            Anotar "PDF convertido quitado porque se borro su Word: $nombre"
        }
    }
}

function Sincronizar {
    ConvertirWord
    $env:PYTHONIOENCODING = "utf-8"
    $salida = & $Python (Join-Path $Base "leer_manuales.py") --sincronizar 2>&1 | ForEach-Object { "$_" }
    foreach ($linea in $salida) { if ($linea.Trim()) { Anotar $linea } }
}

Anotar "Vigilante encendido. Carpeta: $Manuales"
$anterior = Foto
Sincronizar   # por si cambiaron manuales mientras el asistente estaba apagado
$sinN8n = 0; $visto = $false
while ($true) {
    Start-Sleep -Seconds 60
    # n8n puede tardar varios minutos en encender: solo se apaga si n8n estuvo encendido y luego se cerro
    if (N8nEncendido) { $visto = $true; $sinN8n = 0 } elseif ($visto -and ++$sinN8n -ge 3) { break }
    $actual = Foto
    if ($actual -eq $anterior) { continue }
    # espera a que terminen de copiarse los archivos (la foto deja de cambiar)
    do { $previa = $actual; Start-Sleep -Seconds 20; $actual = Foto } while ($actual -ne $previa)
    Anotar "Se detectaron cambios en la carpeta de manuales."
    Sincronizar
    $anterior = Foto
}
Anotar "Vigilante apagado (n8n se cerro)."
$candado.ReleaseMutex()
