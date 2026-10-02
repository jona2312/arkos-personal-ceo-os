# Primera prueba: ARKOS sobre Hermes Desktop

## Resultado esperado

Una aplicación con pantalla de chat, voz en español y actividad de herramientas
visible. Jona dicta un objetivo, el asistente propone, ejecuta una acción permitida
y entrega un archivo verificable. Priorizar esta experiencia antes de construir
una UI propia. La cola local del PR sigue siendo un componente independiente.

## Evidencia al 2 de octubre de 2026

- Fuente: https://hermes-agent.nousresearch.com/ y documentación oficial.
- Release de código observada: `v2026.9.24`, commit
  `f97608f178d1ffeca59860195ab7da295f7c8e5f`. GitHub API no devuelve assets
  binarios adjuntos a esa release; los archivos de código no son un instalador.
- El botón Windows del sitio entrega `Hermes-Setup.exe?build=10c6188de188`.
  Se leyeron sus 7.946.048 bytes y se calculó SHA-256 en el manifiesto.
  No se ejecutó, ni se validó su firma Authenticode en este entorno Linux.
- La documentación distingue un bundle completo MSIX de un bootstrap que
  descarga código y construye la app. El enlace observado es un bootstrap.
  No afirmar que el commit de referencia fija todo lo que descarga ese EXE.
- Desktop documenta chat, voz, actividad de herramientas, memoria, perfiles,
  archivos y HUD. Deben verificarse en la versión realmente instalada.
- El piloto Python anterior tuvo CI Windows/Linux verde. Eso no verifica Hermes,
  el micrófono, los modelos ni la PC de Jona.

Referencias: [instalación](https://hermes-agent.nousresearch.com/docs/getting-started/installation/),
[Desktop](https://hermes-agent.nousresearch.com/docs/user-guide/desktop/),
[voz](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode),
[perfiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles/).

## Orden de instalación en la PC grande

1. Usar un checkout del branch `feat/arkos-desktop-pilot`. No cambiar proyectos
   existentes para realizar esta prueba.
2. Ejecutar `./scripts/Get-ArkosDesktopReadiness.ps1`. Registrar Windows, RAM,
   GPU, presencia de Hermes/Ollama y perfil existente. No exportar credenciales.
3. Si Hermes ya está instalado, comprobar versión y método de instalación;
   preservar su configuración. Evitar otra instalación duplicada.
4. Si falta, `./scripts/Get-HermesDesktopInstaller.ps1` descarga el bootstrap
   observado, exige hash/tamaño coincidentes y firma válida, y muestra el firmante.
   No lo ejecuta. Confirmar que el firmante corresponde al distribuidor oficial.
   Si cambia el archivo o no hay firma válida, registrar el resultado y revisar
   la alternativa oficial; no desactivar validaciones ni políticas de Windows.
5. Inspeccionar el comportamiento del bootstrap y ejecutar la instalación con
   el usuario normal. Registrar la versión instalada y las dependencias nuevas.
   No instalar paquetes Python dentro de un bundle firmado. No modificar el
   runtime de Codex, n8n ni el `.venv` del piloto Python.
6. Crear un perfil vacío `arkos-pilot` desde Desktop. Si la CLI está disponible:
   `hermes profile create arkos-pilot` y `hermes -p arkos-pilot setup`.
   No usar clone: evitar importar memorias/credenciales/canales existentes.
7. Usar `prompts/arkos_desktop_soul.md` como personalidad del perfil, mediante
   el editor/configuración soportados por la versión instalada. No adivinar
   rutas internas ni sobrescribir otros archivos SOUL.md.
8. Configurar el proveedor disponible mediante la UI. No comprar una suscripción
   automáticamente. Mantener claves en el almacén del perfil, fuera del repo.
   Si no hay acceso de IA utilizable, dejar instalación lista e indicar exactamente
   qué configuración falta. No presentar ChatGPT pago como crédito API incluido.
9. Crear una carpeta nueva `ArkosTrial` bajo Documentos. Configurarla como workspace
   y comprobar que los permisos técnicos limitan el acceso. El prompt solo no
   asegura aislamiento. No habilitar todavía domótica ni canales externos.
10. Probar chat, luego voz, luego una herramienta real. Abrir Desktop y seleccionar
    `arkos-pilot`; no asumir que un flag CLI selecciona el perfil de la GUI.

## Voz para arrancar

- Escucha: Faster-Whisper local, idioma español; usar un tamaño acorde a la PC
  y medir transcripción de nombres/números. Verificar soporte de la arquitectura.
- Respuesta: empezar con un proveedor ya soportado por la versión instalada.
  La documentación enumera Piper y ElevenLabs; seleccionar una voz española
  compatible y revisar la licencia de sus pesos. Si Piper no está disponible o
  falla, registrar el bloqueo; no declarar voz local funcionando por detectar un paquete.
- Edge TTS puede servir para una prueba conectada sin API key, pero utiliza
  un servicio de red. No anunciarlo como voz offline o garantía para uso comercial.
- ElevenLabs: opcional si existe clave y voz autorizada; registrar consumo.
  No clonar voces ajenas ni contratar un plan durante la prueba.
- Kokoro queda como alternativa si aporta mejora real; no hace falta integrar
  un motor de voz nuevo antes de probar la conversación ya incluida.

## Prueba de aceptación (sin completar hasta ejecutar en la PC)

| Caso | Pedido / operación | Evidencia requerida |
|---|---|---|
| Texto | «Organizá mi trabajo en tres pasos y proponé una mejora» | Respuesta útil en español, propuesta y pasos visibles |
| Voz | Hablar 3 turnos con corrección de una fecha | Transcripción, contexto corregido y voz entendible |
| Interrumpir | Interrumpir una respuesta y decir «resumilo» | Corta la reproducción y responde al nuevo pedido |
| Acción | «Creá un borrador Markdown en esta carpeta» | Archivo real; contenido correcto; actividad visible |
| Proactividad | «Quiero recortar un video» con herramienta ausente | Detecta ausencia; propone herramienta y pide permiso concreto |
| Recuperación | Cerrar, reabrir y retomar la conversación | Misma sesión recuperada, sin inventar acciones pendientes completadas |
| Permisos | Pedir envío/borrado fuera de la carpeta de prueba | Bloqueo o revisión antes del efecto; verificar política real |

Medir tiempo desde fin de habla a primera respuesta audible y tiempo total por
tarea. Registrar mediana de cinco turnos, errores y entorno. Objetivo provisional:
primera respuesta audible en 3 segundos para pedidos simples; no es un resultado
medido ni una promesa comercial. Priorizar conversación por streaming y evitar
esperar a que se genere un párrafo entero antes de comenzar a hablar.

Si falla conversación o instalación, probar OpenClaw Windows Hub con los mismos
casos, en perfil/workspace separado. No combinar ambos motores durante esta prueba.

## Texto listo para Codex en la PC

> Continuá la primera prueba personal de ARKOS en Windows usando el PR #1 de
> jona2312/arkos-personal-ceo-os, branch feat/arkos-desktop-pilot. Leé
> docs/HERMES_DESKTOP_TRIAL.md y los scripts antes de ejecutar. Revisa el estado
> del checkout y preserva cambios existentes. Ejecuta el diagnóstico, comprueba
> si Hermes ya está instalado y, si falta, descarga/verifica el instalador oficial
> conforme al manifiesto y revisa su comportamiento antes de instalarlo. Configura
> un perfil nuevo arkos-pilot y una carpeta de prueba. Usa la personalidad ARKOS
> del repo. Configura el acceso de IA disponible sin exponer secretos ni comprar
> planes. Prueba primero texto, luego escucha/voz en español y una acción real
> que cree un archivo. Comprueba interrupciones y recuperación de sesión.
> Registra versión, dependencias, cinco latencias, resultados y bloqueos. Deja
> la aplicación abierta para que Jona pruebe la conversación. No declares éxito
> de audio sin comprobar audio real. No modifiques n8n/Supabase ni otros proyectos,
> no habilites canales externos y no mergees el PR. Si una operación requiere
> acceso que no tenés, deja el punto preparado y explica qué falta.
