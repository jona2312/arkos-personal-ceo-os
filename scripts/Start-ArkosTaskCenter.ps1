param(
    [Parameter(Mandatory=$true)][string]$StateDirectory,
    [int]$Port = 8765,
    [string]$PythonPath = 'python',
    [string]$RelaySnapshot,
    [string]$RelayDeviceId,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    & $PythonPath -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Se requiere Python 3.11 o superior.' }
    $centerArguments = @('-m', 'arkos_pilot.task_center', '--state-dir', $StateDirectory, '--port', "$Port")
    if ($RelaySnapshot -or $RelayDeviceId) {
        if (-not $RelaySnapshot -or -not $RelayDeviceId) { throw 'Configurá juntos RelaySnapshot y RelayDeviceId.' }
        $centerArguments += @('--relay-snapshot', $RelaySnapshot, '--relay-device-id', $RelayDeviceId)
    }
    if ($NoBrowser) { $centerArguments += '--no-browser' }
    & $PythonPath @centerArguments
    $centerExit = $LASTEXITCODE
} finally { Pop-Location }
exit $centerExit
