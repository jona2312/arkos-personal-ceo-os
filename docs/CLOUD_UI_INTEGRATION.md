# Cloud en la pantalla: integración con proveedor falso

Base: #15 (`claude/arkos-cloud-transport` @ `40741a2`) + #14 (`claude/task-center-reject-body`
@ `681e0b7`) incorporado con un merge commit; las ramas originales no se modifican.
Sin claves reales, llamadas pagas, despliegues ni streaming. No agrega herramientas.

## Qué ve la persona

- **Local / Cloud** debajo del área de escritura, el placeholder del campo y la etiqueta del
  núcleo dicen siempre dónde se procesa: "esta PC", "Cloud de prueba · gateway ARKOS con
  proveedor falso" o "Cloud no activo · nada se envía".
- **Cloud empieza deshabilitado.** Sin `--cloud-config` la pestaña no se puede elegir. Configurado,
  al elegirla aparece el consentimiento y la escritura queda bloqueada hasta aceptar.
- **Consentimiento** con: proveedor y modelo, qué datos se envían, retención en el gateway ARKOS
  (0 h: una respuesta perdida no se puede recuperar), retención del proveedor (marcada **SIN
  VERIFICAR**), límites de gasto (USD 0,20 por usuario por día, USD 1 global por día, USD 10
  global por mes), que cancelar puede no evitar el cobro y que no hay reintentos automáticos.
  Hay que tildar "Entiendo…" y aceptar. Se puede revocar.
- **Cambiar de modo no envía historial:** Local y Cloud son sesiones separadas. Además, el servidor
  rechaza ("no enviado") cualquier pedido Cloud cuyo historial no salga de turnos Cloud anteriores
  de la misma sesión.
- **Propuestas:** igual que en Local, "Crear nota pendiente" la deja en *Por revisar*. Aprobar y
  ejecutar siguen siendo acciones separadas en Tareas.

| Estado | Qué dice | ¿Salió? | ¿Cobro? |
|---|---|---|---|
| Esperando | "Esperando a Cloud · cancelar deja de esperar, pero puede no evitar el cobro" | Sí | En curso |
| Cancelado | "Dejaste de esperar. Si ya había llegado al proveedor, puede cobrarse igual." | Puede | Posible |
| No enviado | Falta consentimiento, Cloud bloqueado, límites/historial, o gateway sin respuesta | No | No |
| Presupuesto agotado | "No se envió nada. Vuelve al renovarse el tope diario o mensual." | No | No |
| Resultado incierto | "Pudo procesarse y cobrarse. No se reintenta." + **Consultar estado** | Sí | Posible |

Un resultado incierto nunca se reenvía solo. "Consultar estado" lee el gateway y no vuelve a llamar
al proveedor. Si la persona quiere otra respuesta, escribe un pedido nuevo.

## Cuándo se puede activar

`arkos_pilot/cloud_link.py` comprueba **antes de cada turno**:

1. El gateway responde `/v1/status` con el mismo digest de condiciones que muestra la pantalla.
2. Si el gateway informa un proveedor **real**, exige `terms_verified: true`. El ejemplo del piloto
   tiene `false`, así que **la activación real queda bloqueada**. Además, `python -m arkos_cloud serve`
   se niega a arrancar con un proveedor real si las condiciones no están verificadas.
3. Existe consentimiento para ese digest exacto. Los límites de gasto forman parte del digest:
   cambiarlos exige volver a aceptar.

El selector (`arkos_pilot.providers`) acepta `cloud` solo para esa sesión guardada, y el chat local
no puede ser Cloud. No hay fallback entre modos.

## Probar con el proveedor falso

```bash
python -m pip install -r requirements-cloud.txt
python scripts/Run-ArkosCloudTrial.py --state-dir <carpeta-de-prueba>
```

Abre el navegador con el centro de tareas: Local usa el runner sintético y Cloud recorre el gateway
HTTP real y el SDK oficial contra una API falsa en loopback. Todo es local y no hay claves.

Pruebas automáticas:

```bash
python -B -m unittest discover -s tests -v                       # incluye tests/test_cloud_center.py
ARKOS_TEST_PYTHON=<python con requirements-cloud> node scripts/Test-ArkosCloud.cjs
node scripts/Test-ArkosChat.cjs                                  # Local, sin regresiones
```

En contenedores o como root, Chromium necesita un ejecutable sin sandbox:
`ARKOS_TEST_CHROMIUM=/ruta/a/chrome-con---no-sandbox`. Con esa variable, la prueba de Cloud también
desactiva el sandbox de Playwright.

## Uso con un gateway propio (sigue bloqueado para proveedores reales)

```bash
ARKOS_CLOUD_DEVICE_TOKEN=akc_… python -m arkos_pilot.task_center --state-dir <dir> \
  --cloud-config <cloud-client.json> [--cloud-ca-file <ca.pem>]
```

El token del dispositivo es de ARKOS y revocable. Nunca es la clave del proveedor y se lee de una
variable de entorno, no de un argumento.

## Evidencia (`docs/task-center/cloud-screenshots/`)

`desktop-cloud-consent`, `desktop-cloud-conversation`, `desktop-cloud-cancelled`,
`desktop-cloud-uncertain`, `desktop-cloud-budget`, `mobile-cloud-consent`,
`mobile-cloud-conversation` y `browser-results.json`, todos con datos sintéticos.

## Pendiente antes de un proveedor real

Ver `docs/CLOUD_PILOT_REAL.md` (condiciones verificadas, hosting y prueba mínima).


Verificar la retención y las condiciones del proveedor (`terms_verified`), el hosting de una
sola instancia con backups, TLS del dominio y una clave de workspace dedicado con su propio
límite. Luego, un PR que solo cambie `terms_verified` y la URL, con revisión humana.
