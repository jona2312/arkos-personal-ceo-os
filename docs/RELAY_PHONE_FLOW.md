# Recorrido celular → cola → PC → resultado en el celular

Estado: **código y pruebas con datos sintéticos. No desplegado.** Base: relay (#2) y visor (#4).
No se tocó la interfaz de escritorio, la voz, el arranque local, Hermes ni `D:\ARKOS`.

```
Celular (/m/)                 Relay (cola SQLite)                  Agente Windows (saliente)
 crea nota ───────────────▶  awaiting_approval
 revisa + huella local ───▶  approved (vence en 1/8/24 h)
 ve "PC desconectada"         (espera; la PC está apagada)
                                        ◀──── claim / start / complete ── PC inicia sesión
 ve "Hecha" + archivo  ◀────  succeeded {name, bytes, sha256}
```

## Qué estaba hecho y qué agrega esta rama

| Pieza | Antes (#2/#4) | Esta rama |
|---|---|---|
| Cola, aprobaciones con huella, leases, inciertos, agente con diario | Sí | Se reutilizan sin cambios de semántica |
| Cliente del celular | Solo API | `GET /m/`: crear nota, revisar y aprobar con huella calculada en el celular, seguir el estado, resolver inciertos, reintentar, vincular y revocar PCs |
| "¿La PC está disponible?" | `last_seen_at` crudo | `presence` en `/v1/devices`: `online` (llamó hace ≤ 90 s), `offline`, `never_seen`, `revoked` |
| Vencimiento visible | No | `approval_expires_at` en las vistas del usuario |
| Mensajes de error del agente | Podían incluir rutas absolutas de la PC | Se reemplazan por `<ruta local>` (defecto encontrado en esta rama) |
| Encendido remoto | — | Solo diagnóstico: `scripts/Get-ArkosWakeReadiness.ps1` (sección 4) |

## 1. Lo que ve el celular en cada estado

| Estado | Mensaje | Acciones |
|---|---|---|
| `awaiting_approval` | "Revisá el contenido y aprobalo". Si vino de un vencimiento: "La aprobación venció antes de que la PC la tomara. No se ejecutó nada." | Revisar y aprobar · Rechazar · Cancelar |
| `approved` | Según la PC: conectada / desconectada / nunca se conectó / revocada. Muestra hasta cuándo vale la aprobación | Cancelar |
| `claimed` | "La PC la reservó y todavía no hizo nada" | Cancelar |
| `running` | "La PC la está ejecutando. Ya no se puede cancelar" | — |
| `succeeded` | Resultado: nombre del archivo, bytes, sha256 | — |
| `failed` | "No se produjo ningún efecto" + motivo | Crear de nuevo (pide nueva aprobación) |
| `unknown` | "La PC empezó pero no pudo confirmar. No se repite sola" | "Ya revisé la PC" → Sí se creó / No se creó · Crear de nuevo (exige "Entiendo que puede quedar duplicado") |

Si la aprobación vence **entre la reserva y el inicio**, el agente la rechaza localmente, no ejecuta y la tarea
queda `failed` ("Aprobación vencida"). Se vuelve a crear desde el celular.

## 2. Seguridad del cliente

- Sin código externo. Política de contenido: solo scripts y estilos propios, sin `inline`, sin marcos
  (`frame-ancestors 'none'`), `no-referrer`. Todo el texto se pinta con `textContent`.
- El token de usuario no viaja en la URL. Por defecto vive en `sessionStorage` (se olvida al cerrar la pestaña).
  Con "Recordar en este celular" queda en `localStorage` hasta "Salir". Un XSS podría leerlo: por eso la
  política de contenido estricta y ningún HTML dinámico.
- La huella se calcula en el celular con WebCrypto, a partir de lo que se muestra. Si no coincide con la del
  relay, no se aprueba. WebCrypto exige HTTPS (o `localhost`): **por HTTP en la red local no se puede aprobar**,
  y es intencional.
- Reenviar después de un corte usa el mismo `client_request_id`: no duplica.
- Límite heredado: el relay guarda el texto en claro (TLS en tránsito, sin cifrado de extremo a extremo).

## 3. Pruebas sintéticas incluidas

`tests/test_relay_phone_flow.py`: relay real por HTTP, agente real y reloj simulado.

| Caso | Qué se comprueba |
|---|---|
| PC apagada → reconexión | La tarea espera aprobada; al conectar, se ejecuta una vez; el resultado y `presence` llegan al celular |
| Reenvío del celular | Mismo id → `deduplicated`; mismo id con otro texto → 409 |
| Corte durante el informe | Efecto hecho, respuesta perdida, red caída; al reconectar se reenvía el mismo informe; un solo archivo |
| Reinicio del relay | La cola sobrevive |
| Aprobación vencida con la PC apagada | Nunca se ejecuta; vuelve a "pendiente" con motivo; re-aprobada se ejecuta una vez |
| Vence entre reserva e inicio | El agente no inicia; `failed` sin efecto |
| Resultado incierto (la PC muere a mitad) | `running` → `unknown` al vencer el lease; al volver no se re-ejecuta; reintento exige reconocer el duplicado y una aprobación nueva |
| Rutas locales | Un error de disco no publica rutas de la PC |
| Página | Cabeceras estrictas, sin sumideros de HTML dinámico, sin rutas fuera de `/m/` |
| Contrato JS ↔ Python | Mismos bytes canónicos (comillas, barras, controles, emoji, U+2028, enteros); floats rechazados; mensajes por estado |

`scripts/Test-ArkosPhone.cjs` (Playwright, viewport 390×844) recorre la página real contra
`python -m arkos_relay serve` y el agente por CLI: vincular desde el celular, PC nunca vista, nota con texto hostil,
huella igual a la del relay, espera, ejecución, resultado, incierto resuelto por el usuario. Capturas en
`docs/relay-phone-evidence/`.

## 4. Encendido remoto: solo diagnóstico

No se implementa ni se cambia nada. `scripts/Get-ArkosWakeReadiness.ps1` (solo lectura, sin MAC, IP ni nombres
de red) informa: adaptador Ethernet físico, "Wake on Magic Packet", ajustes del driver, dispositivos que pueden
despertar el equipo, estados de suspensión, inicio rápido, batería y puerta de enlace.

Requisitos para que funcione de verdad:

1. **Equipo:** Ethernet por cable; WoL habilitado en BIOS/UEFI; "ErP/Deep Sleep" deshabilitado; Windows con
   "Wake on Magic Packet". Con inicio rápido activo, el apagado S5 puede no despertar en algunas placas.
   Desde suspensión (S3) es lo más confiable.
2. **Red:** el paquete mágico tiene que salir **desde dentro de la LAN**. El relay en internet no llega sin abrir
   puertos ni hacer broadcast dirigido, y no lo vamos a hacer. Hace falta un emisor siempre encendido en la casa
   (router con función WoL, NAS o un equipo chico) que consulte el relay por conexión saliente y envíe el paquete.
3. **Alternativas sin red:** "encender al volver la energía" en BIOS más un enchufe inteligente, o un encendido
   programado (RTC). Las dos se deciden aparte.

Hasta decidirlo, el recorrido funciona así: la tarea espera en la cola y se ejecuta cuando Jona enciende la PC
e inicia sesión.

## 5. Pasos para probar en la PC (Windows, checkout aislado, sin desplegar)

Todo corre en `127.0.0.1` con datos sintéticos, en una carpeta nueva fuera de `D:\ARKOS`.

```powershell
git clone https://github.com/jona2312/arkos-personal-ceo-os.git C:\arkos-phone-test
cd C:\arkos-phone-test
git checkout claude/arkos-relay-phone-flow
python -m unittest tests.test_relay_phone_flow -v          # 13 pruebas, sin red externa

# 1) Relay local y usuario de prueba
python -m arkos_relay admin --db $env:TEMP\arkos-phone\relay.sqlite3 create-user --name "Prueba"   # copiar "token"
python -m arkos_relay serve --db $env:TEMP\arkos-phone\relay.sqlite3 --port 8787                  # dejar abierta
```

En Edge o Chrome: `http://127.0.0.1:8787/m/`, F12 → vista de dispositivo móvil, pegar el token.

| # | Paso | Esperado |
|---|---|---|
| 1 | "PCs vinculadas" → nombre → Generar código | Código de 12 caracteres |
| 2 | Otra consola: `$s="$env:TEMP\arkos-phone\agent"; python -m arkos_relay agent --state-dir $s pair --server http://127.0.0.1:8787 --code <CÓDIGO> --allow-insecure-localhost` | La PC aparece como "Nunca se conectó" |
| 3 | Celular: escribir una nota → Dejar encargo → Aprobar (1 h) | "Aprobada", "La PC todavía no se conectó" y hasta cuándo vale |
| 4 | `python -m arkos_relay agent --state-dir $s run --once` | En ≤ 10 s: "Hecha", archivo `.md`; PC "Conectada". El archivo está en `$s\outputs\notes` |
| 5 | Esperar 2 min sin el agente | PC "Desconectada" |
| 6 | Nueva nota, aprobar; recién al rato correr el agente | Se ejecuta al conectar (PC apagada → disponible) |
| 7 | Incierto: borrar `$s\outputs\notes`, crear un **archivo** llamado `notes`, nueva nota, aprobar, `run --once` dos veces | "Resultado incierto", una sola ejecución, sin rutas de la PC en el mensaje; "Ya revisé la PC" → "No se creó" |
| 8 | Revocar la PC desde el celular y correr el agente | El agente se detiene y pide volver a vincular |
| 9 | `./scripts/Get-ArkosWakeReadiness.ps1` | JSON con hallazgos; no cambia nada |

La aprobación vencida no se puede esperar a mano (mínimo 1 h): la cubren las pruebas con reloj simulado.
Para probar con un celular real hace falta el relay con HTTPS en un host. Eso es despliegue y queda pendiente
de aprobación.
