# Contexto y tareas cotidianas del piloto

La personalidad versionada está en `prompts/arkos_desktop_soul.md`; el contexto
de este despliegue, en `prompts/arkos_pilot_runtime_context.md`. La instalación
de Jonathan conserva su perfil `arkos-pilot`, STT local y modelo Qwen local
reemplazable. Elena/Edge es la base gratuita preparada. La prueba posterior de
ElevenLabs quedó seleccionada por pedido de Jonathan. Su API inicialmente
devolvió `payment_issue`; después de que Jonathan informó haber resuelto el
pago, generó audio real y él confirmó el saludo automático por el Admiral.
No hay un router multiagente conectado.

`config/hermes-daily-tasks.json` contiene los comandos de prueba y sus resultados
esperados. Es un catálogo de pruebas, no un ejecutor que habilita herramientas.

## Qué se puede pedir ahora

| Pedido | Resultado esperado |
|---|---|
| «¿Cómo me llamo y qué relación tengo con ARKOS?» | Jonathan (Jona), creador y operador |
| «Creá plan-del-dia.md con tres prioridades de ejemplo» | Archivo en el workspace |
| «Creá compras.md con pan, leche y frutas» | Lista local, sin compras |
| «Anotá una idea en ideas-arkos.md» | Nota verificable |
| «Redactá una invitación en correo-borrador.md, sin enviarla» | Borrador local |
| «Leé plan-del-dia.md y resumilo» | Resumen del contenido real |
| Dar una fecha, corregirla y preguntar cuál quedó | Usar la última corrección |

Escribir una agenda no crea eventos; redactar un correo no lo envía. El workspace
es `D:/ARKOS/ArkosTrial`; el repositorio es
`D:/ARKOS/repos/arkos-personal-ceo-os`. Hermes no debe confundir esas ubicaciones
ni prometer commits por haber creado un archivo. Codex mantiene el repositorio.

Para ejecutar automáticamente una sesión de pruebas mediante la CLI real de
Hermes, conservando historial y verificando los archivos creados:

```powershell
& $hermesPython scripts/Run-HermesDailyTrial.py --hermes-source D:/ARKOS/hermes/hermes-agent --profile-home D:/ARKOS/hermes/profiles/arkos-pilot --workspace D:/ARKOS/ArkosTrial --report docs/trial-evidence/2026-10-07/daily-cli-trial.json
```

Cada ejecución crea una subcarpeta y sesión nuevas. Usa archivos para pasar los
prompts, tiene límites de tiempo/turnos y deja JSON con respuestas, contenido y
hashes. No habilita conexiones externas. Los casos de conversación requieren
revisión del contenido; recibir una respuesta no equivale a superar el caso.

## Próximas conexiones

Prioridad elegida por Jona: terminar conversación y demora antes de habilitar
navegación. El siguiente incremento autorizado es navegación local gratuita y
una prueba de YouTube; en este incremento sigue pendiente. Correo, calendario,
mensajería, alarmas y control general de PC tampoco están conectados.
No se consideran habilitados por aparecer en este documento.

Una autorización por voz no instala una herramienta ausente. Las aprobaciones
del runtime deben comprobarse por separado. Las claves se introducen únicamente
en campos seguros de la configuración verificada, nunca en el chat ni en Git.
La política sigue siendo cero compras y suscripciones. Jonathan autorizó consumo
de créditos para probar ElevenLabs; esa excepción no autoriza pagar facturas.

## Prueba opcional de ElevenLabs

Instalar la extensión soportada con `hermes pm install --extra tts-premium` en
el entorno privado de Hermes. Reiniciar Desktop: los procesos abiertos conservan
el entorno anterior. Configurar únicamente el perfil de prueba:

```powershell
& $hermesPython scripts/Configure-HermesElevenLabsTrial.py --profile-home D:/ARKOS/hermes/profiles/arkos-pilot --voice-id <ID_AUTORIZADO> --allow-credit-use
```

La clave se solicita sin eco; se guarda en `.env` del perfil. Configuración y
credenciales anteriores quedan respaldadas junto al perfil, fuera de Git. El
comando devuelve una ruta `restore_state`; conservarla. No pegar claves en el
chat ni incluirlas en comandos. La extensión no compra planes.

Para una muestra aislada adicional, solamente si se autoriza ese consumo:

```powershell
& $hermesPython scripts/Test-HermesElevenLabs.py --hermes-source D:/ARKOS/hermes/hermes-agent --profile-home D:/ARKOS/hermes/profiles/arkos-pilot --workspace D:/ARKOS/ArkosTrial --voice-id <ID_AUTORIZADO> --report <REPORTE_JSON> --allow-credit-use
```

El proveedor configurado debe ser `elevenlabs`: el argumento `provider` de la
herramienta de Hermes no sustituye un proveedor diferente del perfil. Este script
verifica generación, no reproducción física ni respuestas automáticas de Desktop.
Para volver a la configuración anterior cuando Jonathan lo solicite:

```powershell
& $hermesPython scripts/Configure-HermesElevenLabsTrial.py --profile-home D:/ARKOS/hermes/profiles/arkos-pilot --restore <RUTA_RESTORE_STATE>
```

En esta PC la extensión instalada usa nombres de módulos que superan MAX_PATH.
Se conserva el parche aplicado a Hermes en
`trial-evidence/2026-10-07/hermes-windows-long-paths.diff`, sobre el commit
`489c1ac298f8ed13ccd688c97e4097f161046c0b`. Activa rutas extendidas de Windows
para importar dependencias; no cambia políticas del sistema. Una actualización
de Hermes puede requerir revisar ese parche.

## Aplicar el contexto sin perder lo anterior

Usar el Python del entorno propio de Hermes. Previsualizar y luego aplicar:

```powershell
& $hermesPython scripts/Sync-ArkosHermesContext.py --profile-home D:/ARKOS/hermes/profiles/arkos-pilot --workspace D:/ARKOS/ArkosTrial
& $hermesPython scripts/Sync-ArkosHermesContext.py --profile-home D:/ARKOS/hermes/profiles/arkos-pilot --workspace D:/ARKOS/ArkosTrial --apply
```

El script reemplaza SOUL del perfil seleccionado con la personalidad y contexto
del repositorio; guarda copia exacta del anterior junto al perfil. Rechaza otros
nombres de perfil, no modifica credenciales ni permisos, y una segunda ejecución
idéntica no crea otro backup. Las sesiones nuevas cargan el contexto actualizado;
las antiguas conservan su historial y pueden seguir repitiendo datos obsoletos.

## Medición reproducible sin hablar al micrófono

Con Desktop y el modelo local ya abiertos:

```powershell
& $hermesPython scripts/Test-HermesVoicePipeline.py --hermes-source D:/ARKOS/hermes/hermes-agent --profile-home D:/ARKOS/hermes/profiles/arkos-pilot --workspace D:/ARKOS/ArkosTrial --report docs/trial-evidence/2026-10-07/voice-pipeline-five-trials.json
```

El script genera cinco WAV sintéticos con Piper. Cada WAV pasa por el endpoint
real de transcripción de Desktop, el modelo llama.cpp local y el endpoint real
de síntesis de Desktop. Conserva el historial de la reunión entre los tres
primeros turnos, guarda transcripciones/respuestas/audio y calcula medianas.
Solo permite modelo autenticado de la instalación local verificada, STT local
y voz Edge/Piper; no exporta los tokens internos. No ejecuta herramientas del
modelo ni cambia sus permisos. No ejecutar otras generaciones simultáneas si
se quiere comparar latencias.

La métrica termina cuando llega **el audio completo**, y comienza al subir un
WAV que ya está grabado. Excluye micrófono, detección de silencio, orquestación
del chat nativo, inicio de reproducción y parlantes. No sustituye la mediana de
cinco turnos humanos desde fin de habla hasta primer audio audible ni demuestra
interrupciones. El modo del modelo de este benchmark desactiva el razonamiento
extenso y limita la respuesta a 256 tokens; esa condición figura en la evidencia.

La aceptación real y sus limitaciones están en
`HERMES_DESKTOP_TRIAL_RESULTS_2026-10-07.md`.
