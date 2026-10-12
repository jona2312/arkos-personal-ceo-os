# ARKOS descargable por cliente: voz en vivo y PC privada

Estado: **propuesta de arquitectura**, 12 de octubre de 2026. Este documento no
implementa voz, instaladores, autenticación comercial ni aislamiento multiusuario.
No habilita proveedores, permisos, credenciales, servicios pagos o despliegues.

## 1. Objetivo y alcance

Cada persona o CEO podrá tener su propio ARKOS: identidad, memoria, dispositivos,
cuentas conectadas y permisos separados. Una app propia en PC y celular será la
entrada para conversar por texto o voz en vivo, revisar propuestas y recibir
resultados. Un agente instalado en la PC actuará únicamente dentro de permisos
explícitos y verificables. WhatsApp seguirá como canal asíncrono opcional.

El diferenciador de producto propuesto es un **archivo durable en poder del usuario**,
organizado en carpetas privadas por proyectos y temas, en PC y en las colecciones
que elija conservar en el celular. Elegir procesamiento cloud no debe obligarlo a
dejar sus únicos registros dentro del servicio. Salir de ARKOS debe permitir llevarse
el archivo completo y leerlo con otras herramientas.

La experiencia buscada es más directa y recuperable. **La mayor fiabilidad es una
hipótesis que debe medirse**, no una consecuencia automática de instalar software.
Una PC privada tampoco evita que audio, contexto o documentos salgan del equipo
si se eligen modelos, transcripción, síntesis, sincronización o conectores cloud.

La propuesta utiliza componentes y protocolos que ARKOS puede construir o integrar.
No presupone acceso a tecnología interna, memoria, cuentas o infraestructura de Dot.
No incluye telefonía PSTN ni acceso remoto irrestricto. La mensajería y llamadas
humanas app-a-app se plantean como una fase posterior independiente de voz con IA.

## 2. Punto de partida verificado

Lectura del repositorio al 2026-10-12; base documental `main` en
[`b19dbb7`](https://github.com/jona2312/arkos-personal-ceo-os/tree/b19dbb7f77fb5c377ff2cd6294b11e301506a3ae).
Los PR citados estaban abiertos y en borrador. Sus pruebas son evidencia publicada
en esas ramas, **no pruebas ejecutadas de nuevo en esta propuesta**.

| Capa | Evidencia existente | Qué permite afirmar | Pendiente |
|---|---|---|---|
| WhatsApp, n8n, Supabase | [Arquitectura base](ARCHITECTURE.md), [roadmap](ROADMAP.md) y archivos en `main` | Hay workflows, migraciones y diseño del canal asíncrono | Despliegue y aceptación actuales no verificados aquí; [seguridad](SECURITY_RULES.md) documenta controles pendientes |
| Piloto local y ensayo de voz | [PR #1](https://github.com/jona2312/arkos-personal-ceo-os/pull/1), `2f69467` | Cola local y ensayo Hermes con evidencia parcial de audio | Fluidez sostenida no aceptada; las herramientas de Hermes no quedan automáticamente bajo la cola ARKOS |
| Relay y lector remoto | [PR #2](https://github.com/jona2312/arkos-personal-ceo-os/pull/2), [#4](https://github.com/jona2312/arkos-personal-ceo-os/pull/4), [#5](https://github.com/jona2312/arkos-personal-ceo-os/pull/5) | Código y pruebas de cola remota, agente saliente y snapshot de lectura | Aceptación productiva celular–PC, autenticación de producto y emisor WhatsApp; texto del relay sin cifrado de extremo a extremo |
| Launcher y conversación escrita | [PR #7](https://github.com/jona2312/arkos-personal-ceo-os/pull/7), [#8](https://github.com/jona2312/arkos-personal-ceo-os/pull/8), [#10](https://github.com/jona2312/arkos-personal-ceo-os/pull/10), [#11](https://github.com/jona2312/arkos-personal-ceo-os/pull/11) | Launcher con Python existente, puente sin herramientas y UI con pruebas sintéticas | Instalador para otra PC, aceptación del modelo real y memoria conversacional persistente |
| Separación Local/Cloud | [PR #12](https://github.com/jona2312/arkos-personal-ceo-os/pull/12), [#13](https://github.com/jona2312/arkos-personal-ceo-os/pull/13), [#15](https://github.com/jona2312/arkos-personal-ceo-os/pull/15), [#16](https://github.com/jona2312/arkos-personal-ceo-os/pull/16) | Contrato, cuotas, transporte y UI ensayados contra proveedor falso | Proveedor real bloqueado, condiciones/retención y operación pendientes; sin streaming de voz |
| Producto descargable multi-cliente con voz live | Este documento | Dirección de producto y criterios propuestos | Implementación, pruebas, revisión de seguridad y aceptación |
| Mensajería entre personas, llamadas app-a-app y encendido remoto | Visión ampliada en este documento | Requisitos propuestos, sin red implementada aquí | Identidades/contactos, push, llamadas, pruebas de dispositivos y compatibilidad de encendido |

La [evidencia de UI Cloud en `4f6f7c1`](https://github.com/jona2312/arkos-personal-ceo-os/blob/4f6f7c15ccbf3eed3c06b1589a0d961ba24bc68f/docs/CLOUD_UI_INTEGRATION.md)
es más reciente que el texto que todavía dice «Cloud no implementado» en el README
de esa rama. El alcance correcto es **Cloud de prueba con proveedor falso**.
Esta propuesta no fusiona el stack de PR ni modifica sus ramas. Al integrarla con
ellos se deberán reconciliar README y roadmap, conservando su evidencia más reciente.
El estado de arranque automático y encendido remoto tampoco se infiere del nombre
«launcher»: [Start-ArkosAgent.ps1 en `4f6f7c1`](https://github.com/jona2312/arkos-personal-ceo-os/blob/4f6f7c15ccbf3eed3c06b1589a0d961ba24bc68f/scripts/Start-ArkosAgent.ps1)
inicia comandos manuales; PR #2 deja el arranque al iniciar sesión pendiente.
No se encontró una implementación de Wake-on-LAN en el árbol y PRs revisados.
La [UI en `4f6f7c1`](https://github.com/jona2312/arkos-personal-ceo-os/blob/4f6f7c15ccbf3eed3c06b1589a0d961ba24bc68f/arkos_pilot/web/app.js)
muestra «Equipo e invitados» como integración pendiente; no se verificó un enlace
de invitación funcional en las ramas revisadas. Si existe en otro entorno, se debe
incorporar su evidencia y contrato antes de marcarlo disponible aquí.

## 3. Componentes propuestos

```text
App ARKOS PC / app ARKOS celular
  |-- texto, micrófono, audio y estado de sesión
  |-- revisión de contexto, propuestas y aprobaciones
  |
Adaptador de conversación (Local o Cloud elegido explícitamente)
  |-- texto / voz -> respuesta y propuestas, nunca autoridad de ejecución
  |
Política de permisos + tareas y aprobaciones existentes
  |-- tarea local -> cola local -> ejecutor local
  |-- tarea remota -> relay -> agente PC por conexión saliente
  |
Memoria del cliente según modo + conectores autorizados

WhatsApp Cloud API -> n8n -> canal asíncrono y memoria existente
  -> integración futura mediante contratos; no canal de audio live
```

- **Apps:** comenzar con la UI responsive existente para validar el recorrido.
  Responsive no significa app móvil nativa, distribución instalable ni acceso remoto.
  El empaquetado de escritorio y la app móvil/PWA se eligen después de medir permisos,
  audio, segundo plano, reconexión y requisitos de cada sistema operativo.
- **Conversación:** reutilizar la frontera `ConversationProvider` y propuestas
  verificadas. Agregar un contrato de sesión de voz versionado como extensión; no
  cambiar silenciosamente el contrato v1 de conversación escrita.
- **Agente PC:** proceso local con lista cerrada de acciones y carpetas autorizadas.
  Sin puerto público, terminal general, navegación arbitraria ni permisos de
  administrador por defecto. Los nuevos conectores necesitan revisión propia.
- **Relay opcional:** coordina encargos y estados cuando celular y PC no comparten
  sesión y es autoridad de aprobación remota. El lector/snapshot remoto del Task
  Center solo muestra estado: su permiso de lectura no permite aprobar ni ejecutar.
- **Control de producto opcional:** cuentas, dispositivos, versiones y consentimientos.
  Su existencia no le da acceso implícito a contenido, archivos o memoria local.

### Una autoridad por tarea

Reutilizar cola, idempotencia y ejecutor actuales. Para encargos remotos, el relay
es la autoridad de aprobación; el agente ejecuta. No copiar una tarea remota a la
cola local para eludir esa autoridad. Las tareas exclusivamente locales conservan
su cola local. Un `task_id` tiene un origen y una autoridad inequívocos.

La conversación propone; la persona crea una tarea pendiente, aprueba y ejecuta
mediante pasos distintos del piloto. La UI remota sigue siendo de solo lectura
hasta una implementación y revisión específicas. Una sesión de voz no concede
autoridad al modelo ni convierte una propuesta en una orden ejecutable.
Estas compuertas describen las acciones del piloto PC. La futura mensajería humana
explícitamente solicitada tiene el flujo acotado de la sección 7A; no requiere pedir
otra aprobación idéntica si contenido, destinatario y riesgo no cambiaron.

## 4. Modos de procesamiento y residencia de datos

El lugar de la app, el lugar del modelo y el lugar de la memoria son decisiones
separadas. La interfaz debe mostrar los tres, además del destino de cada conector.

| Modo propuesto | Voz y modelos | Memoria y archivos | Celular y disponibilidad |
|---|---|---|---|
| Local estricto | STT, modelo, TTS y embeddings locales, sin fallback cloud | Almacén privado en la PC; sin sincronización de contenido por defecto | En la PC; acceso desde celular requiere un enlace autenticado diseñado y probado. PC apagada: sin ejecución ni lectura de archivos |
| Híbrido | Partes elegidas localmente y partes cloud con consentimiento visible | PC como origen de archivos; solo contexto seleccionado sale al proveedor; sincronización opcional y acotada | Puede conversar mediante servicios cloud autorizados; tareas de PC esperan conexión y aprobación vigente |
| Cloud | Conversación en servicios externos elegidos | Backend operativo autorizado y archivo durable exportable del usuario; archivos de PC permanecen locales salvo selección explícita | Conversación puede continuar sin PC; sus acciones locales siguen esperando al agente; sincronización pendiente visible |

«Local estricto» requiere comprobar también dependencias, plugins, telemetría,
crash reports, DNS y procesos hijos. La etiqueta Local y el filtro de sockets Python
del prototipo no equivalen a aislamiento del sistema operativo. Se necesitan
controles de salida del SO y pruebas de red antes de ofrecer esa garantía.

No migrar historial Local a Cloud al cambiar de modo: el piloto separa sesiones y
rechaza ese historial. Una función futura de compartir contexto debe mostrar el
fragmento y destino exactos, pedir consentimiento y tener su propia revisión.
Ni errores ni falta de capacidad local autorizan fallback o cambio de proveedor.

## 5. Un ARKOS por cliente

Compartir una versión del código no implica compartir la información personal.
El cliente puede tener una carpeta o repositorio privado para su configuración y
documentos; **no necesita una cuenta Git ni un fork para usar el producto**. Un fork
por sí solo no aísla memoria, sesiones, credenciales o procesos.

El alta propuesta es **PC primero**: instalar ARKOS y crear allí el archivo privado
principal; luego usar el celular como companion vinculado al mismo dueño. La cuenta
y el alias del producto no dependen de GitHub. El celular conserva copias selectivas
y acceso remoto según permisos, sin cambiar silenciosamente la autoridad del archivo.

Requisitos antes de admitir clientes independientes:

1. Identidad propia, dispositivos vinculados y revocables, sesión autenticada y
   separación por cliente/usuario/dispositivo. Derivar el ámbito de la autenticación,
   nunca confiar en un `user_id` sugerido por el modelo o recibido sin validar.
2. Almacenes y claves propios por cliente; credenciales de cuentas en el almacén
   seguro del SO o backend dedicado. Nunca en repositorios, prompts, logs, instalador
   ni cliente frontend. Sin `service_role` o clave maestra del proveedor en las apps.
3. Memoria, embeddings, archivos, cachés, colas, consentimientos, resultados,
   notificaciones y backups aislados. Pruebas negativas entre dos clientes y entre
   dos PC del mismo cliente, además de pruebas positivas de acceso autorizado.
4. Permisos por acción, carpeta, cuenta y destino; lectura y escritura separadas,
   vencimiento y revocación. El emparejamiento de un dispositivo no concede todos
   esos permisos. Una orden fuera de alcance se rechaza aunque el modelo la pida.
5. En backend compartido, autorización por recurso y controles de aislamiento en
   toda consulta y almacenamiento. El RLS pendiente de la base Supabase y los tokens
   estáticos del relay no son suficientes para lanzamiento multi-cliente. Evaluar
   instancia dedicada por cliente frente a backend compartido antes del despliegue.
6. Sesiones de SO separadas cuando varias personas usan una PC. Cifrado en reposo,
   gestión de claves, recuperación y soporte deben diseñarse y probarse; los archivos
   SQLite y texto plano del piloto no se vuelven cifrados al llamarlos «privados».

El contexto de identidad de Jona de los prompts actuales es una plantilla del piloto.
El alta de otro cliente debe comenzar vacía y usar solo la identidad y cuentas que
esa persona configure. No copiar su memoria, contactos o conexiones de prueba.

## 5A. Archivo propio, portabilidad y salida del servicio

**Requisito de diseño:** conservar los registros seleccionados por el usuario de
forma durable fuera de la sesión y hacerlos utilizables sin login, suscripción ni
software propietario. No se promete almacenar todo para siempre: el usuario elige
qué conservar, dónde y durante cuánto tiempo, sujeto a capacidad y copias reales.

Formato propuesto, no estructura creada por este PR:

```text
ArkosArchive/
  manifest.json                  # versión, IDs, hashes y procedencia
  Projects/<project-id>/          # nombres visibles editables
    project.md
    notes/                       # Markdown legible
    decisions/                   # Markdown + metadatos JSON
    documents/                   # originales autorizados y versiones
  Topics/<topic-id>/
  Conversations/                 # texto elegido; audio opcional, no por defecto
  Tasks/                         # estado y referencias, sin credenciales
  exports/                       # paquetes completos verificables
```

- Markdown UTF-8 para lectura, JSON versionado para estructura y fechas, originales
  con sus formatos estándar. Identificadores estables y enlaces relativos; índices
  semánticos reconstruibles, no única copia de la memoria.
- Registrar una operación local con escritura atómica y huella; confirmar «guardado
  en este dispositivo» solo después de persistir. Cloud puede terminar antes de que
  una copia local esté lista: distinguir «guardado en servidor», «pendiente de
  sincronizar» y «disponible sin conexión». El mismo límite vale para celular.
- PC y celular muestran qué colecciones están descargadas, últimas versiones,
  tamaño y conflictos. La caché que el SO pueda eliminar no cuenta como archivo
  durable. Validar almacenamiento persistente/exportación del SO móvil, cuota,
  archivos grandes y opción de conservar solo colecciones elegidas.
- Exportación completa bajo pedido: registros, conversaciones conservadas, originales,
  metadatos, vínculos y manifiesto con hashes. No incluye claves ni credenciales.
  Permitir exportar mientras el servicio está disponible y conservar la última
  exportación local; una caída del servicio no permite recuperar datos que nunca
  se descargaron. Documentar cualquier dato pendiente o formato no portable.
- Los estados exportados/importados son historial inerte: no transportar credenciales,
  aprobaciones activas o leases, ni reactivar tareas al restaurar un backup. Reconciliar
  registros operativos con su autoridad canónica; un archivo repetido o una restauración
  no autoriza ejecutar ni reintentar tareas inciertas.
- Salir del servicio no elimina automáticamente archivos propios. Desinstalar debe
  separar aplicación, estado operativo y archivo, ofrecer exportación y explicar
  qué se conserva. Cancelar suscripción y solicitar borrado cloud son operaciones
  distintas. Probar lectura/importación del paquete sin ARKOS y sin red.
- Backups cifrados elegidos por el usuario, al menos una copia independiente del
  dispositivo principal y pruebas periódicas de restauración. Sincronización no
  sustituye backup: también puede propagar borrados o corrupción. Versionar,
  detectar conflictos, verificar hashes y explicar cuánto podría perderse.
- Cifrado en reposo protege archivos cuando están bloqueados; para leerlos el proceso
  autorizado debe descifrarlos. Malware o una sesión de SO comprometida siguen siendo
  riesgos. Claves de recuperación y copias no deben estar solo en el equipo perdido;
  definir recuperación y qué sucede si se pierde la clave antes de prometer rescate.

Obsidian será un lector/editor opcional de los Markdown. La Fase 8 original de mirror
Supabase puede alimentar el archivo mediante exportación revisada, pero no debe
quedar como única salida. Diseñar migración, fuentes de verdad y conflictos antes
de invertir la dirección de sincronización; nunca modificar silenciosamente datos
existentes al instalar la app.

## 6. Flujos de datos y privacidad

### A. Conversación local en la PC

Micrófono autorizado -> motor de voz local -> modelo local -> respuesta local.
La búsqueda lee solo memoria del cliente dentro de alcance. La propuesta pasa a
la cola aprobada antes de acceder a archivos o ejecutar acciones. Guardar memoria
durable es una operación definida; una transcripción temporal no debe convertirse
automáticamente en memoria permanente.

### B. Conversación híbrida desde celular

La app muestra proveedor, etapas cloud, datos, retención y coste antes de habilitar
la sesión. Si el proveedor procesa voz, **recibe audio**; enviar menos texto después
no deshace esa transmisión. Si STT es local y el modelo cloud, sale la transcripción
y el contexto seleccionado. Si TTS es cloud, sale el texto de respuesta.

Una propuesta para la PC llega al relay autorizado con identificador y huella del
contenido; tras aprobación vigente, el agente la recupera por conexión saliente.
El resultado vuelve como estado y metadatos. Subir o descargar el archivo real
requiere una política específica; no está habilitado por el snapshot actual.

### C. Canales asíncronos existentes

WhatsApp puede conservar captura de notas, audio por mensajes, notificaciones y
aprobaciones específicas. Meta, n8n, modelos y Supabase reciben los datos que su
flujo procesa: documentar esos destinatarios al conectarlo. No enrutar cada frame
de audio live por workflows n8n ni confundir Fase 2 de audio con conversación dúplex.
La integración deberá mantener el emisor y la deduplicación por mensaje, y evitar
que dos canales creen o ejecuten dos veces el mismo encargo.

### Política de datos propuesta

- Audio crudo sin grabación persistente por defecto; indicar micrófono activo y
  parar captura al colgar, revocar o cerrar. Depurar con muestras sintéticas.
- Retención de transcripciones, memoria, diagnósticos y backups configurable y
  documentada. Exportar y borrar deben abarcar copias y embeddings, con plazos
  verificables. No prometer borrado de copias de terceros que no se haya comprobado.
- Auditoría mínima de permisos y estados sin secretos ni contenido innecesario.
  Reconciliar la regla histórica de auditoría permanente con la política de
  retención antes de implementar; esta propuesta no borra registros existentes.
  La retención de respuesta «0 h» del ensayo Cloud no significa cero metadatos de
  facturación ni cero retención del proveedor. Revisar también hashes de mensajes
  cortos: sin clave pueden permitir confirmar contenido por diccionario.
- TLS protege el transporte; no evita que relay o proveedor lean el contenido.
  El relay del prototipo conserva texto plano y no ofrece E2EE. Cifrado de extremo
  a extremo de contenido opcional exigiría diseñar claves, recuperación y qué
  funciones servidor dejan de estar disponibles; no se presume implementado.
- Memoria local canónica por defecto en modo local; en modo cloud, backend del
  cliente como autoridad operativa elegida, con archivo durable del usuario y estado
  de sincronización independiente. Sincronizar solo colecciones explícitas, con
  versiones, procedencia y conflictos visibles. No unir silenciosamente dos memorias
  ni presentar un espejo desactualizado como la última versión.
- Cambios de proveedor, datos transmitidos, retención, costes o permisos requieren
  renovar el consentimiento correspondiente. Desconectar cuentas y revocar PC debe
  cortar nuevos usos; no equivale a cancelar efectos ya ejecutados.

## 7. Contrato propuesto de voz en vivo

Voz live significa conversación continua dentro de la app, con interrupciones y
estado claro. WebRTC para audio interactivo y un canal de control autenticado son
candidatos a evaluar; transporte, proveedor, SDK y empaquetado siguen abiertos.
El prototipo escrito actual no aporta por sí solo streaming ni duplex de voz.

### Sesión y turnos

- Identificadores de sesión y turno, secuencia de eventos, dispositivo, modalidad,
  capacidades concedidas y versión de consentimiento; identidad vinculada por el
  servidor. Credenciales efímeras y acotadas, sin claves maestras en el dispositivo.
- Estados de voz separados de los estados de tarea: desconectado, conectando,
  escuchando, procesando, hablando, interrumpido y reconectando. La app puede decir
  «tarea en cola» mientras continúa la conversación, sin fingir ejecución.
- Barge-in cancela la reproducción y el turno pertinente. Colgar o cancelar el audio
  no revoca una tarea ya aprobada ni deshace una acción: mostrar su estado y ofrecer
  cancelación separada cuando el contrato la permita.
- Transcripción parcial nunca aprueba ni ejecuta. Para el primer prototipo, las
  acciones se revisan y confirman en UI con contenido, destino, dispositivo y huella.
  Un «sí» suelto, audio de terceros o respuesta del modelo no es una aprobación.
- Límites de duración, concurrencia y presupuesto aplicados antes del uso cloud.
  Cancelar no garantiza que el proveedor no cobre audio ya procesado.
  Los presupuestos actuales de texto no cubren automáticamente streaming, STT o TTS;
  medir y divulgar cada componente de voz por separado.
- Reconectar con cursor y consulta de estado, sin reproducir una aprobación ni
  reenviar audio o invocar modelos pagos automáticamente. Una nueva transmisión
  necesita la intención y consentimiento vigentes de la persona.

### Herramientas y ejecución

El modelo devuelve propuestas tipadas. Política y ejecutor verifican lista cerrada,
permisos, dispositivo, versión/huella del contenido, caducidad y estado de tarea.
No convertir salida libre del modelo en shell, SQL, ruta absoluta ni código.
Documentos, correo y páginas son datos no confiables; su contenido no amplía permisos.

Conservar el [contrato relay probado en `4f6f7c1`](https://github.com/jona2312/arkos-personal-ceo-os/blob/4f6f7c15ccbf3eed3c06b1589a0d961ba24bc68f/docs/RELAY_CONTRACT.md):
aprobación ligada a huella, consumo único al iniciar, diario local e idempotencia.
Un resultado `unknown` requiere reconciliación; nunca se reintenta automáticamente.
No prometer ejecución «exactamente una vez» ante cortes o efectos externos.
Mantener separados los namespaces y formatos de huella local y relay: sus contratos
actuales son distintos; no traducir una huella en una aprobación nueva.

## 7A. Mensajes y llamadas entre personas a través de sus asistentes

**Dirección de producto APROBADA POR JONA el 2026-10-12:** incorporar un espacio
propio de mensajería personal y de trabajo en ARKOS. Esta aprobación fija la dirección
del producto; no aprueba técnicamente este PR, no autoriza merge o despliegue y no
certifica una implementación, cifrado o pruebas. La entrega se divide en fases.

Cada persona puede
renombrar su asistente. El nombre de pantalla no es su identidad ni la del destinatario.
Ejemplo ficticio: una persona pide «Arkos, envía este mensaje a mi contacto B»; el
contacto B llama «Alicia» a su asistente. B recibe un mensaje atribuido a la persona
remitente, con indicación de que se envió mediante su asistente, no un texto ambiguo
que parezca originado por Alicia o por otra persona.

### Alta y contactos una vez, envíos cotidianos sencillos

1. Alta de identidad y aceptación informada del servicio; vincular PC y celular con
   un flujo autenticado y revocable. Configurar notificaciones y descubribilidad.
2. Vincular un dispositivo sincroniza la cuenta de esa persona, **no crea relaciones
   con otras personas**. Resolver contactos por identidad verificada y aceptación
   del vínculo/invitación; no por nombre del asistente, coincidencia de nombre o
   libre acceso a una agenda. Importar contactos requiere elección específica.
3. Ante «envía a B este texto», con contacto inequívoco y contenido ordinario claro,
   esa instrucción explícita autoriza el envío solicitado: evitar otra confirmación
   idéntica. Si hay ambigüedad de contacto, audio mal entendido, contenido faltante,
   información privada adicional o un efecto sensible, aclarar solo lo necesario.
4. El asistente transmite el mensaje pedido. No agrega memoria, documentos, datos de
   terceros, historial o explicaciones privadas porque tenga acceso a ellos. Compartir
   archivos y contenido sensible mantiene permisos y revisión acordes al riesgo.
5. El destinatario puede aceptar/rechazar contactos, silenciar, bloquear, denunciar y
   revocar relaciones. Incorporar cuotas antispam, límites de invitación y mecanismos
   de abuso; dar control de presencia, confirmaciones de lectura y vista previa.

### Invitaciones y espacios compartidos

El enlace de invitación propuesto identifica al emisor verificado, a quién o a qué
espacio se invita, el rol y el alcance. Debe caducar, poder revocarse y limitar usos;
abrirlo no acepta ni concede permisos automáticamente. Tras autenticarse, la persona
ve y acepta ese vínculo. Proteger frente a reenvío del enlace, suplantación y spam.

Entrar a un equipo habilita solo los canales/recursos compartidos que se muestran.
No comparte carpetas privadas, credenciales, archivo personal ni memoria del asistente.
Los subagentes pueden representar tareas internas o acciones delegadas identificadas,
sin hacerse pasar por el dueño ni obtener autoridad por estar en el mismo espacio.
Mostrar siempre remitente humano y, cuando corresponda, asistente/subagente que
actuó y tarea que originó el mensaje. La intención es un mensajero interno con
colaboración acotada; no un compromiso de replicar todas las funciones de WhatsApp.

### Entrega cuando la PC está apagada

Un relay mínimo recibe el sobre autorizado, lo mantiene durante un plazo declarado
y notifica los dispositivos registrados. La app móvil puede recibir el aviso aunque
la PC esté apagada; la PC recupera su estado al conectar. La entrega depende de red,
permisos y servicios de notificación del SO, que deben probarse en dispositivos reales.

Proponer cifrado extremo a extremo del contenido entre dispositivos, con revisión
de claves, alta de nuevos dispositivos y recuperación. El relay y los proveedores
push aún pueden observar metadatos mínimos; no anunciar «cero datos cloud».
Por defecto, push genérico sin contenido privado en pantalla bloqueada. Si se elige
vista previa, explicar qué se transmite y dónde se muestra. Este cifrado es un
requisito futuro: no existe por heredar el relay de tareas actual.

Estados distintos: preparado, aceptado por relay, entregado al dispositivo, leído
si B lo habilita, fallido o vencido. Aceptación del push no demuestra que B lo vio.
Idempotencia por remitente/mensaje, deduplicación, expiración y consulta de estado;
no reenvío automático de contenido incierto como mensaje nuevo.

### Alternativa SMS opcional para quien no tiene la app

App-a-app usa internet y datos, no SMS. Para un contacto sin ARKOS, el MVP Android
puede ofrecer un SMS preparado: abrir la app de mensajes con `ACTION_SENDTO`, destino
`smsto:` y texto; verificar que exista una app compatible. **La persona revisa,
elige SIM si corresponde y pulsa Enviar.** Abrir el compositor no prueba envío ni
entrega. Véase la [documentación oficial de intents Android](https://developer.android.com/guide/components/intents-common#Messaging).

No solicitar envío automático `SEND_SMS` como requisito del MVP; cualquier futura
automatización necesita elegibilidad de distribución, permisos de plataforma y
revisión de la [política oficial de SMS/Call Log de Google Play](https://support.google.com/googleplay/android-developer/answer/10208820?hl=en).
Validar cancelación, ausencia de SIM/app, multi-SIM y límites del operador. No
prometer SMS gratuitos ni cuota ilimitada; pueden existir cargos, roaming o límites.
No es un canal E2EE de ARKOS, ni un fallback automático que cambie el destinatario,
la privacidad o el coste sin elección del usuario. No se envía ningún SMS aquí.

### Llamadas humanas app-a-app

Invitación autenticada entre contactos autorizados, aceptación por el receptor y
control visible de micrófono/cámara. Evaluar señalización y audio interactivo con
relay cuando haga falta; no depende de WhatsApp ni implica telefonía convencional.
Rechazar, ocupado, no responde, pérdida de red y bloqueo tienen estados propios.
Grabar, transcribir o incorporar asistentes a la llamada requiere acuerdo explícito
de participantes; no activar captura ni enviar audio a modelos por defecto.

Esto es comunicación **persona a persona mediada por la app**. La coordinación
autónoma entre agentes es otra capacidad futura: exige propósito, alcance, información
compartible y autoridad específicos. Un contacto aceptado o mensaje humano no concede
a su asistente acceso a memoria, cuentas, archivos ni ejecución en la PC ajena.

### Arquitectura de comunicación propuesta

Prioridad: infraestructura central mínima y uso de los dispositivos propios.
Evaluar P2P en LAN o internet cuando sea viable; NAT, dispositivos offline, ejecución
en segundo plano y entrega móvil impiden prometer conexión directa universal.
Mantener solo lo necesario para directorio, rendezvous, push, cola cifrada y TURN
cuando haga falta. No eliminar persistencia o seguridad para aparentar coste cero.

| Pieza | Responsabilidad | Límite |
|---|---|---|
| API autenticada | Alta, sesiones, dispositivos, directorio de contactos verificados, invitaciones y membresía de espacios | Nombre del asistente no identifica al contacto; autorización por recurso, cuotas y revocación |
| WebSocket | Eventos para apps conectadas: mensajes disponibles, ACK, presencia elegida y señalización | Canal autenticado; reconexión con cursor; estar online no confirma lectura |
| Cola durable | Sobres de mensajes y estado por destinatario/dispositivo, expiración, ACK y deduplicación por ID | Confirmar aceptación tras persistir; recuperar tras cortes sin duplicar; no confundir con cola de ejecución PC |
| Push móvil | Despertar/notificar a apps no conectadas y permitir recuperar mensajes desde API | Aviso genérico y metadatos mínimos; aceptación por proveedor push no demuestra entrega ni lectura |
| WebRTC para llamadas | Audio humano interactivo; señalización autenticada por API/WebSocket, STUN para conectividad y TURN como relay cuando sea necesario | Medir compatibilidad, coste de relay, fallos de red y aceptación del receptor; no implica telefonía PSTN |
| Cifrado de contenido | E2EE usando protocolos y bibliotecas auditados, con verificación de identidad | Pendientes diseño e implementación de claves, membresía, nuevos dispositivos, rotación, revocación y recuperación; no diseñar criptografía propia |
| ASR, TTS y LLM | Transcribir, sintetizar, redactar o asistir cuando se pide | Separados del transporte: un mensaje ordinario o llamada humana no necesita procesarse por IA |

Si una persona pide a su asistente resumir un mensaje cifrado, autoriza un tratamiento
adicional en su dispositivo o proveedor seleccionado; el cifrado del transporte no
permite prometer que ese proveedor nunca recibe texto. No atribuir este diseño a
la implementación interna de WhatsApp o Telegram.

Escala por fases: primero dos identidades y comunicación 1:1; luego espacios personales
y de trabajo con grupos pequeños, roles y límites medidos; grupos grandes y llamadas
grupales solo tras revisar fan-out, cifrado/membresía, abuso, coste y capacidad. Los
subagentes internos se identifican como tales y no reciben cuentas/autoridad humana
por defecto. El MVP de mensajes no crea una red de agentes autónomos sin permisos.

### Arranque y encendido remoto

El inicio al entrar en el SO puede ofrecerse como preferencia reversible, con
indicador y salida clara. No se confunde con encender una PC apagada. Wake-on-LAN u
otra ruta de encendido depende de hardware, alimentación, firmware, estado de
suspensión, red y un componente alcanzable autorizado; no funciona universalmente.
No exponer puertos o cambiar router/firmware para prometer esa función. En ausencia
de una ruta compatible, encolar tareas y mostrar «PC sin conexión; tarea pendiente
hasta reconectar y validar permisos/aprobación vigente». Una desconexión no prueba
que la PC esté apagada.

## 8. Qué ocurre cuando algo falla

| Situación | Comportamiento requerido |
|---|---|
| PC apagada o dormida | Mostrar offline y última conexión; conservar encargos permitidos; no inventar acceso ni resultados; revisar aprobación al reconectar |
| Modelo local ausente | Indisponible; no cambiar a cloud ni descargar un modelo sin elección del usuario |
| Voz pierde conexión | Cerrar micrófono/transmisión según estado, informar y ofrecer texto; no perder ni repetir aprobaciones |
| Proveedor cloud no responde después de enviar | Resultado incierto; consultar estado sin nueva llamada ni devolución de coste supuesta |
| Agente cae durante tarea | Diario y verificación de salida; `unknown` si no hay evidencia suficiente; intervención humana antes de repetir |
| Dispositivo revocado | Rechazar nuevos accesos al servidor y operaciones, retirar vistas cuando se reciba revocación y señalar efectos inciertos; no promete borrar archivos ya descargados ni revocar claves locales mientras el equipo está offline |
| Snapshot o memoria fuera de fecha | Mostrar origen y antigüedad; bloquear decisiones que requieren estado vigente |
| Cuota agotada o consentimiento cambiado | Bloquear antes de transmitir; explicar qué se necesita para continuar |

## 9. Validación antes de prometer fiabilidad

Los siguientes son **objetivos iniciales propuestos**, no resultados ni un SLA.
Fijar hardware, SO, red, idioma, proveedor y coste del ensayo antes de medir.

| Prueba | Evidencia y puerta de salida propuesta |
|---|---|
| Voz real en español | Al menos 100 turnos en 10 sesiones; registrar p50/p95 de fin de habla a primer audio y respuesta completa, errores y aceptación humana; objetivo inicial p95 de primer audio ≤ 2 s en el perfil ensayado, sujeto a validación |
| Interrupciones | Al menos 20 interrupciones y cambios de audio; objetivo de detener reproducción p95 ≤ 300 ms; ningún turno obsoleto crea una propuesta utilizable |
| Seguridad de ejecución | Ninguna acción fuera de lista, sin permiso, con aprobación caducada o contenido cambiado; cero ejecuciones automáticas duplicadas en pruebas de caída/reenvío |
| Aislamiento | Dos clientes, dos dispositivos por cliente, búsquedas, archivos, cachés, resultados y revocación; cero cruces de datos en la batería negativa |
| Local estricto | Captura de tráfico y pruebas con red bloqueada, incluyendo procesos hijos; ninguna transmisión de contenido ni fallback oculto |
| Recuperación | PC dormida, proceso terminado, pérdida de respuesta, replay y red intermitente; estados ciertos o explícitamente inciertos, sin éxito inventado |
| Cloud | Consentimiento exacto, límites, revocación, reserva de coste y resultado incierto; primero proveedor falso, luego ensayo real autorizado y acotado |
| Distribución | Instalar, actualizar, recuperar versión y desinstalar en otra PC limpia; validar firma/integridad, permisos mínimos, conservación/exportación de datos y diagnóstico sin secretos |
| Archivo y salida | Cortar escritura, reiniciar, llenar disco, borrar dispositivo y restaurar backup; comparar hashes y abrir exportación sin ARKOS, cuenta ni red; no perder silenciosamente registros |
| Comunicación humana | Dos personas y varios dispositivos; contacto ambiguo, bloqueo/revocación, duplicados, PC apagada, push denegado, lectura opcional y llamadas rechazadas; ninguna exposición automática de memoria |

Medir contra el canal asíncrono bajo cargas comparables. Registrar tasas de éxito,
latencias, consumo CPU/RAM/batería y coste por sesión. No extrapolar un test sintético
o una muestra breve a todas las PC, voces, redes o clientes.

## 10. Secuencia de implementación propuesta

| Etapa | Entrega | Criterio para avanzar |
|---|---|---|
| LV0: reconciliar base | Inventario de ramas y decisiones, baseline de aceptación, permisos y residencia de datos | Revisión humana del diseño; no duplicar queue/relay/proveedores existentes |
| LV1: contrato y simulación | Contratos de voz y archivo portable, estados, interrupción, exportación y errores con proveedores falsos | Pruebas de permisos, cancelación, replay, aislamiento, archivo y compatibilidad del chat escrito |
| LV2: piloto local real | Sesión voz en la app PC, archivo por proyectos/temas y acción allow-listed tras revisión | Medición real y aceptación humana; persistencia, backup/restauración, controles de salida y recursos medidos |
| LV3: celular e híbrido opcional | Emparejamiento, sesión remota, relay y sincronización elegida; cloud solo tras autorización y límites | Consentimiento, autenticación, red, conflictos, coste y recuperación probados; PC offline visible |
| LV4: distribución por cliente | Paquete firmado, onboarding vacío, cuentas separadas, exportación y soporte | Otra PC y otro cliente, salida del servicio sin perder archivo, actualización/desinstalación y revisión de seguridad/licencias |
| COM1: mensajería humana | Identidades, contactos aceptados, sobre de mensaje y push mínimo; primero simulación | Atribución, entrega offline, permisos, cifrado, antispam, bloqueo y revocación validados |
| COM2: llamadas app-a-app | Invitación y llamada entre personas sin grabación por defecto | Dispositivos reales, aceptación/rechazo, red y privacidad; no autoriza delegación entre agentes |
| COM3: espacios y grupos | Grupos pequeños con roles; ampliación posterior según evidencia | Membresía, invitaciones, claves, privacidad, abuso y coste probados antes de escalar |

Estas etapas complementan el roadmap asíncrono; no cambian sus fases a completadas.
El primer incremento debe reutilizar el piloto e introducir la mínima superficie
de voz para medirla. Instalar un runtime existente o adoptar Hermes no sustituye
la aceptación del producto, ni le concede automáticamente autoridad sobre la PC.

## 11. Decisiones abiertas

- SO inicial y requisitos reales; Windows es el primer candidato por el piloto,
  macOS/Linux y app móvil nativa requieren sus propias pruebas.
- Runtime de app y voz, modelos, licencias y distribución; ninguna elección comercial
  se toma aquí. Revisar también redistribución de dependencias y modelos descargables.
- Autenticación del producto y mecanismo de emparejamiento; instancia por cliente o
  backend compartido, recuperación de claves y revocación fuera de línea.
- Memoria durable de conversación, política de retención y sincronización elegida;
  el historial actual del centro se pierde al reiniciar el servidor.
- Identidad de contactos, cifrado/recuperación, relay push y llamadas entre personas;
  compatibilidad de inicio automático y encendido remoto, siempre medidos por equipo.
- Permisos iniciales, canal de confirmación y operación de soporte sin acceso implícito
  a contenido privado; ampliar capacidades en cambios separados y revisados.
- Proveedor cloud, condiciones, localización de procesamiento y presupuesto, solo
  cuando exista un ensayo real autorizado. No ofrecer «ilimitado» ni privacidad
  absoluta como promesas del diseño.

## 11A. Ediciones y paquetes: diseño comercial exploratorio

Visión: una descarga gratuita y una edición paga con herramientas incluidas; módulos
por profesión para personalizar el asistente. **No hay precios, catálogo contratado,
suscripciones ni unidades económicas validadas en este documento.** No se cambia
la licencia del repositorio ni se compran servicios.

### Alta propuesta

1. Descargar el paquete verificado, elegir nombre del asistente y área privada.
2. Ver requisitos, datos guardados y modo de procesamiento; crear un archivo vacío
   del cliente. La edición gratuita y la paga preservan el principio de portabilidad.
3. **PC primero, luego celular:** la PC muestra «Vincular mi celular» con QR de un
   solo uso y caducidad breve. Escanear abre instalación/apertura del companion
   mediante enlace, tienda o onboarding web con reanudación; no instala una app
   nativa silenciosamente. Tras autenticarse como el mismo dueño, mostrar aprobación
   visible en la PC y el dispositivo que se vincula. El QR contiene un reto acotado,
   nunca secretos duraderos ni rutas/archivos. Asignar ID y claves por dispositivo,
   con revocación y recuperación. Emparejar no concede acceso a otras personas,
   micrófono o todos los archivos por sí solo.
4. Elegir paquetes y permisos mínimos. Separar claramente incluido, opcional y
   servicios externos que requieren cuenta, licencia o consumo aparte.
5. Comprobar nota local, archivo guardado, notificación y estado de conexión con
   datos de prueba. Habilitar voz, tareas remotas o inicio automático solo según sus
   requisitos. Encendido remoto se ofrece únicamente cuando la compatibilidad se valide.

Con PC offline, el celular puede leer lo ya descargado, recibir mensajes mediante
push y dejar tareas pendientes; son tres capacidades distintas. No puede leer un
archivo no sincronizado ni ejecutar una tarea de PC sin que vuelva el agente.
El encendido remoto opcional requiere una ruta compatible y no se promete a todos.

### Paquetes modulares por profesión

Ejemplo genérico: un pack Marketing y Diseño podría incluir instrucciones
especializadas, plantillas, organización de proyectos y adaptadores a herramientas
autorizadas. Instalarlo no demuestra dominio profesional ni conecta cuentas ajenas.
Cada pack necesita manifiesto de versión, dependencias, SO/hardware, permisos,
proveedores/destinos de datos, licencias, costes y pruebas de compatibilidad.

Los paquetes no pueden ampliar permisos mediante su prompt. Revisar procedencia,
firma/integridad y código ejecutable; instalación, actualización y desinstalación
deben preservar el archivo del usuario y permitir desactivar módulos. Un pack pago
puede incluir herramientas propias sin incluir licencias de terceros, cómputo de
modelos, generación de imágenes/video o almacenamiento ilimitados. Mostrarlo antes
de contratar o usar; ningún proveedor se activa como efecto implícito del pack.

### Costes antes de precios

La mensajería ordinaria app-a-app puede plantearse **sin cargo minorista por mensaje**
como objetivo comercial. No equivale a coste cero: hay relay, push, almacenamiento,
ancho de banda, claves, protección antiabuso, soporte y operación. Entregar un mensaje
no requiere llamar a un LLM; redacción, traducción, resumen o delegación opcionales
son funciones separadas con su procesamiento y coste explícitos.

Medir antes de fijar la edición gratuita, la paga o límites:

| Actividad | Unidad de medición propuesta |
|---|---|
| Mensajes y notificaciones | Mensajes, dispositivos, bytes, días retenidos, fallos y reintentos de transporte deduplicados |
| Conversación/voz IA | Tokens o minutos por etapa, duración de sesión, concurrencia, STT/TTS y cancelaciones cobradas |
| Llamadas humanas | Minutos y bytes directos/relayed, señalización y porcentaje que requiere relay |
| Archivo/sincronización | GB almacenados, transferidos, versiones y copias; restauraciones |
| Packs creativos | Ejecuciones y recursos locales, API o GPU externa usada por cada herramienta |
| Operación | Infraestructura fija, soporte, seguridad, abuso, distribución y actualizaciones |

Usar perfiles de uso medidos, incluyendo percentiles y picos; separar costes fijos
de variables y escenarios locales de cloud. Estimar coste por usuario activo y
margen solo con tarifas verificadas y consumo real. Local puede reducir gasto cloud
pero consume hardware, energía y soporte del cliente. No trasladar los topes del
ensayo de texto a un precio por usuario ni anunciar uso ilimitado.

La primera revisión comercial prioriza coste sostenible y límites comprensibles,
sin quitar las pruebas de fiabilidad y privacidad. Ediciones, packs, asignaciones
incluidas y cobro por excedente quedan pendientes de esa medición y decisión humana.

## 12. Relación con los documentos existentes

- [Master spec](ARKOS_PERSONAL_CEO_OS_MASTER_SPEC.md): conserva el MVP original;
  la app descargable y voz live son una ampliación de producto posterior.
- [Arquitectura base](ARCHITECTURE.md): mantiene WhatsApp/n8n/Supabase para sus
  flujos asíncronos. La voz live suma una vía específica y usa las mismas reglas.
- [Roadmap](ROADMAP.md): conserva Fases 0–8 y enlaza la nueva línea LV0–LV4.
- [Migración a API](MIGRATION_TO_ARKOS_CORE_API.md): preservar contratos y coexistencia;
  no reemplazar de golpe n8n ni migrar datos como efecto de este documento.
- [Seguridad](SECURITY_RULES.md): sus pendientes de producción siguen abiertos.
  Ningún nuevo modo eleva permisos ni certifica automáticamente esos controles.
