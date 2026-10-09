# Guided trial launcher. No downloads, execution-policy changes or background services.
param(
    [string]$StateDirectory = (Join-Path $env:LOCALAPPDATA 'ArkosTaskCenterTrial'),
    [int]$Port = 0,
    [string]$PythonPath,
    [string]$RelaySnapshot,
    [string]$RelayDeviceId,
    [switch]$CheckOnly,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
# Temporarily disable runtime-manager installation for probes and launch.
# Restore the caller's process environment even on error or Ctrl+C.
$runtimeEnvironment = @{}
foreach ($setting in @('PYTHON_MANAGER_AUTOMATIC_INSTALL', 'PYLAUNCHER_ALLOW_INSTALL', 'PYLAUNCHER_ALWAYS_INSTALL', 'PYLAUNCHER_DRYRUN')) {
    $runtimeEnvironment[$setting] = @{
        Present = [Environment]::GetEnvironmentVariables('Process').Contains($setting)
        Value = [Environment]::GetEnvironmentVariable($setting, 'Process')
    }
}
try {
    [Environment]::SetEnvironmentVariable('PYTHON_MANAGER_AUTOMATIC_INSTALL', 'false', 'Process')
    foreach ($setting in @('PYLAUNCHER_ALLOW_INSTALL', 'PYLAUNCHER_ALWAYS_INSTALL', 'PYLAUNCHER_DRYRUN')) {
        Remove-Item -LiteralPath "Env:$setting" -ErrorAction SilentlyContinue
    }
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $selectedPython = $null
    $pythonPrefix = @()
    # A supplied executable is authoritative: do not silently choose another runtime.
    $candidates = if ($PythonPath) { @($PythonPath) } else { @('py', 'python', 'python3') }
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $prefix = @()
        if (-not $PythonPath -and $candidate -eq 'py') { $prefix = @('-3') }
        try {
            & $command.Source @prefix -B -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
        } catch { continue }
        if ($LASTEXITCODE -eq 0) {
            $selectedPython = $command.Source
            $pythonPrefix = $prefix
            break
        }
    }
    if (-not $selectedPython) {
        Write-Error 'No se encontró un Python 3.11+ utilizable. Instalalo o indicá -PythonPath con su ejecutable. ARKOS no descarga ni reemplaza runtimes.'
        exit 2
    }
    Push-Location $repoRoot
    try {
        $launchArguments = @('-m', 'arkos_pilot.launcher', '--state-dir', $StateDirectory, '--port', "$Port")
        if ($RelaySnapshot -or $RelayDeviceId) {
            if (-not $RelaySnapshot -or -not $RelayDeviceId) { throw 'Configurá juntos RelaySnapshot y RelayDeviceId.' }
            $launchArguments += @('--relay-snapshot', $RelaySnapshot, '--relay-device-id', $RelayDeviceId)
        }
        if ($CheckOnly) { $launchArguments += '--check-only' }
        if ($NoBrowser) { $launchArguments += '--no-browser' }
        & $selectedPython @pythonPrefix -B @launchArguments
        $launchExit = $LASTEXITCODE
    } finally { Pop-Location }
} finally {
    foreach ($setting in $runtimeEnvironment.Keys) {
        $original = $runtimeEnvironment[$setting]
        if ($original.Present) {
            [Environment]::SetEnvironmentVariable($setting, [string]$original.Value, 'Process')
        } else {
            # On .NET 10, binding PowerShell $null to a string creates an empty
            # variable. The environment provider explicitly removes it instead.
            Remove-Item -LiteralPath "Env:$setting" -ErrorAction SilentlyContinue
        }
    }
}
exit $launchExit
