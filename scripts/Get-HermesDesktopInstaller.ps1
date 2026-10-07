param([string]$DestinationDirectory = (Join-Path $env:LOCALAPPDATA 'ArkosPilot\downloads'))
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Se requiere Windows para validar Authenticode.' }
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content (Join-Path $repoRoot 'config\hermes-desktop-pilot.json') -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
$targetPath = Join-Path $DestinationDirectory 'Hermes-Setup.exe'
if (Test-Path $targetPath) { throw "Ya existe $targetPath. Revisa ese archivo; no se sobrescribe automáticamente." }
$temporaryPath = Join-Path $DestinationDirectory ([guid]::NewGuid().ToString() + '.exe')
try {
    Invoke-WebRequest -Uri $manifest.installer_url -OutFile $temporaryPath -UseBasicParsing
    $actualHash = (Get-FileHash $temporaryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $manifest.installer_sha256 -or (Get-Item $temporaryPath).Length -ne $manifest.installer_size) {
        throw 'El instalador cambió respecto del revisado. Verifica la nueva versión antes de continuar.'
    }
    $signature = Get-AuthenticodeSignature $temporaryPath
    if ($signature.Status -ne 'Valid') { throw "Firma no válida: $($signature.Status). No se prepara el ejecutable." }
    Move-Item -LiteralPath $temporaryPath -Destination $targetPath
    [ordered]@{
        file = $targetPath
        sha256 = $actualHash
        signature_status = [string]$signature.Status
        signer = $signature.SignerCertificate.Subject
        signer_thumbprint = $signature.SignerCertificate.Thumbprint
        executed = $false
        next_step = 'Verifica el firmante y revisa el bootstrap antes de instalar. Este script solo descarga y comprueba; no ejecuta el instalador.'
    } | ConvertTo-Json
} finally {
    if (Test-Path $temporaryPath) { Remove-Item -LiteralPath $temporaryPath }
}
