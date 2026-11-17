# Instala (o quita con -Quitar) la tarea programada "Asistente NAVASOFT": al iniciar sesion en Windows
# enciende guardian_asistente.ps1 sin ventanas, y si el guardian se cierra por error Windows lo vuelve a abrir.
# Uso:  powershell -ExecutionPolicy Bypass -File instalar_guardian.ps1 [-Quitar]
param([switch]$Quitar)
$Nombre = "Asistente NAVASOFT"
if ($Quitar) {
    Unregister-ScheduledTask -TaskName $Nombre -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Tarea '$Nombre' quitada."; exit
}
$guardian = Join-Path $PSScriptRoot "guardian_asistente.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $PSScriptRoot `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$guardian`""
$inicio = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $inicio -Settings $ajustes `
    -Description "Mantiene encendido el Asistente NAVASOFT (base de datos, Ollama, n8n y vigilante de manuales)." -Force | Out-Null
Write-Host "Tarea '$Nombre' instalada. Se enciende sola al iniciar sesión. Para encenderla ahora: Start-ScheduledTask '$Nombre'"
