# Gateway Cloud: servidor, transporte y proveedor

Estado: implementado y probado **solo con un proveedor falso local**. Cloud sigue deshabilitado
por defecto: `select_provider('cloud')` lo rechaza, el centro de tareas no importa `arkos_cloud`
y la UI no lo ofrece. Sin claves reales, llamadas pagas ni despliegues.

```
PC: Conversations → CloudConversationProvider → HttpTransport ──HTTPS──▶ GatewayServer
                                                                           │ CloudGateway (ledger, topes)
                                                                           ▼
                                                   AnthropicProvider (SDK oficial, max_retries=0)
                                                                           ▼
                                                   Messages API  (en pruebas: tests/fake_anthropic.py)
```

| Pieza | Archivo | Qué garantiza |
|---|---|---|
| Servidor | `arkos_cloud/server.py` | Loopback por defecto; fuera de loopback exige TLS o `--behind-tls-proxy`. POST con `Content-Length` ≤ 256 KiB, sin `Transfer-Encoding`. Límite por dirección (60/min) antes de autenticar. Log: método, ruta genérica, estado y ms; nunca tokens, ids ni contenido. |
| Transporte PC | `arkos_cloud/http_transport.py` | Verifica certificado y host (TLS ≥ 1.2); sin proxies del entorno, sin redirecciones ni reintentos. Falla de DNS, conexión o TLS = "no salió" (`provider_unavailable`); cualquier falla posterior = `outcome_uncertain`. |
| Proveedor | `arkos_cloud/provider_anthropic.py` | Un pedido por turno con `max_retries=0`: modelo de la divulgación, `max_tokens`, `output_config.effort=low`, prompt del contrato. Nunca herramientas, caché, streaming ni fallbacks. |
| Presupuesto | `ledger.py`, `config.py` | Topes diarios (usuario y global) **y mensual global aplicado por el gateway**. Las reservas abiertas de días o meses anteriores siguen contando hasta conciliarse. |

Mapeo de errores del proveedor (lo ambiguo se trata como incierto y nunca se reintenta):

| Situación | Resultado | Reserva |
|---|---|---|
| No conectó (`ConnectError`, `ConnectTimeout`) | `provider_unavailable` | Liberada |
| HTTP 4xx (400, 401, 403, 404, 413, 429…) | `provider_unavailable` | Liberada |
| HTTP 408/409, 5xx, 529, timeout de lectura, conexión cortada | `outcome_uncertain` | Retenida hasta conciliar |
| `stop_reason: refusal` | `output_invalid` | Cobrado según `usage` |

## Configuración del piloto (`config/cloud-gateway.example.json`)

- Modelo `claude-haiku-5-5`; effort `low`; `max_input_chars` 12.000; `max_output_tokens` 2.048.
- Precios en µUSD/MTok: 100.000 / 500.000; desde 100.000 tokens de prompt, 500.000 / 2.500.000
  (lista oficial consultada el 2026-10-11).
- Topes: USD 0,20 por usuario por día, USD 1 global por día, **USD 10 global por mes**. Viven en
  `disclosure` (la persona los consiente; cambiarlos exige renovar el consentimiento) y el gateway
  aplica exactamente esos valores.
- `terms_verified: false`: con proveedor real, `serve` no arranca y la pantalla bloquea la activación.
- Retención de respuestas en el gateway: **0 h**.
- `provider_retention_days` = 30 es un **valor a confirmar** con la política y el contrato vigentes
  del proveedor antes de staging. Cambiarlo invalida los consentimientos, como cualquier otro campo.

## Qué implica la retención 0 h

El gateway no guarda el texto de ninguna respuesta. Por lo tanto:

1. Si la respuesta se pierde entre el gateway y la PC (corte de red, timeout del cliente), **no se
   puede recuperar**. El adaptador informa `outcome_uncertain`.
2. "Consultar estado" (`lookup`) sí muestra que el turno se completó y cuánto costó.
3. Reenviar el mismo `request_id` **no vuelve a llamar** al proveedor ni cobra de nuevo: devuelve
   `duplicate_request` ("se respondió y su contenido no se conserva").
4. Para obtener la respuesta, la persona debe hacer un pedido nuevo (otro `request_id`), que se
   cobra de nuevo. Con Haiku 5.5 y estos límites, el peor caso cuesta menos de USD 0,006 por pedido.
5. Con retención > 0 (p. ej. 1 h), el reenvío del mismo `request_id` devuelve la respuesta guardada
   sin costo adicional. Probado en `test_lost_response_is_recoverable_with_retention`.

Lo incierto entre el gateway y el proveedor (5xx, corte) no depende de la retención: el texto nunca
llegó al gateway, así que se concilia el costo con el panel del proveedor y la persona reintenta con un
pedido nuevo.

## Comandos reproducibles (sin claves reales ni red externa)

```bash
python -m pip install -r requirements-cloud.txt     # anthropic==1.12.1, solo en el gateway
python -B -m unittest tests.test_cloud_adapter tests.test_cloud_e2e -v
python -B -m unittest discover -s tests -v           # suite completa
```

Recorrido manual con el proveedor falso, en tres terminales (valores sintéticos):

```bash
# 1) API falsa en loopback
python -c "from tests.fake_anthropic import FakeAnthropic; import time; f=FakeAnthropic(); print(f.url); time.sleep(3600)"
# 2) Gateway (FAKE_URL = la URL impresa en 1)
python -m arkos_cloud token issue --ledger tmp/ledger.sqlite3 --user pilot   # imprime akc_… una sola vez
ARKOS_CLOUD_PROVIDER_KEY=fake-key-for-local-tests-only ARKOS_CLOUD_TEST_PROVIDER_URL=$FAKE_URL \
  python -m arkos_cloud serve --gateway-config config/cloud-gateway.example.json --ledger tmp/ledger.sqlite3 --port 8787
# 3) Consentimiento en la PC de prueba (gateway_url = http://127.0.0.1:8787 en una copia de cloud-client.example.json)
python -m arkos_cloud consent --config tmp/cloud-client.json --state tmp/pc
```

`token issue` crea el ledger si no existe. `ARKOS_CLOUD_TEST_PROVIDER_URL` solo acepta http en
loopback; en producción se omite y el SDK usa su URL oficial.

## Recorridos probados (`tests/test_cloud_e2e.py`)

| Escenario | Resultado comprobado |
|---|---|
| Turno completo por HTTP + SDK real contra la API falsa | Propuesta → tarea `awaiting_approval`; el cuerpo enviado no tiene herramientas, caché ni streaming; `max_tokens` y `effort` correctos; cobro por `usage` |
| Gateway caído | `provider_unavailable`, nada reservado |
| Proveedor 429/400 · 500/529/corte · refusal | Liberado · incierto · cobrado; siempre **un** pedido (sin reintentos del SDK) |
| Proveedor inalcanzable | No enviado, reserva liberada |
| Respuesta perdida PC↔gateway con 0 h | Incierto; `lookup` = completado; reenvío sin nueva llamada ni contenido |
| Respuesta perdida con 1 h | El reenvío recupera la respuesta sin nueva llamada |
| Cancelación durante la llamada | Corte en menos de 1,5 s; el contenido tardío se descarta y el costo se registra |
| `kill -9` del proceso gateway durante la llamada | El reinicio marca incierto; segunda instancia rechazada; reenvío sin segunda llamada; conciliación por CLI |
| Tope mensual | Bloquea antes de llamar aunque el tope diario alcance |
| TLS | Certificado confiable → OK; no confiable → "no salió", sin reserva |
| Logs y límites | Sin tokens, ids, clave ni texto; 411/413/429 |

## Bloqueos restantes antes de staging

1. Hosting aprobado: una instancia, disco local persistente, backup del ledger, secreto
   `ARKOS_CLOUD_PROVIDER_KEY` cargado solo en el servidor.
2. Certificado TLS del dominio del gateway (o un proxy TLS declarado).
3. Confirmar la retención real del proveedor y fijar `provider_retention_days`.
4. Clave de proveedor de un workspace dedicado, con su propio límite de gasto como segunda barrera.
5. Pantalla de consentimiento y selector Cloud en la UI, y un PR aparte que habilite `cloud` en
   `select_provider` después de la aceptación.
6. Cancelar no interrumpe una llamada síncrona del SDK ya enviada: se descarta el resultado y se
   cobra. Abortar de verdad requiere streaming; queda fuera del piloto.
