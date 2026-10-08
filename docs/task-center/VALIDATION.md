# Task Center validation — 2026-10-07

## Observed in this development environment

- `python -m unittest discover -s tests -v`: **28 passed**, no skips. Includes
  the original pilot/Hermes tests, a real FFmpeg cut and 11 HTTP integration tests.
- `node --check arkos_pilot/web/app.js` and
  `node --check scripts/Test-ArkosTaskCenter.cjs`: passed.
- Browser end-to-end test: passed using Playwright 1.62.1 with Chromium 153 from
  `@sparticuz/chromium`, launched with `--no-zygote --disable-dev-shm-usage`.
  The standard browser download was unavailable in this environment. Neither
  browser testing dependency is required by the product.
- Verified actual browser → API → SQLite → approval → execution → generated
  artifact contents, not a mocked response. Also checked cancellation,
  persistence on reload, text injection handling, theme persistence, search,
  proposals, pending connectors, unauthenticated access and server disconnection.
- Screenshots inspected at desktop 1512 px and mobile 390 px. No horizontal
  overflow at the tested mobile size. Dark/blue and light/red were exercised.
- HTTP tests cover exact task selection, invalid approval fingerprint, expired
  approval, source modification, worker exclusion, Host/Origin restrictions,
  access key enforcement, static allowlist and external artifact-path rejection.

These checks do not certify production security, native mobile operation or
performance on Jona's Windows machine. The browser test uses synthetic notes and
an isolated temporary database. No Hermes profile, account connection or PC
installation was changed.

## Windows acceptance for Codex

1. Use a separate checkout of this PR and review its changes. Keep the active
   Hermes checkout/profile intact. Confirm an existing Python 3.11+ executable.
2. Run `python -m unittest discover -s tests -v`. A skipped FFmpeg test means the
   video path remains unverified on that PC; use a verified FFmpeg executable.
3. Launch `./scripts/Start-ArkosTaskCenter.ps1 -StateDirectory
   'D:\ARKOS\TaskCenterTrial'` (one PowerShell command). Keep its session URL private.
4. Create a disposable note, inspect its content, approve it and explicitly run
   it. Open/download the generated note and compare the contents.
5. Create two queued notes, run the second and confirm the first stays queued.
   Cancel another task and confirm it never executes.
6. Prepare a clip from a disposable source, approve/run it, play its output and
   verify that the original remains unchanged.
7. Restart the server and use its new private link. Confirm tasks persist and
   no queued task starts automatically. An interrupted running task requires
   manual review; do not recover or repeat it blindly.
8. Test theme controls, narrow viewport, browser reload and server-offline state.
   Measure startup time and idle/active RAM on the actual target PC.

## Explicitly pending

- Windows/PowerShell execution on the user's machine and hardware measurements.
- Hermes conversation/voice bridge and model memory/CPU measurements.
- Mobile pairing, remote task intake, encrypted relay and background startup.
- Email, calendar, WhatsApp and other external integrations.
- Installer, bundled model distribution, update signing and production review.

The responsive screenshots demonstrate layout only; they do not claim that a
phone can reach the loopback server. The mobile/PC protocol is a separate draft
in `SYNC_CONTRACT_DRAFT.md` and requires coordination before implementation.

## Futuristic UI follow-up — October 7, Argentina time

28 Python tests remain green. The expanded browser flow passed again, including
real task notices, marking seen, preference persistence, a new unread notice,
separate queue/running lanes, clock/timer rendering, the honest voice placeholder,
manual animation pause/persistence and the OS reduced-motion preference.

Desktop dark/cyan, desktop light/red and mobile 390 px screenshots were inspected.
`desktop-focus.png`, `command-center-detail.png` and `mobile-core.png` provide
larger views. `command-center-motion.mp4` is a five-second recording of the actual
local UI with synthetic tasks, converted with FFmpeg; it is evidence only, not
an application asset or video background. Its browser clock uses Argentina time.

No relay, Hermes, microphone, weather source, news feed, translator or team service
was connected by this visual increment. PC uptime and work hours remain pending.

La revisión de intensidad de color y geometría SVG se verificó con el mismo recorrido de
navegador y capturas regeneradas. No cambia APIs, permisos ni ejecución.

## Preparación remota

29 pruebas Python aprobadas, incluido endpoint remoto privado vacío y rechazo
de IDs remotos en acciones locales. La prueba Node de la proyección interna
aprobó los nueve estados y el filtrado de campos. El E2E usa transporte sintético
para los estados remotos; no certifica integración con el productor de Claude.
