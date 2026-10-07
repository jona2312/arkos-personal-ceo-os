param(
    [Parameter(Mandatory=$true)][string]$StateDirectory,
    [int]$Port = 8765,
    [string]$PythonPath = 'python',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    & $PythonPath -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Se requiere Python 3.11 o superior.' }
    $centerArguments = @('-m', 'arkos_pilot.task_center', '--state-dir', $StateDirectory, '--port', "$Port")
    if ($NoBrowser) { $centerArguments += '--no-browser' }
    & $PythonPath @centerArguments
    $centerExit = $LASTEXITCODE
} finally { Pop-Location }
exit $centerExit
