# ARKOS en la PC de Jona — prueba del 7 de octubre de 2026

Registro de hechos observados durante la continuación del PR #1, branch
`feat/arkos-desktop-pilot`, commit ARKOS
`b9a4b61cdc187037ae21b8083db41e3477a3afaa`.

Desktop está instalado y abierto en D:, con `arkos-pilot`, personalidad ARKOS,
modelo local y voz gratuita. Se comprobaron conversación, micrófono, salida
automática por HDMI, nombre/rol en sesión nueva, creación real de un archivo y
recuperación. **La aceptación completa sigue pendiente**: no se completó la
corrección hablada de fecha ni las cinco medidas desde fin de habla hasta primer
audio audible. Se registran defectos y pruebas pendientes abajo, sin reemplazar
esa medición por tiempos de generación de texto.

## Entorno y destino

- Windows 11 Pro 10.0.26200, x64; RAM 63,9 GB.
- NVIDIA GeForce RTX 3090, VRAM 24.576 MiB, driver 591.86.
- Windows enumera `Microphone (High Definition Audio Device)` con estado OK.
  Esta detección no constituye una prueba de captura, transcripción ni reproducción.
- No se encontró Hermes u Ollama en PATH, paquetes AppX o registros de instalación
  antes de empezar; tampoco había perfil `arkos-pilot` detectado.
- No había variables de credenciales de proveedor disponibles en esta sesión.
  No se leyeron credenciales de otros proyectos o aplicaciones.
- A pedido de Jona, el destino se cambió a **D:**, Samsung SSD 980 PRO with Heatsink
  2TB, NTFS, disco 1. Windows lo identifica como NVMe interno, no extraíble.
  La ubicación del programa no limita el uso de CPU, GPU, RAM ni los permisos del
  usuario sobre otros discos.
- Runtime y estado: `D:\ARKOS\hermes`; Python gestionado: `D:\ARKOS\python`;
  caché uv: `D:\ARKOS\cache\uv`; workspace: `D:\ARKOS\ArkosTrial`.
- Checkout ARKOS: `D:\ARKOS\repos\arkos-personal-ceo-os`.
  No se modificaron otros proyectos.

## Instalación: resultados observados

1. Se ejecutó `scripts/Get-ArkosDesktopReadiness.ps1` y se guardó su JSON.
2. Se ejecutó `scripts/Get-HermesDesktopInstaller.ps1`. El EXE tiene 7.946.048
   bytes, SHA-256
   `cfc818adf831a748c61a407152a03c7a426ebee78f499d20a31fae2b5ac5d827`,
   y Authenticode **Valid**, firmante **Nous Research Inc.**.
3. Se revisó el código del bootstrap. El ejecutable se abrió sin elevación y se
   pulsó Install. Descargó `scripts/install.ps1` de la rama mutable `main`;
   el log confirma que el EXE no tenía commit de código fijado.
4. La GUI falló en prerequisites: `Get-FileHash` no reconocido en su proceso.
   Un PowerShell separado sí encuentra el comando. No se cambió la política de
   ejecución ni se desactivaron validaciones. El log del fallo está preservado.
5. Se descargó y revisó el script oficial de fuente en el commit
   `489c1ac298f8ed13ccd688c97e4097f161046c0b`. Se ejecutó sin interacción, con
   Desktop incluido, sin instalar las herramientas opcionales de navegador ni
   de control de computadora. No se configuraron canales ni servicios externos.
6. El primer checkout falló por `Filename too long`. Se detuvo el reintento
   automático y se repitió con `core.longpaths=true` mediante variables de Git
   **solo del proceso**. El segundo checkout se completó.
7. uv descargó Python 3.14.7 pero falló al resolver su enlace de versión en
   AppData. Se observó la redirección de AppData bajo el paquete de Codex.
   Un runtime privado fuera de AppData superó ese fallo. No se modificó el
   runtime de Codex ni un entorno Python de otro proyecto.
8. Antes de terminar la instalación se atendió el pedido de usar el Samsung.
   Se detuvo la instalación y se trasladó el trabajo a D:. Move-Item entre discos
   dejó restos de solo lectura en C:; robocopy completó los destinos y se verificó
   que el checkout de Hermes en D: estaba limpio y en el commit fijado.
9. El empaquetado Desktop se completó, pero la instalación devolvió exit 1 por
   dos errores TS1484 de imports en `web/src/pages/SessionsPage.tsx`. Se agregó
   `type` a `SessionFilterCategory` y `SourceSelectionsByCategory` únicamente en
   este checkout nuevo de Hermes. El build web posterior pasó (exit 0). Hermes
   difiere del commit fijado por esas dos líneas; el diff queda registrado.
10. Desktop se abrió desde `apps/desktop/release/win-unpacked/Hermes.exe`, con
    `--local --skip-build --cwd D:/ARKOS/ArkosTrial`. La barra lateral y el log
    de enrutamiento confirman `arkos-pilot` activo. El bootstrap fallido se cerró.
11. Desde la UI se eligió ejecutar modelos localmente y configurar Qwen3.8 27B.
    Runtime llama.cpp b11370, backend CUDA: instalado. Se completaron
    17.395.586.656 bytes (modelo + proyector). Servidor local en
    `127.0.0.1:18434/v1`, modelo `Qwen3.8-27B-UD-Q4_K_M`; no API externa paga.
12. Se agregaron mediante PM los extras `voice`, `piper`, `edge-tts`, sin tocar
    el Python de Codex ni entornos existentes. Se creó un entorno nuevo privado.

Versión ejecutada: Hermes Agent `v0.21.5+8855.g489c1ac (2026.9.24)`; la UI anuncia
cuatro commits más recientes, que no se instalaron durante esta prueba.
Dependencias del runtime privado: Python 3.14.7, uv 0.12.3, Node 26.7.0,
npm 12.0.2, Git 2.53.0+3, ripgrep 15.2.0 y FFmpeg 9.0.1.

Hay restos de los intentos en C:, en las carpetas nuevas de esta prueba
`ArkosRuntime` y `%LOCALAPPDATA%\ArkosPilot`/`hermes`; no se borraron configuraciones
previas. Se creó inicialmente `Documentos\ArkosTrial` y luego el destino efectivo
se cambió a `D:\ARKOS\ArkosTrial`.

## Perfil y alcance técnico

Se creó con `hermes profile create arkos-pilot`, sin clone, en
`D:\ARKOS\hermes\profiles\arkos-pilot`. Al crear el perfil, su SOUL y la personalidad
del repo tenían el mismo SHA-256:
`0d77261286a1f4a58f0ce7381392777e72d8eec588339ece3e319224e55eef20`.
La CLI creó además el alias nuevo `C:\Users\Jona\.local\bin\arkos-pilot.bat`.

Configuración soportada guardada: cwd `D:/ARKOS/ArkosTrial`, home_mode profile,
sin escaneo de otros repos, aprobación manual; toolsets cli file/todo/tts.
Se deshabilitaron terminal, browser, computer_use, cronjob, connections, catalog,
project, desktop_ui, web, image_gen y video_gen para evitar acciones ajenas.
`HERMES_WRITE_SAFE_ROOT=D:/ARKOS/ArkosTrial` limita escrituras de las herramientas
de archivo. La comprobación directa de `write_file_tool` escribió el archivo de
control interno y bloqueó una ruta nueva fuera; esa ruta externa no existe.
Esto **no** es una sandbox de lecturas ni un aislamiento total del usuario Windows.

STT: local small, español, CPU/int8. La CLI avisa que provider/device/compute_type
no figuran en su validador, aunque el código instalado sí los consume. TTS:
Piper `es_AR-daniela-high`. El model card revisado identifica español argentino,
22.050 Hz y dataset CC BY-SA 4.0; está preservado en `D:\ARKOS\review`.
Edge con `es-AR-TomasNeural` quedó inicialmente como alternativa; se probó y
seleccionó después a pedido explícito de Jona. La preferencia final es una voz
femenina en español: el perfil actual usa `es-AR-ElenaNeural`, como se describe abajo.
`HF_HOME=D:/ARKOS/cache/huggingface` mantiene los pesos STT en el Samsung.
La comprobación sintética de voz pasó: Piper generó un WAV de 3,58 s y Whisper
transcribió «Hola Jona, soy Arcos, la reunión es el 15 de octubre a las 10».
El nombre ARKOS salió como Arcos. Los 37,38 s de TTS y 59,77 s de STT incluyen
descargas/carga inicial: no son latencias de conversación ni prueba humana.
Piper se precargó en el backend en 2.258 ms; Whisper small, en 1.387 ms.
Se inició conversación de voz con el botón y también se accionó Ctrl+Alt+V.
La primera tentativa no recibió frase; Jona reportó indicador sin movimiento.
En el reintento apareció una frase humana en español con reunión el 15 de octubre
a las 10 y una respuesta que la confirma. En esa primera tentativa no se había
comprobado reproducción audible; la verificación posterior se describe abajo.

La prueba humana produjo tres dictados (14,4 s, 13,3 s y un saludo posterior).
Jona confirmó que no escuchó respuesta; la salida deseada es el televisor Admiral
por HDMI. Windows/PortAudio usan `TV-monitor (NVIDIA High Definition Audio)` como
salida predeterminada. No se cambió la salida global de Windows.
El log reveló `speak-stream synthesis failed`: `HERMES_WRITE_SAFE_ROOT` bloqueaba
el MP3 temporal bajo C:\Users\Jona\AppData\Local\Temp. Se configuraron TEMP/TMP
**solo para Hermes** en `D:/ARKOS/ArkosTrial/.tmp` y se reinició. Se mantiene el
límite de escritura. El fallback Piper sí había generado MP3 en la caché privada;
esto por sí solo no demuestra reproducción HDMI.

Tras reiniciar, se pulsó «Leer en voz alta» sobre la confirmación del 15 de octubre
a las 10. El log muestra Piper y MP3 de 14.228 bytes en
`D:/ARKOS/ArkosTrial/.tmp/tmpcor48xiw.mp3` (limpiado por Hermes tras servirlo).
Jona respondió explícitamente que escuchó **esa frase por los parlantes del
Admiral**. Reproducción local por HDMI verificada. La corrección de fecha y la
interrupción audible aún no se completaron. El saludo de Hermes afirmó «audio
probado» antes de esa verificación: se registra como sobreafirmación del modelo.

Launcher para reabrir: `D:\ARKOS\Iniciar-ARKOS.cmd`.

Durante la conversación automática se detectó otro motivo de respuestas solo
en texto: la preferencia Desktop «Leer las respuestas en voz alta» estaba apagada.
Se activó desde su control nativo; la UI cambió a «Dejar de leer las respuestas en
voz alta». El código instalado usa esta preferencia también en el modo de
conversación y la persiste como `hermes.desktop.autoSpeakReplies`. No se cambió
un motor externo ni se introdujo un costo. Hermes respondió «¡Hola, Jona! Es un
gusto trabajar a tu lado para pulir ARKOS» y generó audio automáticamente con
Piper. Jona confirmó explícitamente que el saludo salió solo por los parlantes
del Admiral, sin pulsar «Leer en voz alta». Salida automática audible verificada.

Jona pidió explícitamente que se recuerde su nombre y su rol de creador de ARKOS.
Se agregó una entrada de 407 caracteres mediante MemoryStore del propio Hermes,
solo al perfil nuevo: `D:/ARKOS/hermes/profiles/arkos-pilot/memories/USER.md`.
La entrada fue leída y verificada: Jona, creador/operador, español rioplatense,
respuestas habladas breves, cero pagos y no cambiar el nombre por errores STT.
No se cambió el SOUL del repo. El código carga esta memoria al iniciar sesión;
la sesión ya abierta recibió además un mensaje explícito con el nombre confirmado.
Se observaron errores STT en una frase libre con su nombre; no hay aprendizaje
automático del acento demostrado, pese a que el modelo lo sugirió.

Se abrió una conversación nueva `20261007_133900_301ac1` y se preguntó «¿Cómo me
llamo y cuál es mi relación con ARKOS?», sin suministrar la respuesta. Hermes
contestó «Te llamás Jona y sos el creador y operador de ARKOS». Esto verifica la
carga de la memoria de usuario en otra sesión. Turno 9,8 s; Piper generó audio
automáticamente (11.197 bytes). Evidencia en `session-20261007_133900_301ac1.json`.

La conversación posterior capturó saludos y preguntas humanas, y generó sus
respuestas automáticamente con Piper. Jona reportó voz rápida/cortada/robótica.
El modelo propuso `speed: 0.85`, pero el código Piper instalado no consume esa
clave genérica: usa `tts.piper.length_scale`. Se configuró `length_scale: 1.12`
mediante la CLI solo en el perfil nuevo. El validador de la CLI no reconoce esa
clave, aunque el código sí la consume. Prueba técnica con la misma frase:
4,331 s de audio a escala 1,0 frente a 4,586 s a 1,12. Se verificó que el ajuste
modifica la duración; no se declara naturalidad ni ausencia de cortes por ello.
Los WAV de comparación están en ArkosTrial y el JSON en `piper-pace.json`.
Jona confirmó después «Ahora es más cómoda». Mejora percibida del ritmo
confirmada; no se midió naturalidad ni se demostró eliminar todos los cortes.

Para la interrupción se envió una explicación larga por texto con el modo de voz
activo. El turno terminó en 30,5 s, pero esa respuesta no se leyó automáticamente
(la UI quedó en Escuchando y no hubo síntesis asociada en el log). Las respuestas
a los turnos capturados por micrófono sí generan audio. Se registra el caso mixto
texto mientras el modo de conversación está activo como defecto observado.
Se accionó «Leer en voz alta» sobre la explicación para preparar el intento
humano de «resumilo». Jona confirmó «No toma la interrupción». Después sí apareció
«resumílo» a las 13:47:17 y el asistente resumió en un turno de 2,7 s. Esto
demuestra recepción posterior y respuesta al pedido; no demuestra cortar la
reproducción en el instante de la interrupción. Resultado **fallido en este
recorrido con reproducción manual**. No confundir esa activación manual con
lectura automática ni extender el resultado a todos los recorridos de voz sin
probarlos. La interrupción durante una respuesta originada íntegramente por voz
queda pendiente de otra prueba. Se cerró la captura de este intento dejando la
app abierta; lectura automática sigue activada.

En el segundo intento se comprobó desde la UI que la conversación de voz estaba
activa con Elena. Se indicó a Jona que pidiera una explicación por micrófono y
dijera «Pará, resumilo en una frase» durante la reproducción. Respondió «va bien»
a la consulta de si corta y responde al nuevo pedido. Se registra esa devolución
humana positiva sin convertirla en una medición: la exportación consultada aún
no contiene ese pedido de explicación ni un nuevo «resumilo», y no se midió el
instante del corte. El fallo anterior se conserva; falta correlacionar el segundo
intento con su transcripción para dar por cerrado el caso técnico.

Preferencia explícita de Jona durante la prueba: ARKOS debe poder usar un router
con distintos modelos/proveedores y, mediante integraciones, distintos agentes.
Qwen3.8 es solamente el primer backend local de prueba; no una elección exclusiva.
El piloto de hoy no demuestra enrutamiento multiagente. No se configuró un router
con proveedores externos sin credenciales ni se compraron planes.

Jona también pidió poder sumar una voz ElevenLabs más adelante para uso personal
y pruebas con otras personas. El proveedor está soportado por Hermes. Queda
pendiente conectar la cuenta mediante la UI segura y seleccionar una voz
disponible/autorizada; no se leyó una clave de ElevenLabs ni se clonó ninguna voz.
Piper se conserva como opción local; el proveedor activo pasó después a Edge.

Restricción reafirmada por Jona: cero compras/suscripciones y cero consumo de APIs
pagas durante esta etapa. No se eligió un plan del portal Nous que mostró en su
captura. ElevenLabs queda pendiente de una opción gratuita comprobada con límites;
no habilitar recargas ni cambiar a un proveedor pago para resolver un bloqueo.

Pedido adicional: activación sin habla, por ejemplo aplauso/gesto. Todavía no
implementado. El arranque manual de conversación de voz está visible en la UI;
un detector de aplausos requeriría un componente separado y micrófono activo.
No se habilitó escucha permanente ni se cambió la privacidad de Windows.

## Pruebas de proactividad y permisos

Ante «Quiero recortar un video», Hermes buscó una herramienta y trató de ejecutar
`ffmpeg -version` mediante una llamada diferida a terminal. La llamada devolvió
error: terminal figura como herramienta directa y no puede invocarse mediante
ese puente; además está deshabilitada en este perfil. No se ejecutó el recorte.
Después reconoció la ausencia de acceso, propuso FFmpeg, preguntó ruta y segmento
y pidió habilitación para ejecutarlo. Resultado parcial: propuesta y consulta
concretas, pero intento previo de usar una herramienta no disponible. Duración
del turno: 37,4 s. FFmpeg está instalado en el runtime; el agente no lo verificó.

En otra conversación Jona pidió abrir YouTube. Hermes reconoció que browser/web
están deshabilitados. A continuación afirmó que bastaría una confirmación hablada
para abrir el navegador o instalar software. Esa capacidad no se demostró: el
perfil mantiene terminal/browser/computer_use/web deshabilitados y modo manual.
El código Desktop dispone de solicitudes de aprobación y respuestas mediante
controles/comandos; la revisión no encontró una integración explícita que haga
de un «sí» hablado la resolución de esa solicitud. Se registra la promesa del
modelo como no verificada. La captura enviada por Jona muestra esa conversación,
no una ejecución de navegador ni una instalación; no se habilitaron herramientas
adicionales a partir del contenido de la captura.

Para probar borrado fuera del workspace se creó un archivo desechable propiedad
de esta prueba en `D:/ARKOS/permission-probe-delete.txt`. Hermes respondió «No lo
borro», explicó el límite y no llamó herramientas de borrado. El archivo sigue
presente con el mismo SHA-256
`6db3dba9b9f3469e62e45008eb83d694d2f618383b045ea30bc8612dd5e6425e`.
Duración del turno: 17,7 s. Esto verifica rechazo en esta conversación; la prueba
técnica de escritura queda registrada por separado. La afirmación del modelo de
que toda ruta externa está fuera de su alcance es más amplia que la protección
real: el límite probado restringe escrituras, no todas las lecturas.

## Cambio autorizado a Edge TTS

Después de probar Piper, Jona pidió configurar Edge y expresó que más adelante
quiere utilizar **su propia voz** con ElevenLabs. Se verificó con el servicio real
que `es-AR-TomasNeural` está disponible (masculina, es-AR), y se generó un MP3 de
32.832 bytes con una frase de prueba sin credenciales ni cuenta paga. Consulta
de voces más síntesis: 3,407 s; no es latencia fin de habla a primera voz audible.
Evidencia: `edge-component.json`, audio en `D:/ARKOS/ArkosTrial/voz-edge-prueba.mp3`.

Se preservó la configuración anterior en
`D:/ARKOS/hermes/profiles/arkos-pilot/config.before-edge-20261007.yaml` y se cambió
solo este perfil a `tts.provider: edge`, voz `es-AR-TomasNeural`, velocidad 0,92.
La CLI advierte que su validador no reconoce `tts.edge.speed`; el código instalado
sí usa esa clave y convierte 0,92 a `-8%`. Piper y sus pesos siguen disponibles
para volver al proveedor local; no se configuró un fallback automático.

La respuesta del chat a las 13:49:24 generó automáticamente dos fragmentos con
Edge (39.600 y 20.592 bytes), mostrando la aplicación «Leyendo en voz alta».
Jona confirmó «Sí, la escuché y es más natural», verificando la salida automática
de Tomás por el Admiral. Después pidió una voz femenina en español como requisito.
Edge usa el servicio
de Microsoft por internet; la transcripción Whisper y el modelo Qwen siguen
locales. No se contrataron planes ni se agregó una clave. Esta prueba no demuestra
disponibilidad permanente, licencia comercial ni distribución masiva del servicio.

Se consultó la lista real de voces y se comprobó `es-AR-ElenaNeural`, género
Female, locale es-AR. Se sintetizó otro MP3 de 35.856 bytes a `-8%` en 2,852 s
(consulta más generación, no latencia de conversación). Evidencia:
`edge-component-es-AR-ElenaNeural.json`; audio:
`D:/ARKOS/ArkosTrial/voz-edge-es-AR-ElenaNeural.mp3`.
Se cambió únicamente `tts.edge.voice` a Elena; siguen Edge, velocidad 0,92 y
lectura automática. La preferencia femenina se agregó mediante MemoryStore del
perfil, conservando la entrada de identidad; uso total 759 caracteres.

Se envió desde la UI un pedido de saludo breve sin herramientas. Hermes respondió
«¡Hola, Jona!» a las 13:54:34 y generó automáticamente un MP3 Edge de 14.400 bytes
a las 13:54:48. El turno de texto duró 2,0 s; la síntesis tardó aproximadamente
13,8 s, considerablemente más que la prueba del componente. No se equipara ese
tiempo con la latencia fin de habla a primera voz audible. Jona confirmó «todo ok»
en respuesta a la comprobación de la voz femenina por el Admiral: salida audible
confirmada. No se accionó «Leer en voz alta» para ese saludo.

Sobre la voz «de fábrica», la propuesta inicial fue Tomás/Edge y se actualiza
por la preferencia explícita de Jona a Elena/Edge, con Piper como opción local
sin internet. Es una propuesta:
el instalador público de ARKOS y su selección automática de voz no se construyeron
en esta prueba. La voz propia de Jona en ElevenLabs no se creó ni se conectó.

## Contexto y medición automática posteriores

Jona autorizó que Codex prepare contexto, conexiones y comandos cotidianos en el
repositorio; después eligió terminar conversación/demora antes de navegación.
Se agregaron `HERMES_DAILY_PILOT.md`, el catálogo `hermes-daily-tasks.json` y el
contexto de despliegue. Se reforzó la personalidad para distinguir workspace de
repositorio, voz de modelo, autorizaciones de herramientas efectivas y agenda
local de eventos externos. Se corrigió también la indicación de pegar claves API
en el chat observada en una respuesta de Hermes: el contexto exige configuración
segura, sin credenciales en conversación ni Git. No se conectó ElevenLabs.

`Sync-ArkosHermesContext.py` aplicó la personalidad y el contexto a `arkos-pilot`,
con backup exacto del SOUL anterior junto al perfil. SHA-256 efectivo nuevo:
`6200359c3c14843ffde9c409263f1b1127dfe92b62b5740dd262fbafc827a80a`.
No se cambiaron memorias anteriores, credenciales ni toolsets. El nuevo contexto
se comprueba en una sesión nueva; no se supone que actualice retroactivamente
el historial de la sesión anterior.

La sesión nativa nueva `20261007_141003_a80589` respondió correctamente, sin
incluir las respuestas en el pedido: Jona creador/operador, Edge/Elena 0,92,
workspace distinto del repositorio y navegador/ElevenLabs no conectados. El
turno duró 14,5 s y hubo síntesis Edge automática registrada. Esto verifica el
contexto efectivo del agente dentro de Desktop, además del benchmark separado.

`Test-HermesVoicePipeline.py` completó cinco turnos sintéticos usando las rutas
reales de STT/TTS de Desktop y el endpoint autenticado de llama.cpp de esta
instalación. El intento inicial se detuvo al faltar autenticación del endpoint
local; quedó en `voice-pipeline-initial-failure.json`. Se corrigió usando el
resolutor local verificado de Hermes, sin exportar su token interno, y se
ejecutaron de nuevo los cinco turnos completos. No hubo un proveedor pago.

| Turno sintético | STT (s) | Modelo (s) | TTS (s) | Hasta audio completo (s) |
|---|---:|---:|---:|---:|
| Fijar fecha | 2,961 | 4,244 | 2,011 | 9,216 |
| Corregir fecha | 2,601 | 0,931 | 1,589 | 5,122 |
| Recordar fecha corregida | 2,474 | 0,951 | 2,124 | 5,548 |
| Planificar la mañana | 2,336 | 1,402 | 1,796 | 5,534 |
| Diferenciar agenda de calendario | 2,691 | 1,017 | 1,995 | 5,703 |
| **Mediana** | **2,601** | **1,017** | **1,995** | **5,548** |

Se transcribieron correctamente 15/10/10 y la corrección 16/10/11; el modelo
recordó «16 de octubre a las 11». Hubo errores menores («Corijo», «Ya me tres
pasos») sin alterar esos números. La respuesta sobre calendario aclaró que un
archivo no equivale a crear un evento. Audio Edge producido en los cinco casos.
Evidencia completa: `voice-pipeline-five-trials.json` y audios bajo
`D:/ARKOS/ArkosTrial/voice-benchmark/20261007T170745886267Z/`.

**Límite de la medición:** entrada WAV sintética ya grabada, sin micrófono,
detector de fin de habla, orquestación nativa del agente, herramientas ni salida
física. Modelo sin razonamiento extenso, máximo 256 tokens. Se mide hasta recibir
el audio completo, no hasta el primer fragmento audible. No prueba el objetivo
de tres segundos ni sustituye las cinco latencias humanas solicitadas.

Validación del código: 16 tests pasaron inicialmente y uno de video quedó omitido
por PATH. Se repitió ese test con el FFmpeg privado ya instalado y pasó. Los
17 casos quedaron cubiertos, incluidos preservar otro perfil, backup exacto,
reaplicación sin cambios y rechazo de endpoints públicos/redirecciones.

## Tareas cotidianas ejecutadas con el agente real

La CLI de Hermes completó diez pedidos en la misma sesión
`20261007_141722_5932c9` (título `ARKOS rutina 20261007T171719093967Z`). Se
revisaron las respuestas y los contenidos guardados: nombre/rol correctos,
reunión inicial 15/10 a las 10, corrección y recuerdo 16/10 a las 11, plan,
lista de compras, notas, borrador de correo, resumen del archivo y aclaración
de que un ID de voz no conecta una cuenta. Esa última respuesta es anterior a
la autorización posterior de ElevenLabs. No se enviaron correos ni crearon eventos.

Cuatro archivos reales quedaron en
`D:/ARKOS/ArkosTrial/rutina-20261007T171719093967Z/`:

| Archivo | Bytes | Contenido verificado |
|---|---:|---|
| plan-del-dia.md | 295 | Tres prioridades de ejemplo y casillas |
| compras.md | 43 | Pan, leche y frutas |
| ideas-arkos.md | 93 | Activación con botón e interrupción por voz |
| correo-borrador.md | 360 | Invitación breve, sin destinatario ni envío |

Respuestas, contenido y hashes: `daily-cli-trial.json`. Los tiempos de CLI
incluyen arranque y cierre; no son latencias de voz. El borrador dice que el
piloto «corre en local», pero antes de publicarlo hay que aclarar que Edge y
ElevenLabs necesitan red. La prueba verificó creación de borrador, no aprobó
esa frase como promesa comercial.

## ElevenLabs: integración configurada, audio bloqueado por el servicio

Jonathan entregó una clave y un ID de voz, autorizó una prueba con créditos y
pidió el saludo «Jonathan, ¿estás por ahí?». Después indicó explícitamente
mantener ElevenLabs hasta que él solicite volver a la opción gratuita. No se
compró un plan ni se modificó facturación. No se creó un clon de su voz.

La consulta de voz respondió HTTP 200 (nombre `luxuria`, categoría
`professional`). La consulta de consumo respondió HTTP 401: no se pudo verificar
el saldo ni el consumo de la cuenta; no se afirma costo cero para la API.
La clave se guardó únicamente en el `.env` privado de `arkos-pilot`, con respaldo
de configuración anterior bajo `trial-backups`; no se incluyó en Git. Se advirtió
que una clave pegada en la conversación debe rotarse después de la prueba.

El primer ensayo del componente produjo Edge porque `tts.provider` prevalece
sobre el argumento de la llamada. Quedó marcado como fallo de prueba y se corrigió
el ejecutor para exigir el proveedor real; ese MP3 no es evidencia de ElevenLabs.

Se instaló la extensión oficial `tts-premium` (`elevenlabs==1.59.0`) mediante el
gestor de Hermes. El proceso Desktop anterior conservaba el entorno sin esa
extensión: a las 14:33:23 falló con `No module named 'elevenlabs'`. El texto del
saludo tardó 32,9 s por recarga del modelo tras inactividad. Jonathan confirmó
que no había audio. Después del reinicio, el import falló en un módulo generado
cuyo nombre completo superaba MAX_PATH. Se verificó carga por ruta corta y por
ruta extendida, y se aplicó un parche de cuatro líneas a la activación de
dependencias de Hermes. Parche versionado: `hermes-windows-long-paths.diff`.
No se modificaron políticas de Windows ni paquetes de otros proyectos.

Tras reiniciar con ese arreglo, a las 14:38:16 Hermes llamó realmente a
ElevenLabs. Tanto la síntesis en streaming como su reintento sin streaming
recibieron HTTP 401, `payment_required` / `payment_issue`: el proveedor informa
un pago fallido o incompleto en la suscripción. No hubo síntesis exitosa ni audio
audible de ElevenLabs. No se hicieron más intentos de generación tras identificar
ese bloqueo. Evidencia resumida: `elevenlabs-desktop-trial.json`.

Hermes quedó abierto y ElevenLabs seleccionado por indicación de Jonathan;
Elena/Edge permanece preparada para restaurar cuando él lo pida. La memoria del
perfil ahora reconoce **Jonathan (Jona)** y el saludo solicitado. La restauración
está preparada en `Configure-HermesElevenLabsTrial.py`, con estado privado en
`trial-backups/elevenlabs-20261007T172900697064Z/state.json`.
SHA-256 del SOUL final aplicado con backup:
`4a22f064e8e21223997a9ec2854a3dc4e19272f0c7a2d2135c14c415080a07d1`.
Las sesiones ya abiertas conservan historial/contexto anterior; las nuevas
cargan esta versión, que describe el bloqueo y la excepción de prueba autorizada.

Las cinco pruebas de regresión del contexto/endpoints volvieron a pasar. Una
prueba aislada con credenciales ficticias comprobó configuración y restauración:
conserva voz anterior, variables ajenas, cambios posteriores de configuración y
una clave reemplazada por el usuario. No hizo llamadas a ElevenLabs. Se validó
la sintaxis de los cuatro scripts nuevos de ejecución/configuración y se revisó
que los archivos a publicar no contienen la clave proporcionada ni patrones de
tokens de proveedores; los JSON se parsearon correctamente.

## Reintento de ElevenLabs después del aviso de Jonathan

Jonathan informó «listo todo pago» y se repitió el saludo desde el chat nativo,
manteniendo la voz seleccionada. Hermes respondió «Jonathan, ¿estás por ahí?»
a las 14:43:44; el turno de texto duró 13,8 s. Jonathan confirmó explícitamente
que lo escuchó **automáticamente por los parlantes del Admiral**. No se pulsó
«Leer en voz alta» para este saludo. Después, el chat recibió «Sí, estoy por acá»
y la UI mostraba conversación de voz activa, en estado «Escuchando».

Una muestra adicional breve usando la herramienta real de Hermes confirmó
`provider: elevenlabs`, modelo `eleven_flash_v2_5`, voz autorizada y MP3 de
32.226 bytes, en **1,933 s de síntesis completa**. Archivo:
`D:/ARKOS/ArkosTrial/elevenlabs-trial-20261007T174358909006Z.mp3`.
Hash y resultado: `elevenlabs-after-payment.json`. Esta métrica no incluye
razonamiento, micrófono ni inicio audible; no es latencia conversacional.
La consulta de consumo sigue devolviendo HTTP 401: no se verificó consumo ni
saldo. Codex no efectuó pagos ni cambió la configuración durante el reintento.

El fallo `payment_issue` queda como antecedente; la generación y reproducción
automática ya están confirmadas para esta prueba. ElevenLabs queda activo hasta
que Jonathan solicite cambiarlo. La app permanece abierta para la conversación.

CI detectó además una suposición del test sobre la ruta temporal de Windows:
`RUNNER~1` y `runneradmin` resuelven al mismo directorio. Se corrigió la comparación
para usar la ruta canónica, coherente con el script. Las cinco pruebas específicas
pasaron localmente; las cuatro combinaciones Windows/Linux y Python 3.11/3.12
pasaron en CI para `705860c`. La prueba de video se omite donde falta FFmpeg;
su ejecución local con el binario privado ya está registrada arriba.

Se actualizó la memoria de voz mediante MemoryStore, conservando dos entradas
y un backup privado del USER anterior. El SOUL posterior a la confirmación tiene
SHA-256 `0bf80058cf8fdcf008298c6cff391afadec00e01d3b89d70d58411557ed1f374`.
No se reinició ni interrumpió la conversación que Jonathan ya tenía activa.

## Estática y cortes: prueba del transporte de audio

Jonathan indicó que la estática aparecía solo con Hermes. En la conversación
describió caídas de volumen y palabras que se pierden. La sesión antigua aún
atribuía la voz a Edge y propuso modificar su velocidad; se corrigió explícitamente
el contexto del chat para reconocer Luxuria/ElevenLabs. No se aceptó como
diagnóstico la explicación del modelo sobre la conexión de red. Algunas respuestas
de texto también acababan incompletas; su causa no quedó determinada.

Se comprobó que la muestra MP3 de ElevenLabs generada a las 14:43 decodifica sin
errores (mono, 44.100 Hz, 1,950 s, pico -6,647 dBFS). Eso no sustituye la escucha
humana ni demuestra que la reproducción de Hermes estuviera libre de ruido.

El código de Desktop muestra que el modo directo solicita cada frase después de
terminar de reproducir la anterior. Para probar el transporte integrado por
streaming se cambió **solo `voice.client_direct` a `false`** en `arkos-pilot`,
con backup privado del YAML. El endpoint autenticado confirmó `tts.mode: relay`.
La caché del cliente dura 60 s; el ensayo se lanzó después de ese plazo.
Se mantuvieron proveedor, voz, velocidad, salida HDMI y opciones de interrupción.
No se modificó la configuración de Windows ni se contrató ningún plan.

A las **14:52:04** se envió desde la UI nativa una prueba de tres frases que
empieza «Jonathan, ¿estás por ahí?». Hermes produjo el texto completo a las
**14:52:08** y mostró «Leyendo en voz alta» automáticamente, con conversación de
voz inactiva para aislar la salida. Jonathan confirmó **«Clara, sin estática ni
cortes»**. La diferencia entre registros del pedido y la respuesta fue 3,167 s;
no mide la primera muestra audible y no valida el objetivo conversacional de 3 s.

A pedido de Jonathan se reactivó la conversación de voz y a las **14:53:26** se
envió «Jona, ¿estás? Quiero que hablemos». El texto completo quedó registrado
a las **14:53:28** (2,070 s entre registros). La UI volvió a «Escuchando» y quedó
abierta. La calidad de este segundo llamado con micrófono activo y la estabilidad
durante una conversación larga quedan pendientes de confirmación específica.

La mejora inicial está confirmada por el usuario, pero no aísla todavía la causa:
el primer ensayo cambió el transporte y se hizo sin micrófono. No se declara
resuelta definitivamente la estática ni verificada una interrupción humana.
Evidencia: `voice-relay-stream-trial.json`. El contexto versionado identifica
Luxuria y este resultado puntual para evitar volver a confundirla con Edge.

## Estado de aceptación actualizado

| Caso | Estado actual | Evidencia |
|---|---|---|
| Instalación y apertura Desktop | Apertura verificada | App en D:, backend loopback, build web reparado |
| Perfil vacío y personalidad | Verificado; contexto ampliado con backup | Perfil nuevo, hash inicial coincidente; después SOUL compuesto y versionado |
| Nombre y rol persistentes | Verificado en sesión nueva | USER.md propio del perfil; respuesta correcta sin darle el nombre en el pedido |
| Conversación en español | Ejecutada; lenta | text-transcript.json, tres pasos y mejora; 100,6 s en primer turno |
| Tres turnos de voz y corrección de fecha | Dictados y HDMI comprobados; corrección sintética pasó | WAV → STT → modelo → TTS retiene 16/10 a las 11; corrección humana pendiente |
| Respuesta hablada automática | Verificada | Preferencia Desktop activada; generación Piper y confirmación humana del saludo automático |
| Interrupción audible y nuevo pedido | Fallo inicial; devolución humana positiva en reintento | Lectura manual: «No toma la interrupción». Reintento con conversación de voz/Elena: «va bien»; transcripción específica y tiempo de corte aún no correlacionados |
| Archivo creado por Hermes | Verificado | write_file creó borrador.md, 948 bytes; contenido leído por Codex y actividad visible; 28,0 s |
| Proactividad con herramienta ausente | Parcial; defecto registrado | Propone FFmpeg y pide habilitación; antes intenta terminal y falla; 37,4 s |
| Recuperación de sesión | Verificada | Misma sesión al reabrir y nuevo turno de escritura completado |
| Permisos fuera del workspace | Escritura técnica bloqueada y borrado rechazado | file-guard.json; archivo externo conserva hash; sin sandbox de lecturas |
| Cinco latencias y mediana | Benchmark sintético: 5,548 s; humana pendiente | Hasta audio completo; no fin de habla a primer audio audible |
| Tareas cotidianas del agente | Diez pedidos ejecutados y revisados | Cuatro archivos comprobados; corrección de fecha retenida |
| ElevenLabs | Generación y saludo automático confirmados después del reintento | MP3 real; Jonathan confirmó audio por Admiral; bloqueo inicial conservado en evidencia |
| Estática y cortes | Primera prueba limpia confirmada; conversación prolongada pendiente | Transporte relay, micrófono inactivo en la prueba de las 14:52; después se reactivó la escucha |

## Evidencia

JSON y log originales sanitizados: `docs/trial-evidence/2026-10-07/`.
Los archivos no contienen claves de proveedor.

Incidente de captura: al seleccionar por primera vez la ventana nueva de Hermes,
la imagen devuelta mostró una ventana Chrome ajena con una clave parcialmente
visible. Se informó a Jona. Esa imagen no se guardó como evidencia ni se copió
la clave a archivos ni se utilizó. Se activó explícitamente la ventana de Hermes
y se verificaron las capturas posteriores. El registro no afirma ausencia total
de exposición en esa captura de la conversación.

Fuentes oficiales consultadas el 7 de octubre:

- [Instalación](https://hermes-agent.nousresearch.com/docs/getting-started/installation/).
- [Desktop](https://hermes-agent.nousresearch.com/docs/user-guide/desktop/).
- [Perfiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles/).
- [Voz](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode).
- [Modelos locales](https://hermes-agent.nousresearch.com/docs/user-guide/local-models).
- [Permisos y límites](https://hermes-agent.nousresearch.com/docs/user-guide/security).
