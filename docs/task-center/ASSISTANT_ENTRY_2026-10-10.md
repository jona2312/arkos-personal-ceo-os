# Entrada al asistente — revisión visual sobre #10

Repositorio: jona2312/arkos-personal-ceo-os. Rama: codex/arkos-assistant-entry.
Checkout aislado: C:\ArkosReview\assistant-entry.
Base verificada: 336010ddf49ff90f915410505cefe232f5db4274, HEAD de #10 al comenzar,
Draft abierto y cuatro trabajos CI aprobados. Sin cambios locales en la base.
No hay otro PR abierto para esta revisión visual. No se modifica #10 ni D:\ARKOS.

## Referencia y alcance

Se recuperó la [guía visual de Higgsfield](references/ARKOS_Guia_Visual_Codex.md)
del chat «Ver reel y precios de IA», entrega del 10 de octubre, junto con las
tres URLs de láminas indicadas en su sección 1. Se inspeccionaron las tres imágenes.
Son referencias de diseño, no capturas del producto. No se generó material nuevo
ni se gastaron créditos. Los pasos de implementación del launcher, chat y puente
que esa guía propone ya están incluidos en #10: no se repiten.

La fuente de verdad funcional sigue siendo #10: no se cambian endpoints,
autenticación, contratos, HermesBridge, aprobaciones, ejecución ni lector relay.
El cambio se limita a HTML/CSS y presentación en los dos controladores existentes.
Engram no está disponible en esta sesión; este registro versionado es el handoff.

## Decisiones de interfaz

- Compositor prioritario, antes del historial: permanece visible al abrir Hoy.
  Núcleo de 150 px en escritorio y 80 px en móvil. Bandeja lateral de 320 px en
  escritorio; debajo en tablet/móvil. Tarjetas y contadores conservan sus datos.
- Conversación es una vista enfocada del mismo DOM y controlador de #10: no hay
  otro chat, otro historial ni otro puente. Cambiar de vista conserva el turno.
- Enter envía, Shift+Enter crea una línea e IME no dispara el envío. El borrador
  se restaura ante rechazo HTTP o respuesta fallida; un transporte ambiguo conserva
  el mecanismo previo de reenvío del mismo ID.
- Tipografía de mensajes y notas de 15–16 px, botones de al menos 44 px,
  paneles opacos, foco visible y variantes clara/oscura. No se copian avisos,
  métricas, miembros ni textos ficticios de las láminas.
- Voz próximamente y Equipo por conectar siguen abriendo la explicación existente.
  La entrada normal sin configuración continúa mostrando Hermes por conectar.

## Movimiento y autoridad

Núcleo estable en reposo. Esperar una respuesta produce un pulso de dos segundos
solo en el núcleo; no crea tráfico hacia tarjetas. Hasta tres recorridos SVG/CSS
se calculan entre el núcleo y tarjetas locales visibles del tablero cuyo estado
es running. Las superficies opacas tapan el recorrido bajo el texto.

Una transición observada hacia completed produce un destello de 0,6 segundos
y un retorno dorado de 1,6 segundos; se retira a los 1,7 segundos, sin esperar
otra consulta de tareas. Una tarea ya completada al abrir no dispara el efecto.
La desconexión elimina los recorridos. Relay no participa en esta clasificación.
Ligero, pausa, movimiento reducido y pestaña oculta detienen estos efectos.
La red de fondo queda estática; no es telemetría ni una red neuronal real.

## Validación y evidencia

| Comprobación | Resultado observado |
|---|---|
| Chat existente | PASS: historial/recarga, cancelación, error, XSS literal, doble envío, respuesta POST perdida, propuesta pendiente e idempotencia; cero solicitudes approve/run en esta suite. |
| Entrada y vistas | PASS: Enter/Shift+Enter, borrador ante error, un único compositor e historial al cambiar Hoy/Conversación. |
| Estados visuales | PASS: esperar chat no genera rutas de tareas; máximo tres rutas para running local; retorno al completar, retiro temporizado y desconexión sin recorridos. |
| Responsive | PASS: cinco anchos a escala 1 y cinco equivalentes a 125 %, sin overflow; campo visible al abrir, núcleo 80/150 px. |
| Lectura | PASS en las seis muestras calculadas por tema: contraste mínimo 5,31:1 oscuro y 5,42:1 claro; mensajes 16 px y extractos 15 px. No es una auditoría AA completa de cada control/estado. |
| Accesibilidad visual | PASS: Ligero, pausa, movimiento reducido, explicación de voz/equipo pendientes y controles de 44 px. |
| Tareas/relay existentes | PASS: navegador → API → SQLite → aprobación explícita → ejecución explícita → archivo; nueve estados remotos y lectura sin mutaciones. |
| Sintaxis / clasificadores | PASS: node --check en app/chat; Test-ArkosNeural y Test-ArkosRemoteView. |
| Qwen/Hermes real | NO VERIFICABLE en este alcance; permanece desconectado. |

PowerShell 7.6.5, Node 20.20.2, Python 3.12.14 y Edge instalado, con sandbox.
Sin build/typecheck/linter de aplicación configurados: no se cuentan como PASS.
No se invocó un revisor GGA independiente; se revisó el diff local.

Problemas detectados y corregidos: la cabecera móvil ocultaba el compositor en
288 px efectivos; se compactó el núcleo/estado. El tema claro heredaba una
superficie oscura en el chat; ahora los paneles de lectura son opacos y usan
sus tokens claros. La regresión visual anterior esperaba rotación decorativa
permanente; ahora comprueba reposo estable y recorridos condicionados por running.

Capturas reales, con datos de aceptación sintéticos:

- [Entrada en escritorio](assistant-entry-screenshots/desktop-entry.png)
- [Conversación y propuesta](assistant-entry-screenshots/desktop-conversation.png)
- [Vista enfocada de conversación](assistant-entry-screenshots/conversation-view.png)
- [Móvil 390 px](assistant-entry-screenshots/mobile-viewport.png)
- [Móvil 360 px](assistant-entry-screenshots/mobile-360.png)
- [Reflujo equivalente a 125 %](assistant-entry-screenshots/desktop-125-equivalent.png)
- [Espera del chat](assistant-entry-screenshots/desktop-waiting.png)
- [Error del chat](assistant-entry-screenshots/chat-error.png)
- [Tareas running mediante fixture visual](assistant-entry-screenshots/tasks-running-synthetic.png)
- [Desconexión](assistant-entry-screenshots/disconnected.png)

El runner sintético de #10 se conserva y está rotulado. Ninguna prueba de esta
entrega conecta Qwen, crea arkos-bridge, activa micrófono o llama proveedores pagos.
Las capturas de running usan una respuesta HTTP sintética de tareas, únicamente
para comprobar la presentación. No se presentan como ejecución del modelo.

Comandos desde este checkout, sin instalar dependencias:

    $python = 'C:\Users\Jona\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $env:CODEX_PRIMARY_RUNTIME_NODE_MODULES = 'C:\Users\Jona\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
    $env:ARKOS_TEST_PYTHON = $python
    $env:ARKOS_TEST_CHROMIUM = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    $env:ARKOS_TEST_HEADED = '1'
    node --check arkos_pilot/web/app.js
    node --check arkos_pilot/web/chat.js
    node scripts/Test-ArkosNeural.cjs
    node scripts/Test-ArkosRemoteView.cjs
    node scripts/Test-ArkosChat.cjs
    $env:ARKOS_TEST_EVIDENCE = "$env:LOCALAPPDATA\ArkosReview\assistant-entry-20261010\task-regression"
    node scripts/Test-ArkosTaskCenter.cjs

Las suites usan Edge visible con sandbox activado. No se usa --no-sandbox.
El detalle de medidas está en assistant-entry-screenshots/browser-results.json.
La matriz incluye 360, 390, 768, 1366 y 1920 px a escala 1. La comprobación
equivalente a 125 % divide el viewport CSS por 1,25 y usa DPR 1,25: verifica
reflujo equivalente; no constituye una prueba del control nativo de zoom del navegador.
No certifica un teclado virtual físico. Se usan viewport dinámico, safe-area
y la solicitud de redimensionar contenido al aparecer el teclado.

Las muestras CDP de Performance durante 1,1 segundos registran tiempo ocupado
del renderer y heap JS en Completo/Ligero. Son una observación corta del navegador,
no CPU total de Windows, GPU, batería ni un benchmark concluyente del equipo.
En la corrida final: Completo 0,06 s de trabajo del renderer / 1,11 s y heap
5,74 MB; Ligero 0,01 s / 1,11 s y heap 6,74 MB. El orden y la corta duración no
permiten atribuir el cambio de heap al modo ni afirmar un ahorro de memoria.

## Abrir y cerrar

Portada normal, sin Hermes:

    cd C:\ArkosReview\assistant-entry
    $trial = "$env:LOCALAPPDATA\ArkosReview\assistant-entry-manual"
    ./scripts/Open-Arkos.ps1 -StateDirectory $trial -Port 0 -PythonPath $python -CheckOnly
    ./scripts/Open-Arkos.ps1 -StateDirectory $trial -Port 0 -PythonPath $python

Prueba sintética deliberada, en otra carpeta:

    & $python -B scripts/Run-ArkosChatTrial.py --state-dir "$env:LOCALAPPDATA\ArkosReview\assistant-entry-synthetic" --port 0

Cerrar con Ctrl+C en la consola del servidor y después cerrar su pestaña.
Cerrar la pestaña solamente no detiene el servidor. Las suites cierran sus procesos
de servidor y navegador; no detienen procesos de otras pruebas o Hermes.

Hermes real continúa pendiente de autorización y creación de perfil dedicado,
configuración explícita de rutas y aceptación con Qwen. No hay merge, deploy,
instalaciones, cambios de infraestructura, credenciales ni perfiles en esta entrega.
