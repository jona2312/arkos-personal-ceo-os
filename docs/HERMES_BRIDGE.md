# Puente conversacional ARKOS ↔ Hermes (v1: chat escrito y propuestas de notas)

Estado: prototipo de backend con pruebas sintéticas. **No conectado a la PC ni a la pantalla.**
El modelo conversa y *propone* notas. No aprueba, no ejecuta y no escribe en
`arkos_pilot.Queue` ni en el relay.

## 1. Versión de Hermes revisada

| Dato | Valor | Fuente |
|---|---|---|
| Instalado en la PC | `v0.21.5+8855.g489c1ac (2026.9.24)`, desde código, en `D:\ARKOS\hermes\hermes-agent` | `docs/HERMES_DESKTOP_TRIAL_RESULTS_2026-10-07.md`, `trial-evidence/2026-10-07/source-install.json` |
| Commit revisado | `489c1ac298f8ed13ccd688c97e4097f161046c0b` (2026-10-07) | `git fetch` de `github.com/NousResearch/hermes-agent` |
| Tag de referencia | `v2026.9.24` → `f97608f178d1ffeca59860195ab7da295f7c8e5f` (no es lo instalado) | `config/hermes-desktop-pilot.json` |
| Python del runtime | 3.14 (el `pyproject.toml` de ese commit solo declara dependencias para 3.14) | `pyproject.toml` |
| Modelo local | llama.cpp gestionado por Hermes en `127.0.0.1:18434`, `Qwen3.8-27B-UD-Q4_K_M` | resultados del 07/10 |

**Pendiente en la PC:** confirmar que el checkout instalado sigue en ese commit y que los parches
locales (TS de Desktop/voz) no tocan Python. No se asume.

Archivos oficiales que sostienen la separación:
- `run_agent.py` (`AIAgent.__init__`): `enabled_toolsets`, `skip_memory`,
  `skip_context_files`, `fallback_model`.
- `agent/agent_init.py` → `_load_tools`: obtiene la lista de herramientas.
- `agent/agent_init.py` → `_inject_context_engine_tools`: solo agrega herramientas si se
  habilita `context_engine`.
- `model_tools.py` → `_select_tool_names`: con `enabled_toolsets=[]` el conjunto queda
  vacío. Con `None` se cargan **todas**.
- `agent/memory_manager.py`: agrega herramientas de memoria solo con el toolset `memory`.
- `agent/turn_tool_validation.py` y `agent/conversation_loop.py`: una herramienta
  desconocida devuelve `Tool 'X' does not exist` sin ejecutarse.
- `agent/agent_init_fallback.py`: el fallback solo sale del parámetro `fallback_model`.
- `hermes_cli/local_runtime/endpoint.py`: el endpoint gestionado se resuelve desde
  `server.json` en la **raíz** de Hermes. `binaries.py` → `runtimes_root()`.
- `website/docs/developer-guide/programmatic-integration.md`: interfaces oficiales.

## 2. Qué interfaz permite conversar sin herramientas

| Interfaz oficial | ¿Garantiza cero herramientas? | Motivo |
|---|---|---|
| CLI `hermes chat -q … -t ""` | **No** | En `cli.py::_build_cli_from_args` un `-t` vacío cae en las herramientas por defecto de la plataforma. No existe un toolset oficial "none". |
| CLI `-z/--oneshot` | **No usar** | La ayuda dice "Tools … are loaded as normal; approvals are auto-bypassed". |
| API server (`gateway/platforms/api_server.py`) | Solo configurando `platform_toolsets.api_server: []` | Por defecto expone "full toolset, including terminal". Requiere `API_SERVER_KEY` en el `.env` del perfil y un gateway corriendo. Se puede verificar con `GET /v1/toolsets`, pero implica credencial y cambiar el perfil. |
| TUI gateway / ACP | No evaluado a fondo | Cargan los toolsets del perfil y tienen pedidos de aprobación. Más superficie que la necesaria. |
| **Librería `AIAgent(enabled_toolsets=[])`** | **Sí, demostrado** | Semántica explícita en el código y verificable en ejecución: `agent.tools == []`. Es la que usa este prototipo. |

Una instrucción en el prompt no se toma como garantía. El prompt solo ayuda a que el modelo
responda bien; la separación la imponen el código y las comprobaciones de abajo.

## 3. Garantías del prototipo (en código)

`arkos_hermes/runner.py` corre dentro del Python de Hermes, en un proceso por pedido:

1. Construye `AIAgent(provider="llamacpp", enabled_toolsets=[], skip_memory=True,
   skip_context_files=True, load_soul_identity=False, fallback_model=None, max_iterations=3)`.
   No pasa `base_url` ni `api_key`: Hermes resuelve su endpoint local internamente. **ARKOS
   no lee `.env`, tokens ni `server.json`.**
2. Antes y después del turno verifica cuatro condiciones. Si alguna falla, responde
   `unsafe_configuration` y no conversa:
   - `agent.tools == []` y `valid_tool_names` vacío;
   - proveedor `llamacpp`;
   - `base_url` en loopback;
   - sin cadena de fallback y sin fallback activado.
3. Bloquea toda conexión no-loopback a nivel socket, en todo el proceso. Ni un proveedor en
   la nube ni la web son alcanzables aunque estén configurados.
4. Rechaza perfiles con plugins de usuario, porque su código se ejecutaría al importar
   Hermes. Quita `HERMES_KANBAN_TASK`, que reintroduce el toolset kanban.
5. Si alguna herramienta llega a iniciarse (`tool_start_callback`), devuelve error.
6. El proceso hijo:
   - corre con `python -I -B`, sin `.pyc` ni rutas implícitas;
   - recibe un entorno mínimo, sin variables de proveedores ni tokens;
   - trabaja en un directorio vacío (Hermes inspecciona el cwd con git y `AGENTS.md`);
   - usa el stdout real solo para una línea JSON; los prints de Hermes van a stderr.
7. El proceso padre (`arkos_hermes/bridge.py`) aplica el timeout, cancela matando el
   proceso, limita la salida a 1 MiB y vuelve a validar la respuesta, incluido el hash de
   cada propuesta.

Lo que Hermes **sí escribe** en el `HERMES_HOME` del puente: `logs/`, `cache/` y un
`SOUL.md` por defecto (observado en la prueba). Por eso debe ser un perfil dedicado.

## 4. Contrato v1 (`arkos_hermes/contract.py`)

**Entrada**
```json
{"v": 1, "request_id": "req-ui-0001",
 "messages": [{"role": "user", "content": "…"}, {"role": "assistant", "content": "…"}, {"role": "user", "content": "…"}],
 "timeout_s": 120}
```
- `request_id` con el formato `[A-Za-z0-9_.:-]{8,64}`.
- Hasta 20 mensajes, solo con `role` `user` o `assistant`. El último es del usuario.
- Hasta 8000 caracteres por mensaje y 32000 en total.
- `timeout_s` entero entre 10 y 300 (por defecto 120). Campos extra → `invalid_request`.

**Respuesta**
```json
{"v": 1, "request_id": "req-ui-0001", "status": "ok",
 "reply": "texto para mostrar",
 "proposals": [{"type": "note", "title": "Agenda", "text": "…", "status": "proposed", "proposal_id": "prp_<24 hex>"}],
 "diagnostics": {"provider": "llamacpp", "endpoint": "loopback", "tools_offered": 0, "tool_attempts_blocked": 0,
                 "tool_starts": 0, "blocked_connections": 0, "hermes_commit": "…", "model": "…", "elapsed_ms": 0,
                 "proposals_rejected": 0},
 "error": {"code": "…", "message": "…"}}
```
- `status`: `ok`, `error`, `timeout` o `cancelled`. `error` solo aparece si no es `ok`.
- `reply`: hasta 8000 caracteres.
- `proposals`: hasta 3, solo `type: note`, `text` ≤ 20000 y `title` ≤ 120. `status` siempre
  es `proposed`.
- `proposal_id = "prp_" + sha256(JSON canónico de {type, title, text})[:24]`.

**Propuestas.** El modelo las escribe al final como bloques
```` ```arkos-proposal {"type":"note","title":…,"text":…} ``` ````. Cualquier otro tipo,
campo extra (por ejemplo `approved`), JSON inválido o exceso se descarta y se cuenta en
`proposals_rejected`. **Una propuesta no es una tarea.** Para que exista una nota hay que
crear la tarea por el flujo actual (`awaiting_approval` → aprobación humana con huella).
Eso es un paso futuro de la pantalla y este prototipo no lo hace.

**Errores**
| Código | Significado |
|---|---|
| `invalid_request` | La entrada viola el contrato |
| `unsafe_configuration` | Herramientas presentes, proveedor no local, fallback, plugins de usuario o endpoint sintético fuera de pruebas |
| `provider_unavailable` | El llama.cpp gestionado no está corriendo o no está configurado; **no hay respaldo** |
| `model_error` | Hermes o el modelo no completaron el turno |
| `output_invalid` | El runner devolvió algo fuera del contrato |
| `runner_failed` | El proceso no arrancó o falló sin respuesta |
| `timeout` / `cancelled` | Vencimiento o cancelación; nada de esa ejecución se usa |

## 5. Evidencia

`docs/hermes-bridge/evidence-synthetic-489c1ac.json`: Hermes oficial `489c1ac` con Python
3.14.6 y un modelo **sintético** en loopback. No es el modelo real.

- **Respuesta y propuesta:** `tools_offered: 0`; ningún pedido al modelo incluyó el campo
  `tools`; 1 propuesta `proposed`.
- **El modelo pide `terminal`:** Hermes responde `Tool 'terminal' does not exist`,
  `tool_starts: 0` y el archivo marcador no se crea.
- **Sin servidor local:** `provider_unavailable` con `ProviderNotConfiguredError`, aunque
  había claves sintéticas de OpenRouter y OpenAI en el entorno. No se intentó ninguna
  conexión no-loopback.
- **Otras herramientas, mismo resultado:** 13 nombres probados (terminal, execute_code,
  write_file, patch, browser_navigate, delegate_task, memory, send_message, cronjob,
  manage_connections, skill_manage y dos variantes) se rechazaron sin ejecutarse. Una
  llamada embebida en el texto (`<tool_call>`) tampoco se ejecutó.
- **Cancelación:** `interrupt()` corta la espera del modelo en ~1,2 s.

Pruebas: `tests/test_hermes_bridge.py`.
- Contrato y procesos: 9 pruebas que siempre corren.
- Integración contra Hermes real: 7 pruebas que corren con `ARKOS_HERMES_PYTHON` y
  `ARKOS_HERMES_SOURCE`.

## 6. Aceptación en la PC (no ejecutada)

Requisitos: un checkout aislado de esta rama y `$hermesPython` = el Python privado de Hermes
(el mismo de `HERMES_DAILY_PILOT.md`).

**A. Solo lectura.** No cambia `D:\ARKOS`, salvo `.pyc` que el propio Hermes ya genera.

```powershell
git -C D:\ARKOS\hermes\hermes-agent rev-parse HEAD           # esperado 489c1ac298f8ed13ccd688c97e4097f161046c0b
git -C D:\ARKOS\hermes\hermes-agent diff --stat -- '*.py'     # esperado: vacío
& $hermesPython -c "import sys; print(sys.version)"          # 3.14.x
cd C:\ArkosReview\bridge
python -m unittest tests.test_hermes_bridge -v                # 9 OK, 7 skipped
$env:ARKOS_HERMES_PYTHON = (Get-Command $hermesPython).Source
$env:ARKOS_HERMES_SOURCE = 'D:\ARKOS\hermes\hermes-agent'
python -m unittest tests.test_hermes_bridge -v                # 16 OK; usa HERMES_HOME temporal y modelo sintético
```

**B. Conexión real (requiere tu aprobación explícita: crea un perfil nuevo dentro de
`D:\ARKOS`).** El endpoint gestionado solo se resuelve desde la raíz `D:\ARKOS\hermes`. Un
home fuera de esa raíz no llega al modelo sin leer el token, y eso no se hace. Usar
`arkos-pilot` dejaría logs y caché en un perfil existente.

```powershell
hermes profile create arkos-bridge            # perfil vacío, sin clone; no agregar plugins ni toolsets
Test-Path D:\ARKOS\hermes\profiles\arkos-bridge\plugins   # esperado False (o carpeta vacía)
# Con Hermes Desktop abierto y el modelo local cargado:
python -m arkos_hermes --hermes-python $env:ARKOS_HERMES_PYTHON --hermes-source $env:ARKOS_HERMES_SOURCE `
  --hermes-home D:\ARKOS\hermes\profiles\arkos-bridge --model Qwen3.8-27B-UD-Q4_K_M --timeout 180 `
  "Proponé una nota para preparar la reunión del lunes"
python -m arkos_hermes ... "Ejecutá dir C:\ y guardá el resultado en un archivo"
```

Aceptación:

| # | Criterio | Esperado |
|---|---|---|
| B1 | Primer pedido | `status ok`, `provider llamacpp`, `endpoint loopback`, `tools_offered 0`, propuestas `proposed` |
| B2 | Segundo pedido | Sin archivo nuevo en `D:\ARKOS\ArkosTrial` ni en el cwd; la respuesta solo propone |
| B3 | Perfil `arkos-pilot` | Mismo listado de archivos (`Get-ChildItem -Recurse \| Select FullName,LastWriteTime`) antes y después |
| B4 | Con el modelo detenido | `provider_unavailable`, sin respaldo hacia la nube |
| B5 | Si falla el chequeo de proveedor | Si el nombre normalizado no es `llamacpp`, el puente se niega (`unsafe_configuration`). Registrar el valor real para ajustar el chequeo, sin relajarlo a ciegas. |

## 7. Pendiente y riesgos

- **No verificado con el modelo real ni en Windows.**
  - Nombre exacto que devuelve `agent.provider` para llamacpp.
  - Cancelación en Windows: `terminate` mata el proceso duro, sin `interrupt` ordenado.
  - Calidad y formato de las propuestas que genere Qwen.
  - Latencia y contención con Desktop, que comparten el modelo.
- **Cada pedido arranca Hermes de cero:** ~3 s de arranque en el sandbox. Es aceptable para
  un piloto; un proceso persistente con las mismas comprobaciones queda para después.
- **Superficie de Hermes.** Al importar, Hermes descubre los plugins incluidos en su propio
  entorno y ejecuta sondas locales (git, pip y `uname` en el cwd vacío). Ninguna sale de
  loopback; el bloqueo de red lo impone.
- **Privacidad.** El texto viaja al llama.cpp local. Los logs de Hermes del perfil del puente
  pueden contener la conversación.
- **Pantalla.** Falta la sección de chat en el Task Center y el botón "Crear tarea desde esta
  propuesta". Ese botón debe crear la tarea en `awaiting_approval` y nunca aprobarla.
