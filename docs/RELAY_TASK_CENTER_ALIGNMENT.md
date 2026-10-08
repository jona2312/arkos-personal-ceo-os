# Relay (PR #2) ↔ Task Center (PR #3): diferencias y conexión

Revisado: PR #3 `codex/arkos-task-center` en HEAD `15bf2e8`, incluido
`docs/task-center/SYNC_CONTRACT_DRAFT.md` v0.1. Este documento no modifica esa rama.
Ambos PR están apilados sobre #1 y no tocan los mismos archivos. #3 solo cambia
`Queue.run_next(task_id=None)`; el relay no usa `Queue`, solo `core.execute` y
`core.file_digest`, que no cambian.

## 1. Diferencias

| Tema | Task Center local (#3) | Relay (#2) | Consecuencia |
|---|---|---|---|
| **Acciones** | `note {text}`, `clip {source: ruta absoluta, source_sha256, start, duration}` (segundos float) | `note.create {text}`, `document.create {filename, text}`, `video.clip {root, path relativa, start_ms, duration_ms, source_sha256?}` | No son intercambiables. El relay nunca envía rutas absolutas: la PC traduce `root` con carpetas autorizadas localmente. |
| **Estados** | `awaiting_approval, queued, running, completed, blocked, cancelled` | `awaiting_approval, approved, claimed, running, succeeded, failed, unknown, rejected, cancelled` | `blocked` mezcla vencida, error e incierto. El relay los separa: vuelve a `awaiting_approval` (`state_reason=approval_expired`), `failed` (sin efecto) o `unknown`. El `needs_review` del borrador equivale a `unknown`. |
| **Huella** | `sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False))`: separadores con espacios, floats, sin destino ni versión | `sha256(canonical({v, action, params, target_device_id}))`: compacta, solo enteros, liga dispositivo y versión de contrato | Una huella local nunca valida una tarea remota ni a la inversa. Hay que mantener dos namespaces. |
| **Aprobación** | `approve(id, fingerprint, hours≤24)` en SQLite local; se puede reaprobar desde `blocked` | Registro `apr_…` ligado a `(task_id, payload_sha256)`, ≤ 24 h, consumido una vez en `start` | Si una tarea remota se aprueba también en local, existen dos autoridades. Ver §2. |
| **Identificadores** | `id` = UUID hex sin prefijo; sin usuario ni dispositivo | `usr_…`, `dev_…`, `tsk_…`, `apr_…`, `lse_…`; `client_request_id` para idempotencia; `version` monotónica | El mapa `(user, device, remote_task_id) → local_task_id` que pide el borrador no hace falta si el agente es el único ejecutor (opción B): su diario usa `tsk_…` como clave. |
| **Resultados** | `result` = ruta local o texto del error; `GET /api/tasks/{id}/artifact` descarga el archivo | `{message, output: {name, sha256, bytes, source_sha256?}}`, sin rutas ni contenido | El relay **no sube artefactos**: el celular ve metadatos, no el archivo. Eso es lo que pide el borrador ("opaque artifact IDs, ownership, size limits"), pero falta implementarlo. |
| **Autenticación** | `X-Arkos-Key` efímera + Host/Origin, solo loopback | Bearer `aku_`/`akd_` hasheados; vinculación y revocación de dispositivos | Coherentes: la clave loopback nunca sale de la PC. |
| **Cancelación** | Antes de ejecutar | En `awaiting_approval`, `approved` o `claimed`; `start` la rechaza después | Coincide con el borrador: definitiva antes del efecto. |
| **Privacidad** | El borrador exige decidir E2EE antes de desplegar | **El relay guarda y transporta texto plano** (TLS en tránsito, sin E2EE) | Coinciden en que no hay E2EE. No prometerlo. |

El relay ya cubre estos requisitos del borrador: dueño derivado de la credencial,
vinculación de un solo uso, revocación, conexión saliente, idempotencia de envío,
entrega y resultado, leases, `unknown` sin reintento ciego y sincronización por cursor.

Falta en el relay respecto del borrador:
- **Artefactos:** subida, ID opaco, límites de tamaño y vencimiento.
- **Conectividad:** una señal separada de la PC; hoy solo existe `devices.last_seen_at`.
- **Versión de esquema:** el relay la publica en `/healthz` y en la huella (`v`), no por mensaje.

## 2. Cómo conectar la pantalla sin duplicar aprobaciones ni ejecuciones

Regla: **una sola autoridad de aprobación (el relay) y un solo ejecutor por tarea
remota (el agente)**. La cola local de #3 sigue siendo autoridad únicamente para las
tareas creadas en la PC y marcadas como "solo esta PC".

| Opción | Cómo funciona | Riesgo | Veredicto |
|---|---|---|---|
| A. Proyectar las tareas remotas en `Queue` local | El agente inserta la tarea en `tasks` local con la aprobación sintetizada | Dos aprobaciones, porque la UI puede reaprobar `blocked` y relanzar. Dos ejecutores: el worker de #3 y el agente. | **No** |
| **B. Pantalla como espejo y luego como cliente del relay** | Las tareas remotas se ven en la pantalla, pero se aprueban y ejecutan solo vía relay + agente | Hay que enseñar dos orígenes en la UI | **Recomendada** |

### Pasos (B)

1. **Espejo de solo lectura (sin credenciales nuevas).**
   - El agente expone su estado a la pantalla por un archivo o un endpoint loopback del
     Task Center que lea `ArkosRelayAgent\journal.sqlite3` y `agent.json` en modo
     `?mode=ro`.
   - La pantalla muestra una sección "Del celular" con estado, fase y resultado.
   - Sin botones de aprobar ni ejecutar para esas tareas.
2. **Etiquetado de origen.**
   - Cada tarjeta lleva `origen: local | relay`.
   - Las tareas `relay` no aparecen en `/api/tasks` locales ni pueden recibir `run`.
   - Esto evita la doble ejecución sin tocar `Queue`.
3. **Aprobar desde la pantalla (opcional, después).**
   - La pantalla actúa como un cliente más del relay, igual que el celular, con un token
     de usuario propio (`issue-token --label pc-ui`) guardado con DPAPI.
   - Recalcula la huella canónica de lo que muestra y llama a `POST /v1/tasks/{id}/approve`.
   - La aprobación sigue siendo la única del relay; el agente la consume una vez en `start`.
4. **Mapeo de estados en la UI.**

   | Relay | Etiqueta |
   |---|---|
   | `awaiting_approval` | Por aprobar |
   | `approved` | En cola (esperando PC si `last_seen_at` es antiguo) |
   | `claimed` / `running` | En ejecución |
   | `succeeded` | Completada |
   | `failed` | Falló sin efecto |
   | `unknown` | Necesita revisión: botones *Resolver* y *Reintentar* (este último con confirmación de posible duplicado) |
   | `rejected` / `cancelled` | Cerrada |

5. **Resultados.**
   - En la PC, la pantalla abre el archivo local desde `ArkosRelayAgent\outputs\…`,
     verificando `sha256`.
   - En el celular, solo metadatos hasta que exista una política de artefactos.
6. **Unificar más adelante (fuera del piloto).**
   - Que las tareas creadas en la pantalla también pasen por el relay (`channel=pc-ui`).
   - Así queda un solo registro canónico y la cola local se retira para tareas
     compartidas.

### Pruebas a agregar cuando se conecte

- Una tarea `relay` no se puede aprobar ni ejecutar desde `/api/tasks/{id}/approve|run`
  locales (404/409).
- Ejecutar el agente y el worker de #3 a la vez produce exactamente un artefacto por
  `tsk_…`.
- Aprobar desde la pantalla con una huella recalculada distinta da 409
  `payload_mismatch`.
- Vector de huella común en JS (`test_digest_golden_vector`).

## 3. Observaciones sobre #3, sin cambios aplicados

- `Start-ArkosTaskCenter.ps1 -StateDirectory 'D:\ARKOS\TaskCenterTrial'` ubica el estado
  dentro de `D:\ARKOS`. El agente del relay usa `%LOCALAPPDATA%\ArkosRelayAgent` para
  no tocar esa instalación. Conviene alinear la convención.
- La salida JSON de `arkos_pilot` usa `ensure_ascii=False`. En una consola o pipe cp1252,
  un texto con caracteres fuera de esa página (por ejemplo emoji) puede fallar como
  falló `arkos_relay --help`. El relay ya tiene la corrección (`safe_console`) y su
  prueba de regresión.
