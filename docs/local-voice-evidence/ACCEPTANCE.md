# Evidencia — 21/10/2026

Base: PR #20 a73bcb24b23cd583000101f87c1465473f2da9cf.
Rama: codex/arkos-local-voice. Sin cambios en Hermes instalado ni en el modelo.

- PASS: 246 pruebas Python, 224 aprobadas, 22 omitidas (dependencias opcionales: SDK Cloud y FFmpeg según los skips).
- PASS: Test-ArkosVoice.cjs (cinco turnos sintéticos, interrupción, silencio, eco textual, cierre, permiso tardío/denegado, pestaña oculta).
- PASS: Test-ArkosDictation.cjs, Test-ArkosNeural.cjs, Test-ArkosRemoteView.cjs.
- PASS: Test-ArkosChat.cjs en Edge real, runner sintético; propuestas, aprobación, cancelación, XSS, doble envío y móvil.
- PASS: navegador Edge real con micrófono de archivo sintético, Whisper/Piper reales y modelo sintético. Capturas adjuntas no contienen claves. El rótulo inferior «Voz próximamente» de estas capturas fue corregido posteriormente a «Voz local experimental».
- PENDIENTE: cinco turnos físicos de Jona, Admiral, eco acústico, barge-in físico y cierre verificado en su dispositivo. Jona siguió utilizando Hermes durante la preparación.

La prueba de navegador usa un archivo de audio repetido hasta detenerlo. No debe interpretarse como un turno humano ni compararse con la prueba de componentes de una frase: el tramo STT registrado fue de 22,308 s, no una validación de baja latencia. El primer intento de la prueba falló por exigir un solo turno pese al audio en bucle; se corrigió esa expectativa del fixture, conservando las comprobaciones deterministas contra turnos duplicados en Test-ArkosVoice.cjs.

No se dispone de tiempo al primer fragmento de modelo ni al sonido físico audible. Ambos quedan null. Las capturas móviles verifican ausencia de desbordamiento, no funcionamiento del micrófono en un teléfono.

Consultar ../LOCAL_VOICE.md para componentes, comparación acotada, comandos y aceptación física.
