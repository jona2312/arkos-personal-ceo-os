param([Parameter(Mandatory=$true)][string]$PythonPath)
$ErrorActionPreference = 'Stop'
$names = @('PYTHON_MANAGER_AUTOMATIC_INSTALL','PYLAUNCHER_ALLOW_INSTALL','PYLAUNCHER_ALWAYS_INSTALL','PYLAUNCHER_DRYRUN')
$trialRoot = Join-Path ([IO.Path]::GetTempPath()) ('arkos-env-' + [guid]::NewGuid().ToString('N'))
$saved = @{}
function Snapshot {
    $values = [Environment]::GetEnvironmentVariables('Process')
    $rows = foreach ($name in $names) {
        [pscustomobject]@{Name=$name;Present=$values.Contains($name);Value=$values[$name]}
    }
    ConvertTo-Json -InputObject @($rows) -Compress
}
foreach($name in $names) {
    $saved[$name]=@{Present=(Test-Path "Env:$name");Value=[Environment]::GetEnvironmentVariable($name)}
}
try {
    foreach ($kind in @('absent','empty','value')) {
        foreach ($outcome in @('success','nonzero','exception','missing-python')) {
            foreach ($name in $names) {
                Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
                if ($kind -ne 'absent') {
                    $value = if ($kind -eq 'empty') { '' } else { 'original-value' }
                    [Environment]::SetEnvironmentVariable($name,$value,'Process')
                }
            }
            if ($kind -eq 'empty' -and -not (Test-Path "Env:$($names[0])")) {
                Write-Output "SKIP empty: this platform cannot retain empty environment values"
                break
            }
            $before = Snapshot
            $options=@{StateDirectory=$trialRoot;PythonPath=$PythonPath;CheckOnly=$true}
            if($outcome -eq 'nonzero'){$options.Port=-1}
            if($outcome -eq 'exception'){$options.RelaySnapshot='synthetic-incomplete'}
            if($outcome -eq 'missing-python'){$options.PythonPath=Join-Path $trialRoot 'missing-python.exe'}
            $caught=$false; $exitCode=0
            try { & "$PSScriptRoot/Open-Arkos.ps1" @options | Out-Null; $exitCode=$LASTEXITCODE }
            catch { $caught=$true }
            if ($before -cne (Snapshot)) { throw "Environment changed: $kind/$outcome" }
            if (Test-Path -LiteralPath $trialRoot) { throw 'CheckOnly created state' }
            if ($outcome -eq 'success' -and ($caught -or $exitCode -ne 0)) { throw 'Expected success' }
            if ($outcome -eq 'nonzero' -and ($caught -or $exitCode -ne 2)) { throw 'Expected exit 2' }
            if ($outcome -in @('exception','missing-python') -and -not $caught) { throw 'Expected exception' }
            Write-Output "PASS $kind/$outcome"
        }
    }
    Write-Output "PowerShell $($PSVersionTable.PSVersion); no state created"
} finally {
    foreach($name in $names) {
        if($saved[$name].Present){[Environment]::SetEnvironmentVariable($name,[string]$saved[$name].Value,'Process')}
        else{Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue}
    }
}
