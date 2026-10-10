# Tema neuronal aprobado

Actualización sobre #10: ver [entrada al asistente](ASSISTANT_ENTRY_2026-10-10.md).
El núcleo ahora mide 150 px en escritorio y 80 px en móvil, permanece estable
en reposo y pulsa solo durante la espera de chat. La red de fondo es estática.
Hasta tres recorridos van hacia tarjetas locales running o vuelven después de
una transición observada a completed (1,7 s); el destello dura 0,6 s.
Esto reemplaza la rotación decorativa permanente y los pulsos generales descritos
en el antecedente de #9 que sigue abajo. Ligero, pausa, pestaña oculta y movimiento
reducido detienen los efectos; relay nunca se usa como autoridad de ejecución.

Tema predeterminado negro, dorado y rojo con una red SVG detrás de paneles oscuros. La propuesta de imagen fue aprobada por Jona; la implementación mantiene colores semánticos adicionales para distinguir resultados y errores. No representa una red neuronal real ni razonamiento interno del modelo.

## Controles

En «Personalizar espacio»: Dorado y rojo, Brillo del fondo (Suave, Medio, Intenso o Sin fondo), Rendimiento visual (Ligero o Completo) y movimiento activado/pausado. Las preferencias persisten en este navegador. Se conservan los temas anteriores y el modo claro; una preferencia guardada anteriormente no se reemplaza automáticamente. En una primera apertura, el brillo inicial es Intenso en escritorio y Suave hasta 760 px. Las preferencias ya guardadas siguen teniendo prioridad: para ver el aspecto luminoso en una sesión anterior, elegir «Intenso» y «Completo». En una primera apertura desde una pantalla de hasta 760 px, se selecciona Ligero; una elección guardada tiene prioridad.

La red contiene 228 nodos, 76 halos radiales y destellos estáticos y una cantidad acotada de enlaces, construidos una sola vez. Usa SVG y CSS locales sin canvas, WebGL, paquetes, fuentes externas, CDN ni consultas nuevas. No requiere GPU dedicada, aunque el coste real depende del navegador y equipo. Ligero elimina animaciones y halos; movimiento reducido del dispositivo y pestaña oculta detienen los pulsos. Sin fondo oculta el fondo entero. No se hizo un benchmark en la PC del usuario.

## Actividad verificable

Los pulsos de red solo se habilitan cuando la última consulta local informa una tarea `running`, o durante 10 segundos después de observar una transición hacia `completed`. Una tarea ya terminada al abrir la pantalla no dispara una celebración. Los estados en cola y por revisar se muestran como espera. Si no se puede actualizar el servidor local, se detienen los pulsos y el texto indica información sin actualizar.

La clasificación usa exclusivamente tareas locales: no supone que una tarjeta relay `claimed` o una copia remota fresca sea ejecución activa. El núcleo circular conserva su movimiento decorativo en modo Completo; ese movimiento no es un indicador de ejecución. La animación es una representación del último estado consultado (intervalo habitual 3 s), no telemetría continua ni evidencia de que el proceso siga vivo entre consultas. No modifica ni ejecuta tareas.

## Validación

- `node scripts/Test-ArkosNeural.cjs`: clasificación de reposo, espera, ejecución y desconexión.
- `node scripts/Test-ArkosRemoteView.cjs`: contrato remoto conservado.
- E2E `scripts/Test-ArkosTaskCenter.cjs`: tarea real local hasta resultado, persistencia, XSS, layouts, controles de brillo/rendimiento/movimiento, inicio móvil ligero y red observando transiciones. El escenario `running → completed` del fondo usa respuestas HTTP sintéticas controladas: comprueba presentación, no el ejecutor real.
- Capturas en `screenshots/`: pantalla real con tareas sintéticas de prueba.

La revisión de brillo y densidad se apila sobre #8 (`2a00be43f0bc70608486cfee9f63b02e458165c2`). No añade voz, herramientas Hermes ni permisos nuevos. Falta aceptación en Windows del usuario. No instala, despliega ni modifica su PC.

## Referencia luminosa

La revisión añade conexiones rojas y doradas más densas, halos locales SVG, destellos estáticos, bordes dorados luminosos y un núcleo de 230 px en escritorio amplio. Los paneles de lectura conservan fondo oscuro opaco. Los destellos son decorativos y estáticos: los pulsos de ejecución conservan la clasificación local anterior. Ligero oculta halos, destellos y ramificaciones rojas; no cambia estados ni permisos.

La captura de referencia es una propuesta artística; no demuestra conectores funcionando. El navegador de la PC deberá validar el parecido, el ancho responsive y el coste real.

Las rutas luminosas del núcleo aparecen solo para `running` o la transición `completed` ya observada localmente. Son decorativas y no prueban una transferencia de red. Desaparecen en modo Ligero, movimiento pausado, pestaña oculta y movimiento reducido.

El semáforo complementa los nombres exactos: rojo para aprobación pendiente, bloqueo o fallo; amarillo para cola, reserva, ejecución o resultado incierto; verde para resultado terminado; gris para cancelación. Los nueve estados remotos siguen diferenciados por texto: color compartido no implica estado ni autoridad compartidos. El acceso «Equipo · por conectar» solo explica lo pendiente y no crea miembros, mensajes ni invitaciones.
