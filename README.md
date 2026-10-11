# ARKOS Personal CEO OS

Asistente personal y de trabajo: conversar, revisar propuestas y seguir tareas
con aprobación humana. Proyecto de INPiensa / INB, impulsado por Jona Romero.

**Estado: piloto en desarrollo.** Las capacidades dependen de la rama y su evidencia
de aceptación. La interfaz se ha probado con respuestas sintéticas; la conexión
Hermes/Qwen real del centro de tareas sigue pendiente de aceptación en la PC.

## Qué está implementado

- Centro de tareas responsive: notas y recortes de video, revisión, aprobación
  explícita, ejecución y resultados. Los recortes requieren FFmpeg.
- Chat asíncrono mediante HermesBridge: historial de sesión, cancelación, errores
  y propuestas de notas. Crear una tarea no la aprueba ni la ejecuta.
- Tema neuronal, modo ligero y reducción de movimiento; actividad visual basada
  en estados observados, no telemetría continua del modelo.
- Servicio relay, agente y snapshot local de lectura. La vista remota conserva
  sus estados y no puede aprobar, ejecutar ni descargar resultados remotos.
- Launcher Windows con CheckOnly y selección de carpeta/puerto de prueba.

## Qué todavía no es un producto listo

| Capacidad | Estado |
|---|---|
| Hermes/Qwen en el chat | Adaptador implementado; aceptación con modelo real pendiente |
| Cloud para el centro de tareas | No implementado; [contrato y próximos pasos](docs/LOCAL_CLOUD_CONVERSATION.md) |
| Voz y chat de equipo | Pendientes en esta interfaz |
| Correo, calendario y WhatsApp de extremo a extremo | No acreditados como integraciones operativas del piloto |
| Relay productivo celular–PC | Código y pruebas; despliegue/aceptación real pendientes |
| Instalador para usuarios finales | Pendiente; el launcher aún requiere Python existente |
| Memoria conversacional persistente | Pendiente; el historial actual se pierde al reiniciar el servidor |

## Probar el centro local

Usar un checkout aislado y Python 3.11+ existente. En Windows, desde el repo:

```powershell
./scripts/Open-Arkos.ps1 -StateDirectory "$env:LOCALAPPDATA\ArkosTaskCenterTrial" -CheckOnly
./scripts/Open-Arkos.ps1 -StateDirectory "$env:LOCALAPPDATA\ArkosTaskCenterTrial"
```

Sin configuración Hermes la pantalla indica **Hermes por conectar**. No instala
modelos ni representa una conversación real. Ver requisitos y opciones en la
[guía del launcher](docs/task-center/GUIDED_LAUNCHER.md).
Para el recorrido sintético, comandos, cierre y límites, consultar la
[aceptación Windows](docs/task-center/CONVERSATION_ACCEPTANCE_2026-10-09.md).

## Documentación del piloto

- [Centro de tareas](docs/task-center/README.md)
- [Chat y propuestas](docs/task-center/CONVERSATION_HOME.md)
- [Puente Hermes](docs/HERMES_BRIDGE.md)
- [Local y Cloud: contrato común y aceptación pendiente](docs/LOCAL_CLOUD_CONVERSATION.md)
- [Entrada conversacional y diseño aplicado](docs/task-center/ASSISTANT_ENTRY_2026-10-10.md)
- [Contrato relay](docs/RELAY_CONTRACT.md)
- [Integración del lector](docs/task-center/RELAY_INTEGRATION.md)
- [Piloto de escritorio](docs/DESKTOP_PILOT.md)

## Infraestructura experimental anterior

El repositorio también conserva migraciones Supabase, workflows n8n y documentos
para WhatsApp y agentes empresariales. Su presencia no acredita despliegue,
seguridad ni funcionamiento actual. No son requisitos para abrir el centro local.
Ver [arquitectura](docs/ARCHITECTURE.md), [workflows](docs/N8N_WORKFLOWS.md) y
[reglas de seguridad](docs/SECURITY_RULES.md) antes de planificar su integración.

## Licencia y contribuciones

La licencia pública y las condiciones comerciales están pendientes de definición
y revisión. Este README no concede una licencia nueva ni cambia los derechos de
terceros. Las dependencias conservan sus condiciones y avisos correspondientes.
