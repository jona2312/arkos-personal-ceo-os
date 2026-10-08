# Integración de lectura relay → centro de tareas

Rama de integración de la interfaz #3 con el productor #4 (`faee05b`). El diseño aprobado se conserva. No requiere instalar paquetes Python adicionales.

## Configuración explícita en Windows

Primero vincular el lector y ejecutar `agent view-sync` según `docs/RELAY_SNAPSHOT_CONTRACT.md`. El usuario debe autorizar el lector; esta pantalla no emite credenciales ni inicia ese proceso.

```powershell
# Después de vincular el agente, usando su carpeta de estado por defecto:
$relayDeviceId = (Get-Content "$env:LOCALAPPDATA\ArkosRelayAgent\agent.json" -Raw | ConvertFrom-Json).device_id
./scripts/Start-ArkosTaskCenter.ps1 -StateDirectory "$env:LOCALAPPDATA\ArkosTaskCenterTrial" -RelaySnapshot "$env:LOCALAPPDATA\ArkosRelayAgent\viewer\relay-snapshot.json" -RelayDeviceId $relayDeviceId
```

Si el agente se vinculó con una carpeta de estado distinta, usá su `agent.json` y el snapshot correspondiente. Estos comandos no instalan el agente ni lo vinculan. Para la aceptación no usar `D:\ARKOS`: conservar el checkout y el estado de prueba separados de la instalación existente.

Los dos parámetros de lectura son opcionales pero se deben proporcionar juntos. El ID real tiene prefijo `dev_` y 32 caracteres hexadecimales. Sin configuración se mantiene la pantalla local y el aviso «Conexión pendiente». No hay búsqueda automática de archivos, lectura de tokens ni llamadas al relay desde la interfaz.

## Comportamiento

El endpoint privado `/api/remote-view` lee y cierra el archivo en cada actualización. Limita la lectura a 1 MiB y 500 tarjetas, acepta solo UTF-8 sin BOM y valida esquema, versión, origen, identificadores, estados y destino esperado. Un archivo ausente, mal formado o de otro dispositivo devuelve una vista vacía «Sin información disponible», sin revelar rutas ni errores del sistema. Reemplazar el archivo con uno válido recupera la vista en la próxima actualización.

Los nueve estados se muestran separados. `claimed` indica reserva, no ejecución. `unknown` requiere revisión y nunca activa un reintento. Se recalcula la frescura con el reloj del lector: pasado el límite del productor (máximo 120 s), o con una fecha futura, no se muestra como sincronizado. `offline` conserva la copia con aviso; `unauthorized` y `never_synced` ocultan las tarjetas. Una copia truncada tiene un aviso visible. La frescura no prueba que la PC ejecutora esté conectada.

Acoplamiento explícito del contrato v1: el productor escribe `stale_after_seconds: 120` y el lector admite límites positivos de hasta 120 s. Mantener `agent view-sync --interval` por debajo de ese límite (por defecto 30 s); la latencia o los fallos de conexión igualmente pueden volver stale la copia. Un cambio del límite exige actualizar y probar ambos extremos.

Solo se proyectan campos necesarios para mostrar las tarjetas. No se entregan parámetros, rutas, hashes de aprobación ni credenciales al navegador. El texto se muestra con `textContent`. Los resultados son metadatos; no se abren, verifican ni descargan archivos remotos. Que el productor marque `available` no significa que esta pantalla haya comprobado su SHA-256.

Leer no crea tareas locales, no aprueba, reserva, consume aprobaciones ni ejecuta. No cambia la cola, el diario ni las credenciales del agente. El snapshot y el espejo del productor siguen sin cifrado en reposo: esto no añade cifrado de extremo a extremo ni aislamiento frente a otro proceso con acceso a los archivos del mismo usuario.

## Verificación

`python -m unittest discover -s tests -q` verifica el conjunto piloto, relay, productor y lector. La prueba conjunta usa el servicio relay con transporte WSGI en proceso, produce el snapshot real con `ViewerSync` y consulta la pantalla por HTTP real en loopback. Confirma que la tarea sigue aprobada con cero intentos y que la cola local está vacía. No equivale a una prueba con servidor HTTPS desplegado ni en la PC del usuario.

`node scripts/Test-ArkosRemoteView.cjs` valida el contrato de presentación. `scripts/Test-ArkosTaskCenter.cjs` verifica el navegador, tareas locales, estilos y tarjetas remotas sintéticas. Esas tarjetas son datos de prueba, no una conexión desplegada.

Pendientes: prueba de aceptación en la PC Windows, relay HTTPS real, arranque del lector al iniciar sesión, aprobaciones desde la pantalla y descarga segura de resultados. WhatsApp sigue sin emisor. No se modifica Supabase ni se despliega nada con esta integración.
