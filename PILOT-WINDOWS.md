# ARKOS: paquete Windows de prueba

**No es un instalador autónomo.** Requiere un Python 3.11+ real, instalado
manualmente, con SQLite. No contiene Python, Hermes, modelos, FFmpeg, claves,
perfiles, conversaciones ni configuración de prueba activa. No instala nada.
No se promete compatibilidad ni velocidad de modelos: no se han medido aquí.

El centro usa biblioteca estándar. No necesita pip, Node, Git ni el SDK Cloud
para abrirse. PowerShell y un navegador moderno son requisitos manuales.
FFmpeg es opcional, solo para recortes; las notas no lo requieren.
Cloud queda deshabilitado por defecto. Hermes figura por conectar. La voz y
Equipo siguen pendientes; no se activa el micrófono. La lectura relay sigue
siendo solo lectura y necesita configuración explícita fuera de esta prueba.

## Verificar y extraer

Obtener ZIP y `.zip.sha256` del mismo artefacto de CI del commit indicado.
Comparar `(Get-FileHash -Algorithm SHA256 .\arkos-windows-pilot-*.zip).Hash`
con el checksum publicado en CI. Un checksum detecta corrupción, no autentica
un origen: verificar también repositorio, commit y ejecución de GitHub Actions.
Extraer con el Explorador a una carpeta **nueva**, por ejemplo
`C:\ArkosPilotTest`. No extraer encima de una instalación o checkout existente.
`MANIFEST.json` identifica versión, commit, dependencias y hashes de cada archivo
de contenido. `SHA256SUMS.txt` incluye además el manifiesto; no se incluye a sí
mismo. El checksum externo cubre el ZIP completo.

## Diagnóstico e inicio

Abrir PowerShell en la carpeta extraída. Elegir una ruta de Python existente
y una carpeta de estado nueva, exclusiva para esta prueba:

```powershell
$python = 'C:\ruta\real\python.exe' # Reemplazar por el Python instalado
$trial = Join-Path $env:LOCALAPPDATA 'ArkosPackagedTrial-01'
if (Test-Path -LiteralPath $trial) { throw 'Elegí otra carpeta de estado nueva' }
.\scripts\Open-Arkos.ps1 -PythonPath $python -StateDirectory $trial -CheckOnly
Test-Path -LiteralPath $trial # Debe ser False
.\scripts\Open-Arkos.ps1 -PythonPath $python -StateDirectory $trial -Port 0
```

CheckOnly comprueba Python, SQLite, recursos web, carpeta, puerto y espacio en
el volumen de estado sin crear la cola. Exige una reserva operativa de 100 MiB;
no es una estimación para modelos ni garantía de capacidad futura. Espacio y
permisos pueden cambiar después. Un error bloquea el inicio; no descarga nada.
La extracción también necesita espacio para el ZIP y su contenido: sumar los
bytes del manifiesto, el ZIP y margen libre antes de extraer.

El launcher abre el navegador y sirve solo en loopback. Conservá abierta la
consola. El enlace contiene una clave de sesión: **no compartirlo ni adjuntarlo
a informes**. No hace falta abrir firewall. Para impedir la apertura automática
del navegador, agregar `-NoBrowser` y usar el enlace privado de la consola.

Si la política bloquea PowerShell, no cambiar políticas ni usar bypass. Desde
la carpeta extraída se puede usar un ejecutable Python autorizado directamente:

```powershell
& $python -B -m arkos_pilot.launcher --state-dir $trial --check-only
& $python -B -m arkos_pilot.launcher --state-dir $trial --port 0
```

Diagnóstico adicional opcional: `.\scripts\Get-ArkosDesktopReadiness.ps1`.
Solo informa hardware y detecciones; no acredita rendimiento ni que un alias
funcione. Revisar cualquier informe antes de compartirlo. Ante un fallo guardar
solo código de salida y checks sanitizados, nunca claves ni datos personales.

## Cerrar y retirar

1. Esperar a que terminen las tareas. Pulsar **Ctrl+C en la consola que inició
   esta prueba**; cerrar su pestaña del navegador no detiene el servidor.
2. Confirmar que el puerto de esa sesión ya no acepta conexiones. No detener
   otros procesos Python. Si se interrumpió una tarea, revisar su resultado
   manualmente; no volver a ejecutarla a ciegas.
3. Conservar los archivos deseados de `outputs` antes de retirar la prueba.
4. Eliminar con el Explorador solo la carpeta de extracción elegida, su ZIP y
   la carpeta de estado exacta elegida en `$trial`. Esto borra la cola y notas
   de prueba. No eliminar una carpeta padre ni otras instalaciones.

No hay servicio, arranque automático, acceso directo ni desinstalador. El Python
manual y otras herramientas existentes permanecen intactos.

## Aceptación pendiente en una segunda PC

Registrar versión Windows, PowerShell, Python, SHA del paquete y resultado real
de cada paso (PASS/FAIL/NO VERIFICABLE). **Esta lista no acredita una aceptación.**

- Verificar checksum y manifiesto; extraer en ruta nueva con espacios y acentos.
- Python ausente o versión no válida: error claro, cero instalaciones automáticas.
- CheckOnly con Python válido: PASS, sin carpeta de estado; puerto ocupado:
  rechazo sin crear estado. Registrar espacio detectado.
- Abrir con puerto 0; interfaz legible. Hermes por conectar, Cloud deshabilitado,
  sin respuestas simuladas, sin micrófono ni conexiones externas configuradas.
- Crear una nota sintética; comprobar pendiente, sin archivo generado. Aprobar:
  comprobar que todavía no se ejecutó. Ejecutar explícitamente y revisar archivo.
- Sin configurar un relay real, verificar que su ausencia no impide tareas locales.
- Ctrl+C, verificar cierre; reabrir con el mismo estado y comprobar persistencia.
- Retirar según el procedimiento y comprobar que otras instalaciones no cambiaron.

No conectar servicios productivos ni usar tareas o documentos personales.
