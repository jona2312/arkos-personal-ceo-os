# Snapshot de lectura del relay para la pantalla (v1)

Estado: implementado en `arkos_relay/viewer.py` con pruebas sintéticas. **No desplegado.**
Lo produce un proceso de la PC (`agent view-sync`) que solo **lee** el relay. El Task
Center (PR #3) lo consume como archivo local. Ejemplo real con datos sintéticos:
[`examples/relay-snapshot.example.json`](examples/relay-snapshot.example.json).

## 1. Qué credencial permite leer la cola completa

| Credencial | Prefijo | Qué puede hacer | ¿Ve la cola completa? |
|---|---|---|---|
| Usuario (celular) | `aku_` | crear, aprobar, rechazar, cancelar, resolver, reintentar; ver **todas** sus tareas | Sí, de todos sus dispositivos |
| Dispositivo (agente) | `akd_` | `claim`, `heartbeat`, `start`, `complete`; leer **solo las tareas que reservó** | **No** |
| Lectura de pantalla (nueva) | `akr_` | `GET /v1/viewer/tasks` | Sí, pero solo las tareas de su usuario con `target_device_id` = ese dispositivo o `null` |

Decisiones:
- **No se amplía el token del dispositivo** ni se le da acceso de usuario: el agente
  sigue sin poder listar la cola.
- El `akr_` **lo autoriza el usuario**: `POST /v1/devices/{id}/viewer-codes` exige un
  token `aku_` y devuelve un código de 10 minutos y un solo uso. La PC lo canjea con
  `agent viewer-pair --code …`. Un dispositivo no puede emitirse su propia credencial
  de lectura (prueba `test_viewer_token_is_read_only_and_separate`).
- El `akr_` no sirve en ninguna ruta de usuario ni de agente (401). Se revoca solo con
  `POST /v1/devices/{id}/viewer-tokens/revoke`, o junto con el dispositivo.
- Se guarda con DPAPI en `…\ArkosRelayAgent\viewer.token`, separado de `device.token`.
  El proceso `view-sync` **nunca carga** `device.token`, el diario ni el ejecutor.
- Las tareas dirigidas a **otra** PC del mismo usuario no se muestran. Verlas requiere
  el token de usuario, a propósito.

Leer aplica los vencimientos por tiempo del relay (lease o aprobación vencida), igual
que cualquier otra llamada. Nunca aprueba, reserva, consume una aprobación ni ejecuta.

## 2. Sincronización

- **Incremental:** `GET /v1/viewer/tasks?after_version=N&limit≤500` devuelve
  `{tasks, has_more, head_version}` en orden de `version`. El cursor se guarda en
  `viewer\viewer.sqlite3`.
- **Reconciliación completa:** en la primera sincronización de cada proceso y cada
  10 minutos. Si `head_version` es menor que el cursor (relay restaurado), se hace en
  el acto. Las páginas se juntan en memoria y reemplazan el espejo en una sola
  transacción; un corte a mitad conserva el espejo anterior.
- **Sin red o con un error:** el espejo y el snapshot anteriores se conservan; se
  actualizan `last_attempt_at` y `last_error`.
- **Reinicio:** el espejo SQLite y el snapshot persisten, y el snapshot se regenera aun
  sin conexión.

## 3. Archivo `relay-snapshot.json`

Ubicación: `%LOCALAPPDATA%\ArkosRelayAgent\viewer\relay-snapshot.json`. UTF-8 JSON.
Todas las fechas son **segundos Unix UTC** (float), como en el Task Center.

### Raíz

| Campo | Tipo | Nota |
|---|---|---|
| `schema` | `"arkos.relay.snapshot"` | Rechazar si difiere |
| `schema_version` | `1` | Rechazar versiones desconocidas |
| `source` | `"relay"` | |
| `generated_at` | number | Cuándo se escribió el archivo |
| `device_id` | string | PC para la que se generó |
| `sync.status` | `fresh` \| `stale` \| `offline` \| `never_synced` \| `unauthorized` | Valor al escribir; **recalcular** al leer |
| `sync.last_success_at` | number \| null | Última sincronización correcta |
| `sync.last_attempt_at` | number | |
| `sync.last_error` | null \| `offline` \| `unauthorized` \| `http_<código>` | Nunca incluye mensajes del servidor ni secretos |
| `sync.stale_after_seconds` | number (120) | |
| `sync.cursor` | integer | Diagnóstico |
| `limits` | `{max_tasks: 500, max_bytes: 1048576, preview_chars: 280}` | |
| `truncated` | boolean | `true` si se omitieron tareas terminadas antiguas |
| `task_count` | integer | Igual a `tasks.length` |
| `tasks` | array | Activas primero, luego por `updated_at` descendente |

### Tarjeta (`tasks[]`)

| Campo | Tipo | Nota |
|---|---|---|
| `origin` | `"relay"` | Distingue estas tarjetas de las tareas locales del Task Center |
| `remote_id` | `tsk_…` | ID del relay. **No** es un ID de `arkos_pilot.Queue` |
| `version` | integer | Cambia con cada transición; usar `remote_id:version` como clave de aviso |
| `action` | `note.create` \| `document.create` \| `video.clip` | |
| `state` | `awaiting_approval`, `approved`, `claimed`, `running`, `succeeded`, `failed`, `unknown`, `rejected`, `cancelled` | Los 9 estados del relay |
| `state_reason` | string \| null | Por ejemplo `approval_expired`, `lease_expired_during_execution`, o el mensaje del resultado |
| `target_device_id` | string \| null | `null` = cualquier PC del usuario |
| `for_this_device` | boolean | |
| `created_at`, `updated_at` | number | |
| `approval_expires_at` | number \| null | Solo en `approved` y `claimed` |
| `attempts` | integer | Cuántas veces fue reservada |
| `retry_of` | `tsk_…` \| null | |
| `payload_sha256` | hex64 | Huella canónica del relay; sirve para mostrar un prefijo |
| `summary` | object | Notas y documentos: `title`, `preview` (≤ 280). Recortes: `title`, `root`, `path`, `start_ms`, `duration_ms` |
| `result` | null \| `{message (≤ 500), output?: {name, sha256, bytes, source_sha256?}}` | |
| `artifact.status` | `none` \| `available` \| `missing` \| `mismatch` \| `unknown` | Ver abajo |
| `artifact.relative_path` | string | Relativo a `…\ArkosRelayAgent\outputs\` (`notes/…`, `documents/…`, `clips/…`) |
| `artifact.sha256`, `artifact.bytes` | | Del resultado del relay |

`artifact.status`:
- `available`: el archivo existe y su tamaño coincide. El lector **debe verificar
  `sha256` antes de abrirlo o servirlo**.
- `missing`: no está en esta PC (se ejecutó en otra o se borró).
- `mismatch`: el tamaño difiere (archivo alterado).
- `none`: la tarea no tiene salida.

Nunca contiene tokens (`aku_`/`akd_`/`akr_`), `lease_id`, `client_request_id`, el texto
completo de notas largas ni rutas absolutas.

## 4. Límites y escritura atómica

- Como máximo 500 tareas y 1 MiB. Al exceder, se omiten primero las terminadas más
  antiguas y se marca `truncated`. Las tareas activas (`awaiting_approval`, `approved`,
  `claimed`, `running`, `unknown`) tienen prioridad.
- Escritura: archivo temporal `.snapshot-*.tmp` en la **misma carpeta**, `fsync` y
  `os.replace`. Un lector ve el archivo anterior o el nuevo, nunca uno a medias.
- En Windows, un lector con el archivo abierto bloquea el reemplazo. Se reintenta
  5 veces cada 50 ms; si falla, queda el snapshot anterior y el temporal se borra. **El
  lector debe abrir, leer completo y cerrar enseguida.**

## 5. Cómo debe leerlo ARKOS (Task Center)

1. Si el tamaño supera 1 MiB, si `schema` o `schema_version` no coinciden o si el JSON
   es inválido, mostrar "Sincronización no disponible" y no usar los datos.
2. Recalcular la frescura con el reloj propio: si `now - sync.last_success_at >
   stale_after_seconds`, mostrar "Datos desactualizados (última sincronización: …)".
   Mostrar `offline`, `unauthorized` y `never_synced` tal cual. La implementación de
   referencia es `arkos_relay.viewer.read_snapshot`.
3. Mostrar las tarjetas en una sección **"Del celular"**, sin los botones de *aprobar*
   y *ejecutar* de la cola local. Nunca insertar en `arkos_pilot.Queue` ni llamar
   `/api/tasks/{id}/approve|run` con un `remote_id`.
4. Avisos: clave `relay:<remote_id>:<state>:<version>`. Así no colisionan con los
   avisos locales `id:state:updated`.
5. Abrir un resultado solo si `artifact.status == "available"` y el SHA-256 del
   archivo coincide con `artifact.sha256`.
6. Texto con `textContent`, nunca HTML. `summary` y `result.message` pueden traer
   cualquier carácter.

## 6. Operación (sin automatizar)

```powershell
# En el celular (token de usuario): emitir el código de lectura para la PC
#   POST /v1/devices/{device_id}/viewer-codes  -> {"code":"XXXX-XXXX-XXXX"}
./scripts/Start-ArkosAgent.ps1 viewer-pair --code XXXX-XXXX-XXXX
./scripts/Start-ArkosAgent.ps1 view-sync --once        # o view-sync --interval 30
```

No crea tareas programadas ni servicios. Arrancarlo al iniciar sesión queda como paso
manual pendiente de aprobación de Jona.

## 7. Limitaciones

- **El relay guarda texto plano**, y el espejo local `viewer.sqlite3` también contiene
  el texto completo de las tareas. Ambos sin cifrar, más allá del perfil de Windows.
- **WhatsApp sigue sin emisor.**
- La pantalla no puede aprobar todavía. Hacerlo requeriría su propio token `aku_`
  (paso 3 de la alineación), no el `akr_`.
