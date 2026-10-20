# Dictado local → nota verificable

Implementación sobre PR #18, `bd53cf682de150ff6a1c57979eb69100b187fbc4`,
rama `codex/arkos-local-dictation`. Se conserva la base de la conversación local
recuperada; no incorpora los cambios Cloud independientes de #19.
El acceso instalado y su conversación activa no se reemplazan durante esta prueba.

## Contrato

1. Activación explícita de micrófono, máximo 30 segundos. Detener transcribe;
   descartar, ocultar o cerrar la página libera los tracks. No hay escucha permanente.
2. WAV mono PCM16 a 16 kHz en memoria. API autenticada, Host/Origin existentes,
   límite de cuerpo 1.281.000 bytes. No Web Speech ni proveedor remoto.
3. Un proceso faster-whisper CPU int8 por dictado, cuatro hilos, máximo 90 segundos.
   Ejecutable y directorio de modelo son configuración del operador, nunca del navegador.
   Modelo completo existente, `local_files_only=True`, modo offline y bloqueo de
   conexiones Python. No instalación automática. No se conservan archivos de audio.
4. Texto agregado al campo editable; nunca enviado automáticamente. Cambio de
   conversación descarta dictado pendiente. El micrófono no está disponible en Cloud.
5. HermesBridge existente recibe el texto enviado explícitamente. Contrato existente
   de propuestas `note`; no herramientas nuevas. Crear nota usa la propuesta del
   servidor y deduplicación existente; queda `awaiting_approval`.
6. Revisión del contenido → aprobación por fingerprint → ejecución separada.
   La cola vuelve a comprobar la huella antes de escribir el resultado. Relay
   permanece de solo lectura.

Errores y cancelaciones no aportan texto ni propuestas. Recibos acotados a 128
dictados por sesión impiden reenvío y cancelación adelantada seguida de ejecución.
No se guarda audio, pero el texto enviado queda sujeto al historial y persistencia
de notas ya existentes. “Local” no significa que el navegador/Windows no pueda
administrar permisos o memoria del proceso.

## Configuración manual

El launcher funcional anterior permanece igual. El centro existente agrega opciones:

```powershell
python -B -m arkos_pilot.task_center --state-dir C:\ArkosReview\mi-prueba\estado --port 0 --dictation-python C:\ruta\voice-runtime\Scripts\python.exe --dictation-model C:\ruta\modelo-whisper
```

Esto habilita únicamente dictado. Para conversación se deben conservar las opciones
Hermes existentes y el runner protegido aprobado para esta PC; no iniciar otro
servidor de modelo. Sin bridge configurado se muestra “Hermes por conectar”.
Cerrar con Ctrl+C cancela el worker de dictado propio. Nunca cerrar por nombre todos
los procesos Python. La grabación máxima es 30 s y la transcripción máxima 90 s.

No se empaquetan Python de voz, faster-whisper ni modelos. Dependencias opcionales
manuales. En esta PC ya existen faster-whisper y el modelo small; no se descargó nada.
No se garantiza velocidad en otro equipo. Captura usa AudioContext/ScriptProcessor
del navegador: requiere permiso, contexto seguro loopback y soporte de 16 kHz;
si falta, se conserva la escritura manual.

## Aceptación

Separar evidencia sintética de micrófono físico:

- CI: PCM inválido/excesivo, configuración incompleta, concurrencia, cancelación,
  timeout, repetición, respuesta maliciosa como texto, sin archivos de audio.
- Navegador: permiso rechazado, captura visible, detener/descartar, edición antes de
  enviar, ningún envío automático. Capturas de escritorio/móvil sin claves.
- Recorrido local real: audio de ejemplo → Whisper instalado → texto editado →
  Qwen existente → propuesta validada → nota pendiente → aprobación → ejecución →
  archivo con contenido exacto. Medir cada latencia, sin extrapolar rendimiento.
- Jona: prueba de micrófono físico pendiente hasta que confirme voz reconocida.
- Cierre/reapertura del acceso funcional: pendiente hasta terminar su conversación.
