# Piloto Cloud real: condiciones verificadas, hosting y prueba mínima

Estado: **preparado, no ejecutado**. No hubo despliegue, credenciales reales ni llamadas pagas.
Cloud real sigue **bloqueado por código** hasta completar el registro de condiciones.

## 1. Condiciones del proveedor (Anthropic, Claude API `api.anthropic.com`, `claude-haiku-5-5`)

Registro auditable: `config/cloud-terms-record.json` (revisado 2026-10-14, válido hasta 2027-01-12).

### Públicas (documentación oficial, leídas el 2026-10-14)

| Tema | Lo que dice la fuente | Fuente | Lo que muestra el consentimiento |
|---|---|---|---|
| Retención ordinaria | Docs de plataforma: "Conversation content … is not retained by default; the exception is Covered Models (30-day)". Privacy Center (solo vía índice): se borra "dentro de 30 días" | [S1](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention), [S3](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) | "Hasta 30 días" (tope conservador; ver D1) |
| Excepción por seguridad | Contenido marcado por sistemas de seguridad: hasta 2 años, aun con ZDR; además retenciones legales | S1 | "Si su sistema de seguridad marca el pedido, hasta 730 días" |
| Covered Models | Retención mínima de 30 días y sin ZDR: Fable 5/5.1 y Mythos 5/5.1. **Haiku 5.5 no está en la lista** | [S2](https://support.claude.com/en/articles/15425695-covered-models) (2026-09-01) | Modelo `claude-haiku-5-5` |
| Entrenamiento | "Anthropic may not train models on Customer Content from Services." / "Retained data is never used for model training without your express permission." | [S4](https://www.anthropic.com/legal/commercial-terms), S1 | "No entrena modelos con estos datos" |
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
| A2 | Retención estándar del workspace, sin ZDR ni acuerdo distinto (resuelve D1) | Console > Settings > Data retention |
| A3 | Workspace geo `us`; `allowed_inference_geos` incluye `global` | Console > Workspaces > Data residency |
| A4 | Ningún programa opcional que habilite entrenamiento o feedback | Console > Privacy |
| A5 | `claude-haiku-5-5` habilitado y con límites suficientes | Console > Limits; `GET /v1/models/claude-haiku-5-5` (sin tokens) |
| A6 | Límite de gasto del workspace en USD 10 por mes o menos (USD 5 durante la prueba) | Console > Limits / Billing |
| A7 | Entidad y país de facturación, impuestos | Console > Billing |
| A8 | El caso de uso cumple la Usage Policy | anthropic.com/legal/aup |
| A9 | Subprocesadores revisados | trust.anthropic.com |

**Discrepancia abierta D1:** la documentación de plataforma dice "no se retiene por defecto" y el
Privacy Center dice "dentro de 30 días". Mientras no se resuelva, se declara el tope de 30 días.
El Privacy Center no se pudo leer directamente desde el entorno de trabajo (bloqueo de red); hay que
abrirlo y confirmarlo.

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
workspace dedicado y un límite de gasto propio. Así el riesgo queda acotado a USD 10 por mes. Antes de
sumar usuarios, conviene pasar a una VM dedicada.

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

**Presupuesto máximo propuesto: USD 1** para toda la fase. Lo aplican el tope global diario del gateway
(USD 1) y, como segunda barrera, el límite del workspace (USD 5).

**Costo esperado:** 3 a 5 turnos cortos de Haiku 5.5, cerca de USD 0,0005 cada uno. Peor caso por turno
con estos límites: USD 0,006. Total esperado por debajo de USD 0,05.

**Fases** (cada una requiere aprobación):

1. **Registro completo.** Una persona completa A1–A9 y D1, lee S3 directamente y abre un PR que solo
   actualiza el registro y pone `terms_verified: true` en las dos configuraciones. Las pruebas verifican
   la coherencia.
2. **Infraestructura sin clave.** Instalar con el proveedor falso en loopback del servidor
   (`ARKOS_CLOUD_TEST_PROVIDER_URL`) y recorrer HTTPS de punta a punta desde la PC con
   `Run-ArkosCloudTrial`. Probar TLS, DNS, proxy, límite por dirección, backup y restauración. Costo cero.
3. **Clave real.** Cargarla según la sección 2, quitar la URL de prueba y reiniciar. `serve` solo arranca
   si el registro está completo. Hacer el chequeo A5 (`GET /v1/models`, sin tokens).
4. **Humo.** `ARKOS_CLOUD_DEVICE_TOKEN=… python scripts/Run-ArkosCloudRealSmoke.py --state-dir … --cloud-config … --confirm-paid-calls`
   (3 turnos, máximo 5). Se detiene ante cualquier resultado que no sea correcto y no reintenta.
   El informe trae estados, costos y latencia, sin contenido.
5. **Manual en la pantalla.** Una propuesta pasa a tarea pendiente; cancelar a mitad de turno; cortar
   la red de la PC después de enviar (debe quedar incierto, consultar estado y conciliar con la Console).

**Criterios de éxito (todos):**
- [ ] La pantalla muestra "Cloud" (no "de prueba"), con condiciones verificadas y la fecha de revisión.
- [ ] Los 3 turnos de humo terminan `ok`, en español, con latencia p95 menor a 15 s.
- [ ] La propuesta queda `awaiting_approval`; no hay ejecución automática.
- [ ] Cancelar avisa del posible cobro y el ledger registra el costo.
- [ ] El corte deja el turno incierto, sin segunda llamada en el uso de la Console; se concilia con `reconcile`.
- [ ] El costo del ledger coincide con el uso de la Console del día (±USD 0,01) y el total es menor a USD 0,10.
- [ ] La Console (Usage/Cost API por geo) muestra la inferencia según lo declarado (`global`).
- [ ] El log del gateway y el informe no tienen texto, tokens ni clave.
- [ ] Backup y restauración probados.

**Corte inmediato:** poner `global_daily_micro_usd` en 0 y reiniciar (no sale ningún pedido), o revocar
la key en la Console, o detener el servicio. La PC vuelve a Local sin fallback.

## 4. Riesgos

- **Privacidad:** el texto sale hacia Anthropic. Se retiene hasta 30 días, o hasta 2 años si se marca por
  seguridad. El consentimiento lo muestra.
- **Legal:** es orientación, no asesoramiento. Para abrirlo a terceros hacen falta una política de
  privacidad y términos propios (transferencia internacional y rol de encargado del proveedor).
- **Infraestructura:** compartir el VPS con n8n aumenta el impacto de un compromiso. El límite del
  workspace y la key dedicada lo acotan.
