# Centro de mando — diseño y próximos incrementos

Pedido de Jona: estética futurista con colores brillantes y movimiento, sin
figuras humanas, manteniendo una interfaz didáctica en PC y celular.
Referencia visual: reel `DeMM_2eBHXW` de Instagram, observado parcialmente en el
navegador. Se toma la dirección de contornos luminosos y geometría; no se afirma
haber verificado cómo funciona el producto mostrado.

## Incremento implementado

- Fondo CSS con auroras, trama y puntos; núcleo con tres anillos animados.
  Revisión de color: cian eléctrico con magenta/violeta, luz interior y
  paneles con tintes más intensos. Avisos y estados usan colores distintos,
  además de sus etiquetas; no dependen solo del color para interpretarse.
  La herramienta de generación de imágenes se usó para explorar un concepto
  visual. Su dirección se tradujo a CSS/SVG: malla esférica decorativa, marcos
  geométricos y contornos de luz. El bitmap del concepto no es la aplicación,
  no se usa de fondo ni incorpora sus datos decorativos al producto.
  No usa WebGL, canvas, video de fondo, dependencias ni recursos externos.
- Movimiento configurable, preferencia persistente, respeto a
  `prefers-reduced-motion`; animaciones pausadas con pestaña oculta.
- Núcleo central con entrada a escritura y espacio de voz live. Escritura abre
  el preparador determinista existente. Voz explica la integración pendiente y
  **no solicita ni activa el micrófono**.
- Bandeja personal derivada de las tareas reales: requiere aprobación, lista
  para ejecutar, ejecutando, completada o bloqueada. No es un buzón de correo ni
  un servicio de mensajería entre personas. Muestra el estado actual de cada
  tarea, no un historial completo de sus transiciones.
- Marcar vistos no altera la tarea, su aprobación ni su ejecución. Solo guarda
  identificadores/estados de avisos en este navegador (máximo 1000). Un cambio de
  estado produce un aviso nuevo. El contador abarca todos los avisos pendientes;
  se muestran los cinco más recientes y el tablero conserva el resto de tareas.
- Tablero y contadores separados: por revisar, en cola, ejecutando y terminadas.
- Hora y fecha del dispositivo. El cronómetro mide tiempo transcurrido desde la
  apertura de la página, incluido tiempo en segundo plano; se reinicia al
  recargar. **No mide horas de trabajo ni tiempo desde el arranque de Windows.**
- Módulos de clima, noticias, actividad de PC, equipo y traducción con estado
  pendiente y próximo paso explícito. No consultan servicios ni muestran datos
  inventados.

## Orden de ejecución recomendado

| Prioridad | Entrega | Aceptación concreta |
|---|---|---|
| 1 | Conectar UI al relay del PR #2 | Crear un encargo con PC apagada, aprobar contenido exacto, ejecutar al reconectar y mostrar estado/resultados sin duplicar aprobaciones. Antes acordar acciones, IDs, estados y JSON canónico. |
| 2 | Conversación con Hermes | Un pedido produce una propuesta estructurada dentro de la lista permitida; texto del modelo nunca habilita una ejecución por sí mismo. |
| 3 | Voz | Hablar, transcribir, responder, interrumpir y detener; indicador de micrófono, fallback a escritura, prueba en CPU y permisos explícitos. |
| 4 | Clima y noticias | Ciudad elegida manualmente, intereses, fuentes, fecha de consulta, caché y estado sin conexión. Autorizar salida de los datos necesarios. |
| 5 | Actividad de PC y día a día | Agente local distingue arranque, sesión activa y pausas; prioridades y resumen diario; sin capturar teclas o contenido de otras apps. |
| 6 | Traductor de texto | Idiomas de origen/destino, original junto a traducción, indicar procesamiento local/nube y revisión antes de enviar. Voz traducida después. |
| 7 | Equipos e invitados | Identidad, espacios compartidos, permisos por miembro, responsables, comentarios y mensajes; aislamiento de archivos personales. |
| 8 | Distribución | Instalador, modelo CPU adecuado, desinstalación, actualizaciones firmadas y mediciones reales de RAM, disco y latencia. |

El PR #2 y esta UI siguen separados. Esta entrega no importa tokens del relay,
no abre puertos de la PC ni convierte la clave loopback en una identidad remota.
El contrato `SYNC_CONTRACT_DRAFT.md` sigue siendo una propuesta; se debe reconciliar
con `arkos_relay/contract.py` antes de conectar ambas piezas.

## Rendimiento y privacidad

El diseño busca evitar una GPU dedicada, pero eso no certifica rendimiento en
hardware de destino ni cambia los requisitos del modelo/voz. Medir con el agente
real en `D:\ARKOS`: CPU/RAM en reposo, fondo activado/pausado, tareas y voz.

Clima, noticias, mensajería y modelos en nube pueden requerir salida de datos.
Antes de conectarlos, mostrar qué se envía, a quién y con qué permiso. El relay de
Claude documenta notas en texto plano: la privacidad exclusivamente local y el
acceso móvil remoto requieren una decisión de diseño que aún no está resuelta.

Un piloto individual en tres días es un objetivo de trabajo, no un compromiso de
que voz, equipos, WhatsApp, instalador y seguridad productiva quedarán certificados
al mismo tiempo.
