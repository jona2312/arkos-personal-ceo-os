# ARKOS Task Center — local pilot

This increment adds a responsive interface for the existing Python/SQLite queue.
It is a local browser application, not a Hermes Desktop plugin, a cloud service,
a mobile pairing service or an installed PWA. It requires Python 3.11+ and no new
runtime packages. The interface, fonts and assets are local; no CDN or external
analytics are loaded.

## Start safely on Windows

Use a separate checkout of this PR. Do not replace the running Hermes checkout
or the `arkos-pilot` profile. Start with a disposable state directory:

```powershell
./scripts/Open-Arkos.ps1 -CheckOnly
./scripts/Open-Arkos.ps1
```

If Python is not on PATH, pass `-PythonPath` with an existing, verified Python
3.11+ executable. The launcher does not download or install Python. Do not assume
that the Python used by Codex is the Hermes runtime.

Equivalent on any supported OS:

```sh
python -m arkos_pilot.task_center --state-dir /absolute/path/to/trial --port 8765
```

The server binds **only to 127.0.0.1**. It opens the browser with a private,
per-process session key in a URL fragment. Do not share that link, tunnel the
server, bind it to a LAN address, or log the key in reports. The fragment is
removed by the UI and the key is stored in that tab's session storage. After a
server restart, reopen the freshly printed link. A reload of the same server's
tab preserves access. `--no-browser` prints the link without opening a browser.

This key is a loopback access guard, not a user account, pairing credential,
OS sandbox or multi-user authentication system. Other programs running under
the same OS account are not isolated by it. The HTTP service requires exact Host,
same Origin for writes and an access key for every private read or mutation;
there is no CORS permission for other origins.

## What works

- **Hoy:** actual counts, queue overview and real empty states. No seeded demo
  data or simulated connections in the application. Review/queued/running/done
  are separate lanes and counts. Task notices form a personal inbox with
  browser-local seen preferences; these are not email or team messages.
- **Tareas:** create notes or prepare a clip from an absolute path on this PC;
  review exact content, approve for 24 hours, separately execute the selected
  task, cancel before execution, filter and search.
- **Resultados:** safely preview note text (not rendered HTML/Markdown), download
  note/video artifacts from the queue's output directory.
- **Conversación:** deterministic proposal helper from the existing catalog.
  It explicitly describes itself as a preparer; it does not impersonate an LLM
  conversation. Proposals can be saved as notes, not executed as arbitrary code.
- **Conexiones:** local notes available; FFmpeg availability detected from PATH;
  Hermes chat, email, calendar and WhatsApp explicitly pending. The separate relay snapshot reader is available when explicitly configured; it cannot approve or execute remote work.
- **Personalización:** dark/light, gold/red neural and blue/red/violet/monochrome, stored in the
  current browser. A CSS neon background and orbital core add motion, with
  pause controls, brightness settings, a lightweight mode, reduced-motion support and hidden-tab animation pause. See [NEURAL_THEME.md](NEURAL_THEME.md). Usable
  at a 390 px mobile viewport, without horizontal scroll.
- Device clock/date and a page-open timer are real. The timer is elapsed page
  time (including background time), resets on reload, and is not PC uptime or
  hours worked. Voice, weather, news, PC activity, teams and translation have
  explicit pending explanations; no microphone or external request is started.
- Background polling updates task state every three seconds while visible and
  no dialog is open. A disconnected server is shown explicitly; cached data is
  not labeled live.

FFmpeg is not bundled or installed by this increment. If Hermes has a private
copy not on the launcher's PATH, the UI will correctly report it as undetected.
Codex must choose a verified binary/PATH before the clip acceptance test.

## Execution and recovery boundaries

The only shared-core change is `Queue.run_next(task_id=None)`. Existing CLI
behavior remains FIFO. The optional ID lets the UI claim the selected approved
task inside the existing SQLite transaction; selecting one task cannot run a
different queued task. Existing fingerprint, expiry, file hashing and exclusive
output creation checks remain active.

The browser server starts one background worker at a time on explicit Run.
Approval alone does not execute. There is no automatic startup, scheduler,
remote intake, arbitrary shell executor or Hermes tool bridge here. The server
can be stopped with Ctrl+C; this does not guarantee a running subprocess finishes.
An interrupted `running` task stays visibly in that state. Stop all workers,
inspect output and use the existing CLI `recover-interrupted` only after review;
there is deliberately no automatic replay or HTTP recovery endpoint.

A canceled task is retained in history. The API rejects repeat approval/run in
invalid states. Writes are not automatically retried after a network failure;
refresh the task list before resubmitting an uncertain request. Creation does not
yet have durable idempotency keys; these are a requirement of the future relay.

Clip paths refer to the current PC, not a phone filesystem. Preparing a clip
reads/hashes the selected local source, as the original CLI does. This service
does not implement a general file picker, upload, OS read sandbox or encrypted
database. Keep the pilot private and use test files. Artifact downloads serve
only the generated task filename, reject symlinks/path mismatches and use an
attachment disposition; video bytes are streamed by the server.

## Verification

```sh
python -m unittest discover -s tests -v
node --check arkos_pilot/web/app.js
node scripts/Test-ArkosRemoteView.cjs
node scripts/Test-ArkosTaskCenter.cjs
```

Node/Playwright are needed only for the optional browser test, not for users of
Task Center. This environment used Playwright 1.62.1 and Chromium 153 from
`@sparticuz/chromium`; the standard Playwright browser download was unavailable.
It resolves Playwright from ordinary Node resolution or
`CODEX_PRIMARY_RUNTIME_NODE_MODULES`. To use a separate dev environment, install
that Playwright version there and expose its module folder through `NODE_PATH`;
install its Chromium using the package's official CLI. `ARKOS_TEST_PYTHON` can
select the Python executable. `ARKOS_TEST_CHROMIUM` can select an existing
browser executable, and `ARKOS_TEST_CHROMIUM_ARGS` accepts a JSON array of
launch arguments. `ARKOS_TEST_RECORD_MOTION=1` optionally records a short UI
video; it requires the Playwright recording FFmpeg binary plus system FFmpeg
for conversion. No paid calls are made by these tests.

The browser test creates a temporary state directory, drives actual UI actions,
compares generated artifact content, tests reload, cancellation, XSS-safe text,
mobile overflow, theme persistence, search, pending connections, missing auth and
disconnection. It then removes its state. Screenshots under `screenshots/` show
synthetic tasks created through the real UI; they are not Jona's personal data.

See [RELAY_INTEGRATION.md](RELAY_INTEGRATION.md) for the configured read-only snapshot reader. [REMOTE_VIEW_PREPARATION.md](REMOTE_VIEW_PREPARATION.md) records its earlier preparation.
See [UI_ROADMAP.md](UI_ROADMAP.md) for the new design and prioritized modules.
See [VALIDATION.md](VALIDATION.md) for observed results and Windows acceptance.
The older [SYNC_CONTRACT_DRAFT.md](SYNC_CONTRACT_DRAFT.md) is historical; the relay contract and snapshot contract in the parent docs directory are authoritative for remote tasks.

## Guided Windows trial launch

Use `./scripts/Open-Arkos.ps1 -CheckOnly` to inspect requirements, then `./scripts/Open-Arkos.ps1` to open the center with a separate default trial state and a free loopback port. See [GUIDED_LAUNCHER.md](GUIDED_LAUNCHER.md). Python 3.11+ remains a prerequisite; this is not a bundled installer.
