# Relay (PR #2) ↔ Task Center (PR #3): diferencias y conexión

Revisado: PR #3 `codex/arkos-task-center` en HEAD
`92cb4625e39e8ed984e62a2fd45c9892cae51980`, incluido
`docs/task-center/SYNC_CONTRACT_DRAFT.md` v0.1. Este documento no modifica esa rama.
Ambos PR están apilados sobre #1 y no tocan los mismos archivos. #3 solo cambia
`Queue.run_next(task_id=None)`; el relay no usa `Queue`, solo `core.execute` y
`core.file_digest`, que no cambian.

### Cambios de #3 entre `15bf2e8` y `92cb462`

- Solo cambió la UI (`app.js`, `index.html`, `style.css`), la documentación
  (`UI_ROADMAP.md`, `README.md`, `VALIDATION.md`), las capturas y la prueba de
  navegador. **No cambiaron** `core.py`, `task_center.py`, la API local ni
  `SYNC_CONTRACT_DRAFT.md`, así que las diferencias de contrato de §1 siguen vigentes.
- **Nuevo:** columnas separadas *Por revisar / En cola / Ejecutando / Terminadas*, y una
  bandeja de avisos personal con clave `id:state:updated` y "visto" guardado solo en el
  navegador (máximo 1000).
- `UI_ROADMAP.md` pone como prioridad 1 "Conectar UI al relay del PR #2" sin duplicar
  aprobaciones, y repite que el relay guarda texto plano.
- Los avisos remotos necesitan una clave propia (`relay:<remote_id>:<state>:<version>`)
  para no chocar con los locales. Las columnas del relay se mapean así:

  | Columna | Estados del relay |
  |---|---|
  | Por revisar | `awaiting_approval`, `unknown` |
  | En cola | `approved` |
  | Ejecutando | `claimed`, `running` |
  | Terminadas | `succeeded`, `failed`, `rejected`, `cancelled` |

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

1. **Espejo de solo lectura de toda la cola visible (implementado en el PR apilado sobre #2).**
   - *Corrección de la propuesta anterior:* leer `journal.sqlite3` no alcanza. El diario
     solo tiene tareas que el agente ya reservó; no ve las pendientes de aprobación, las
     aprobadas sin reservar ni las canceladas antes de llegar a la PC.
   - En su lugar, `agent view-sync` usa una **credencial de lectura `akr_` emitida por
     el usuario**, sin ampliar el token del dispositivo. Escribe
     `ArkosRelayAgent\viewer\relay-snapshot.json`; contrato en
     [RELAY_SNAPSHOT_CONTRACT.md](RELAY_SNAPSHOT_CONTRACT.md).
   - La pantalla lee ese archivo con su propio reloj para detectar datos
     desactualizados. Muestra la sección "Del celular" con estado, destino, fechas,
     resultado y disponibilidad del archivo.
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
- Lector del snapshot en #3: rechaza un esquema desconocido o un archivo de más de 1 MiB,
  marca "desactualizado" con su propio reloj y no llama a ninguna ruta de
  aprobación o ejecución al renderizar.

Ya cubiertas en el relay (`tests/test_relay_viewer.py`): aislamiento entre usuarios y
entre PCs del mismo usuario; tareas pendientes no entregadas; sincronización
incremental y paginada; reinicio y desconexión; backup restaurado; snapshot
desactualizado; ausencia de secretos; límites de tamaño; escritura atómica; leer
sin ejecutar.

## 3. Observaciones sobre #3, sin cambios aplicados

- `Start-ArkosTaskCenter.ps1 -StateDirectory 'D:\ARKOS\TaskCenterTrial'` ubica el estado
  dentro de `D:\ARKOS`. El agente del relay usa `%LOCALAPPDATA%\ArkosRelayAgent` para
  no tocar esa instalación. Conviene alinear la convención.
- La salida JSON de `arkos_pilot` usa `ensure_ascii=False`. En una consola o pipe cp1252,
  un texto con caracteres fuera de esa página (por ejemplo emoji) puede fallar como
  falló `arkos_relay --help`. El relay ya tiene la corrección (`safe_console`) y su
  prueba de regresión.
