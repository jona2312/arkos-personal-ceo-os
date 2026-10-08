# Mobile–PC contract proposal v0.1

**DRAFT FOR COORDINATION**, not an agreed or deployed relay API. This local UI
was implemented without modifying n8n, SQL migrations, Hermes settings, cloud
credentials or the voice work. Claude's relay work must reconcile this proposal
with its inspected architecture before any connection is enabled.

## Ownership and terminology

- This increment owns `arkos_pilot/task_center.py`, `arkos_pilot/web/`, the launch
  script, its tests and these docs. The only core extension is optional targeted
  claiming in `Queue.run_next(task_id=None)`.
- Future relay owns remote identity, devices, durable receipt, delivery and sync.
- The Windows executor owns local action validation, local approval enforcement,
  execution and artifact creation. Local task IDs remain unchanged.
- Exactly one canonical record per remote request; the PC queue is an execution
  projection, not an independently editable second copy. Persist a unique map
  `(user_id, device_id, remote_task_id) → local_task_id` when integrating.

## Current local API (implemented)

All `/api/*` routes require `X-Arkos-Key`. Mutations additionally require the
exact server Origin and JSON. This is **not** authentication reusable in cloud.

| Route | Input | Output |
|---|---|---|
| GET /api/status | — | local capabilities, FFmpeg availability, worker busy |
| GET /api/tasks | — | `{tasks: [...]}` from SQLite |
| POST /api/tasks | `{action: "note", text}` or `{action: "clip", source, start, duration}` | `{task}`; 201, awaiting_approval |
| POST /api/propose | `{goal}` | deterministic catalog proposal; no task execution |
| POST /api/tasks/{id}/approve | `{fingerprint}` | `{task}`; 200 |
| POST /api/tasks/{id}/cancel | `{}` | `{task}`; 200 |
| POST /api/tasks/{id}/run | `{}` | `{accepted: true, task_id}`; 202 |
| GET /api/tasks/{id}/artifact | — | attachment from verified local output |

A task has `id` (UUID hex), `payload`, `fingerprint`, `state`, `approval_until`,
`approved_fingerprint`, `created`, `updated` (Unix seconds), `result` (local path
or error text). These are local formats, not permission to reveal all fields to
a remote client. The relay should use opaque artifact IDs, never expose arbitrary
Windows paths or raw exception traces.

## Remote envelope requirements (not implemented)

- `schema_version`, server-derived owner, `device_id`, `remote_task_id`,
  `idempotency_key`, action payload/hash, revision, created/updated times.
- `approval`: verified approver, exact action/hash, scope and expiry. A chat
  sentence or an LLM-generated boolean is not an approval artifact. Revalidate
  on the executor immediately before effect; payload changes invalidate approval.
- Identity is derived from verified credentials, never trusted from JSON IDs.
  Device pairing has short-lived one-use codes, revocation and account ownership.
- Executor connects outbound; no exposed PC port, general terminal or raw Hermes
  RPC on the public internet. The loopback key never leaves the local UI.
- Durable intake: return received only after commit. Idempotency must cover
  duplicate phone requests, duplicate delivery and result acknowledgements.
- Time-bounded task leases; only one active claimant. A lost connection during a
  side effect produces `needs_review` until its outcome can be reconciled.
  Do not promise exactly-once side effects or blindly rerun after lease expiry.
- Cancellation is definitive only before the action is claimed; otherwise report
  request/acknowledgement separately. A lost cancel request is not a canceled task.
- Sync changes by version/cursor; device connectivity and task execution are
  separate signals. A queued task is not "running" merely because PC is online.
- Artifacts need ownership checks, explicit upload policy, size limits and expiry.

## Display-state mapping

| Meaning | Current local state | Future remote presentation |
|---|---|---|
| Needs decision | awaiting_approval | Por aprobar |
| Approved, waiting | queued | En cola; waiting-for-device is a separate reason |
| Claimed/executing | running | En ejecución with executor acknowledgement |
| Result verified | completed | Completada with accessible artifact metadata |
| Error/expired/uncertain | blocked | Necesita revisión; show reason |
| Canceled before claim | cancelled | Cancelada |

While offline on the phone: label a local unsynced draft as such. Do not say it
was received in cloud. With PC offline: the relay can persist authorized jobs,
but cannot claim that a local model or tool is executing.

## Privacy decision before deployment

End-to-end encryption for mobile–PC payloads is a product requirement to design
and validate, **not provided by this increment**. TLS and encrypted-at-rest
storage alone are not E2EE. Decide key generation, pairing, recovery and revocation
before making that promise. If a cloud interpreter needs plaintext, show and
obtain the corresponding data-processing authorization; ciphertext-only relay
and server-side inference are different modes. WhatsApp/cloud voice providers
have their own data boundaries.

## Joint acceptance scenario

1. A phone authenticated as user A submits a note while A's PC is offline.
2. Receipt survives relay restart and duplicate submission returns the same task.
3. User B and a revoked device cannot read, approve, claim or fetch A's result.
4. A's PC reconnects; only an authorized, unexpired task can execute.
5. A disconnect after claim does not cause a duplicate effect on reconnect.
6. Phone sees verified completion and can fetch the permitted artifact.
7. Expired approval, changed payload and uncertain execution remain blocked for
   review. Local checks cannot be bypassed by an LLM, channel or relay request.
