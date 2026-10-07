# ARKOS relay: celular → cola persistente → PC Windows

Objetivo: Jona deja una tarea desde el celular aunque la PC esté apagada. Al iniciar
sesión en Windows, el agente ARKOS se conecta **saliendo** hacia el relay, recupera
las tareas aprobadas, las ejecuta dentro de una lista cerrada y devuelve estado y
resultado. La PC no abre puertos; Hermes y la terminal no se exponen.

Estado: código y pruebas con datos sintéticos. **No desplegado.**

```
Celular / WhatsApp ──HTTPS──▶ Relay (API + SQLite) ◀──HTTPS saliente── Agente Windows
   crea, aprueba,             cola, aprobaciones,          claim → start → ejecuta
   consulta estado            leases, auditoría            → complete (con diario local)
```

## 1. Entidades del contrato

| Entidad | Campos clave | Notas |
|---|---|---|
| Usuario | `user_id` (`usr_…`) | Token de usuario `aku_…` (Bearer), guardado solo como SHA-256. |
| Dispositivo | `device_id` (`dev_…`), `name`, `last_seen_at`, `revoked_at` | Token `akd_…` emitido una sola vez al vincular; revocable. |
| Código de vinculación | 12 caracteres `XXXX-XXXX-XXXX`, 10 min | Un solo uso; 10 fallos por IP cada 10 min → 429. |
| Tarea | `id` (`tsk_…`), `client_request_id`, `action`, `params`, `target_device_id`, `payload_sha256`, `state`, `state_reason`, `lease_id`, `attempts`, `result`, `version` | `UNIQUE(user_id, client_request_id)` = deduplicación. |
| Aprobación | `id` (`apr_…`), `task_id`, `payload_sha256`, `expires_at` (≤ 24 h), `consumed_at`, `revoked_at` | De un solo uso; se consume en `start`. |
| Resultado | `{message, output: {name, sha256, bytes, source_sha256?}}` | Solo metadatos: sin contenido ni rutas absolutas. |
| Evento | `at, actor, from_state, to_state, detail` | Auditoría permanente por tarea. |

### Acciones v1 (lista cerrada; todo lo demás → 400)

| `action` | `params` | Efecto en la PC |
|---|---|---|
| `note.create` | `{text}` | `outputs/notes/<task_id>.md` |
| `document.create` | `{filename: *.md o *.txt, text}` | `outputs/documents/<task_id>-<filename>` |
| `video.clip` | `{root, path, start_ms, duration_ms, source_sha256?}` | `outputs/clips/<task_id>.mp4` con FFmpeg (reutiliza `arkos_pilot.core.execute`) |

`root` es un **alias** que solo la PC traduce a una carpeta (`agent allow-root`). El
servidor nunca envía rutas absolutas. Se rechazan `..`, unidades, rutas absolutas y
symlinks que salgan de la carpeta. Los archivos de salida se crean en modo exclusivo:
nunca se sobrescriben. No hay ejecución de comandos.

### Huella (cómo se liga una aprobación al contenido)

```
payload_sha256 = sha256( canonical({"v":1,"action":A,"params":P,"target_device_id":T}) )
canonical = JSON UTF-8, claves ordenadas, sin espacios, solo enteros (sin floats)
```

Vector fijo en `tests/test_relay_service.py::test_digest_golden_vector`. En JS:
`JSON.stringify` con claves ordenadas recursivamente da los mismos bytes para estos
tipos. La UI debe **recalcular** la huella con lo que muestra y enviarla al aprobar.

## 2. Estados

```
awaiting_approval ──approve(hash)──▶ approved ──claim──▶ claimed ──start──▶ running ──▶ succeeded
      ▲   │                            │  ▲                 │                  │    ──▶ failed   (sin efecto)
      │   └─reject─▶ rejected          │  └─lease vence─────┘                  │    ──▶ unknown  (incierto)
      └──── aprobación vence ──────────┘   (sin efecto)        lease vence ────┘
 cancel: awaiting_approval | approved | claimed ─▶ cancelled
 unknown ──resolve (humano)──▶ succeeded | failed      unknown/failed/cancelled ──retry──▶ tarea nueva
```

Garantías y no-garantías:

- **No se promete ejecución exactamente una vez.** Se garantiza *a lo sumo una
  ejecución automática por aprobación*. La aprobación se consume en `start` y un
  `unknown` nunca se reintenta solo.
- `claimed` con lease vencido vuelve a `approved`, porque todavía no hubo efecto.
- `running` con lease vencido pasa a `unknown`. Si después llega un informe real del
  agente, se acepta y la tarea queda resuelta.
- `retry` sobre `unknown` exige `acknowledge_possible_duplicate: true` y una nueva
  aprobación.
- La vigencia de la aprobación se comprueba dos veces: el servidor la valida en `start`
  (autoridad) y el agente la revisa antes de llamar (defensa ante desfase de reloj).

## 3. API v1

Todas las respuestas son JSON. Los errores tienen la forma
`{"error":{"code","message"}}`. Un recurso de otro usuario responde **404**, igual que
uno inexistente.

| Método y ruta | Auth | Uso |
|---|---|---|
| `GET /healthz` | — | Salud + `contract_version` |
| `POST /v1/pair` `{code}` | — | La PC canjea el código → `{device_id, device_token}` |
| `GET /v1/me` | usuario | |
| `POST /v1/devices/pairing-codes` `{device_name}` | usuario | Código de 10 min |
| `GET /v1/devices` · `POST /v1/devices/{id}/revoke` | usuario | Revocar libera `claimed` y marca `running` como `unknown` |
| `POST /v1/tasks` `{client_request_id, action, params, target_device_id?}` | usuario | 201 nueva · 200 `deduplicated:true` · 409 mismo id con otro contenido |
| `GET /v1/tasks?after_version=N&limit=` | usuario | Sincronización incremental (`next_after_version`) |
| `GET /v1/tasks/{id}` | usuario | Incluye `events` |
| `POST /v1/tasks/{id}/approve` `{payload_sha256, ttl_seconds≤86400}` | usuario | 409 `payload_mismatch` si no coincide |
| `POST /v1/tasks/{id}/reject` · `/cancel` | usuario | |
| `POST /v1/tasks/{id}/resolve` `{outcome, note?}` | usuario | Solo desde `unknown` |
| `POST /v1/tasks/{id}/retry` `{client_request_id, acknowledge_possible_duplicate?}` | usuario | Crea una tarea nueva que vuelve a requerir aprobación |
| `POST /v1/agent/claim` `{max_tasks≤10}` | dispositivo | Devuelve tareas + `lease_id` + `approval` |
| `GET /v1/agent/tasks/{id}` | dispositivo | Solo las tareas que reservó |
| `POST /v1/agent/tasks/{id}/heartbeat` `{lease_id}` | dispositivo | Extiende el lease |
| `POST /v1/agent/tasks/{id}/start` `{lease_id, payload_sha256}` | dispositivo | Última compuerta: lease, aprobación vigente, hash. Idempotente por lease |
| `POST /v1/agent/tasks/{id}/complete` `{lease_id, outcome, result}` | dispositivo | Idempotente (mismo resultado → 200) |
| `GET/POST /v1/channels/whatsapp/webhook` | firma Meta | Desactivado sin `WHATSAPP_APP_SECRET` + `WHATSAPP_VERIFY_TOKEN` |

Si no se indica `target_device_id`: se usa el único dispositivo activo; si hay varios,
responde 400 `target_required`; si no hay ninguno, la tarea queda para cualquier PC
que el usuario vincule después.

## 4. Agente Windows (orden y recuperación)

El diario local (`journal.sqlite3`) se escribe **antes** de cada paso de red:
`claimed → start_sent → running → done_local → reported`.

| Corte en… | Al reiniciar |
|---|---|
| `claimed` / `start_sent`, servidor en `claimed` o `approved` | Nada se ejecutó: se descarta; el lease vence y la tarea vuelve a ofrecerse. |
| `start_sent`, servidor en `running` (se perdió la respuesta) | Todavía no hubo efecto y sigue autorizada: se ejecuta una vez. |
| `running` sin `done_local` | Se verifica la salida esperada (bytes exactos). Si coincide → `succeeded`; si no → `unknown`. **No se re-ejecuta.** |
| `done_local` sin `reported` | Se reenvía el mismo resultado (idempotente). |
| Sin red | Se conserva el diario; reintento con backoff de hasta 5 min. |
| 401 (dispositivo revocado) | El agente se detiene y pide volver a vincular. |

El token del dispositivo se guarda con DPAPI (usuario actual de Windows) en
`%LOCALAPPDATA%\ArkosRelayAgent\device.token`. Fuera de Windows se guarda en un
archivo con permisos 0600. El agente rechaza `http://` salvo localhost con
`--allow-insecure-localhost`. No toca `D:\ARKOS`, Hermes, la voz ni la interfaz.

## 5. Adaptador WhatsApp (futuro, mismo contrato y misma cola)

`arkos_relay/adapters/whatsapp.py`:

- Valida `X-Hub-Signature-256` con HMAC del app secret. El workflow n8n actual no lo hace.
- Mapea número → usuario mediante `channel_bindings`. Los números no vinculados se
  descartan sin escribir en la cola.
- Deduplica por `wamid`: los reintentos de Meta no crean tareas dobles. La tarea usa
  `client_request_id = wa:<wamid>`.
- Comandos: `nota <texto>`, `aprobar <id8> <huella8>`, `cancelar <id8>`, `estado`.
  `aprobar` exige el prefijo de la huella que se mostró, así que aprueba ese contenido y
  no "la última pendiente" (a diferencia del flujo n8n actual).
- Las respuestas se escriben en `channel_outbox`. **Falta el emisor**: drenarlo con
  `ARKOS_SEND_WHATSAPP_TEXT` o con un cliente de la Cloud API.

## 6. Infraestructura del repo: existente vs desplegada

Verificado el 7 de octubre de 2026 con consultas de solo lectura.

| Pieza | En Git | Desplegado | Reutilización |
|---|---|---|---|
| `arkos_pilot` (cola local, FFmpeg) | Sí (PR #1) | En la PC de Jona, solo como CLI | Se reutilizan `execute`/`file_digest` para recortes. Su cola local no se usa como fuente de verdad remota, para evitar dos autoridades de aprobación. |
| Supabase `arkos-ceo` (migraciones 001–010) | Sí | **Sí**: proyecto activo, 10 migraciones aplicadas, 1 usuario, 0 aprobaciones | `users` se puede mapear a `user_id`. `arkos_approvals` no sirve tal cual: le faltan hash, consumo único y vínculo con la tarea. **RLS está desactivado en las 9 tablas** (aviso crítico de Supabase). |
| n8n (8 workflows, `N8N_BASE_URL`) | Sí | No verificado desde aquí | El emisor de WhatsApp puede drenar `channel_outbox`. |
| WhatsApp Cloud API | Documentación | La app de Meta figura pendiente en el ROADMAP | Adaptador listo, desactivado. |
| Hermes Desktop | Parches y evidencia | En la PC de Jona | No se integra ni se expone. |
| CI GitHub Actions (Linux/Windows, 3.11/3.12) | Sí | Sí | Ejecuta también estas pruebas. |

## 7. Operación (pilot, sin desplegar)

```bash
# Servidor (detrás de un proxy HTTPS; requiere disco persistente)
python -m arkos_relay admin --db relay.sqlite3 create-user --name "Jona"   # imprime token una vez
python -m arkos_relay serve --db relay.sqlite3 --host 127.0.0.1 --port 8787
```

```powershell
# PC Windows
./scripts/Start-ArkosAgent.ps1 pair --server https://RELAY --code XXXX-XXXX-XXXX
./scripts/Start-ArkosAgent.ps1 allow-root videos "$env:USERPROFILE\Videos"
./scripts/Start-ArkosAgent.ps1 run --once     # luego: run (bucle)
./scripts/Start-ArkosAgent.ps1 status
```

## 8. Riesgos y límites conocidos

- SQLite con un solo proceso de escritura es suficiente para el piloto personal. Para
  varios usuarios o alta disponibilidad hay que portar el esquema a Postgres con
  `SELECT … FOR UPDATE SKIP LOCKED`.
- El token de usuario es estático (bootstrap por CLI). Antes de abrirlo a terceros,
  reemplazarlo por Supabase Auth/JWT y agregar rotación.
- El limitador de intentos de vinculación vive en memoria y se reinicia junto con el
  proceso.
- Las notas viajan y se guardan en texto plano en el relay. No hay cifrado de extremo a
  extremo.
- En WhatsApp, el texto de una nota pasa por Meta. Revisar las políticas del canal antes
  de usarlo con datos sensibles.
