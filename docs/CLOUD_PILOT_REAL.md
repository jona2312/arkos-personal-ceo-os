# Piloto Cloud real: condiciones verificadas, hosting y prueba mínima

Estado: **preparado, no ejecutado**. No hubo despliegue, credenciales reales ni llamadas pagas.
Cloud real sigue **bloqueado por código** hasta completar el registro de condiciones.

## 1. Condiciones del proveedor (Anthropic, Claude API `api.anthropic.com`, `claude-haiku-5-5`)

Registro auditable: `config/cloud-terms-record.json` (revisado 2026-10-19, válido hasta 2027-01-17).

### Públicas (documentación oficial; S1–S9 leídas el 2026-10-14, S10–S11 el 2026-10-19)

| Tema | Lo que dice la fuente | Fuente | Lo que muestra el consentimiento |
|---|---|---|---|
| Retención ordinaria | Docs de plataforma: "Conversation content … is not retained by default; the exception is Covered Models (30-day)". Centro de ayuda: "API customers can use our standard 30-day retention or … Zero Data Retention"; la Console muestra "Zero data retention" o "30 day retention" por workspace. Privacy Center (**solo vía índice, no verificado**): se borra "dentro de 30 días" | [S1](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention), [S10](https://support.claude.com/en/articles/15707726-using-claude-for-legal-work-privilege-confidentiality-and-how-to-think-about-configuration) (2026-08-26), [S11](https://support.claude.com/en/articles/16824617-turn-on-data-retention-for-a-workspace-in-a-zero-data-retention-organization) (2026-09-05), [S3](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) | "Hasta 30 días" (tope conservador; ver D1) |
| Excepción por seguridad | Contenido marcado por sistemas de seguridad: hasta 2 años, aun con ZDR; además retenciones legales | S1 | "Si su sistema de seguridad marca el pedido, hasta 730 días" |
| Covered Models | Retención mínima de 30 días y sin ZDR: Fable 5/5.1 y Mythos 5/5.1. **Haiku 5.5 no está en la lista** | [S2](https://support.claude.com/en/articles/15425695-covered-models) (2026-09-01) | Modelo `claude-haiku-5-5` |
| Entrenamiento | "Anthropic may not train models on Customer Content from Services." / "Retained data is never used for model training without your express permission." / "We do not train on your content by default." | [S4](https://www.anthropic.com/legal/commercial-terms), S1, S10 | "No entrena modelos con estos datos" |
| Otros plazos | Puntajes de clasificación de seguridad hasta 7 años y feedback 5 años | Solo S3 vía índice: **no verificado** | No se declara (ver "no declarado" en el registro) |
| Región de inferencia | `global` (por defecto, cualquier geografía) o `us` (×1,1 en el precio); Haiku 5.5 la admite | [S5](https://platform.claude.com/docs/en/manage-claude/data-residency) | "Inferencia: cualquier geografía disponible" |
| Almacenamiento | El geo del workspace hoy solo puede ser `us` y no se cambia después de crearlo | S5 | "Almacenamiento del proveedor: US" |
| ZDR | Solo por acuerdo con ventas o cuenta, por organización | S1 | No se declara |
| Disponibilidad | `claude-haiku-5-5` en la API; retiro no antes del 2027-10-07; Argentina figura entre las ubicaciones admitidas | [S6](https://platform.claude.com/docs/en/about-claude/models/overview.md), [S7](https://platform.claude.com/docs/en/api/supported-regions) | — |
| DPA | El DPA con SCC queda incorporado al aceptar los Términos Comerciales | [S8](https://support.claude.com/en/articles/7996862-i-am-a-commercial-customer-how-do-i-view-your-data-processing-addendum-dpa) (2026-03-16) | — |
| Precio | Haiku 5.5: USD 0,10 / 0,50 por MTok hasta 100.000 tokens de prompt | [S9](https://platform.claude.com/docs/en/about-claude/pricing.md) (2026-10-11) | Topes de gasto |

### De la cuenta o del contrato (pendientes, requieren acceso a la Console)

| Id | Qué confirmar | Dónde |
|---|---|---|
| A1 | La organización está bajo Términos Comerciales (cuenta de API) | Console > Organization |
| A2 | Retención estándar del workspace, sin ZDR ni acuerdo distinto (resuelve D1) | Console > Organization settings > Workspaces, columna Data retention (S11) |
| A3 | Workspace geo `us`; `allowed_inference_geos` incluye `global` | Console > Workspaces > Data residency |
| A4 | Ningún programa opcional que habilite entrenamiento o feedback | Console > Privacy |
| A5 | `claude-haiku-5-5` habilitado y con límites suficientes | Console > Limits; `GET /v1/models/claude-haiku-5-5` (sin tokens) |
| A6 | Límite de gasto del workspace del piloto en USD 5 (ver sección 3) | Console > Limits / Billing |
| A7 | Entidad y país de facturación, impuestos | Console > Billing |
| A8 | El caso de uso cumple la Usage Policy | anthropic.com/legal/aup |
| A9 | Subprocesadores revisados | trust.anthropic.com |

**Estado de la evidencia, separado:**

| Tipo | Qué hay | Estado |
|---|---|---|
| Público, leído directamente | S1, S2, S4–S11 | Respaldan cada valor declarado. Basta S10 o S11 para el tope de 30 días |
| Público, **no** leído directamente | S3 (Privacy Center): retención, 2 años si se marca, 7 años para puntajes de clasificación, 5 años para feedback | Pendiente. El 2026-10-19 se reintentó: `privacy.claude.com` y `privacy.anthropic.com` rechazan el túnel con 403 desde este entorno. Hay que abrirlo desde un navegador |
| De nuestra cuenta | A1–A9 | Todas pendientes. No hay evidencia de cuenta en este repositorio |
| Discrepancia | D1 | Abierta (abajo) |

**Discrepancia abierta D1:** S1 dice "no se retiene por defecto, salvo Covered Models". S10 y S11
hablan de una retención estándar de 30 días para la API, y S3 (vía índice) dice "dentro de 30 días".
El tope declarado de 30 días es cierto con cualquiera de las dos lecturas, así que el consentimiento no
cambia. Se resuelve con A2: la Console debe mostrar "30 day retention" para el workspace. S11 describe esa
columna en el contexto de organizaciones con ZDR ("las que ya retienen 30 días no tienen este ajuste"), así
que puede no aparecer en una cuenta estándar. En ese caso hace falta una **respuesta escrita de Anthropic**.
Mientras tanto, D1 sigue abierta y bloquea la activación real.

### Cómo se marca como verificado (no es un cambio de bandera)

`arkos_cloud/terms.py` acepta un proveedor real solo si se cumple **todo** esto:

1. Los valores declarados en el registro coinciden con los que muestra el consentimiento (modelo,
   región, retención, retención por seguridad, entrenamiento, almacenamiento).
2. Cada valor está respaldado por una fuente https de un dominio oficial, leída hace 90 días o menos
   y leída directamente.
3. Todas las comprobaciones A1–A9 están en `confirmed`, con `evidence`, `confirmed_by` y `confirmed_on`.
   `evidence` es una **referencia** a un archivo privado; nunca capturas ni datos de cuenta en este
   repositorio público.
4. No quedan discrepancias abiertas y el registro no venció.
5. `terms_verified: true` en las dos configuraciones.

Si la bandera está en `true` pero falta cualquier punto, `serve` no arranca con el proveedor real y la
pantalla muestra "Activación real bloqueada (N pendientes)". La PC exige además que el gateway use el
mismo registro (mismo digest). El consentimiento muestra la fecha de revisión y la cantidad de pendientes.

## 2. Hosting, TLS, backups y clave

| Opción | Compatibilidad | Ventajas | Riesgos |
|---|---|---|---|
| **VPS existente de n8n** (`n8n.inbigfinanzas.com`) | Compatible **si** es un Linux con disco persistente, acceso por shell y un proxy TLS (o lugar para Caddy). No lo pude inspeccionar | Sin costo nuevo; DNS y TLS ya resueltos | Comparte máquina con las credenciales de n8n: si se compromete una, quedan expuestas las dos |
| **VM chica dedicada** | Compatible | Aislamiento real, permisos simples | Costo mensual (cotizar; no verificado) |
| Vercel | **No compatible**: funciones sin disco persistente ni proceso único; el ledger SQLite exige una instancia con lock local | — | — |
| Supabase | **No compatible hoy**: el ledger es SQLite; pasar a Postgres requiere portar transacciones y lock (y había una restricción de no tocar Supabase) | Futuro: varias instancias | — |

**Recomendación:** para el piloto, el VPS de n8n, con un usuario o contenedor separado, la clave de un
workspace dedicado y un límite de gasto propio. Así el riesgo queda acotado a USD 1 por la prueba del
gateway y a USD 5 por el límite del workspace (sección 3). Antes de sumar usuarios, conviene pasar a una
VM dedicada.

Plantillas en `deploy/cloud-gateway/`. **Ninguna está habilitada.** En el servidor se copia
`config/cloud-gateway.example.json` a `config/cloud-gateway.json` (ignorado por git).

- **systemd** (`arkos-gateway.service`): `DynamicUser`, `ProtectSystem=strict` y escucha solo en
  `127.0.0.1:8787`. La clave entra con `LoadCredential`, que expone `%d/provider_key` y fija
  `ARKOS_CLOUD_PROVIDER_KEY_FILE`; si el archivo es legible por otros usuarios, `serve` se niega a arrancar.
  `systemd-analyze verify` solo marca la ruta del venv, que aún no existe.
- **Caddy** (`Caddyfile`): TLS automático con Let's Encrypt en un subdominio a aprobar (propuesta:
  `arkos-gw.inbigfinanzas.com`), solo las rutas del gateway, cuerpo hasta 300 KB, HSTS y sin access log.
  El gateway confía en `X-Forwarded-For` solo si el par es `127.0.0.1` (`--trusted-proxy`).
- **Docker Compose** (`compose.yaml` + `Dockerfile`): alternativa si el VPS usa contenedores.
  `docker compose config` validó la sintaxis; la imagen no se construyó porque no hay daemon en este entorno.
- **Backups:** `python -m arkos_cloud backup` hace una copia consistente en caliente, verifica
  `integrity_check`, guarda con permisos 600 y rota 14 copias. Hay un timer diario de plantilla. Agregar
  una copia fuera del servidor (cifrada, con restic o rclone) a un bucket. Restaurar = detener el
  servicio, copiar el archivo y arrancar (`recover()` pasa a "incierto" lo que quedó en vuelo). El
  ledger no guarda conversaciones (retención 0 h); sí guarda hashes de tokens y facturación.
- **Firewall:** solo 80 (ACME) y 443 abiertos; 8787 cerrado al exterior.

**Carga segura de la clave:**
1. En la Console, crear el workspace `arkos-pilot` (geo `us`), con límite de gasto de USD 5.
2. Crear una API key de ese workspace.
3. Copiarla **directo al servidor** por SSH (`install -m 400 -o root /dev/stdin /etc/arkos/provider_key`
   y pegar). Nunca por chat, repo, tickets ni portapapeles compartido.
4. Reiniciar el servicio. Verificar en el log que no aparece y que el estado reporta `provider_mode: real`.
5. **Rotación o revocación:** desactivar la key en la Console (efecto inmediato), crear otra y repetir 3–4.
   Si hay sospecha de fuga: revocar primero y fijar el tope del workspace en 0.

## 3. Prueba real mínima

### Límites: tres capas distintas

| Capa | Quién lo aplica | Valor | Alcance | Si se alcanza |
|---|---|---|---|---|
| Límite de gasto del workspace (A6) | El proveedor (Console) | **USD 5** durante el piloto | Todo lo que facture el workspace `arkos-pilot`, incluso fuera del gateway | El proveedor rechaza los pedidos |
| Topes del gateway (consentidos en la PC) | `arkos_cloud` (ledger) | USD 0,20 por usuario y día; USD 1 global por día; USD 10 global por mes | Ventanas diarias y mensuales en UTC; se reinician | `budget_exhausted` antes de llamar al proveedor |
| **Presupuesto de la prueba** | `arkos_cloud` (ledger, tabla `trials`) | **USD 1 acumulado** para toda la prueba | Desde que se abre hasta que se cierra; **no** se reinicia por día ni por reinicio | `budget_exhausted` antes de llamar al proveedor |

Los USD 10 mensuales son un tope de configuración del gateway, no el límite de la Console. Se informan en el
consentimiento y no se tocan para el piloto. El valor efectivo de la prueba es el más chico de los tres:
USD 1.

**Presupuesto de la prueba (implementado):** `serve --trial-name piloto-real-1 --trial-budget-micro-usd 1000000`
(ya está en las plantillas de systemd y Docker).

- Cuenta lo cobrado **más** las reservas abiertas: en vuelo o inciertas, que se cuentan al peor caso
  hasta conciliarse.
- Vive en el ledger SQLite: sobrevive reinicios del proceso, del servidor y cambios de día.
- Ese mismo presupuesto no puede ampliarse ni reabrirse una vez cerrado. Cerrada la prueba, el gateway
  no envía nada más, aunque siga corriendo. Cambiar el monto o el nombre
  con una prueba abierta hace fallar el arranque.
- Con un proveedor real, `serve` **no arranca** sin una prueba abierta.
- No hay reintentos automáticos: un turno incierto queda reservado hasta `reconcile`.
- Comandos: `python -m arkos_cloud trial status --ledger …` muestra lo cobrado, lo abierto, lo que queda,
  las latencias y los percentiles. `trial close --name piloto-real-1` cierra la prueba.
- Probado con proveedor falso (`tests/test_cloud_trial.py`, y en `tests/test_cloud_e2e.py` matando y
  reiniciando el proceso).

**Costo esperado:** turnos cortos de Haiku 5.5, cerca de USD 0,0005 cada uno. Peor caso por turno con
estos límites: USD 0,006. El humo funcional (3–5 turnos) y una muestra de latencia de 60 turnos suman
cerca de USD 0,035. El script exige que lo que queda de la prueba cubra los turnos planeados **al peor
caso** (60 × 0,006 = USD 0,36) antes de enviar nada.

**Fases** (cada una requiere aprobación):

1. **Registro completo.** Una persona completa A1–A9 y D1, lee S3 directamente y abre un PR que solo
   actualiza el registro y pone `terms_verified: true` en las dos configuraciones. Las pruebas verifican
   la coherencia.
2. **Infraestructura sin clave.** Instalar con el proveedor falso en loopback del servidor
   (`ARKOS_CLOUD_TEST_PROVIDER_URL`) y recorrer HTTPS de punta a punta desde la PC con
   `Run-ArkosCloudTrial`. Probar TLS, DNS, proxy, límite por dirección, backup y restauración. Costo cero.
3. **Clave real.** Cargarla según la sección 2, quitar la URL de prueba y reiniciar. `serve` solo arranca
   si el registro está completo **y** hay una prueba abierta. Hacer el chequeo A5 (`GET /v1/models`, sin
   tokens).
4. **Humo funcional.** `ARKOS_CLOUD_DEVICE_TOKEN=… python scripts/Run-ArkosCloudRealSmoke.py --state-dir … --cloud-config … --confirm-paid-calls`
   (3 turnos con historial, máximo 5). Se detiene ante cualquier resultado que no sea correcto y no
   reintenta.
5. **Muestra de latencia.** El mismo script con `--latency-sample 60`: turnos independientes de un
   mensaje, separados `--pace-seconds` (3,5 s por defecto). Cada turno hace unos 3 pedidos y el gateway
   admite 60 por dirección y minuto, así que la muestra tarda unos 4 minutos. El informe trae estados,
   costos y la latencia de cada turno, sin contenido.
6. **Manual en la pantalla.** Una propuesta pasa a tarea pendiente; cancelar a mitad de turno; cortar
   la red de la PC después de enviar (debe quedar incierto; consultar estado y conciliar con la Console).
7. **Conciliación diferida.** Al menos **24 h** después de la última llamada (ver abajo), comparar
   ledger y Console y cerrar la prueba con `trial close`.

**Latencia:** el ledger guarda `latency_ms` de cada llamada (desde la reserva hasta el resultado del
proveedor). El informe del script guarda la latencia de cada turno vista desde la PC, que incluye red y
gateway. Con menos de 20 turnos no se calcula p50/p95 (rango más cercano): 3–5 turnos solo dan un máximo.
Con 60 turnos el p95 es el 57.º valor ordenado. Es **indicativo**: un usuario, una red y una franja
horaria. No es un SLO.

**Datos de consumo de la Console:** Usage y Cost se actualizan con demora, normalmente en unos 5 minutos
y a veces más. El Cost API tiene granularidad diaria y exige una Admin API key, que las cuentas
individuales no tienen. Por eso se concilia en las pantallas Usage y Cost de la Console, por día UTC, y
nunca antes de 24 h después de la última llamada. Si la cifra todavía cambia, se repite al día siguiente.

**Criterios de aceptación (todos):**
- [ ] La pantalla muestra "Cloud" (no "de prueba"), con condiciones verificadas y la fecha de revisión.
- [ ] Humo funcional: todos los turnos terminan `ok`, en español, y ninguno supera 30 s.
- [ ] Muestra de latencia: 60 turnos `ok`, con cada latencia registrada en el informe y en el ledger
      (`trial status`). Se informan máximo, p50 y p95. El p95 se toma como referencia, sin umbral de
      aprobación, salvo que se fije uno antes de correr la muestra.
- [ ] La propuesta queda `awaiting_approval`; no hay ejecución automática.
- [ ] Cancelar avisa del posible cobro y el ledger registra el costo.
- [ ] El corte deja el turno incierto, sin segunda llamada en el uso de la Console; se concilia con `reconcile`.
- [ ] Pasadas 24 h o más, el costo del ledger por día UTC coincide con la Console (±USD 0,01). El total
      queda por debajo de USD 0,10 y `trial status` nunca superó USD 1 (cobrado + abierto).
- [ ] La Console (Usage por geo) muestra la inferencia según lo declarado (`global`).
- [ ] El log del gateway y el informe no tienen texto, tokens ni clave.
- [ ] Backup y restauración probados.

**Corte inmediato:** `python -m arkos_cloud trial close --name piloto-real-1 --ledger …`. Se puede correr
con el servicio en marcha: el siguiente pedido ya no sale (un ledger que tuvo una prueba nunca vuelve a
"sin tope"), y al reiniciar, `serve` no arranca con la prueba cerrada. También
sirve poner `global_daily_micro_usd` en 0 y reiniciar, revocar la key en la Console o detener el
servicio. La PC vuelve a Local sin fallback.

## 3 bis. Lo que Jona tiene que comprobar en la Console

Anotar cada dato **en un archivo privado** (fuera de este repositorio) y referenciarlo en `evidence`.
No copiar claves, IDs de organización ni datos de facturación en el PR.

| # | Pantalla | Dato no secreto a anotar | Cubre |
|---|---|---|---|
| 1 | Organization settings > Organization | Tipo de cuenta (API, comercial) y fecha de aceptación de los Términos Comerciales si aparece | A1 |
| 2 | Organization settings > Workspaces | Que existe `arkos-pilot` y qué dice la columna **Data retention** ("30 day retention" esperado) | A2, D1 |
| 3 | Workspace `arkos-pilot` > Data residency | Workspace geo (`us`), `allowed_inference_geos` (incluye `global`), geo por defecto | A3 |
| 4 | Organization settings > Privacy (y programas aceptados) | Que no hay programas de feedback o socios de desarrollo activos | A4 |
| 5 | Limits (workspace) | `claude-haiku-5-5` disponible y sus límites de tasa | A5 |
| 6 | Limits / Billing (workspace) | Spend limit del workspace = **USD 5** | A6 |
| 7 | Billing | País de facturación e impuestos aplicados (sin datos de tarjeta) | A7 |
| 8 | Usage y Cost (después de la prueba, ≥ 24 h) | Costo por día UTC del workspace y uso por geo | Conciliación |

**No se resuelve desde la Console:**
- **A8 (Usage Policy):** es una revisión humana del texto público frente al caso de uso.
- **A9 (subprocesadores):** está en el Trust Center (`trust.anthropic.com`), no en la Console.
- **S3 (Privacy Center):** es una página pública. Hay que leerla en un navegador y registrar fecha y texto.
- **D1:** si la pantalla 2 no muestra la columna Data retention, la Console no la resuelve. Hace falta una
  confirmación escrita de Anthropic (soporte).
- **A1:** la Console puede no mostrar la fecha ni la versión de los términos aceptados. Si no aparece,
  se anota así y se consulta a soporte.

## 4. Riesgos

- **Privacidad:** el texto sale hacia Anthropic. Se retiene hasta 30 días, o hasta 2 años si se marca por
  seguridad. El consentimiento lo muestra.
- **Legal:** es orientación, no asesoramiento. Para abrirlo a terceros hacen falta una política de
  privacidad y términos propios (transferencia internacional y rol de encargado del proveedor).
- **Infraestructura:** compartir el VPS con n8n aumenta el impacto de un compromiso. El límite del
  workspace y la key dedicada lo acotan.
