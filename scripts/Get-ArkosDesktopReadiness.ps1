$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Este diagnóstico corresponde a Windows.' }
$osInfo = Get-CimInstance Win32_OperatingSystem
$computerInfo = Get-CimInstance Win32_ComputerSystem
$graphics = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion)
$commands = [ordered]@{}
foreach ($toolName in @('hermes', 'ollama', 'python', 'git', 'ffmpeg')) {
    $detected = Get-Command $toolName -ErrorAction SilentlyContinue
    $commands[$toolName] = [bool]$detected
}
[ordered]@{
    checked_at = (Get-Date).ToUniversalTime().ToString('o')
    os = $osInfo.Caption
    os_version = $osInfo.Version
    architecture = $osInfo.OSArchitecture
    ram_gb = [math]::Round($computerInfo.TotalPhysicalMemory / 1GB, 1)
    graphics = $graphics
    commands_in_path = $commands
    hermes_profile_exists = (Test-Path (Join-Path $env:LOCALAPPDATA 'hermes\profiles\arkos-pilot'))
    note = 'No se inspeccionan credenciales ni documentos. VRAM, audio y capacidades reales requieren comprobación en la aplicación. Un alias no demuestra que un programa arranque.'
} | ConvertTo-Json -Depth 5
