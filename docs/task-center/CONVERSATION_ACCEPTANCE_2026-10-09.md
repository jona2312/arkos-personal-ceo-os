# Conversación en portada — aceptación Windows, 9 de octubre de 2026

Implementación en codex/arkos-conversation-home, apilada sobre PR #9, base
2b3f6a5c5b5e300ca5d7c4ec927af5b8e6a1d5c4. El HEAD remoto de #9 coincidía al
comenzar; cuatro CI aprobados. #8 ya estaba incluido. Checkout nuevo:
C:\ArkosReview\conversation. Estado/evidencia auxiliar bajo LOCALAPPDATA y TEMP.

Esta evidencia usa el HermesBridge real con un runner **sintético**, sin importar
Hermes ni llamar a Qwen. No demuestra calidad o latencia del modelo real.

## Resultados

| Área | Resultado | Evidencia |
|---|---|---|
| Launcher | PASS | Fallo reproducido antes: cuatro variables ausentes quedaban vacías. Corregido con presencia explícita y eliminación por el proveedor Env. 12 casos: ausente/vacío/valor × éxito/exit 2/excepción/Python ausente. |
| CheckOnly | PASS | Ninguno de los destinos de regresión se creó; no se instalaron runtimes. |
| Python | PASS | 142 descubiertos: 135 aprobados, 0 fallidos, 7 omitidos por requerir Hermes real. Incluye FFmpeg sobre archivos sintéticos. |
| Chat HTTP | PASS | Historial, un turno concurrente, consultas de tareas durante espera, doble envío, cancelación antes/después de arrancar, timeout, respuesta inválida, cierre del subprocess, aislamiento de sesión y límites. |
| Propuesta → tarea | PASS | 12 solicitudes concurrentes producen la misma nota pendiente; sin aprobación, fingerprint aprobado, archivo de salida ni ejecución. Recibo y tarea se guardan en una transacción SQLite. Campos/ID/contenidos manipulados se rechazan. |
| Navegador nuevo | PASS | Conversación, recarga del historial, cancelación, error, HTML malicioso como texto, doble envío y respuesta POST perdida sin otro turno; propuesta pendiente; voz/equipo pendientes. |
| Navegador existente | PASS | Test-ArkosTaskCenter.cjs: creación/aprobación/ejecución explícita y archivo, cancelación, XSS, preferencias, estados locales y remotos, autenticación y desconexión. |
| Tema y móvil | PASS | Edge visible con sandbox, escritorio 1512 × 1080, móvil 390 × 844, escala visual 1 y DPR 1. Ancho de contenido 1497/375 por scrollbar, sin desbordamiento. Dorado/rojo, Intenso, Completo; Ligero inicial móvil, pausa y movimiento reducido comprobados. |
| Relay | PASS regresión | Nueve estados y autoridad de lectura conservados; pruebas Python/Node y navegador previo. No se vinculó un relay productivo. |
| Hermes/Qwen real | NO VERIFICABLE | No autorizado en esta etapa. No se creó perfil ni se abrió conversación. |

Node 20.20.2; Python de pruebas 3.12.14; PowerShell 7.6.5, .NET 10.0.11;
Windows 26200. FFmpeg n9.0.1 existente, agregado solo al PATH del proceso de tests.
Sin dependencias nuevas. No hay build, typecheck ni linter de aplicación configurados
en este piloto de biblioteca estándar/JS estático: esos gates están ausentes,
no “aprobados”. Sí se ejecutaron node --check y análisis sintáctico PowerShell.

Se revisó el diff candidato localmente. No se contó una revisión independiente GGA:
no hay herramienta GGA ni Engram disponible en esta sesión. CI del PR debe consultarse
para su HEAD exacto; esta tabla describe la aceptación local, no reemplaza CI.

## Defectos encontrados durante la aceptación

- Un estilo anterior sobrescribía el fill de los halos SVG y producía discos opacos.
  Se quitó únicamente ese fill para respetar los gradientes de #9.
- El mínimo automático de la grilla ensanchaba el panel del chat en móvil.
  Se corrigieron los mínimos y se verificó geometría real, sin ocultar overflow.
- La regresión de navegador previa asumía LF en la salida Windows y observaba un
  contador antes del render. Conserva sus aserciones con normalización CRLF y
  espera por la tarjeta creada.
- Edge headless cerró durante el arranque; otro Chromium ya presente devolvió
  spawn UNKNOWN. La aceptación se completó con Edge visible y chromiumSandbox=true.
  No se instaló navegador ni se usó --no-sandbox.

## Capturas nuevas

Todas muestran datos sintéticos. La etiqueta visible impide confundirlas con Qwen.

- [Portada con conversación y bandeja](conversation-screenshots/desktop-conversation.png)
- [Espera del modelo separada de ejecución](conversation-screenshots/desktop-waiting.png)
- [Propuesta revisable](conversation-screenshots/chat-proposal.png)
- [Móvil, sin overflow](conversation-screenshots/mobile-conversation.png)
- [Mediciones y resultado del navegador](conversation-screenshots/browser-results.json)

## Comandos de verificación y apertura

Desde el checkout, usar un Python 3.11+ existente. En esta PC:

    cd C:\ArkosReview\conversation
    $python = 'C:\Users\Jona\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    ./scripts/Test-ArkosLauncherEnvironment.ps1 -PythonPath $python
    & $python -B -m unittest discover -s tests -v
    node scripts/Test-ArkosNeural.cjs
    node scripts/Test-ArkosRemoteView.cjs
    node --check arkos_pilot/web/app.js
    node --check arkos_pilot/web/chat.js

Para repetir el recorte sintético de FFmpeg, su directorio existente debe estar
en el PATH de ese proceso. Los siete tests HermesIntegrationTests deben seguir
omitidos: no configurar ARKOS_HERMES_PYTHON ni ARKOS_HERMES_SOURCE en esta etapa.

Prueba de navegador sin instalaciones:

    $env:CODEX_PRIMARY_RUNTIME_NODE_MODULES = 'C:\Users\Jona\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
    $env:ARKOS_TEST_PYTHON = $python
    $env:ARKOS_TEST_CHROMIUM = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    $env:ARKOS_TEST_HEADED = '1'
    node scripts/Test-ArkosChat.cjs
    # Para no reemplazar capturas históricas del test anterior:
    $env:ARKOS_TEST_EVIDENCE = "$env:TEMP\ArkosConversationRegression"
    node scripts/Test-ArkosTaskCenter.cjs

Abrir la portada normal, **sin Hermes**:

    $trial = "$env:LOCALAPPDATA\ArkosReview\conversation-manual"
    ./scripts/Open-Arkos.ps1 -StateDirectory $trial -Port 0 -PythonPath $python -CheckOnly
    ./scripts/Open-Arkos.ps1 -StateDirectory $trial -Port 0 -PythonPath $python

La pantalla indica Hermes por conectar; no inventa respuestas.
Para probar deliberadamente el flujo sintético en otra carpeta:

    & $python -B scripts/Run-ArkosChatTrial.py --state-dir "$env:LOCALAPPDATA\ArkosReview\conversation-synthetic" --port 0

El encabezado dice PRUEBA SINTÉTICA. Texto normal genera una propuesta de prueba;
[wait] permite cancelar; [error] y [invalid] permiten verificar errores.
No usa modelos, micrófono ni proveedores pagos.

**Cerrar:** Ctrl+C en la consola que abrió cada prueba; el servidor cancela el
turno activo y espera al worker. Después cerrar su pestaña. Cerrar solo el
navegador no detiene el servidor ni implica cancelación del turno. Un cierre
forzado del proceso/Windows no equivale a ese cierre ordenado.
Las suites cierran sus propios servidores y navegadores; nunca detienen Hermes.

## Hermes instalado: lectura de diferencias, sin cambios

HEAD observado: 489c1ac298f8ed13ccd688c97e4097f161046c0b.
Se inspeccionaron únicamente estos cuatro diffs preexistentes:

- use-voice-conversation.ts: ceder la escucha a un turno escrito y descartar
  transcripción antigua cuando ese turno toma control.
- use-voice-conversation.test.tsx: regresiones de ese comportamiento y limpieza
  de autoSpeakReplies entre tests.
- pm/environments.py: prefijo de ruta extendida Windows al activar dependencias.
- web/src/pages/SessionsPage.tsx: importaciones marcadas como tipos.

No se revirtieron ni reemplazaron. No se abrieron .env, tokens ni exportaciones
de memoria. No se modificó D:\ARKOS. No se creó arkos-bridge.
El Python privado previamente localizado permanece separado del Python de pruebas;
no se cargó Hermes dentro de esta aceptación.

## Conexión real pendiente

Después de autorización separada: crear un perfil dedicado vacío arkos-bridge
en la raíz gestionada de Hermes, sin clonar arkos-pilot ni agregar plugins/tools.
Eso escribirá configuración, identidad y luego logs/cache propios. Revisar antes
el parche Python preexistente. Nunca reutilizar un perfil personal para “hacerlo pasar”.

El centro admite opciones explícitas --hermes-python, --hermes-source,
--hermes-home y --hermes-model; verificar --help. Exige rutas existentes, no crea
el perfil. Sin esas opciones no instancia el puente.
HermesBridge conserva proveedor local, cero herramientas, validación de loopback,
sin fallback y límites de salida. Su bloqueo de sockets Python no es sandbox del SO.
La futura prueba real debe medir disponibilidad, cancelación, latencia e
idempotencia de propuestas con Qwen. La voz y cualquier proveedor pago siguen fuera.

Historial: en memoria del servidor, hasta 64 turnos; el navegador conserva solo el
ID del último turno en sessionStorage para recarga. No hay archivo de conversaciones.
Reiniciar el servidor pierde los turnos; los recibos de notas ya creadas y la cola
persisten. Nueva conversación limpia el historial visible, no borra tareas ni
reinicia el límite de 64 turnos de esa sesión.
