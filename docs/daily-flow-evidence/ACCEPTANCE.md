# Evidencia local — 20 de octubre de 2026

Base #18: bd53cf682de150ff6a1c57979eb69100b187fbc4, HEAD verificado, 7 checks aprobados.
Rama aislada codex/arkos-local-dictation. #19 sigue separado (Cloud, fuera de alcance).
Sin AGENTS adicional en este checkout; se aplicaron las instrucciones globales de Jona.
Sin acceso Engram en esta sesión: este documento es el handoff saneado.

## Implementado y verificado

- Acceso «Abrir ARKOS local» anterior conservado; ninguna interrupción de los PID
  57872 (llama-server) y 59280 (pantalla original). Cierre/reapertura sigue pendiente.
- Runtime existente: Python voz 3.14.7, faster-whisper 1.2.1, CTranslate2 4.8.1,
  NumPy 2.4.3. Modelo small, 486.212.372 bytes incluyendo archivos auxiliares,
  snapshot 536b0662742c02347bc0e980a01041f333bce120. Sin descargas.
- SHA256 model.bin: 3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671.
- Carga offline: 1,2 s. Inferencia CPU int8, sin competir por VRAM con Qwen.
- Windows local: build 26200, PowerShell 7.6.5. Python de pruebas 3.12.14.
- Edge con sandbox habilitado, viewport 1440×1000 y 390×844, escala 1.
- Audio de ejemplo generado por Microsoft Sabina instalado; entrada de micrófono
  simulada del navegador. No se capturó voz personal. El WAV sintético se conserva
  exclusivamente como evidencia; el producto no guarda audio.
- Recorrido real PASS: audio → faster-whisper → campo editable → edición explícita →
  Qwen local existente → propuesta del contrato → nota pendiente → rechazo de ejecución
  anticipada y de fingerprint inválido → aprobación → ejecución → archivo exacto
  (con terminador CRLF de Windows).
- Latencias individuales del ensayo final: transcripción 2,953 s; respuesta con
  propuesta 20,752 s; ejecución observada 0,156 s. El ensayo anterior fue 2,941 / 12,539 / 0,162 s. No son percentiles ni una validación
  estadística de rendimiento. El primer ensayo descubrió un error de expectativa LF
  del test y una frase sintética mal codificada; se corrigió el harness, no la cola.
- Captura descartada libera micrófono; móvil sin desbordamiento. Capturas sin clave.
- Regresiones sintéticas de navegador del chat existente: PASS, incluyendo cancelación,
  XSS, propuestas, doble clic, estados, relay y presentación. Separadas del modelo real.
- Suite local completa: 240 tests, 218 aprobados y 22 omitidos por SDK Cloud ausente; no se instaló. Siete tests nuevos de backend y prueba Node del ciclo de captura: PASS.
- Los cuatro archivos modificados de Hermes mantienen su diff anterior; no se editaron.

## Comandos de verificación

```powershell
python -B -m unittest discover -s tests -v
node scripts/Test-ArkosDictation.cjs
node scripts/Test-ArkosNeural.cjs
node scripts/Test-ArkosRemoteView.cjs
node scripts/Test-ArkosChat.cjs
```

El test de navegador usa Playwright/Edge existentes con ARKOS_TEST_PYTHON,
CODEX_PRIMARY_RUNTIME_NODE_MODULES, ARKOS_TEST_CHROMIUM y ARKOS_TEST_HEADED=1.
No se instalaron dependencias. El paquete se prueba después del commit porque su
builder usa blobs comprometidos, no archivos sueltos del working tree.

## Pendiente y límites

- Micrófono físico de Jona, precisión con su voz/ruido y demora percibida.
- Arranque frío y cierre/reapertura del acceso anterior, cuando termine de conversar.
- No se reemplazó el acceso estable por la rama experimental. La pantalla de prueba
  usa estado separado y reutiliza exclusivamente el servidor de modelo existente.
- El primer turno puede incluir carga del motor de dictado; este piloto inicia un
  worker acotado por dictado, sin mantener otro modelo residente.
- No hay voz de salida, herramientas nuevas, proveedor remoto ni ejecución libre.
- CI y SHA final se informan en el PR; este registro no presume sus resultados.


## Legibilidad y micrófono — 21 de octubre

El botón con icono de micrófono y etiqueta «Dictar» está dentro del formulario,
junto a Enviar; detener y descartar aparecen en esa misma zona. Mensajes y campo
usan 18 px y mayor peso. No cambia el motor ni activa el micrófono por sí solo.
Prueba de navegador sintética PASS en escritorio y móvil, incluyendo aserción de
micrófono visible dentro del chat y tamaño calculado de 18 px. Capturas
microphone-readable-* corresponden al runner sintético, no a otra llamada a Qwen.
