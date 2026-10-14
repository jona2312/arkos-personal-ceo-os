# Propuesta de despliegue: ARKOS Cloud (conversación de texto)

Estado: **propuesta, no ejecutada**. Versión operativa y condiciones verificadas: `docs/CLOUD_PILOT_REAL.md`. Revisión de preparación: `docs/CLOUD_STAGING_REVIEW.md`. Nada de esto se desplegó ni se configuró. Requiere
aprobación explícita de Jona en cada fase. Lo financiero es estimativo y educativo.

## 1. Decisiones que hay que aprobar antes de escribir código productivo

| Decisión | Recomendación | Alternativa | Por qué |
|---|---|---|---|
| Proveedor y modelo | Claude Haiku 5.5 (`claude-haiku-5-5`), effort `low` | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | El chat es breve y sin herramientas; Haiku cuesta ~20× menos. Sonnet solo si la calidad medida en español no alcanza. |
| Hosting del gateway | 1 contenedor con volumen persistente **local** (p. ej. una VM chica o una plataforma con volumen adjunto) | Cloud Run + Postgres | El ledger es SQLite con lock de instancia única (`<ledger>.lock`): exige **una** réplica y disco local, no de red. Serverless sin disco rompe la idempotencia. |
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
4. CLI de operador: **hecho** (`python -m arkos_cloud token issue|revoke|list`, `reconcile`).
   La purga por retención corre en cada pedido. Falta: backup del ledger antes de cada despliegue.
5. Pantalla de consentimiento en la UI (texto de `Disclosure.summary()`, código a confirmar,
   revocar) y selector Local/Cloud con sesión nueva por defecto: sin historial local previo.
6. Aceptación en staging (sección 4) con evidencia sanitizada.
7. Recién entonces: PR separado que habilita `'cloud'` en `select_provider`.

## 3. Costo estimado (corregido 2026-10-11)

**Fuente**: lista oficial `platform.claude.com/docs/en/about-claude/pricing`, consultada el
2026-10-11. Precios en USD por millón de tokens (MTok):

| Modelo | Entrada | Salida | Nota |
|---|---|---|---|
| Claude Haiku 5.5, prompt ≤ 100.000 tokens | 0,10 | 0,50 | |
| Claude Haiku 5.5, prompt > 100.000 tokens | 0,50 | 2,50 | El pedido entero paga el tramo alto |
| Claude Sonnet 5.5 | 2 | 10 | Sin tramo por longitud |
| `inference_geo` = US | ×1,1 | ×1,1 | Si se fija región US; incluirlo en los precios del gateway |

**Supuestos explícitos** (validarlos en staging contra `usage` real):
- Los tokens de razonamiento (thinking adaptativo, activo por defecto en Haiku 5.5) se facturan
  como salida y quedan acotados por `max_tokens` = `max_output_tokens`.
- Turno típico: 1.500 tokens de entrada (prompt de sistema de 604 bytes + historial + mensaje) y
  800 de salida (≈300 visibles + razonamiento con effort `low`). El tokenizador de Haiku 5.5 cuenta
  ≈30 % más tokens que el de Haiku 4.5.
- Sin prompt caching (sin cargos de escritura de caché), sin batch, sin herramientas.
- Cota de reserva = 1 token por byte UTF-8 + 16 por mensaje + 64. Es un supuesto sobre
  tokenizadores BPE de bytes: staging debe confirmarlo (las desviaciones quedan como `overrun`).

| Escenario | Haiku 5.5 | Sonnet 5.5 |
|---|---|---|
| Turno típico | USD 0,00055 | USD 0,011 |
| 1 usuario, 50 turnos/día (≈1.500/mes) | ≈ USD 0,83/mes | ≈ USD 16,5/mes |
| 10 usuarios iguales | ≈ USD 8,3/mes | ≈ USD 165/mes |
| Reserva peor caso, `max_input_chars` 12.000, salida 2.048, texto ASCII | USD 0,0023 | USD 0,046 |
| Reserva peor caso, 12.000 caracteres de 4 bytes (emoji) | USD 0,0059 | USD 0,118 |
| Reserva peor caso, 32.000 caracteres de 4 bytes (entra en el tramo > 100.000) | USD 0,070 | USD 0,278 |
| Hosting del gateway (1 instancia + volumen) | No verificado: cotizar con el proveedor elegido | igual |

La estimación anterior (USD 0,0003 por turno con Haiku) **no contaba el razonamiento** como salida
ni el tramo de contexto largo; la corregida es ≈ 1,8× mayor.

Configuración recomendada para el piloto:
- `max_input_chars`: 12.000. Con eso la cota de entrada (< 49.000 tokens) nunca alcanza el tramo
  largo de Haiku y la reserva del peor caso queda por debajo de USD 0,006.
- `max_output_tokens`: 2.048. Con 1.024, el razonamiento puede agotar el límite y cortar la
  respuesta (se cobraría igual).
- Precios del gateway en µUSD/MTok para Haiku 5.5: 100.000 / 500.000, umbral 100.000,
  500.000 / 2.500.000 (×1,1 si `inference_geo` = US).
- `per_user_daily_micro_usd`: 200.000 (USD 0,20); `global_daily_micro_usd`: 1.000.000 (USD 1);
  límite mensual en la consola del proveedor: USD 10.

Las reservas abiertas (en vuelo o inciertas) siguen contando contra el tope de los días
siguientes hasta conciliarse: un incidente de red no puede llevar el gasto por encima del tope.

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
