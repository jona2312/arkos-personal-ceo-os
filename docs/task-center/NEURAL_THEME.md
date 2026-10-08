# Tema neuronal aprobado

Tema predeterminado negro, dorado y rojo con una red SVG detrás de paneles oscuros. La propuesta de imagen fue aprobada por Jona; la implementación mantiene colores semánticos adicionales para distinguir resultados y errores. No representa una red neuronal real ni razonamiento interno del modelo.

## Controles

En «Personalizar espacio»: Dorado y rojo, Brillo del fondo (Suave, Medio, Intenso o Sin fondo), Rendimiento visual (Ligero o Completo) y movimiento activado/pausado. Las preferencias persisten en este navegador. Se conservan los temas anteriores y el modo claro; una preferencia guardada anteriormente no se reemplaza automáticamente. El brillo inicial es Suave. En una primera apertura desde una pantalla de hasta 760 px, se selecciona Ligero; una elección guardada tiene prioridad.

La red contiene 77 nodos y una cantidad acotada de enlaces, construidos una sola vez. Usa SVG y CSS locales sin canvas, WebGL, paquetes, fuentes externas, CDN ni consultas nuevas. No requiere GPU dedicada, aunque el coste real depende del navegador y equipo. Ligero elimina animaciones y halos; movimiento reducido del dispositivo y pestaña oculta detienen los pulsos. Sin fondo oculta el fondo entero. No se hizo un benchmark en la PC del usuario.

## Actividad verificable

Los pulsos de red solo se habilitan cuando la última consulta local informa una tarea `running`, o durante 10 segundos después de observar una transición hacia `completed`. Una tarea ya terminada al abrir la pantalla no dispara una celebración. Los estados en cola y por revisar se muestran como espera. Si no se puede actualizar el servidor local, se detienen los pulsos y el texto indica información sin actualizar.

La clasificación usa exclusivamente tareas locales: no supone que una tarjeta relay `claimed` o una copia remota fresca sea ejecución activa. El núcleo circular conserva su movimiento decorativo en modo Completo; ese movimiento no es un indicador de ejecución. La animación es una representación del último estado consultado (intervalo habitual 3 s), no telemetría continua ni evidencia de que el proceso siga vivo entre consultas. No modifica ni ejecuta tareas.

## Validación

- `node scripts/Test-ArkosNeural.cjs`: clasificación de reposo, espera, ejecución y desconexión.
- `node scripts/Test-ArkosRemoteView.cjs`: contrato remoto conservado.
- E2E `scripts/Test-ArkosTaskCenter.cjs`: tarea real local hasta resultado, persistencia, XSS, layouts, controles de brillo/rendimiento/movimiento, inicio móvil ligero y red observando transiciones. El escenario `running → completed` del fondo usa respuestas HTTP sintéticas controladas: comprueba presentación, no el ejecutor real.
- Capturas en `screenshots/`: pantalla real con tareas sintéticas de prueba.

Este cambio se apila sobre #5. No añade voz, herramientas Hermes ni permisos nuevos. Falta aceptación en Windows del usuario. No instala, despliega ni modifica su PC.
