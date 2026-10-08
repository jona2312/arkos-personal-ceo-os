# Apertura guiada del piloto ARKOS

Desde un checkout aislado en Windows, con Python 3.11+ instalado:

```powershell
# Diagnóstico sin crear el estado ni abrir el navegador:
./scripts/Open-Arkos.ps1 -CheckOnly

# Abrir la pantalla; crea el estado de prueba si falta:
./scripts/Open-Arkos.ps1
```

Usa `%LOCALAPPDATA%\ArkosTaskCenterTrial` por defecto; no `D:\ARKOS`. El puerto predeterminado `0` deja que Windows elija uno libre. El servidor muestra un enlace privado de sesión y abre el navegador; cerrá la consola con Ctrl+C cuando termines. No compartas ese enlace. El launcher no cambia ExecutionPolicy: si PowerShell bloquea un script, no eludas la política; usá el comando Python directo permitido por tu equipo o revisá la política con su administrador.

## Opciones

```powershell
./scripts/Open-Arkos.ps1 -StateDirectory "$env:TEMP\ArkosAcceptance\center" -CheckOnly
./scripts/Open-Arkos.ps1 -PythonPath 'C:\ruta\python.exe' -NoBrowser
```

El ejecutable indicado es autoritativo: si falla o no es Python 3.11+, no se selecciona otro silenciosamente. Sin `PythonPath`, intenta `py -3`, `python` y `python3`, verificando la versión. Desactiva temporalmente la instalación automática del administrador/launcher de Python durante la comprobación y ejecución, y restaura esos ajustes de proceso al terminar. No escribe la configuración permanente de Python. Referencias oficiales: [administrador de Python](https://docs.python.org/3/using/windows.html#configuration), [launcher anterior](https://docs.python.org/3.11/using/windows.html#install-on-demand).

Invoca Python con `-B` para evitar escrituras de bytecode. No crea un entorno virtual, instala paquetes, descarga modelos ni consulta credenciales. El centro actual usa solo biblioteca estándar; Node/Playwright son herramientas de desarrollo y no requisitos de uso.

El diagnóstico verifica versión, SQLite, archivos web, disposición de la carpeta de estado y disponibilidad del puerto local. Rechaza un estado que sea archivo/enlace, salidas que sean archivo/enlace o una base que sea carpeta/enlace. No modifica SQLite durante el diagnóstico. Verificar acceso a la carpeta y el puerto es orientativo: permisos, bloqueo de SQLite o carreras de puerto pueden cambiar después; la apertura real también maneja el error sin mostrar una traza con rutas.

FFmpeg es opcional: si no está en PATH, se puede trabajar con notas. El launcher no asegura que Hermes, voz, GPU o modelos funcionen ni los abre. Tampoco evalúa seguridad de un ejecutable Python arbitrario elegido por el operador.

## Lectura del relay

Solo después de vincular el agente y el lector mediante el flujo autorizado:

```powershell
$relayDeviceId = (Get-Content "$env:LOCALAPPDATA\ArkosRelayAgent\agent.json" -Raw | ConvertFrom-Json).device_id
./scripts/Open-Arkos.ps1 -RelaySnapshot "$env:LOCALAPPDATA\ArkosRelayAgent\viewer\relay-snapshot.json" -RelayDeviceId $relayDeviceId
```

Usá la configuración correspondiente si se eligió una carpeta distinta para el agente. Un snapshot ausente/desactualizado produce un aviso y permite abrir la pantalla local; un ID inválido o parámetro de lectura incompleto bloquea la apertura. No obtiene tokens, crea credenciales, inicia `view-sync` ni ejecuta la cola. Para sincronizar siguen siendo necesarios el relay y el lector por separado.

## Python directo y aceptación

```powershell
python -B -m arkos_pilot.launcher --state-dir "$env:LOCALAPPDATA\ArkosTaskCenterTrial" --check-only
python -B -m arkos_pilot.launcher --state-dir "$env:LOCALAPPDATA\ArkosTaskCenterTrial"
```

El ejemplo directo presupone un Python real ya instalado. Fuera de Windows, indicar `--state-dir` explícitamente. La salida del diagnóstico es JSON con `ready`, comprobaciones y advertencias; retorna `0` si se puede intentar abrir, `2` si faltan requisitos. No publica enlaces ni rutas de credenciales en ese reporte.

Pruebas nuevas: diagnóstico sin estado, FFmpeg ausente, puerto ocupado, disposición inválida preservada, configuración relay parcial/ausente, errores comprensibles y apertura real por subprocess hasta consulta privada de una cola vacía. CI Windows también analiza PowerShell y ejecuta `Open-Arkos.ps1 -CheckOnly`, verificando que no cree estado y restaure el ajuste del administrador Python. Falta la prueba en la PC del usuario.

Esto es un launcher de prueba, no un instalador empaquetado para distribución pública. No crea acceso directo, servicio ni tarea programada; no reemplaza Hermes ni el launcher previo.
