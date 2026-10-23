// Browser acceptance for the phone client against a real relay process and the real agent CLI.
// Synthetic data only; everything runs on 127.0.0.1 in a temporary folder.
//   node scripts/Test-ArkosPhone.cjs            (needs the "playwright" package)
//   ARKOS_PYTHON=python3 ARKOS_TEST_CHROMIUM=/path/to/chrome ARKOS_PHONE_SHOTS=docs/relay-phone-evidence
'use strict';
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const PY = process.env.ARKOS_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const SHOTS = process.env.ARKOS_PHONE_SHOTS ? path.resolve(ROOT, process.env.ARKOS_PHONE_SHOTS) : null;

let chromium;
try { ({ chromium } = require('playwright')); } catch (e) {
  console.log('SKIP: falta el paquete playwright (npm i -g playwright y NODE_PATH)');
  process.exit(0);
}

function relay(args, opts = {}) {
  const r = spawnSync(PY, ['-B', '-m', 'arkos_relay', ...args], { cwd: ROOT, encoding: 'utf-8', ...opts });
  if (r.status !== 0) throw new Error(`arkos_relay ${args.join(' ')} -> ${r.status}\n${r.stderr}`);
  return r.stdout;
}

function freePort() {
  return new Promise((resolve) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); }); });
}

async function waitHealth(base) {
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(base + '/healthz')).ok) return; } catch (e) { /* not yet */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('El relay no arrancó');
}

function check(cond, message) { if (!cond) throw new Error('FALLA: ' + message); console.log('ok -', message); }

async function cardState(page, id) { return page.locator(`li.task[data-id="${id}"]`).getAttribute('data-state'); }

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'arkos-phone-'));
  const db = path.join(tmp, 'relay.sqlite3');
  const agentDir = path.join(tmp, 'agent');
  const { token } = JSON.parse(relay(['admin', '--db', db, 'create-user', '--name', 'Jona Sintético']));
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const server = spawn(PY, ['-B', '-m', 'arkos_relay', 'serve', '--db', db, '--port', String(port)], { cwd: ROOT, stdio: 'ignore' });
  let browser;
  const agent = (...a) => relay(['agent', '--state-dir', agentDir, ...a]);
  const api = async (p) => (await fetch(base + p, { headers: { Authorization: 'Bearer ' + token } })).json();
  try {
    await waitHealth(base);
    browser = await chromium.launch({
      headless: true, timeout: 15000,
      ...(process.env.ARKOS_TEST_CHROMIUM ? { executablePath: process.env.ARKOS_TEST_CHROMIUM } : {}),
    });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: 'es-AR' });
    const page = await context.newPage();
    const problems = [];
    page.on('pageerror', (e) => problems.push(e.message));
    page.on('console', (m) => { if (m.type() === 'error') problems.push(m.text()); });
    const shot = async (name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png'), fullPage: true }); } };

    await page.goto(base + '/m/');
    await page.fill('#token', token);
    await page.click('#login-form button[type=submit]');
    await page.waitForSelector('#app:not([hidden])');
    check(await page.textContent('#pc-name') === 'Sin PC vinculada', 'sin PC: el celular lo dice');
    check(!page.url().includes(token), 'el token no aparece en la URL');
    check(await page.evaluate(() => localStorage.getItem('arkos.token')) === null, 'sin "recordar", el token no queda en localStorage');

    // Pair the PC from the phone; the PC redeems the code (outbound) but stays off afterwards.
    await page.click('#pcs summary');
    await page.fill('#pc-name-input', 'PC de prueba');
    await page.click('#pair-form button');
    const code = (await page.textContent('#pair-code .code')).trim();
    agent('pair', '--server', base, '--code', code, '--allow-insecure-localhost');
    await page.reload();
    await page.waitForSelector('#app:not([hidden])');
    check(/Nunca se conectó/.test(await page.textContent('#pc-state')), 'PC vinculada que todavía no se conectó');

    // Phone leaves a task while the PC is off. Hostile text must render as text.
    const text = '<img src=x onerror="window.__pwned=1"> Llamar al contador el lunes';
    await page.fill('#note', text);
    await page.click('#new button[type=submit]');
    await page.waitForSelector('#review:not([hidden]) #r-approve:not([disabled])');
    const [task] = (await api('/v1/tasks')).tasks;
    const shown = (await page.textContent('#r-digest')).replace(/\s/g, '');
    check(shown === task.payload_sha256, 'la huella calculada en el celular coincide con la del relay');
    check(await page.textContent('#r-text') === text, 'la revisión muestra el contenido exacto');
    await shot('1-revisar-y-aprobar');
    await page.click('#r-approve');
    await page.waitForSelector(`li.task[data-id="${task.id}"][data-state="approved"]`);
    check(/todavía no se conectó/.test(await page.textContent(`li.task[data-id="${task.id}"] .hint`)), 'aprobada: espera a la PC');
    await shot('2-esperando-pc');

    // The PC comes online and runs one cycle.
    agent('run', '--once');
    await page.reload();
    await page.waitForSelector(`li.task[data-id="${task.id}"][data-state="succeeded"]`);
    check(await page.textContent('#pc-state') === 'Conectada', 'la PC figura conectada');
    check((await page.textContent(`li.task[data-id="${task.id}"] .result`)).includes(task.id + '.md'), 'el resultado llega al celular');
    check(fs.readFileSync(path.join(agentDir, 'outputs', 'notes', task.id + '.md'), 'utf-8') === text + '\n', 'la PC creó exactamente la nota aprobada');
    check(await page.evaluate(() => window.__pwned === undefined && !document.querySelector('#tasks img')), 'el texto hostil no se ejecuta');
    await shot('3-resultado');

    // Uncertain outcome: the PC starts, then cannot confirm (synthetic disk fault). Never retried by itself.
    fs.mkdirSync(path.join(agentDir, 'outputs'), { recursive: true });
    fs.rmSync(path.join(agentDir, 'outputs', 'notes'), { recursive: true });
    fs.writeFileSync(path.join(agentDir, 'outputs', 'notes'), 'no es una carpeta');
    await page.fill('#note', 'Nota con resultado incierto');
    await page.click('#new button[type=submit]');
    await page.waitForSelector('#review:not([hidden]) #r-approve:not([disabled])');
    await page.click('#r-approve');
    const second = (await api('/v1/tasks')).tasks.find((t) => t.id !== task.id);
    agent('run', '--once');
    agent('run', '--once');
    await page.reload();
    const card = `li.task[data-id="${second.id}"]`;
    await page.waitForSelector(card + '[data-state="unknown"]');
    check(/No se repite sola/.test(await page.textContent(card + ' .hint')), 'incierto: se explica y no se repite');
    check(!(await page.textContent('#tasks')).includes(tmp), 'el resultado no revela rutas locales de la PC');
    const events = (await api('/v1/tasks/' + second.id)).task.events.map((e) => e.to_state);
    check(events.filter((s) => s === 'running').length === 1, 'una sola ejecución para la tarea incierta');
    await shot('4-incierto');
    await page.click(card + ' >> text=Ya revisé la PC');
    await page.click(card + ' >> text=No se creó');
    await page.waitForSelector(card + '[data-state="failed"]');
    check(/Marcada por vos/.test(await page.textContent(card + ' .hint')), 'el usuario resuelve el incierto tras revisar la PC');
    await shot('5-resuelto');

    check(problems.length === 0, 'sin errores de consola: ' + problems.join(' | '));
    console.log('PASS Test-ArkosPhone');
  } finally {
    if (browser) await browser.close();
    server.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch((e) => { console.error(e); process.exit(1); });
