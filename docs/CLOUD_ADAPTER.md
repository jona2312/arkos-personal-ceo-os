# Adaptador conversacional Cloud (transporte simulado)

Estado: implementado y probado con transporte y proveedor **simulados**. Cloud sigue
**deshabilitado**: `arkos_pilot.providers.select_provider(..., 'cloud')` rechaza el modo,
`task_center.py` no importa `arkos_cloud` y la interfaz no lo ofrece. No hay transporte
HTTP real, clave de proveedor ni llamadas pagas en este cambio.

## Piezas

```
PC (ARKOS)                                         Servidor ARKOS (futuro)
Conversations ──converse()──▶ CloudConversationProvider ──transport──▶ CloudGateway ──▶ proveedor LLM
(chat existente)               token akc_ revocable           (simulado)   ledger SQLite    (simulado)
                               consentimiento local                         clave del proveedor
```

| Módulo | Rol |
|---|---|
| `arkos_cloud/config.py` | Configuración explícita y estricta (`ClientConfig`, `GatewayConfig`, `Disclosure`). Sin valores por defecto, rechaza campos desconocidos, nombres tipo `api_key/secret/token` y valores con forma de credencial. `https` obligatorio (http solo loopback). |
| `arkos_cloud/consent.py` | Consentimiento local ligado al digest exacto de la divulgación (proveedor, modelo, región, retenciones, límites, texto de datos enviados). Cambiar cualquiera lo invalida. Aceptar exige escribir el código mostrado. |
| `arkos_cloud/adapter.py` | Implementa `ConversationProvider` (mismo contrato v1). Un `converse()` = como máximo una solicitud al gateway. |
| `arkos_cloud/gateway.py` | Autenticación, consentimiento, límites, idempotencia, reserva de presupuesto y una sola llamada al proveedor. Expone `dispatch()` con forma HTTP para un servidor futuro. |
| `arkos_cloud/ledger.py` | SQLite: estado por `(usuario, request_id)` y gasto reservado/cobrado por usuario y global por día UTC. |
| `python -m arkos_cloud consent` | Muestra la divulgación, registra o revoca el consentimiento. No envía datos. |

Reutiliza `arkos_hermes.contract` (validación, límites, `SYSTEM_PROMPT`, `parse_reply`,
digest de propuestas) y `arkos_pilot.chat.Conversations` + `Queue.add` para notas. No hay
otra cola, otro chat ni otra aprobación. El contrato solo suma tres códigos de error:
`consent_required`, `budget_exhausted`, `outcome_uncertain`.

## Garantías y dónde se prueban (`tests/test_cloud_adapter.py`, 37 pruebas)

| Requisito | Comportamiento | Prueba |
|---|---|---|
| Configuración explícita | Campos completos, tipos y rangos; sin defaults | `ConfigTests` |
| Sin claves del proveedor en el cliente | Config rechaza secretos; el adaptador solo acepta `akc_…`; el paquete no lee entorno ni abre red | `test_provider_secrets_*`, `test_adapter_refuses_*`, `test_cloud_package_reads_no_environment_or_network` |
| Consentimiento antes de enviar | Sin consentimiento vigente: cero bytes al transporte. El gateway lo verifica de nuevo (412) | `ConsentTests` |
| Límites de entrada | Contrato v1 + `max_input_chars` en cliente y gateway; cuerpo ≤256 KiB | `LimitTests` |
| Límites de salida | `max_output_tokens` al proveedor; salida cruda acotada; respuesta ≤8000 chars, ≤3 propuestas; respuesta del gateway ≤256 KiB y revalidada (digest de propuestas) | `test_output_limits`, `test_tampered_proposal_is_rejected` |
| Reserva previa | Peor caso (1 token por byte UTF-8 + salida máxima) reservado y confirmado, y fila en `sent`, **antes** de llamar | `test_reservation_is_committed_before_the_call_and_settled_after` |
| Presupuesto agotado | 429 `budget_exhausted`, sin llamada; tope por usuario y global | `test_exhausted_budget_*`, `test_global_budget_*` |
| Idempotencia | Mismo `request_id` + mismo contenido → misma respuesta, 1 llamada; otro contenido → conflicto; 12 concurrentes → 1 llamada | `IdempotencyTests` |
| Respuesta perdida | `outcome_uncertain`; la reserva queda retenida; reintentar el mismo id nunca vuelve a llamar; conciliación manual | `LostResponseTests` |
| Cancelación | Corta la espera en <1 s, avisa al gateway, el contenido tardío se descarta; el costo real se registra | `CancelTests`, `test_chat_cancel_reaches_the_gateway` |
| Reinicio del gateway | `reserved` → liberado (nunca salió); `sent` → incierto (nunca se reenvía) | `test_gateway_restart_recovers_without_resending` |
| No aprueba ni ejecuta | La propuesta crea una tarea `awaiting_approval` solo por acción humana del chat existente | `test_reuses_chat_and_queue_and_never_approves` |
| Cloud sigue cerrado | `select_provider('cloud')` y `TaskCenter(chat_mode='cloud')` fallan antes del socket; UI sin referencias | `test_cloud_mode_stays_disabled` |

## Estados del ledger

`reserved → sent → completed | failed (sin cobro) | cancelled | uncertain → reconciled`

- **uncertain**: pudo haberse cobrado. Retiene la reserva hasta `Ledger.reconcile()` con el
  consumo informado por el proveedor. El usuario ve "resultado incierto, no se reintenta".
- Un reintento humano debe usar un `request_id` nuevo. El gateway es la autoridad: aunque el
  PC se reinicie y reenvíe el mismo id, no habrá segunda llamada.
- Si el proveedor informa un consumo mayor que la reserva, se cobra el real (puede exceder el
  tope diario por ese margen). Las reservas usan una cota superior para que esto no ocurra.

## Límites conocidos

- Sin transporte HTTP real ni servidor: `dispatch()` está listo para envolverse.
- SQLite = una sola instancia del gateway. Escalar requiere Postgres con las mismas transacciones.
- El historial lo arma el cliente (igual que en local). Al pasar de Local a Cloud, el
  historial previo no debería enviarse salvo selección explícita; eso pertenece a la UI pendiente.
- `processing` en el estado del chat sigue en `synthetic` para estas pruebas; `cloud` llegará
  con la aceptación descrita en `docs/CLOUD_DEPLOYMENT_PROPOSAL.md`.

## Validación

```
python -B -m unittest tests.test_cloud_adapter -v
python -B -m unittest discover -s tests -v
```
