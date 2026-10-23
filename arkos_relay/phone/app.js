'use strict';
// ARKOS phone client: create a task, approve its exact content, follow it until the PC reports.
// No external code. All dynamic text goes through textContent (never innerHTML).
(function () {
  const CONTRACT_VERSION = 1;
  const POLL_MS = 10000;
  const ACTIONS = { 'note.create': 'Nota', 'document.create': 'Documento', 'video.clip': 'Recorte de video' };
  const STATES = {
    awaiting_approval: 'Pendiente de aprobación', approved: 'Aprobada', claimed: 'Reservada por la PC',
    running: 'Ejecutándose', succeeded: 'Hecha', failed: 'Falló sin efecto', unknown: 'Resultado incierto',
    rejected: 'Rechazada', cancelled: 'Cancelada',
  };

  // Notes this client sends with /resolve ("resolved_by_user" is the relay default).
  const USER_RESOLVED = ['confirmado_en_pc', 'no_estaba_en_pc', 'resolved_by_user'];

  // Same bytes as arkos_relay.contract.canonical: sorted keys, no spaces, integers only.
  function canonical(value) {
    if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
    if (typeof value === 'number') {
      if (!Number.isSafeInteger(value)) throw new Error('Solo se admiten enteros en el contrato');
      return String(value);
    }
    if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
    if (typeof value === 'object') {
      return '{' + Object.keys(value).sort().map((k) => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
    }
    throw new Error('Tipo no admitido en el contrato');
  }

  function digestBody(task) {
    return canonical({ v: CONTRACT_VERSION, action: task.action, params: task.params, target_device_id: task.target_device_id });
  }

  function clock(ts) {
    if (!ts) return '—';
    return new Date(ts * 1000).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  }

  function waitingForPc(device) {
    if (!device) return 'No hay una PC vinculada: se ejecutará en la primera que vincules.';
    if (device.presence === 'online') return 'La PC está conectada; la toma en su próximo ciclo.';
    if (device.presence === 'revoked') return 'La PC de destino fue revocada: cancelá este encargo.';
    if (device.presence === 'never_seen') return 'La PC todavía no se conectó nunca.';
    return 'La PC no está conectada. Se ejecuta cuando vuelva, si la aprobación sigue vigente.';
  }

  // Pure: what the phone shows for a task and which actions it offers. Covered by scripts/Test-ArkosPhone.cjs.
  function describe(task, device) {
    const d = { label: STATES[task.state] || task.state, tone: 'wait', hint: '', actions: [] };
    switch (task.state) {
      case 'awaiting_approval':
        d.tone = 'act';
        d.hint = task.state_reason === 'approval_expired'
          ? 'La aprobación venció antes de que la PC la tomara. No se ejecutó nada. Revisá el contenido y aprobá de nuevo.'
          : 'Revisá el contenido y aprobalo para que la PC lo ejecute.';
        d.actions = ['review', 'reject', 'cancel'];
        break;
      case 'approved':
        d.hint = (task.state_reason === 'lease_expired_before_start'
          ? 'La PC la tomó pero no llegó a empezar; no hizo nada y vuelve a ofrecerse. ' : '') + waitingForPc(device)
          + (task.approval_expires_at ? ' Aprobación vigente hasta ' + clock(task.approval_expires_at) + '.' : '');
        d.actions = ['cancel'];
        break;
      case 'claimed':
        d.hint = 'La PC la reservó y todavía no hizo nada.';
        d.actions = ['cancel'];
        break;
      case 'running':
        d.hint = 'La PC la está ejecutando. Ya no se puede cancelar.';
        break;
      case 'succeeded':
        d.tone = 'ok';
        d.hint = USER_RESOLVED.includes(task.state_reason) ? 'Marcada como hecha por vos tras revisar la PC.' : 'La PC confirmó el resultado.';
        break;
      case 'failed':
        d.tone = 'bad';
        d.hint = USER_RESOLVED.includes(task.state_reason) ? 'Marcada por vos: no se creó en la PC.' : 'No se produjo ningún efecto en la PC.';
        d.actions = ['retry'];
        break;
      case 'unknown':
        d.tone = 'warn';
        d.hint = 'La PC empezó pero no pudo confirmar qué pasó. No se repite sola: revisá la PC y marcá el resultado.';
        d.actions = ['resolve', 'retry'];
        break;
      case 'cancelled':
        d.tone = 'bad';
        d.actions = ['retry'];
        break;
      case 'rejected':
        d.tone = 'bad';
        break;
    }
    return d;
  }

  function deviceFor(task, devices) {
    if (task.target_device_id) return devices.find((dv) => dv.id === task.target_device_id) || null;
    const active = devices.filter((dv) => !dv.revoked_at);
    return active.length === 1 ? active[0] : null;
  }

  function preview(task) {
    const p = task.params || {};
    if (task.action === 'video.clip') return p.root + '/' + p.path + ' desde ' + Math.round(p.start_ms / 1000) + ' s, ' + Math.round(p.duration_ms / 1000) + ' s';
    return (task.action === 'document.create' ? p.filename + ': ' : '') + (p.text || '');
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { canonical, digestBody, describe, deviceFor, preview, CONTRACT_VERSION };
    return;
  }

  // ---------------------------------------------------------------- browser only
  const $ = (id) => document.getElementById(id);
  const state = { token: null, devices: [], tasks: new Map(), after: 0, reviewing: null, timer: null, confirming: null };

  function store(kind) { try { return window[kind]; } catch (e) { return null; } }
  function loadToken() {
    for (const kind of ['sessionStorage', 'localStorage']) {
      const s = store(kind);
      const value = s && s.getItem('arkos.token');
      if (value) return value;
    }
    return null;
  }
  function saveToken(token, remember) {
    const s = store(remember ? 'localStorage' : 'sessionStorage');
    if (s) s.setItem('arkos.token', token);
  }
  function forget() {
    for (const kind of ['sessionStorage', 'localStorage']) {
      const s = store(kind);
      if (s) { s.removeItem('arkos.token'); s.removeItem('arkos.pending'); }
    }
  }

  class Http extends Error { constructor(status, code, message) { super(message || code); this.status = status; this.code = code; } }

  async function api(method, path, body) {
    let response;
    try {
      response = await fetch(path, {
        method, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer',
        headers: Object.assign({ Authorization: 'Bearer ' + state.token }, body ? { 'Content-Type': 'application/json' } : {}),
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      throw new Http(0, 'network', 'Sin conexión con el relay');
    }
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { logout('El token no es válido o fue revocado.'); throw new Http(401, 'unauthorized'); }
    if (!response.ok) throw new Http(response.status, (data.error || {}).code || 'error', (data.error || {}).message);
    return { status: response.status, data };
  }

  async function sha256hex(text) {
    if (!(window.crypto && crypto.subtle)) throw new Error('La aprobación necesita HTTPS (o localhost) para calcular la huella.');
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
    return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join('');
  }

  function show(id, visible) { $(id).hidden = !visible; }
  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }

  function logout(message) {
    forget();
    state.token = null;
    clearInterval(state.timer);
    state.tasks.clear(); state.after = 0;
    show('app', false); show('logout', false); show('login', true);
    $('login-error').textContent = message || '';
  }

  async function login(token, remember) {
    state.token = token;
    try {
      await api('GET', '/v1/me');
    } catch (e) {
      if (e.status !== 401) $('login-error').textContent = e.message;
      state.token = null;
      return;
    }
    saveToken(token, remember);
    show('login', false); show('app', true); show('logout', true);
    await refresh();
    state.timer = setInterval(() => { if (!document.hidden) refresh(); }, POLL_MS);
  }

  async function refresh() {
    try {
      const devices = await api('GET', '/v1/devices');
      state.devices = devices.data.devices;
      for (let page = 0; page < 20; page++) {
        const r = await api('GET', '/v1/tasks?after_version=' + state.after + '&limit=200');
        r.data.tasks.forEach((t) => state.tasks.set(t.id, t));
        state.after = r.data.next_after_version;
        if (r.data.tasks.length < 200) break;
      }
      $('sync').textContent = 'Actualizado ' + new Date().toLocaleTimeString('es-AR');
      $('sync').classList.remove('error');
    } catch (e) {
      if (e.status === 401) return;
      $('sync').textContent = e.message + '. Mostrando lo último recibido; se reintenta solo.';
      $('sync').classList.add('error');
    }
    render();
  }

  function activeDevices() { return state.devices.filter((d) => !d.revoked_at); }

  function renderPc() {
    const active = activeDevices();
    const dot = $('pc-dot');
    dot.className = 'dot';
    if (!active.length) {
      dot.classList.add('none');
      $('pc-name').textContent = 'Sin PC vinculada';
      $('pc-state').textContent = 'Los encargos quedan en la cola hasta que vincules una PC.';
    } else {
      const shown = active.find((d) => d.presence === 'online') || active[0];
      dot.classList.add(shown.presence);
      $('pc-name').textContent = shown.name + (active.length > 1 ? ' (+' + (active.length - 1) + ')' : '');
      $('pc-state').textContent = {
        online: 'Conectada', offline: 'Desconectada · vista ' + clock(shown.last_seen_at), never_seen: 'Nunca se conectó',
      }[shown.presence] || shown.presence;
    }
    const select = $('target');
    const multi = active.length > 1;
    show('target', multi); show('target-label', multi);
    if (multi && select.options.length !== active.length) {
      select.replaceChildren(...active.map((d) => { const o = el('option', null, d.name); o.value = d.id; return o; }));
    }
  }

  function renderDevices() {
    const list = $('devices');
    const labels = { online: 'conectada', offline: 'desconectada', never_seen: 'nunca se conectó', revoked: 'revocada' };
    list.replaceChildren(...state.devices.map((dv) => {
      const li = el('li');
      li.append(el('span', 'dot ' + dv.presence), el('span', 'name', dv.name + ' · ' + (labels[dv.presence] || dv.presence)));
      if (!dv.revoked_at) {
        const key = dv.id + ':revoke';
        if (state.confirming === key) {
          li.append(button('Confirmar revocación', 'danger', async () => {
            await api('POST', '/v1/devices/' + dv.id + '/revoke'); state.confirming = null; await refresh();
          }));
        } else {
          li.append(button('Revocar', 'secondary', async () => { state.confirming = key; render(); }));
        }
      }
      return li;
    }));
    if (!state.devices.length) list.replaceChildren(el('li', 'muted small', 'Ninguna todavía.'));
  }

  async function pairPc(event) {
    event.preventDefault();
    const name = $('pc-name-input').value.trim();
    if (!name) return;
    try {
      const r = await api('POST', '/v1/devices/pairing-codes', { device_name: name });
      const out = $('pair-code');
      out.replaceChildren(el('div', 'code', r.data.code),
        el('div', 'muted', 'Vale 10 minutos y una sola vez. En la PC: Start-ArkosAgent.ps1 pair --server <relay> --code ' + r.data.code));
      $('pc-name-input').value = '';
    } catch (e) {
      if (e.status !== 401) $('pair-code').textContent = e.message;
    }
  }

  function renderTasks() {
    const list = $('tasks');
    const tasks = Array.from(state.tasks.values()).sort((a, b) => b.created_at - a.created_at);
    list.replaceChildren(...tasks.map(renderTask));
    if (!tasks.length) list.replaceChildren(el('li', 'muted small', 'Todavía no hay encargos.'));
  }

  function renderTask(task) {
    const device = deviceFor(task, state.devices);
    const d = describe(task, device);
    const li = el('li', 'task tone-' + d.tone);
    li.dataset.id = task.id;
    li.dataset.state = task.state;
    const head = el('div', 'head');
    head.append(el('span', null, (ACTIONS[task.action] || task.action) + ' · ' + task.id.slice(4, 12)), el('span', 'state', d.label));
    const text = preview(task);
    li.append(head, el('div', 'preview', text.length > 160 ? text.slice(0, 160) + '…' : text), el('div', 'hint', d.hint));
    li.append(el('div', 'muted small', 'Creada ' + clock(task.created_at) + (device ? ' · ' + device.name : '')));
    if (task.result) {
      const r = el('div', 'result');
      r.append(el('div', null, task.result.message || ''));
      if (task.result.output) {
        const o = task.result.output;
        r.append(el('code', null, o.name + ' · ' + o.bytes + ' bytes · sha256 ' + String(o.sha256).slice(0, 12)));
      }
      li.append(r);
    }
    const row = el('div', 'row');
    for (const action of d.actions) row.append(...actionButtons(task, action));
    if (row.childNodes.length) li.append(row);
    return li;
  }

  function button(label, cls, handler) {
    const b = el('button', cls, label);
    b.type = 'button';
    b.addEventListener('click', async () => {
      b.disabled = true;
      try { await handler(); } catch (e) { if (e.status !== 401) alertTask(e.message); }
      finally { b.disabled = false; }
    });
    return b;
  }

  function alertTask(message) { $('sync').textContent = message; $('sync').classList.add('error'); }

  function actionButtons(task, action) {
    const path = '/v1/tasks/' + task.id;
    const confirmKey = task.id + ':' + action;
    if (action === 'review') return [button('Revisar y aprobar', null, () => openReview(task))];
    if (action === 'reject') return [button('Rechazar', 'secondary', async () => { await api('POST', path + '/reject'); await refresh(); })];
    if (action === 'cancel') return [button('Cancelar', 'danger', async () => { await api('POST', path + '/cancel'); await refresh(); })];
    if (action === 'resolve') {
      if (state.confirming !== confirmKey) {
        return [button('Ya revisé la PC', 'secondary', async () => { state.confirming = confirmKey; render(); })];
      }
      const resolve = (outcome) => async () => {
        await api('POST', path + '/resolve', { outcome, note: outcome === 'succeeded' ? 'confirmado_en_pc' : 'no_estaba_en_pc' });
        state.confirming = null; await refresh();
      };
      return [button('Sí, se creó', null, resolve('succeeded')), button('No se creó', 'danger', resolve('failed'))];
    }
    if (action === 'retry') {
      const nodes = [];
      let ack = null;
      if (task.state === 'unknown') {
        const label = el('label', 'check');
        ack = el('input'); ack.type = 'checkbox';
        label.append(ack, document.createTextNode(' Entiendo que puede quedar duplicado'));
        nodes.push(label);
      }
      nodes.push(button('Crear de nuevo', 'secondary', async () => {
        if (ack && !ack.checked) throw new Error('Marcá que entendés el posible duplicado antes de crear de nuevo.');
        const r = await api('POST', path + '/retry', { client_request_id: 'phone-' + crypto.randomUUID(), acknowledge_possible_duplicate: !!(ack && ack.checked) });
        await refresh();
        openReview(r.data.task);
      }));
      return nodes;
    }
    return [];
  }

  async function openReview(task) {
    state.reviewing = task;
    const device = deviceFor(task, state.devices);
    $('r-action').textContent = ACTIONS[task.action] || task.action;
    $('r-target').textContent = task.target_device_id ? (device ? device.name : task.target_device_id) : 'La primera PC que vincules';
    $('r-text').textContent = preview(task);
    $('r-digest').textContent = '…';
    $('review-error').textContent = '';
    $('r-approve').disabled = true;
    show('review', true);
    $('review').scrollIntoView({ block: 'start' });
    try {
      const digest = await sha256hex(digestBody(task));
      $('r-digest').textContent = digest.match(/.{1,8}/g).join(' ');
      if (digest !== task.payload_sha256) {
        $('review-error').textContent = 'La huella calculada acá no coincide con la del relay. No se aprueba.';
        return;
      }
      $('r-approve').dataset.digest = digest;
      $('r-approve').disabled = false;
    } catch (e) {
      $('review-error').textContent = e.message;
    }
  }

  async function approve() {
    const task = state.reviewing;
    const btn = $('r-approve');
    btn.disabled = true;
    try {
      await api('POST', '/v1/tasks/' + task.id + '/approve', { payload_sha256: btn.dataset.digest, ttl_seconds: Number($('ttl').value) });
      show('review', false);
      state.reviewing = null;
      await refresh();
    } catch (e) {
      if (e.status !== 401) $('review-error').textContent = e.code === 'payload_mismatch'
        ? 'El contenido cambió en el relay: no se aprobó.' : e.message;
      btn.disabled = false;
    }
  }

  function pendingCreate(text, target) {
    // Same client_request_id until the relay confirms: resending after a network error never duplicates.
    const s = store('sessionStorage');
    let pending = null;
    try { pending = JSON.parse((s && s.getItem('arkos.pending')) || 'null'); } catch (e) { pending = null; }
    if (!pending || pending.text !== text || pending.target !== target) {
      pending = { id: 'phone-' + crypto.randomUUID(), text, target };
      if (s) s.setItem('arkos.pending', JSON.stringify(pending));
    }
    return pending;
  }

  async function createTask(event) {
    event.preventDefault();
    $('new-error').textContent = '';
    const text = $('note').value;
    if (!text.trim()) return;
    const multi = activeDevices().length > 1;
    const target = multi ? $('target').value : null;
    const pending = pendingCreate(text, target);
    const body = { client_request_id: pending.id, action: 'note.create', params: { text } };
    if (target) body.target_device_id = target;
    const submit = event.submitter || $('new').querySelector('button');
    submit.disabled = true;
    try {
      const r = await api('POST', '/v1/tasks', body);
      const s = store('sessionStorage'); if (s) s.removeItem('arkos.pending');
      $('note').value = '';
      await refresh();
      openReview(r.data.task);
    } catch (e) {
      if (e.status === 401) return;
      $('new-error').textContent = e.status === 0
        ? 'No se pudo confirmar el envío. Tocá de nuevo: no se duplica.'
        : e.message;
    } finally {
      submit.disabled = false;
    }
  }

  function render() { renderPc(); renderDevices(); renderTasks(); }

  document.addEventListener('DOMContentLoaded', () => {
    $('login-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const token = $('token').value.trim();
      $('token').value = '';
      if (!/^aku_[A-Za-z0-9_-]{16,}$/.test(token)) { $('login-error').textContent = 'Ese no parece un token de usuario (aku_…).'; return; }
      login(token, $('remember').checked);
    });
    $('logout').addEventListener('click', () => logout(''));
    $('new').addEventListener('submit', createTask);
    $('pair-form').addEventListener('submit', pairPc);
    $('r-approve').addEventListener('click', approve);
    $('r-close').addEventListener('click', () => { show('review', false); state.reviewing = null; });
    document.addEventListener('visibilitychange', () => { if (!document.hidden && state.token) refresh(); });
    const saved = loadToken();
    if (saved) login(saved, false); else show('login', true);
  });
})();
