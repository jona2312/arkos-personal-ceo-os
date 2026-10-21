# Conversación por voz local — aceptación física pendiente

## Alcance y base

Trabajo separado sobre PR #20, `a73bcb24b23cd583000101f87c1465473f2da9cf`,
rama `codex/arkos-local-voice`. Conserva chat, HermesBridge, historial, cola,
relay de solo lectura, dictado editable y aprobación del contenido exacto.
No modifica Hermes instalado, perfiles, modelo Qwen ni el launcher funcional.
No habilita herramientas, Cloud, descargas ni instalaciones.

## Componentes realmente disponibles (PC Windows, 21 de octubre de 2026)

| Parte | Hermes Desktop recuperado | ARKOS de esta rama |
|---|---|---|
| Captura | Chromium/Electron, micrófono, detección de silencio, monitor de interrupción | Web Audio a 16 kHz; permiso explícito, RMS sostenido y silencio de 750 ms |
| Transcripción | Registros de hoy confirman faster-whisper `small` | Mismo runtime/modelo local existente, CPU/int8, español; sin descarga |
| Modelo | Qwen3.8-27B-UD-Q4_K_M en llama.cpp local | Mismo modelo a través del puente existente, sin herramientas |
| Respuesta hablada | Historial y registro de la voz recuperada identifican ElevenLabs/Luxuria: servicio externo | Piper 1.8.0, Daniela es_AR high ya instalada: local, sin claves |
| Alternativa anterior | Edge/Elena también usa servicio externo, aunque no requiera una suscripción | No se utiliza ni como respaldo |
| Audio guardado | El historial contiene archivos TTS anteriores | Captura, transcripción y reproducción en memoria; no guarda audio por defecto |

El motor local disponible es faster-whisper 1.2.1 y la voz ONNX instalada ocupa
114.199.011 bytes más JSON. No se copia al paquete ni se cambia la voz configurada
en Hermes. Reutilizar su código de alto nivel directamente arrastraría API de perfiles,
resolución de credenciales, proveedores remotos y descargas perezosas. Esta integración
reutiliza los componentes instalados, con rutas fijas y proceso sin credenciales;
adapta las ideas de pre-roll, umbral durante reproducción y descarte de eco del
código de Hermes. La heurística de eco no equivale a cancelación acústica certificada.

## Inicio y cierre

El acceso **Abrir Hermes** del escritorio usa el launcher conservado en
`C:\ArkosReview\hermes-desktop-launcher\Abrir-Hermes.ps1`.
Configura solo el entorno del proceso: `HERMES_HOME=D:\ARKOS\hermes`,
`HERMES_DESKTOP_HERMES_ROOT=D:\ARKOS\hermes\hermes-agent`,
`HERMES_DESKTOP_PYTHON=<Python privado existente>`, `HERMES_DISABLE_LAZY_INSTALLS=1`,
y elimina `ELECTRON_RUN_AS_NODE` para ese proceso. No cambia variables globales.
La raíz y el Python explícitos evitan buscar otra instalación en AppData; el flag de
lazy installs por sí solo NO evita el instalador de Desktop. El fallo observado fue
búsqueda de raíz incorrecta y checkout fallido por rutas largas en la instalación nueva.
Los cuatro cambios locales y `arkos-pilot` se conservan. El launcher ofrece `-CheckOnly`.

Para ARKOS, usar las opciones existentes de `python -m arkos_pilot.task_center`:

```powershell
& <Python-del-centro> -m arkos_pilot.task_center --state-dir <estado-exclusivo> --port 0 `
  --hermes-python <Python-privado> --hermes-source <fuente-existente> `
  --hermes-home <perfil-arkos-bridge-existente> --hermes-model <modelo-actual> `
  --dictation-python <Python-con-Whisper-y-Piper> --dictation-model <Whisper-local> `
  --voice-piper-model <voz.onnx-existente>
```

Son marcadores de rutas, no un comando listo para copiar. Sin estos componentes el
botón queda deshabilitado. No hay configuración de prueba activa distribuida.
El enlace de sesión es privado: no incluirlo en capturas ni compartirlo.
El launcher general conserva su comportamiento; esta opción requiere configuración explícita.

Activar **Conversar por voz** una vez. Primero prepara los motores y solicita permiso.
Muestra escuchando, procesando, hablando o pausado. El reconocimiento envía al mismo
formulario e historial del chat local. Dictar sigue dejando texto editable sin enviarlo.
**Detener conversación y micrófono**, ocultar/cerrar pestaña, cambiar de modo o empezar
dictado libera las pistas y el AudioContext y cancela el proceso de voz propio.
Ctrl+C cierra el servidor y sus workers, sin cerrar llama.cpp ni Hermes Desktop.
Un worker abandonado se libera después de 120 s inactivo; pedidos limitados a 90 s.

## Latencia: qué se puede y qué no se puede afirmar

El panel guarda solo hasta 50 mediciones numéricas en memoria de la página:

- Última muestra con voz detectada → transcripción lista (incluye espera de silencio).
- Transcripción lista → **respuesta completa** del puente.
- Respuesta completa → inicio de reproducción programado por Web Audio.

El puente actual devuelve un contrato JSON final validado. No expone primer fragmento
del modelo: ese dato queda `null`, no se confunde con respuesta completa. Web Audio
no acredita el instante de sonido físico del Admiral: `audible_audio_ms` queda `null`.
Medir ambos extremos con precisión requiere instrumentar streaming en el puente y
captura/calibración de salida acústica, respectivamente. No se simulan esos datos.

Piper sintetiza frases completas y prepara la siguiente mientras reproduce la actual.
Esto reduce esperas entre síntesis; NO permite hablar antes de recibir la respuesta
completa del modelo. No se reestructura el contrato de propuestas para obtener una demo.

Comparación de componentes con el MISMO archivo sintético preexistente, tres muestras
en esta PC mientras Hermes seguía en uso (no benchmark de rendimiento humano):

| Componente | Antes | Proceso residente |
|---|---|---|
| Whisper por solicitud | 5370 / 5200 / 4955 ms | 2742 / 2651 / 2589 ms |
| Piper | Sin comparación anterior equivalente | 2881 / 624 / 688 ms |
| Preparación conjunta | No aplicable | 6649 ms |

La carga repetida es una demora medida y eliminada en la transcripción. No se afirma
que sea el mayor cuello de botella de cinco turnos reales: esa medición sigue pendiente.
La prueba de componentes no reprodujo audio ni usó micrófono físico.

## Aceptación física obligatoria

Pendiente: Jona estaba usando Hermes y pidió preparar ARKOS sin interrumpirlo.
Antes de probar, detener su sesión de voz para evitar dos micrófonos/asistentes activos.

1. Activar ARKOS, confirmar el indicador y decir cinco frases distintas consecutivas.
2. Registrar por turno los tiempos disponibles, cortes, pausas y si sale por Admiral.
3. Durante una respuesta, decir «Pará, resumilo». Comprobar corte y nuevo turno completo.
4. Dejar silencio: no debe generar mensajes. Dejar sonar una respuesta sin hablar:
   no debe reenviarse a sí misma. Repetir con el volumen y distancia habituales.
5. Detener: confirmar pistas terminadas e indicador del navegador apagado; hablar no
   debe enviar nada. Cerrar pestaña durante permiso, STT, modelo y reproducción.
6. Si se propone nota, verificar que permanece propuesta y requiere botón de creación,
   aprobación y ejecución separados. Hablar «aprobala» no ejecuta tareas.

Limitaciones: RMS y el AEC solicitado al navegador pueden fallar ante ruido/altavoces;
el filtro de eco puede rechazar una repetición intencional. Una falsa detección puede
cortar playback aunque se descarte la transcripción. No se certifica ausencia de eco
ni interrupción física hasta completar esta aceptación. Primer audio de Piper puede
tener coste de calentamiento; texto largo y respuestas de Qwen pueden añadir pausas.

## Verificación automatizada

`tests/test_voice.py`: reutilización de proceso, aislamiento de entorno, validación,
cancelación previa y durante trabajo, timeout, exclusión de sesiones, Host/Origin/token,
consulta de tareas no bloqueada y ausencia de tareas creadas.
`scripts/Test-ArkosVoice.cjs`: cinco turnos SINTÉTICOS, silencio, interrupción, filtro de
eco, cierre, permiso denegado/tardío y pestaña oculta. No sustituye prueba física.
Se conserva la regresión del dictado y del chat/propuestas.
