# Propuesta de despliegue: ARKOS Cloud (conversación de texto)

Estado: **propuesta, no ejecutada**. Nada de esto se desplegó ni se configuró. Requiere
aprobación explícita de Jona en cada fase. Lo financiero es estimativo y educativo.

## 1. Decisiones que hay que aprobar antes de escribir código productivo

| Decisión | Recomendación | Alternativa | Por qué |
|---|---|---|---|
| Proveedor y modelo | Claude Haiku 5.5 (`claude-haiku-5-5`), effort `low` | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | El chat es breve y sin herramientas; Haiku cuesta ~20× menos. Sonnet solo si la calidad medida en español no alcanza. |
| Hosting del gateway | 1 contenedor con volumen persistente (p. ej. Fly.io, Railway o una VM chica) | Cloud Run + Postgres | El ledger es SQLite: exige **una** instancia con disco. Serverless sin disco rompe la idempotencia. |
| Autenticación PC→gateway | Token `akc_` por dispositivo, guardado como hash en el servidor, revocable | OAuth/login de usuario | Igual que el relay (`akd_`); sin cuentas todavía. |
| Credencial del proveedor | Solo en el secreto del gateway; consola del proveedor con **límite de gasto mensual** | — | El cliente nunca la ve; el tope en la consola es la última barrera. |
| Retención | Gateway: 24 h de contenido para idempotencia y después se purga; facturación se conserva | 0 h (sin replay de contenido) | Confirmar la retención vigente del proveedor y escribirla en `provider_retention_days`; cualquier cambio invalida el consentimiento. |
| Supabase | No se usa en esta fase | Postgres de Supabase para el ledger | Respeta la restricción vigente; se reevalúa al escalar. |

## 2. Requisitos para habilitar `cloud` (todos obligatorios)

1. `ProviderTransport` real con SDK oficial, **`max_retries=0`** (los reintentos automáticos
   del SDK duplicarían cobros), timeout explícito, sin streaming ni herramientas.
   - Error de conexión antes de enviar → `ProviderNotSent`; 4xx definitivos → `ProviderRejected`;
     timeout/reset/5xx tras enviar → `ProviderLost` (incierto). Ante la duda: incierto.
   - `stop_reason == "refusal"` → error `model_error`, cobrando el consumo informado.
   - No asumir que el proveedor deduplica: no hay clave de idempotencia documentada para
     Messages API; la autoridad es el ledger del gateway.
2. Servidor HTTPS que envuelva `CloudGateway.dispatch()`: TLS del hosting, cuerpo ≤256 KiB,
   rate limit por IP, logs **sin** contenido (solo request_id, estado, µUSD, latencia).
3. Transporte HTTPS del PC (`urllib`) que distinga "no conectó" (`TransportNotSent`) de
   "se perdió"; verificación de certificado obligatoria; sin proxies implícitos.
4. CLI de operador: emitir/revocar tokens `akc_`, ver gasto del día, `reconcile` de inciertos,
   purga por retención (tarea manual, no programada, hasta aprobarlo).
5. Pantalla de consentimiento en la UI (texto de `Disclosure.summary()`, código a confirmar,
   revocar) y selector Local/Cloud con sesión nueva por defecto: sin historial local previo.
6. Aceptación en staging (sección 4) con evidencia sanitizada.
7. Recién entonces: PR separado que habilita `'cloud'` en `select_provider`.

## 3. Costo estimado

Precios de lista consultados el 2026-10-06 (verificar al contratar): Haiku 5.5 USD 0,10 /
0,50 por millón de tokens de entrada/salida (prompts ≤100K); Sonnet 5.5 USD 2 / 10.

Supuestos: turno típico = 1.500 tokens de entrada (prompt de sistema + historial) y 300 de salida.

| Escenario | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Turno típico | USD 0,0003 | USD 0,006 |
| Reserva peor caso, conversación corta | USD 0,0008 | USD 0,016 |
| Reserva peor caso, historial máximo (32.000 chars, 20 mensajes) | USD 0,0038 | USD 0,076 |
| 1 usuario, 50 turnos/día (≈1.500/mes) | ≈ USD 0,45/mes | ≈ USD 9/mes |
| 10 usuarios iguales | ≈ USD 4,5/mes | ≈ USD 90/mes |
| Hosting gateway (1 instancia + volumen 1 GB) | ≈ USD 2–7/mes, orden de magnitud | igual |

Topes propuestos para el piloto (en µUSD, configuración del gateway):
- `per_user_daily_micro_usd`: 200.000 (USD 0,20/día ≈ 50 turnos de peor caso con Haiku).
- `global_daily_micro_usd`: 1.000.000 (USD 1/día).
- Límite mensual en la consola del proveedor: USD 10.

Las reservas inciertas cuentan contra el tope hasta conciliarlas: un incidente de red no
puede llevar a gastar más que el tope.

## 4. Pasos de despliegue (cada uno con aprobación)

1. **Staging sin proveedor real**: gateway con `SimulatedProvider`, token de prueba, PC de
   prueba. Criterios: escenarios equivalentes a los 37 tests pasan sobre HTTPS real (consentimiento,
   límites, idempotencia, pérdida, cancelación, reinicio del contenedor).
2. **Clave real con tope mínimo**: secreto en el hosting, límite de USD 5 en la consola,
   `global_daily_micro_usd=200000`. Pruebas: 10 turnos en español, una propuesta→tarea
   pendiente→aprobación humana separada, cancelar a mitad, cortar la red tras enviar
   (debe quedar incierto y no reintentar), conciliar con el panel de uso del proveedor.
3. **Piloto con Jona**: habilitar selector Cloud en su PC, una semana, revisar gasto real
   contra el ledger a diario.
4. **Fuera de alcance**: más usuarios, cobro, streaming, voz, búsqueda web y fallback
   Local↔Cloud. Cada uno requiere su propio contrato y aprobación.

## 5. Reversión

| Situación | Acción | Efecto |
|---|---|---|
| Gasto o comportamiento anómalo | `global_daily_micro_usd=0` y reiniciar el gateway | Toda reserva se rechaza **antes** de llamar (kill switch). |
| Dispositivo comprometido | Revocar su token `akc_` | 401 inmediato; los demás siguen. |
| Clave del proveedor expuesta | Revocarla en la consola y rotar el secreto | Las llamadas fallan como no enviadas, sin cobro. |
| Retirar Cloud del PC | `python -m arkos_cloud consent ... --revoke` y borrar la config Cloud | El adaptador no envía nada; Local sigue igual (no hay fallback). |
| Revertir el código | Revertir el PR que habilitó `cloud` en el selector | El centro vuelve a rechazar `cloud` antes de abrir el socket. |
| Desmantelar | Conciliar los inciertos, purgar contenido, exportar facturación, borrar volumen y app | No queda contenido de conversaciones en el gateway. |

## 6. Riesgos

- **Privacidad**: el texto sale del PC hacia el proveedor. Por eso hay consentimiento ligado al
  digest y retención declarada. No describir Cloud como privado ni Local como privacidad absoluta.
- **Legal**: antes de abrirlo a terceros hacen falta términos y política de datos (procesador
  externo, transferencia internacional). Esta propuesta no los cubre; es orientación, no
  asesoramiento legal.
- **Costos**: los precios cambian. Los topes en µUSD son configuración y hay que revisarlos al
  cambiar de modelo.
- **Inyección de prompt**: sin herramientas, el daño se limita al texto y a propuestas que
  siempre requieren aprobación humana.
