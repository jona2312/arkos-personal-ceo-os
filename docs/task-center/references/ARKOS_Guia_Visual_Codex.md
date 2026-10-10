# ARKOS — Dirección visual y contrato de interfaz
Fecha: 10 de octubre de 2026. Entrega para Codex.
Estado: DISEÑO PROPUESTO. No certifica código, despliegue ni conexión real con Hermes.

## 1. Referencias creadas con Higgsfield
Estas son las tres referencias de esta entrega. Las imágenes previas creadas con otra herramienta son exploraciones adicionales. Para este encargo usar las siguientes de Higgsfield:
- Portada: https://d8j0ntlcm91z4.cloudfront.net/user_3E2m07B5VIsmgzg8Fc98SavF2C0/hf_20261010_123004_01d16d66-db9d-4fde-be3d-9a164a26cc1b.png
- Conversación: https://d8j0ntlcm91z4.cloudfront.net/user_3E2m07B5VIsmgzg8Fc98SavF2C0/hf_20261010_123032_b0f4b7ef-405e-400b-a0f3-0aa9db92336d.png
- Controles y móvil: https://d8j0ntlcm91z4.cloudfront.net/user_3E2m07B5VIsmgzg8Fc98SavF2C0/hf_20261010_123039_e0e89440-23a9-4f8b-bf3b-3ed117a9391b.png

Modelo usado dentro de Higgsfield: gpt_image_2_5. Tres generaciones completadas.
Las láminas son referencias estéticas, no especificaciones exactas de texto o estado. Si una imagen contradice este documento, manda este documento. No transcribir posibles errores de tipografía ni etiquetas generadas. No usar una captura completa como fondo de una interfaz funcional.

## 2. Objetivo
Un asistente que se entiende en segundos: escribirle, ver qué propone, revisar permisos y seguir tareas. Debe sentirse vivo, brillante y personal, sin que la decoración esconda el trabajo. No usar figuras humanas.

Mantener la interfaz y la ejecución existentes. La pantalla actual es la base; esta entrega no autoriza reemplazar toda la arquitectura ni cambiar contratos para ajustarlos al dibujo.

## 3. Sistema visual
| Elemento | Valor propuesto |
|---|---|
| Fondo | #08090D |
| Panel | #12151C, casi opaco |
| Dorado principal | #F5C76B |
| Dorado de énfasis | #FFD98E |
| Rojo neuronal / atención | #FF4B57 |
| Amarillo de espera / trabajo | #F3B44B |
| Verde de éxito confirmado | #40D99A |
| Texto principal | #F3F4F7 |
| Texto secundario | #ADB5C4 |
| Bordes | dorado tenue, 1 px |
| Radio de tarjetas | 16 px |
| Radio de controles | 10–12 px |
| Espaciado | múltiplos de 4: 8, 12, 16, 24, 32 |
| Texto de cuerpo | 15–16 px; no achicar para encajar |
| Objetivo táctil | mínimo 44 × 44 px |

Usar fuentes locales/system disponibles, sin descargar fuentes. Texto y controles deben conservar contraste AA; medir contraste de los estados finales, no asumirlo por usar esta paleta.
Dorado para acciones importantes; rojo para atención o fallo, no para todos los botones. Verde solo para éxitos reales.
Icono y etiqueta acompañan siempre al color. Foco visible con teclado. Nada de texto sobre partículas brillantes.

## 4. Portada: Hoy
Orden:
1. Cabecera: ARKOS, reloj local, Mensajes, Ajustes.
2. Navegación: Hoy, Conversación, Tareas, Resultados, Conexiones.
3. Pregunta principal: “¿Qué hacemos ahora?”.
4. Entrada de texto y estado del asistente visibles sin desplazarse.
5. Núcleo abstracto pequeño, con conexiones hacia el trabajo observado.
6. Avisos personales derivados de eventos reales; pestaña Equipo por conectar.
7. Cuatro grupos: Requieren revisión, En cola, En curso, Terminadas.
8. Tarjetas y encargos del celular; identificar origen Local o Relay.
9. Información secundaria: hora local; clima por conectar si no hay servicio.

Desktop >=1200 px: barra lateral aproximada de 200–220 px, área principal flexible y avisos de 300–340 px. No dejar que el núcleo domine la pantalla: ~140–180 px en escritorio, ~72–96 px en móvil. Estas medidas prevalecen si el dibujo muestra un núcleo demasiado grande.
Tablet 768–1199 px: dos columnas flexibles, mensajes pasan debajo si falta espacio.
Móvil <768 px: una columna, núcleo compacto, entrada de texto antes de las tarjetas, navegación inferior. El teclado no debe tapar el compositor; respetar safe-area y viewport dinámico.
Comprobar 360, 390, 768, 1366 y 1920 px, zoom 100% y 125%. Sin desplazamiento horizontal.

Con cola vacía: mostrar “No tenés tareas pendientes” y una entrada útil. No inventar estadísticas ni tarjetas para llenar huecos.
Las notificaciones personales actuales no equivalen a correo ni a mensajería de personas.

## 5. Conversación
El chat debe ocupar la mayor parte de su vista. Núcleo y animación son secundarios.
Compositor accesible con etiqueta propia, Enviar y, durante una respuesta, Cancelar respuesta.
Enter envía; Shift+Enter agrega línea. Impedir envío vacío y doble envío.
Mantener el borrador si falla la petición. Mostrar errores breves y accionables, sin rutas locales, tokens ni stderr.
Un turno activo por conversación inicialmente; no permitir que una respuesta tardía cancelada reaparezca.
Estados: Por conectar, Listo, Respondiendo, Cancelado, Error. No confundir “Respondiendo” con tarea en ejecución.
No anunciar streaming si el puente solo devuelve una respuesta final.
Historial limitado por el contrato del bridge. No guardar conversaciones completas permanentemente sin una decisión explícita; la propuesta inicial es memoria de sesión.
Sanear la presentación: texto del modelo como texto, o Markdown limitado con sanitización. Nunca interpretar HTML, JS o comandos.

Si Hermes no está configurado: “Hermes · por conectar”, explicar el siguiente paso y no simular respuestas inteligentes. Un modo demo debe estar separado y rotulado.
Voz por ahora: “Voz · próximamente”. No pedir micrófono ni mostrar un indicador de escucha falso.
Adjuntos: no mostrar un clip accionable hasta tener soporte real.

## 6. Propuesta, aprobación y ejecución
Flujo obligatorio:
Conversación → propuesta → Crear tarea pendiente → tarea esperando aprobación → aprobación válida → ejecución explícita → resultado.

Una propuesta no es una tarea. “Crear tarea pendiente” no aprueba ni ejecuta.
“Aprobar” habilita el paso permitido por el contrato; no crea otra tarea ni dispara ejecución.
“Ejecutar” solo aparece habilitado en tareas locales aprobadas y elegibles según el backend.
La vista remota del relay sigue siendo de solo lectura. No agregarle Aprobar, Ejecutar ni Descargar mediante este rediseño.
Ediciones deben respetar la invalidez de aprobaciones previas: no conservar una aprobación para contenido cambiado.
Doble clic/reintento al convertir una propuesta no debe duplicar la tarea: protección e idempotencia en servidor, además de deshabilitar el botón.
No crear tareas ni conservar propuestas a partir de respuestas error, timeout o cancelled.
Resultado incierto exige revisión explícita; nunca reintentar automáticamente.

## 7. Contrato de botones
| Control | Comportamiento exacto |
|---|---|
| Enviar | inicia un turno conversacional; no ejecuta herramientas |
| Cancelar respuesta | cancela ese pedido del chat; no cancela tareas |
| Crear tarea pendiente | valida propuesta y crea una única tarea sin aprobación |
| Revisar | abre contenido, origen y detalle del trabajo |
| Aprobar | usa el flujo de aprobación existente para ese contenido |
| Rechazar | solo ofrecer si el backend permite la transición; no inventar endpoint |
| Ejecutar | ejecuta únicamente la tarea local elegible seleccionada |
| Cancelar tarea | acción separada de Cancelar respuesta; respetar estado permitido |
| Ver resultado | abre resultado real, con descarga solo donde ya está autorizada |
| Mensajes | abre avisos personales reales |
| Equipo | informa Por conectar, sin integrantes ficticios |
| Conexiones | muestra estado comprobado de cada integración |
| Brillo | cambia presentación; no altera permisos ni tareas |
| Modo ligero | reduce decoración y movimiento |
| Reducir movimiento | detiene movimiento y respeta preferencia del sistema |

## 8. Estados de tareas
El color agrupa visualmente; la etiqueta exacta conserva el significado. No sustituir el contrato por tres colores.
| Estado relay | Texto | Grupo / color |
|---|---|---|
| awaiting_approval | Esperando aprobación | Revisión / rojo |
| approved | Aprobada, en cola | Cola / amarillo |
| claimed | Reservada por la PC | En curso / amarillo |
| running | En ejecución | En curso / amarillo |
| succeeded | Terminada | Terminadas / verde |
| failed | Falló | Revisión / rojo |
| unknown | Resultado incierto | Revisión / amarillo con aviso |
| rejected | Rechazada | Archivo / gris |
| cancelled | Cancelada | Archivo / gris |

Para tareas locales conservar su enum real y la correspondencia ya implementada; no renombrar estados de persistencia para imitar la tabla del relay.
No contar rechazadas o canceladas como terminadas exitosamente.
Frescura y conectividad son otra dimensión: una tarea terminada puede estar dentro de una copia desactualizada. Mantener ambos avisos.
No cambiar límite de frescura ni reglas de snapshots; consultar contrato actual.

## 9. Movimiento: conexiones que trabajan
Implementar con SVG/CSS propios, pocos caminos y animación de transform/opacity. No usar un video como motor de interfaz ni requerir GPU dedicada.
Las referencias Higgsfield indican aspecto. El comportamiento depende de datos:
| Evento observado | Reacción visual propuesta |
|---|---|
| En reposo | núcleo estable, halo tenue; sin tráfico de tareas |
| Respuesta del chat en curso | pulso suave del núcleo, texto Respondiendo |
| Esperando aprobación | nodo rojo fijo, sin simular ejecución |
| En cola | camino tenue amarillo, sin carreras falsas |
| Tarea realmente running | punto de luz sale hacia su tarjeta y recorre una ruta |
| Éxito observado | destello verde breve en tarjeta y retorno dorado al núcleo |
| Fallo | acento rojo fijo y aviso legible |
| unknown / desconexión | dejar de representar progreso y mostrar incertidumbre |

Duraciones propuestas: pulso de conversación 1.6–2.4 s; viaje 1.2–1.8 s; confirmación 0.4–0.7 s. Máximo 3 recorridos animados simultáneos; agrupar el resto con indicador textual.
La UI observa estados por sincronización; no representa telemetría continua ni neuronas reales.
Tab oculto: pausa decoraciones. prefers-reduced-motion o modo ligero: red estática, sin partículas, viajes ni pulsos.
Móvil: modo ligero inicialmente salvo preferencia guardada. No hacer benchmark ficticio: medir fluidez, uso CPU y consumo en el equipo de aceptación y reportar limitaciones.

## 10. Otras vistas
Tareas: filtros por estado/origen, búsqueda local, detalle; controles permitidos según tarea. Separar fallos e inciertos de éxitos.
Resultados: archivos realmente generados, identificación de tarea y disponibilidad; no prometer archivo remoto descargable.
Conexiones: Hermes, Relay y demás servicios con estados comprobados. Correo, WhatsApp, clima, traducción, equipo no se dan por conectados por aparecer en la pantalla.
Tiempo de trabajo: hasta tener medición del sistema mostrar “Tiempo de esta sesión”; no llamarlo horas desde encender la PC.
Equipo: siguiente fase independiente, con invitaciones, autenticación y permisos. No implementar un enlace público que exponga tareas privadas.
Asistentes colaborando entre equipos: futura capa de permisos y propuestas, no una consecuencia de tener un chat.

## 11. Plan de implementación para Codex
1. Leer AGENTS.md y documentación vigente; revisar working tree y HEAD actuales. No asumir que las referencias históricas son el HEAD actual.
2. Crear rama y checkout aislados sobre la última base revisada apropiada, sin pisar trabajo de otro agente.
3. Corregir primero el launcher: distinguir variables ausentes de presentes vacías, restaurarlas exactamente en éxito y error. Repetir aceptación Windows.
4. Aplicar layout, tokens y controles conservando APIs y contratos.
5. Integrar chat con el HermesBridge existente. Validación inicial con runner sintético rotulado; no equivale a prueba con Qwen real.
6. Añadir conversión explícita propuesta→tarea pendiente con validación/idempotencia server-side.
7. Añadir movimiento condicionado por estados observados, modo ligero y movimiento reducido.
8. Validar interfaz y pruebas relevantes, publicar Draft PR con SHA, CI, capturas y límites.
9. Conexión real Hermes y perfil dedicado solo dentro de la autorización explícita vigente. No modificar/revertir los archivos existentes de Hermes para hacer pasar la prueba.

Referencia histórica del puente: PR #8 en 2a00be43f0bc70608486cfee9f63b02e458165c2. Referencia histórica de radiance: PR #9 en 2b3f6a5c5b5e300ca5d7c4ec927af5b8e6a1d5c4. No comprobadas de nuevo en esta entrega.
La aceptación informada fue parcial: tareas/notas y lectura de snapshots pasaron; launcher falló por variables; Hermes real no se probó. No convertir ese informe en “todo aprobado”.

## 12. Aceptación
- Nota real: creada, aprobada y ejecutada en tres acciones distintas, resultado verificado.
- Propuesta: doble clic/reintento produce una sola tarea pendiente y cero ejecuciones.
- Chat: cancelar solo afecta su pedido; error/timeout/cancelled no deja propuestas ni ejecución.
- Contenido adversarial del modelo no ejecuta HTML, JS ni comandos.
- Relay: origen, estados exactos, frescura, desconexión y revocación conservados; sin botones de escritura remota.
- Teclado: navegación/foco visibles; texto y estados entendibles sin color.
- Vista vacía/desconectada honesta; no mensajes ni tareas de muestra mezcladas con datos reales.
- Capturas de portada, chat, tareas, conexión fallida y móvil, más grabación corta opcional de animación.
- Movimiento reducido y modo ligero detienen decoración; cambiar brillo no pierde tareas ni historial.
- GET de tareas continúa respondiendo mientras Hermes tarda.
- Windows launcher restaura presencia y valor de las cuatro variables; CheckOnly no crea estado.
- Capturas reales del producto se rotulan como tales; estas tres láminas siguen siendo diseño.

## 13. Texto breve para enviar junto con las láminas
“Codex: usá las tres láminas de Higgsfield como dirección estética y este documento como contrato funcional. Implementá en una rama aislada, verificando el HEAD actual antes de trabajar. Priorizá chat visible, tareas claras y botones simples. Conservá aprobación y ejecución separadas, relay de solo lectura y las funciones pendientes honestamente marcadas. No copies texto erróneo de imágenes. Entregá un Draft PR con CI, capturas reales, pruebas relevantes y los pendientes para Hermes real. No hagas merge, deploy, instalaciones automáticas, cambios de Supabase, firewall, arranque ni modificaciones de D:/ARKOS fuera de autorización explícita.”

## 14. Prompts visuales reutilizables
Portada: ARKOS en negro mate, paneles opacos, dorado brillante, rojo neuronal selectivo, fondo de nodos conectados. Núcleo abstracto compacto sin humanos, compositor “Escribile a ARKOS…”, mensajes personales, grupos Revisión/Cola/En curso/Terminadas y tarjetas reales. Etiquetas de conexiones pendientes. Amplio formato 16:9, tipografía legible.

Chat: mismo sistema visual, conversación como área principal, propuesta de nota con Crear tarea pendiente; panel lateral de flujo Propuesta/Tarea pendiente/Aprobación/Ejecución/Resultado; Aprobar y Ejecutar separados. Voz por conectar; sin adjuntos ficticios. 16:9.

Controles/móvil: mismo sistema visual, botones y estados con icono/texto, ajustes de brillo/modo ligero/movimiento reducido, vista móvil en una columna con compositor prioritario. Ningún humano, métricas inventadas o servicios aparentemente conectados.
