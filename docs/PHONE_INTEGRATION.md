# Integración: celular + relay con pantalla, voz y launcher de Codex

Rama `claude/arkos-phone-voice-integration` =
- `codex/arkos-local-voice` (#21 @ `1c704c1`, candidato actual de Codex),
- más `claude/arkos-relay-phone-flow` (#22 @ `ed5c107`),
- más las correcciones de esta integración.

Las ramas originales no se modificaron. **No desplegado.**

## 1. Convivencia

| Pieza | Proceso | Puerto / estado | Interacción con el relay |
|---|---|---|---|
| Pantalla, voz y dictado (`arkos_pilot`, Codex) | Centro de tareas local | `127.0.0.1:8765`, estado propio del launcher | Solo lee el snapshot del visor (`relay_snapshot.py`); no reserva ni ejecuta |
| Launcher (`Open-Arkos.ps1` / `Start-Arkos.ps1`) | Arranque guiado | No inicia el relay ni el agente | Ninguna |
| Agente del relay | `python -m arkos_relay agent run` | Solo saliente; `%LOCALAPPDATA%\ArkosRelayAgent` | Único proceso que reserva y ejecuta |
| Relay + cliente móvil | `python -m arkos_relay serve` | Por defecto **8787**, el mismo que el gateway Cloud | En pruebas locales usar **8790** |

El único conflicto de la fusión fue el workflow de CI, y se conservaron los pasos de ambos lados.

## 2. Correcciones de la integración

1. **Aprobación vencida entre reserva e inicio.** El contrato (§2) dice que una aprobación vencida vuelve a
   `awaiting_approval` sin efecto. Antes, el resultado dependía de qué compuerta la detectaba:
   - el relay, en `start` → `awaiting_approval`;
   - el reloj del agente → `failed`.

   La prueba de #22 había fijado este segundo caso. Ahora:
   - el relay libera de inmediato las tareas `claimed` cuya aprobación ya no vale;
   - responde 409 `approval_expired` a la PC que tenía la reserva;
   - el agente, si lo detecta por su reloj, abandona sin informar `failed`.
2. **Rutas locales en otros errores.** #22 cubría un caso, pero quedaban fugas:
   - la verificación previa (archivo de origen inexistente → ruta absoluta);
   - la salida de FFmpeg (rutas con espacios y nombres de archivo);
   - informes de agentes anteriores.

   Ahora:
   - fuera de la PC solo viajan mensajes propios, la clase del error y su `errno`, y el detalle queda en el
     registro local;
   - el agente y el relay además redactan cualquier ruta, incluso entre comillas y con espacios.
3. **Consultar no tiene efectos.** Hay una prueba nueva: presencia, lista, detalle, visor de la pantalla y
   página `/m/`, repetidos, no reservan, no ejecutan, no cambian la versión y no marcan la PC como conectada.

## 3. Aceptación en nuestra PC (Windows, checkout aislado, datos sintéticos)

No toca `D:\ARKOS`, Hermes, perfiles ni credenciales reales. Todo en `127.0.0.1`.

```powershell
# 0) Copia aislada
git clone https://github.com/jona2312/arkos-personal-ceo-os.git C:\arkos-int
cd C:\arkos-int
git checkout claude/arkos-phone-voice-integration
git rev-parse HEAD                                   # anotar el SHA probado

# 1) Pruebas automáticas
python -m unittest discover -s tests -v              # toda la suite (pantalla, voz, relay, celular)
node scripts\Test-ArkosVoice.cjs                     # máquina de estados de voz (Codex)
node scripts\Test-ArkosDictation.cjs
node scripts\Test-ArkosRemoteView.cjs
# Con Playwright instalado (npm i -g playwright; $env:NODE_PATH = "$(npm root -g)"):
node scripts\Test-ArkosPhone.cjs                     # página real del celular + relay + agente

# 2) Convivencia: pantalla de Codex abierta mientras corre el relay
$d = "$env:TEMP\arkos-int"
./scripts/Open-Arkos.ps1 -StateDirectory $d\screen -CheckOnly   # el launcher no inicia relay ni agente
python -m arkos_relay admin --db $d\relay.sqlite3 create-user --name "Prueba"     # copiar "token"
python -m arkos_relay serve --db $d\relay.sqlite3 --port 8790                     # consola aparte
```

En Edge, `http://127.0.0.1:8790/m/` con la vista de celular (F12), pegando el token:

| # | Acción | Esperado |
|---|---|---|
| 1 | PCs vinculadas → Generar código; en otra consola: `python -m arkos_relay agent --state-dir $d\agent pair --server http://127.0.0.1:8790 --code <CÓDIGO> --allow-insecure-localhost` | "Nunca se conectó" |
| 2 | Nota → Dejar encargo → Aprobar 1 h | "Aprobada", la PC no se conectó; la pantalla de ARKOS sigue respondiendo y la voz no cambia |
| 3 | `python -m arkos_relay agent --state-dir $d\agent run --once` | En ≤ 10 s: "Hecha" con el archivo; PC "Conectada" |
| 4 | 2 minutos sin agente | "Desconectada" |
| 5 | Pantalla de ARKOS leyendo el relay (ver bloque siguiente) | El centro de tareas muestra las mismas tareas; voz y conversación funcionan; ningún estado cambia en el celular |
| 6 | Incierto: reemplazar `$d\agent\outputs\notes` por un **archivo** con ese nombre, nueva nota aprobada, `run --once` dos veces | "Resultado incierto", una sola ejecución; el mensaje dice `FileExistsError (errno 17)`, sin rutas |
| 7 | Revocar la PC en el celular, `run --once` | El agente se detiene: hay que volver a vincular |
| 8 | `./scripts/Get-ArkosWakeReadiness.ps1` | JSON de diagnóstico; no cambia nada |

Paso 5, pantalla de Codex junto al relay (credencial de solo lectura, separada de la del agente):

```powershell
$token = "<token aku_ que imprimió create-user>"
$dev = (Get-Content $d\agent\agent.json | ConvertFrom-Json).device_id
$code = (Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8790/v1/devices/$dev/viewer-codes" `
          -Headers @{ Authorization = "Bearer $token" }).code
python -m arkos_relay agent --state-dir $d\agent viewer-pair --code $code
python -m arkos_relay agent --state-dir $d\agent view-sync --once
./scripts/Open-Arkos.ps1 -StateDirectory $d\screen -RelaySnapshot $d\agent\viewer\relay-snapshot.json -RelayDeviceId $dev
```

La aprobación vencida no se puede esperar a mano (mínimo 1 h); la cubren las pruebas con reloj simulado:
`python -m unittest tests.test_relay_phone_flow -k approval -v`.

Para limpiar: cerrar el relay y borrar `$d`. No quedan servicios instalados.

## 4. Propuesta: acceso HTTPS privado para el teléfono (sin desplegar)

**Restricción de base:** el relay no puede vivir en la PC, porque su función es recibir encargos mientras la
PC está apagada. Necesita un host siempre encendido. Además, la aprobación exige HTTPS de verdad: WebCrypto
no funciona sobre HTTP fuera de `localhost`.

| Opción | Exposición | Quién ve el texto de las tareas | Costo / operación | Veredicto |
|---|---|---|---|---|
| **A. Tailscale + `tailscale serve`** en el VPS existente; celular y PC en la misma red privada (tailnet) | Ninguna pública: el relay escucha en `127.0.0.1` y solo lo alcanzan los equipos de la tailnet | Solo el VPS: el tráfico va cifrado de equipo a equipo (WireGuard) y el TLS termina en el VPS | Plan personal; app en celular y PC; sin cambios de router | **Recomendada** |
| B. Cloudflare Tunnel + Cloudflare Access | Nombre público, protegido por Access | Cloudflare termina TLS y puede ver el texto | Gratis; cuenta y DNS en Cloudflare | Aceptable si se prioriza no instalar apps; peor privacidad |
| C. Caddy público en el VPS (como el gateway Cloud) | Puerto 443 abierto a internet; protege solo el token | Solo el VPS | Mínimo | No para datos personales: superficie pública |
| D. WireGuard propio en el VPS | Ninguna pública | Solo el VPS | Más operación (claves, configuración en el celular) | Alternativa a A si no queremos un tercero |

**Plan A, paso a paso** (para cuando se apruebe; nada de esto se ejecutó):

1. En el VPS, un usuario o contenedor separado de n8n:
   `python -m arkos_relay serve --db /var/lib/arkos-relay/relay.sqlite3 --host 127.0.0.1 --port 8790`
   como servicio systemd, reutilizando el endurecimiento de `deploy/cloud-gateway/arkos-gateway.service`.
2. Instalar Tailscale en el VPS, la PC y el celular, con la misma cuenta. En la consola de Tailscale:
   activar MagicDNS y certificados HTTPS. Crear una ACL que permita **solo** celular y PC → VPS:443.
3. En el VPS: `tailscale serve --bg --https=443 http://127.0.0.1:8790`. El relay queda en
   `https://<vps>.<tailnet>.ts.net/m/`, con certificado válido y solo dentro de la tailnet.
   **No** usar `tailscale funnel`, que lo publicaría en internet.
4. Sin cambios de router ni de firewall entrante. Verificar: `curl` desde fuera de la tailnet falla, y desde
   el celular abre `/m/`.
5. PC: `Start-ArkosAgent.ps1 pair --server https://<vps>.<tailnet>.ts.net --code …`. Las conexiones siguen
   siendo solo salientes.
6. Backups: copia diaria de la base de datos del relay con la misma rutina que el ledger Cloud
   (`integrity_check`, permisos 600, rotación).

**A verificar antes de ejecutar** (no pude leer `tailscale.com` desde este entorno: la red lo bloquea):

- **Nombres de los equipos:** los certificados HTTPS de `ts.net` se publican en los registros públicos de
  transparencia de certificados, con el nombre del equipo y de la tailnet. Usar nombres que no identifiquen
  a nadie.
- **Opciones y planes:** confirmar los nombres actuales de las opciones de `serve`, MagicDNS, los
  certificados y la sintaxis de las ACL, y las condiciones del plan personal.
- **Cuenta:** Tailscale coordina las claves y ve los metadatos de qué equipos hay; no ve el contenido.

## 5. Qué datos quedan en el relay

**Hoy el texto se guarda sin cifrado de extremo a extremo.** Hay TLS en tránsito. En el disco del host, el
relay guarda en claro (SQLite):

| Dato | Dónde | Forma |
|---|---|---|
| **Texto completo de notas y documentos**, nombre de archivo, alias de carpeta y ruta relativa de recortes | `tasks.params` | **En claro** |
| Resultado: mensaje, nombre del archivo creado, bytes, sha256 | `tasks.result`, `task_events.detail` | En claro (sin contenido ni rutas absolutas) |
| Historial de estados con fechas y actores (IDs de usuario y dispositivo) | `task_events` | En claro |
| Huellas de aprobación, vencimientos y consumo | `approvals` | En claro (no revelan el texto) |
| Nombre visible del usuario y nombres de las PCs; última conexión de cada PC | `users`, `devices` | En claro |
| Tokens de usuario, PC y visor; códigos de vinculación | `*_tokens`, `*_codes` | Solo SHA-256 |
| Si se activa WhatsApp: número vinculado, ID de mensaje y texto de las respuestas | `channel_*` | En claro (desactivado) |

No hay borrado automático: todo queda hasta que se borre el archivo. Quien tenga acceso al disco o a un
backup del host lee las notas.

Mitigaciones propuestas, sin implementar, en orden de costo:

1. **Retención:** al terminar una tarea, borrar `params.text` después de N días (por ejemplo, 7) y conservar
   solo la huella y los metadatos. Es barata y reduce casi todo el riesgo.
2. **Disco cifrado y backups cifrados** en el host (restic con clave fuera del VPS).
3. **Cifrado de extremo a extremo:**
   - el celular cifra `params` con una clave pública de la PC y el relay solo ve el texto cifrado y la huella;
   - el agente lo descifra con una clave protegida por DPAPI;
   - requiere cambiar el contrato: la huella se calcula sobre el texto en claro y el relay ya no puede
     validarlo, sino solo transportarlo;
   - la vista previa en el celular sale de su propio registro local;
   - es el cambio correcto si el relay pasa a un host de terceros. Se diseña aparte.
