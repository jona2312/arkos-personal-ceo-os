param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ArkosArguments)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Instala Python 3.11 o superior y agrégalo a PATH. Luego vuelve a ejecutar este script.' }
    & $pythonCommand.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Se requiere Python 3.11 o superior.' }
    $pilotPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $pilotPython)) {
        & $pythonCommand.Source -m venv (Join-Path $repoRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno local.' }
    }
    if (-not $ArkosArguments) { $ArkosArguments = @('doctor') }
    & $pilotPython -m arkos_pilot @ArkosArguments
    $pilotExit = $LASTEXITCODE
} finally { Pop-Location }
exit $pilotExit
