# ARKOS: piloto de escritorio

La siguiente etapa prioriza probar una interfaz existente completa:
[Hermes Desktop: instalación, voz y aceptación en la PC](HERMES_DESKTOP_TRIAL.md).
Kokoro y un puente propio no son requisitos para empezar esa prueba. El control
Python descrito abajo sigue separado del runtime Hermes.

## Qué existe y qué entrega este incremento

Inventario al 2 de octubre de 2026: ocho workflows n8n, diez migraciones SQL,
prompts de CEO y voz Marin, documentación de WhatsApp, memoria y aprobaciones.
Su presencia en Git no demuestra que estén desplegados o funcionando.
Este incremento agrega un ejecutable Python local, una cola SQLite persistente,
catálogo de herramientas, propuestas basadas en reglas y dos acciones reales:
guardar una nota Markdown y recortar un video con FFmpeg instalado.
No modifica contratos n8n, SQL ni credenciales existentes.

## Base seleccionada de GitHub

| Componente | Base | Uso previsto | Estado en este PR |
|---|---|---|---|
| Motor conversacional | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | Conversación, proveedores y herramientas | Detectado en PATH; puente pendiente |
| Voz local | [hexgrad/kokoro](https://github.com/hexgrad/kokoro) | Hablar español sin tarifa por llamada a API | Detectar paquete; síntesis pendiente |
| Escucha | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Transcribir audio local | Detectar paquete; captura/transcripción pendiente |
| Video | [FFmpeg](https://ffmpeg.org/) | Recorte real aprobado | Implementado y probado |
| Domótica | [Home Assistant](https://www.home-assistant.io/) | Entidades compatibles expuestas vía MCP | Conector pendiente |
| Control ARKOS | Este repositorio | Cola, selección, revisión y ejecución | Implementado para nota/recorte |

Hermes es el motor recomendado, no un modelo de pesos. Elegir proveedor/modelo
y presupuesto será parte de su configuración. Antes de conectarlo al ejecutor,
verificar que ninguna herramienta omita la revisión ARKOS. No lanzar comandos
arbitrarios generados por un modelo desde esta cola. No se incluye ni instala
código upstream en este PR. Fijar commit/versiones y revisar licencias de código,
pesos, voces y dependencias antes de empaquetar una distribución comercial.

## Probar ahora

Python 3.11 o superior. El núcleo no necesita paquetes externos ni una API key.
Desde la raíz del repo:

```powershell
./scripts/Start-Arkos.ps1 doctor
./scripts/Start-Arkos.ps1 propose "Quiero recortar un video para mañana"
./scripts/Start-Arkos.ps1 note "Preparar una propuesta con tres variantes"
./scripts/Start-Arkos.ps1 list
```

`note` devuelve una tarea pendiente: revisar `payload`, copiar su `id` y
`fingerprint`, y aprobar exactamente ese encargo:

```powershell
./scripts/Start-Arkos.ps1 approve ID HUELLA
./scripts/Start-Arkos.ps1 run-next
./scripts/Start-Arkos.ps1 show ID
```

Para video, instalar FFmpeg mediante su distribución oficial y verificar PATH:

```powershell
./scripts/Start-Arkos.ps1 clip 'C:\Videos\original.mp4' --start 5 --duration 10
```

Revisar y aprobar con el mismo procedimiento. La salida se crea con nombre
único en `%LOCALAPPDATA%\ArkosPilot\outputs`; el original no se sobrescribe.
La huella vincula también el contenido del archivo, no solo su nombre.
Cambiar el original obliga a crear una tarea nueva. Los recortes se recodifican
a MPEG-4/AAC; no se promete conservación exacta de calidad o todos los streams.

En Linux/macOS: sustituir el launcher por `python -m arkos_pilot`.
Datos por defecto: `~/.local/share/ArkosPilot`; para pruebas usar
`python -m arkos_pilot --state-dir RUTA ...`.

## Preparar la PC grande

1. Descargar/clonar este branch y revisar el PR. Mantener una copia del repo.
2. Tener Python 3.11+ disponible en PATH. El launcher crea `.venv` aislado.
3. Ejecutar `doctor` y `python -m unittest discover -s tests -v`.
4. Probar nota y recorte sobre un archivo de prueba. Revisar la salida real.
5. En el siguiente incremento, instalar Hermes fijado a una versión revisada,
   configurar el proveedor y conectar propuestas al esquema de acciones.
6. Probar voz local y luego UI/arranque automático con permisos limitados.

Este launcher prepara y ejecuta el piloto. Todavía no es un instalador firmado,
actualizador ni servicio de inicio automático. No instala Hermes, modelos,
FFmpeg o drivers, ni cambia políticas de Windows. La ejecución en Windows se
verifica con CI; la PC del usuario necesita su propia prueba de aceptación.

## Cola y límites actuales

`awaiting_approval → queued → running → completed`; una aprobación vencida,
archivo modificado o error deja la tarea `blocked`. `cancel` solo funciona antes
de ejecutar. `run-next` reclama una tarea por transacción y luego termina.
No hay ejecución en segundo plano ni recepción remota en este incremento.
La cola sobrevive a un apagado, pero no trabaja mientras la PC está apagada.
Tras encenderla hay que ejecutar `run-next`. Las aprobaciones duran hasta 24 h;
una tarea más antigua requiere nueva revisión.

Si hubo interrupción durante `running`, detener todos los workers, revisar
salidas y usar `recover-interrupted`: bloquea las tareas y exige nueva aprobación.
No reintenta acciones automáticamente. SQLite y archivos son locales y no
están cifrados por este piloto; un usuario con acceso al perfil puede alterarlos.
La huella evita confusiones/cambios accidentales, no sustituye aislamiento de SO.

Catálogo: detecta ejecutables en PATH y paquetes Python. No afirma detectar todas
las aplicaciones instaladas ni que un paquete tenga sus modelos listos. Propuestas
son reglas iniciales, no comprensión general. Canva, Alexa, browser, instalación
consentida, MCP y acciones financieras aún no son ejecutores del piloto.

## Roadmap de ejecución

Estimación orientativa de dos o tres jornadas para un piloto personal, condicionada
a configuración del modelo, Windows y pruebas; no equivale a producto comercial.

| Orden | Trabajo | Criterio para darlo por terminado |
|---|---|---|
| 1 / este PR | Cola, catálogo, aprobaciones, nota/video, launcher y CI | Pruebas pasan; encargo aprobado produce un archivo real |
| 2 / jornada 1–2 | Hermes fijado + adaptador de propuestas estructuradas | Modelo propone; acciones fuera del esquema se rechazan; sin vías que eludan aprobación |
| 3 / jornada 2 | Kokoro español + faster-whisper y botón hablar | Audio real entra, se transcribe, propone y responde por voz en la PC |
| 4 / jornada 2–3 | UI simple, historial, cancelar y retomar al iniciar | Cerrar/reabrir conserva encargos; muestra resultado/error verificable |
| 5 / después del piloto | Catálogo instalable con versión, fuente y revisión | Consentimiento concreto instala una herramienta y se comprueba su funcionamiento |
| 6 | Browser y primer MCP (Blender o Home Assistant) | Una tarea representativa funciona con permisos mínimos y resultado verificable |
| 7 | Relay nube + móvil y tareas cuando PC está apagada | Emparejamiento autenticado, aislamiento por usuario, deduplicación y entrega al reconectar |
| 8 | Cobros, cuotas, ElevenLabs y actualizaciones firmadas | Medición de costes, límites aplicados y recuperación/rollback probado |

La base WhatsApp/n8n es otra vía existente que requiere sus pruebas y revisión
de restricciones del canal antes de publicitarla para un asistente general.
No depende de ella la aceptación del piloto local.
