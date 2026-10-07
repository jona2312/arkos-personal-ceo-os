# Runs the ARKOS relay agent for the current Windows user (outbound HTTPS only).
# Usage: ./scripts/Start-ArkosAgent.ps1 pair --server https://relay.example --code XXXX-XXXX-XXXX
#        ./scripts/Start-ArkosAgent.ps1 allow-root videos "$env:USERPROFILE\Videos"
#        ./scripts/Start-ArkosAgent.ps1 run
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$AgentArguments)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw 'Instala Python 3.11 o superior y agrégalo a PATH.' }
    & $pythonCommand.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Se requiere Python 3.11 o superior.' }
    if (-not $AgentArguments) { $AgentArguments = @('status') }
    & $pythonCommand.Source -m arkos_relay agent @AgentArguments
    $agentExit = $LASTEXITCODE
} finally { Pop-Location }
exit $agentExit
