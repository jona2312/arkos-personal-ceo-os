# Revisión de preparación para staging Cloud (PR #13)

Revisado sobre `398fcc3`. Los defectos se reprodujeron con un script sintético antes de corregirlos;
cada corrección tiene una regresión en `tests/test_cloud_adapter.py::StagingReadinessRegressionTests`.
Sin red, sin claves reales, sin llamadas pagas.

## Hallazgos

| # | Gravedad | Hallazgo en 398fcc3 (reproducido) | Corrección | Regresión |
|---|---|---|---|---|
| 1 | Alta | Una segunda instancia del gateway sobre el mismo ledger arrancaba y su `recover()` pasaba a `uncertain` la llamada en vuelo de la primera; esa llamada completada quedaba sin cobro registrado (`charged=0`, reserva retenida) | `InstanceLock`: lock exclusivo del SO sobre `<ledger>.lock` antes de abrir el ledger; versión de esquema (`PRAGMA user_version`) incompatible → no arranca | `test_second_gateway_instance_*`, `test_incompatible_schema_is_refused` |
| 2 | Alta | Los tokens vivían solo en memoria: revocar exigía reiniciar el gateway | Tokens en el ledger (solo hash), consultados en cada pedido; `revoke_token/revoke_user/revoke_prefix` y CLI de operador | `test_revoked_token_*`, `test_operator_cli_*` |
| 3 | Alta | Al cambiar el día UTC, una reserva incierta del día anterior dejaba de contar: se podía gastar 2× el tope diario | Las reservas abiertas (`reserved`, `sent`, `uncertain`) de días previos suman al tope hasta conciliarse | `test_day_change_carries_open_reservations_until_reconciled`, `test_call_in_flight_across_midnight_*` |
| 4 | Media | Con Haiku 5.5 la reserva usaba precio plano; una entrada de peor caso (>100.000 tokens) se factura entera al precio largo (5×) | Configuración de precios por tramos (`long_context_threshold_tokens` y precios largos); se aplican a reserva y a liquidación | `test_reservation_covers_haiku_long_context_tier` |
| 5 | Media | `gateway_retention_hours` se declaraba pero nunca se aplicaba; con 0 h igual se guardaba la respuesta | Purga en cada pedido; con 0 h no se guarda contenido | `test_retention_zero_*` |
| 6 | Media | Una excepción dentro de una transacción del ledger la dejaba abierta: el gateway quedaba bloqueado | Transacciones con `ROLLBACK` garantizado | `test_ledger_errors_never_leave_a_transaction_open` |
| 7 | Media | Un timeout del cliente no avisaba al gateway; y si la cancelación llegaba antes que el pedido, se ignoraba y el pedido se ejecutaba | El timeout envía cancelación; una cancelación de un id desconocido deja una marca que rechaza el pedido tardío | `test_timeout_and_cancel_that_overtakes_the_request` |
| 8 | Baja | Un consumo informado mayor que la reserva se cobraba sin señal | Se cobra lo real y se marca `overrun`; consumos negativos o no enteros cuentan como desconocidos (se cobra la reserva) | `test_usage_above_reservation_is_charged_and_flagged` |

Pendientes de baja gravedad (no corregidos, documentados):
- El digest del pedido es SHA-256 sin clave: con acceso al ledger y el `request_id`, un mensaje corto podría confirmarse por diccionario. Propuesta: HMAC con secreto del servidor.
- Un duplicado concurrente mientras el original está en vuelo recibe `outcome_uncertain` en vez de "en curso".
- No hay tope mensual en el gateway (sí en la consola del proveedor, propuesto).
- La UI del chat muestra un error genérico ante `outcome_uncertain`; el texto "incierto, no se reintenta" llegará con la UI de Cloud.

## Verificado sin defectos

- **Identidad**: B no puede leer, cancelar ni gastar sobre los pedidos de A (cancelar un id ajeno crea una marca propia de B y no toca la fila de A). Mismo `request_id` con otro contenido → conflicto.
- **Persistencia**: tras reiniciar se conservan tokens, gasto, reservas inciertas e idempotencia; una respuesta perdida nunca dispara otra llamada (ni del adaptador, ni del chat, ni del gateway).
- **Concurrencia**: 4 hilos con conexiones SQLite independientes + 3 procesos compiten por un tope de 10 reservas: exactamente 10.
- **Consentimiento**: cambiar proveedor, modelo, retenciones, política o límites del gateway → 412 sin reserva ni llamada.
- **Privacidad**: el ledger (incluidos `-wal`) no contiene el texto de los pedidos ni los tokens; los errores no reflejan el contenido.
- **Integración**: `arkos_cloud` no importa `arkos_pilot`, no aprueba, no ejecuta y no ofrece herramientas; `select_provider('cloud')` sigue cerrado y no existe respaldo silencioso del modo local.

## Cómo se impide una segunda instancia

1. Lock exclusivo del SO (`fcntl.flock` / `msvcrt.locking`) en `<ledger>.lock` durante toda la vida del gateway; se toma **antes** de abrir el ledger o recuperar.
2. `PRAGMA user_version` distinto de la versión del código → no arranca y no modifica el archivo.
3. El lock solo es confiable en disco local de **un** host: no usar volúmenes de red ni varias réplicas. El CLI de operador sí puede abrir el ledger en paralelo (sus escrituras usan `BEGIN IMMEDIATE`; no ejecuta recuperación).

## Qué conserva cada parte

| Dónde | Qué | Cuánto |
|---|---|---|
| PC (ARKOS) | Turnos del chat en memoria del proceso y `sessionStorage`; `cloud-consent.json` (divulgación aceptada, sin tokens) | Hasta cerrar el centro / revocar |
| Gateway (ARKOS) | Por pedido: usuario, `request_id`, SHA-256 del pedido, estado, µUSD reservados/cobrados, `overrun`, fechas. Hash de tokens | Indefinido (facturación) |
| Gateway (ARKOS) | Respuesta y propuestas (para reenviar sin volver a cobrar) | `gateway_retention_hours` (0–72 h) |
| Gateway (ARKOS) | Texto de los pedidos, tokens en claro, logs de contenido | No se guardan |
| Proveedor | Prompt de sistema, historial enviado y respuesta | Según su política y contrato; se declara en `provider_retention_days` y debe verificarse antes de staging |

## Implementado / simulado / pendiente

| Componente | Estado |
|---|---|
| Contrato v1, límites de entrada/salida, revalidación de propuestas | Implementado |
| Consentimiento ligado al digest (PC + gateway), CLI | Implementado |
| Ledger: idempotencia, reservas, topes diarios con arrastre, conciliación, retención, tokens revocables | Implementado |
| Lock de instancia única y versión de esquema | Implementado (Linux probado; Windows en CI) |
| CLI de operador (tokens, conciliación) | Implementado |
| Transporte PC→gateway | Implementado (`HttpTransport`, ver `docs/CLOUD_GATEWAY_SERVER.md`) |
| Proveedor LLM | Implementado con el SDK oficial; probado solo contra una API falsa local |
| Servidor HTTPS alrededor de `dispatch()` (TLS, rate limit, logs sin contenido) | Implementado; TLS probado con certificado autofirmado |
| Presupuesto mensual global aplicado por el gateway | Implementado |
| Hosting con volumen local, backups del ledger, secreto del proveedor | Pendiente |
| Pantalla de consentimiento y selector Cloud en la UI | Pendiente |
| Habilitar `cloud` en `select_provider` | Pendiente (PR separado, después de staging) |

## Veredicto

**NO LISTO para staging.** La lógica de dominio quedó lista para staging y probada, pero todavía
no hay nada que desplegar ni contra qué probar de verdad. Bloqueos concretos:

1. Servidor HTTPS que envuelva `CloudGateway.dispatch()`.
2. Transporte HTTPS del PC que distinga "no salió" de "se perdió".
3. `ProviderTransport` real con `max_retries=0` y su mapeo de errores (aunque la fase 1 use el simulado, el contrato tiene que estar fijado).
4. Hosting aprobado de una sola instancia con disco local y backups del ledger.
5. Decisiones de Jona: proveedor y modelo, retención declarada, topes y límite mensual en la consola.
