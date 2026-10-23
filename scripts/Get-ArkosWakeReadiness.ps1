# Diagnostico de solo lectura: requisitos para encender la PC a distancia (Wake-on-LAN).
# No cambia BIOS, adaptadores, energia, firewall ni router. No informa MAC, IP ni nombres de red.
# Uso: ./scripts/Get-ArkosWakeReadiness.ps1            (JSON en la salida)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Este diagnostico corresponde a Windows.' }

function Try-Read([scriptblock]$block) {
    try { return & $block } catch { return [ordered]@{ error = $_.Exception.GetType().Name } }
}

$adapters = @(Try-Read { Get-NetAdapter -Physical -ErrorAction Stop }) | Where-Object { $_ -and $_.Name }
$adapterReport = foreach ($adapter in $adapters) {
    $power = Try-Read { Get-NetAdapterPowerManagement -Name $adapter.Name -ErrorAction Stop }
    $advanced = @(Try-Read {
        Get-NetAdapterAdvancedProperty -Name $adapter.Name -ErrorAction Stop |
            Where-Object { $_.DisplayName -match 'Wake|WOL|Magic|Shutdown|Energy|EEE|Green' } |
            ForEach-Object { [ordered]@{ setting = $_.DisplayName; value = $_.DisplayValue } }
    })
    [ordered]@{
        description = $adapter.InterfaceDescription
        wired = [bool]($adapter.PhysicalMediaType -match '802\.3')
        status = [string]$adapter.Status
        wake_on_magic_packet = if ($power -and $power.WakeOnMagicPacket) { [string]$power.WakeOnMagicPacket } else { 'desconocido' }
        windows_may_turn_off_device = if ($power -and $power.AllowComputerToTurnOffDevice) { [string]$power.AllowComputerToTurnOffDevice } else { 'desconocido' }
        driver_settings = $advanced
    }
}

$wakeArmed = @(Try-Read { & powercfg /devicequery wake_armed 2>$null }) | Where-Object { $_ -and $_ -notmatch '^NONE$|^NINGUNO$' }
$sleepStates = (Try-Read { (& powercfg /a 2>$null) -join "`n" })
$fastStartup = Try-Read {
    (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -ErrorAction Stop).HiberbootEnabled
}
$battery = [bool](Try-Read { Get-CimInstance Win32_Battery -ErrorAction Stop })
$gateway = [bool](Try-Read { Get-NetIPConfiguration -ErrorAction Stop | Where-Object { $_.IPv4DefaultGateway } })

$wired = @($adapterReport | Where-Object { $_.wired })
$findings = [System.Collections.Generic.List[string]]::new()
if (-not $wired.Count) { $findings.Add('Sin adaptador Ethernet fisico: Wake-on-LAN por Wi-Fi casi nunca funciona con la PC apagada.') }
elseif (-not ($wired | Where-Object { $_.wake_on_magic_packet -eq 'Enabled' })) { $findings.Add('El adaptador Ethernet no tiene "Wake on Magic Packet" habilitado en Windows.') }
if ($fastStartup -eq 1) { $findings.Add('Inicio rapido de Windows activo: desde "apagado" (S5) puede impedir el encendido por red en algunos equipos.') }
if (-not $gateway) { $findings.Add('Sin puerta de enlace: la PC no esta en una red con router.') }
if ($battery) { $findings.Add('Equipo con bateria: muchas notebooks solo despiertan por red conectadas a corriente y con la tapa abierta.') }

[ordered]@{
    checked_at = (Get-Date).ToUniversalTime().ToString('o')
    adapters = @($adapterReport)
    wake_armed_devices = @($wakeArmed)
    sleep_states = $sleepStates
    fast_startup_enabled = $fastStartup
    has_battery = $battery
    has_default_gateway = $gateway
    findings = @($findings)
    not_verifiable_from_windows = @(
        'BIOS/UEFI: "Wake on LAN" / "Power On by PCI-E" habilitado y "ErP/Deep Sleep" deshabilitado (hay que entrar al setup).',
        'Que la placa mantenga energia en la placa de red con la PC apagada (luz del puerto encendida).',
        'Un emisor siempre encendido dentro de la misma red local: el relay en internet no puede enviar el paquete magico a la LAN sin abrir puertos.'
    )
    note = 'Solo lectura. No se modifico ninguna configuracion. Sin MAC, IP ni nombres de red.'
} | ConvertTo-Json -Depth 6
