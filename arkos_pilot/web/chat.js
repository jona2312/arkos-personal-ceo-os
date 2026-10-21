/* Chat uses the same authenticated local API; it never approves or executes work.
   Local and Cloud are separate sessions: switching never sends one's history to the other,
   Cloud starts disabled and needs explicit consent, and nothing is ever re-sent automatically. */
(() => {
  'use strict';
  const MODES = {
    local: {api:'/api/chat', key:'arkos-chat-last-turn', history:[], nodes:[], configured:false, restored:true},
    cloud: {api:'/api/cloud/chat', key:'arkos-cloud-last-turn', history:[], nodes:[], configured:false, restored:false},
  };
  let current = 'local', pending = null, cancelRequested = false, polling = false;
  let localInfo = null, cloudInfo = null;
  const M = () => MODES[current];
  const log = $('chat-log'), input = $('chat-input');
  function remember(rid) { try { if(rid)sessionStorage.setItem(M().key,rid);else sessionStorage.removeItem(M().key); } catch { /* history remains in this page */ } }
  input.addEventListener('keydown',event=>{
    if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('chat-form').requestSubmit();}
  });
  function status(value, message) {
    document.documentElement.dataset.chat = value;
    $('chat-state').textContent = message;
    const configured = M().configured;
    $('chat-send').disabled = !configured || !!pending;
    input.disabled = !configured || !!pending;
    $('chat-cancel').hidden = !pending;
    $('chat-cancel').disabled = cancelRequested;
    $('chat-new').disabled = !!pending;
    $('cloud-cancel-note').hidden = !(current === 'cloud' && pending);
    $('mode-local').disabled = !!pending;
    $('mode-cloud').disabled = !!pending || !(cloudInfo && cloudInfo.configured);
    window.dispatchEvent(new CustomEvent('arkos-chat-state', {detail:{state:value, mode:current, requestId:pending?.request_id || null}}));
  }
  function message(role, text) {
    const row = element('article', 'chat-message '+role);
    row.append(element('strong', '', role === 'user' ? 'Vos' : (current === 'cloud' ? 'ARKOS · Cloud' : 'ARKOS')), element('p', '', text));
    log.append(row); return row;
  }
  function outcome(text) { const p = element('p', 'chat-outcome', text); log.append(p); return p; }
  function proposalCard(rid, proposal, created) {
    const base = M().api;
    const card = element('details', 'chat-proposal'); card.open = true;
    card.append(element('summary', '', 'Propuesta · '+proposal.title), element('pre', '', proposal.text));
    const help = element('p', 'field-help', 'Crear la nota la deja pendiente de tu aprobación. No la ejecuta.');
    const button = element('button', 'secondary', created ? 'Tarea creada' : 'Crear nota pendiente');
    button.disabled = !!created;
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await api(base+'/'+rid+'/note', {proposal_id:proposal.proposal_id});
        button.textContent = 'Tarea creada';
        help.textContent = 'Encontrala en Tareas. Su aprobación y ejecución se hacen por separado.';
        await refresh();
      } catch(e) { help.textContent=e.message; button.disabled=false; }
    });
    card.append(help, button); return card;
  }
  // What each Cloud outcome means for the person: sent or not, billed or maybe billed.
  const CLOUD_OUTCOMES = {
    consent_required:['No enviado','No enviado: Cloud necesita tu consentimiento para estas condiciones. No hubo cobro.',true],
    unsafe_configuration:['No enviado','No enviado: Cloud está bloqueado con esta configuración. No hubo cobro.',true],
    invalid_request:['No enviado','No enviado: el pedido supera los límites de Cloud o su historial no es de esta conversación Cloud. No hubo cobro.',true],
    provider_unavailable:['No enviado','No enviado o rechazado antes de procesarse: no se pudo usar el servicio Cloud. No hubo cobro.',true],
    budget_exhausted:['Presupuesto agotado','Presupuesto agotado: no se envió nada. Cloud vuelve a estar disponible cuando se renueve el tope diario o mensual.',true],
    duplicate_request:['Ya respondido','Ese pedido ya se respondió, pero el gateway no conserva su contenido. Si lo necesitás, hacé un pedido nuevo (puede cobrarse otra vez).',false],
    output_invalid:['Sin respuesta utilizable','El servicio respondió algo inválido y se descartó. Puede haberse cobrado.',false],
  };
  function uncertain(rid) {
    const box = outcome('Resultado incierto: el pedido pudo procesarse y cobrarse, pero la respuesta no llegó. No se reintenta automáticamente.');
    box.dataset.outcome = 'outcome_uncertain';
    const detail = element('span', 'outcome-detail', '');
    const check = element('button', 'secondary', 'Consultar estado');
    check.type = 'button';
    check.addEventListener('click', async () => {
      check.disabled = true;
      try {
        const s = await api('/api/cloud/chat/'+rid+'/check');
        const cost = typeof s.charged_micro_usd === 'number' ? ' Costo registrado: USD '+(s.charged_micro_usd/1e6).toFixed(4)+'.' : '';
        detail.textContent = s.state === 'completed' ? 'El gateway lo registra como respondido; su contenido no se conserva.'+cost
          : s.state === 'uncertain' ? 'Sigue incierto: se concilia con el uso informado por el proveedor. No se reenvía.'
          : s.state === 'cancelled' ? 'Registrado como cancelado.'+cost
          : s.state === 'reconciled' ? 'Conciliado con el proveedor.'+cost
          : 'Sin información del gateway por ahora. No se reenvió nada.';
      } catch(e) { detail.textContent = e.message; }
      finally { check.disabled = false; }
    });
    box.append(detail, check);
  }
  function finish(turn) {
    if (!pending || turn.request.request_id !== pending.request_id) return;
    const rid = pending.request_id;
    if (turn.state === 'waiting') return;
    const result = turn.response;
    const code = result && result.error_code;
    let label;
    if (turn.state === 'ok' && result) {
      M().history = [...turn.request.messages, {role:'assistant',content:result.reply}].filter(m=>m.content.trim());
      const row=message('assistant',result.reply);
      for(const p of result.proposals) row.append(proposalCard(rid,p,turn.created_tasks[p.proposal_id]));
    } else if (current === 'cloud') {
      document.documentElement.dataset.cloudOutcome = turn.state === 'cancelled' ? 'cancelled' : (turn.state === 'timeout' ? 'outcome_uncertain' : code || 'error');
      if (turn.state === 'cancelled') {
        outcome('Cancelado: dejaste de esperar. Si el pedido ya había llegado al proveedor, puede cobrarse igual. Sin propuestas ni tareas nuevas.');
        label = 'Cancelado · puede haberse cobrado';
      } else if (turn.state === 'timeout' || code === 'outcome_uncertain') {
        uncertain(rid); label = 'Resultado incierto · no se reintenta';
      } else {
        const known = CLOUD_OUTCOMES[code] || ['Error de conversación','No se pudo completar el turno. Sin propuestas ni tareas nuevas.',false];
        outcome(known[1]); label = known[0];
        if (known[2]) input.value = turn.request.messages.at(-1).content;  // nothing was sent: safe to edit and send
      }
    } else {
      if(turn.state!=='cancelled')input.value=turn.request.messages.at(-1).content;
      outcome(turn.state==='cancelled' ? 'Turno cancelado. Sin propuestas ni tareas nuevas.' :
        turn.state==='timeout' ? 'Se agotó el tiempo de espera. Sin propuestas ni tareas nuevas.' :
        'No se pudo completar el turno. Sin propuestas ni tareas nuevas.');
    }
    pending=null; cancelRequested=false;$('chat-retry').hidden=true;
    status(turn.state, label || (turn.state==='ok'?'Respuesta recibida · ejecución de tareas por separado':
      turn.state==='cancelled'?'Conversación cancelada':turn.state==='timeout'?'Tiempo de espera agotado':'Error de conversación'));
    log.scrollTop=log.scrollHeight; input.focus();
    window.dispatchEvent(new CustomEvent('arkos-chat-result', {detail:{mode:current, requestId:rid,
      state:turn.state, reply:turn.state==='ok' ? result.reply : ''}}));
  }
  async function poll() {
    if (!pending || polling) return;
    const queried=pending, base=M().api;
    polling=true;
    try {
      const turn=await api(base+'/'+queried.request_id);
      if(pending!==queried)return;
      if (cancelRequested && turn.state==='waiting') await api(base+'/'+queried.request_id+'/cancel',{});
      finish(turn);
    } catch(e) { if(pending===queried)status('offline','No se puede consultar el turno. Se reintentará la lectura; no se vuelve a enviar.'); }
    finally { polling=false; if(pending)setTimeout(poll,700); }
  }
  $('chat-form').addEventListener('submit',async event=>{
    event.preventDefault();
    if(pending||!M().configured||!input.value.trim())return;
    const text=input.value, base=M().api;
    const messages=[...M().history,{role:'user',content:text}];
    const maxChars = current==='cloud' && cloudInfo ? cloudInfo.disclosure.max_input_chars : 32000;
    if(messages.length>20 || messages.reduce((n,m)=>n+m.content.length,0)>maxChars){
      status('error','El historial alcanzó su límite. Elegí Nueva conversación.');return;
    }
    pending={v:1,request_id:(current==='cloud'?'cl-':'ui-')+crypto.randomUUID(),messages};
    const submitted=pending;
    remember(submitted.request_id);
    cancelRequested=false;
    delete document.documentElement.dataset.cloudOutcome;
    message('user',text);input.value='';
    status('waiting',current==='cloud'?'Esperando a Cloud · cancelar deja de esperar, pero puede no evitar el cobro':
      'Esperando a ARKOS · ninguna tarea se está ejecutando por este turno');
    try {
      const turn=await api(base,submitted);
      if(pending!==submitted)return;
      if(cancelRequested && turn.state==='waiting') await api(base+'/'+pending.request_id+'/cancel',{});
      finish(turn);
      if(pending)poll();
    } catch(e) {
      if(pending!==submitted)return;
      if(e.status){
        pending=null;cancelRequested=false;
        input.value=text;
        remember(null);
        outcome(e.message);
        status('error',e.message);return;
      }
      // A lost POST response is ambiguous. Query its SAME id before allowing another send.
      try { const turn=await api(base+'/'+pending.request_id);finish(turn);if(pending)poll(); }
      catch {
        // Preserve the exact request for an explicit, idempotent retry (same id: never a second call).
        $('chat-retry').hidden=false;
        status('offline',e.message+' Podés reenviar el mismo turno sin duplicarlo.');
      }
    }
  });
  $('chat-retry').addEventListener('click',async()=>{
    if(!pending)return;
    const submitted=pending, base=M().api;
    $('chat-retry').disabled=true;
    try {
      const turn=await api(base,submitted);
      if(pending!==submitted)return;
      $('chat-retry').hidden=true;
      if(cancelRequested&&turn.state==='waiting')await api(base+'/'+pending.request_id+'/cancel',{});
      finish(turn);if(pending)poll();
    } catch(e) {
      if(pending!==submitted)return;
      if(e.status){input.value=submitted.messages.at(-1).content;pending=null;cancelRequested=false;remember(null);$('chat-retry').hidden=true;}
      status('error',e.message);
    }
    finally{$('chat-retry').disabled=false;}
  });
  $('chat-cancel').addEventListener('click',async()=>{
    if(!pending)return;
    const cancelled=pending, base=M().api;
    cancelRequested=true;status('waiting',current==='cloud'?'Dejando de esperar… si ya llegó al proveedor, puede cobrarse':'Cancelando conversación…');
    try{finish(await api(base+'/'+cancelled.request_id+'/cancel',{}));}
    catch { if(pending===cancelled){status('offline','Cancelación sin confirmar. Se consultará el turno.');poll();} }
  });
  function idleMessage() {
    if (current === 'cloud') return M().configured ? 'Listo para conversar por Cloud' : 'Cloud no está activo';
    return M().configured ? 'Listo para conversar' : 'Hermes por conectar';
  }
  $('chat-new').addEventListener('click',()=>{if(pending)return;M().history=[];remember(null);log.replaceChildren();
    if(current==='cloud')outcome('Conversación Cloud nueva. No incluye tu conversación local.');
    status('idle',idleMessage());input.focus();});

  // ---- Local / Cloud ----
  function localWhere() {
    if (!localInfo) return 'Se procesa en: esta PC';
    return localInfo.mode==='synthetic' ? 'Se procesa en: esta PC · prueba sintética, sin modelo real'
      : localInfo.configured ? 'Se procesa en: esta PC · Hermes local' : 'Se procesa en: esta PC · Hermes por conectar';
  }
  function cloudWhere() {
    const a = cloudInfo && cloudInfo.activation, d = cloudInfo && cloudInfo.disclosure;
    if (!a) return 'Cloud no está configurado en esta PC';
    const who = d.provider+' · '+d.model;
    if (a.state === 'ready') return a.test ? 'Se procesa en: Cloud de prueba · gateway ARKOS con proveedor falso ('+who+')'
      : 'Se procesa en: Cloud · gateway ARKOS → '+who;
    return 'Cloud no activo · nada se envía ('+(a.state==='needs_consent'?'falta tu consentimiento':a.state==='blocked'?'bloqueado':'gateway no disponible')+')';
  }
  function showWhere() {
    const cloud = current === 'cloud';
    document.documentElement.dataset.processing = cloud ? 'cloud' : 'local';
    $('processing-where').textContent = cloud ? cloudWhere() : localWhere();
    $('mode-local').setAttribute('aria-checked', String(!cloud));
    $('mode-cloud').setAttribute('aria-checked', String(cloud));
    const ready = cloudInfo && cloudInfo.activation && cloudInfo.activation.state === 'ready';
    $('chat-mode').textContent = cloud ? (ready && cloudInfo.activation.test ? 'CLOUD DE PRUEBA · proveedor falso' : ready ? 'CLOUD' : 'CLOUD · inactivo')
      : (localInfo && localInfo.mode==='synthetic' ? 'PRUEBA SINTÉTICA · sin modelo real' : localInfo && localInfo.configured ? 'Hermes · conversación local' : 'Hermes por conectar');
    $('cloud-footer').hidden = !(cloud && ready);
    input.placeholder = cloud ? (ready ? 'Se envía a Cloud'+(cloudInfo.activation.test ? ' de prueba' : '')+'. Contame qué querés resolver…' : 'Cloud no activo: no se envía nada.')
      : 'Se procesa en esta PC. Contame qué querés resolver…';
  }
  function term(list, label, value, warn) {
    const dd = element('dd', warn ? 'unverified' : '', value);
    list.append(element('dt', '', label), dd);
  }
  function showConsent() {
    const panel = $('cloud-consent'), a = cloudInfo.activation, d = cloudInfo.disclosure;
    panel.hidden = !(current === 'cloud' && a.state !== 'ready');
    if (panel.hidden) return;
    const list = $('cloud-terms'); list.replaceChildren();
    const usd = n => 'USD '+n.toFixed(2);
    term(list, 'Proveedor y modelo', d.provider+' · '+d.model+(a.test ? ' · PRUEBA con proveedor falso' : ''));
    term(list, 'Qué se envía', d.data_sent+' Hasta '+d.max_input_chars+' caracteres por pedido.');
    term(list, 'Retención en ARKOS', d.gateway_retention_hours === 0
      ? '0 h: el gateway no guarda el texto de las respuestas. Si una respuesta se pierde, no se puede recuperar.'
      : d.gateway_retention_hours+' h, para poder reenviar una respuesta perdida sin volver a cobrar.');
    term(list, 'Retención del proveedor', d.provider_retention_days+' días según su política'+(d.terms_verified ? '' : ' · SIN VERIFICAR'), !d.terms_verified);
    term(list, 'Límites de gasto', usd(d.limits_usd.per_user_daily)+' por usuario por día · '+usd(d.limits_usd.global_daily)+' global por día · '+usd(d.limits_usd.global_monthly)+' global por mes');
    term(list, 'Cancelar', 'Deja de esperar la respuesta. Si el pedido ya llegó al proveedor, puede cobrarse igual.');
    term(list, 'Reintentos', 'Nunca automáticos. Un resultado incierto se consulta, no se reenvía.');
    const blocked = a.state !== 'needs_consent';
    $('cloud-block').hidden = !blocked;
    $('cloud-block').textContent = blocked ? a.reason : '';
    $('cloud-agree-row').hidden = blocked;
    $('cloud-accept').hidden = blocked;
    $('cloud-recheck').hidden = a.state !== 'unavailable';
    $('cloud-agree').checked = false;
    $('cloud-accept').disabled = true;
  }
  async function loadCloud(refresh) {
    try { cloudInfo = await api('/api/cloud'); }
    catch { cloudInfo = {configured:false}; }
    MODES.cloud.configured = !!(cloudInfo.configured && cloudInfo.activation && cloudInfo.activation.state === 'ready');
    $('mode-cloud').disabled = !!pending || !cloudInfo.configured;
    $('mode-cloud').title = cloudInfo.configured ? '' : (cloudInfo.reason || 'Cloud no está configurado en esta PC.');
    if (refresh) { showWhere(); if (current === 'cloud') showConsent(); }
  }
  async function restoreCloudTurn() {
    if (MODES.cloud.restored) return;
    MODES.cloud.restored = true;
    let last=null;try{last=sessionStorage.getItem(MODES.cloud.key);}catch{}
    const rid = (cloudInfo && cloudInfo.active_request_id) || last;
    if (!rid) return;
    try { const turn = await api('/api/cloud/chat/'+rid); pending = turn.request; MODES.cloud.history = turn.request.messages.slice(0,-1);
      for (const m of turn.request.messages) message(m.role, m.content); finish(turn); if (pending) poll(); }
    catch { remember(null); }
  }
  async function switchTo(mode) {
    if (pending || mode === current) return;
    if (mode === 'cloud' && !(cloudInfo && cloudInfo.configured)) return;
    M().nodes = [...log.childNodes];               // keep each session's own view
    current = mode;
    log.replaceChildren(...M().nodes);
    if (mode === 'cloud') {
      await loadCloud(false);
      if (!log.childNodes.length) outcome('Conversación Cloud nueva. No incluye tu conversación local.');
      await restoreCloudTurn();
    } else {
      $('cloud-consent').hidden = true;
    }
    showWhere(); if (mode === 'cloud') showConsent();
    if (!pending) status('idle', idleMessage());
  }
  $('mode-local').addEventListener('click', () => switchTo('local'));
  $('mode-cloud').addEventListener('click', () => switchTo('cloud'));
  $('cloud-back').addEventListener('click', () => switchTo('local'));
  $('cloud-recheck').addEventListener('click', async () => { await loadCloud(true); if (!pending) status('idle', idleMessage()); });
  $('cloud-agree').addEventListener('change', () => { $('cloud-accept').disabled = !$('cloud-agree').checked; });
  $('cloud-accept').addEventListener('click', async () => {
    if (!$('cloud-agree').checked || !cloudInfo) return;
    $('cloud-accept').disabled = true;
    try { await api('/api/cloud/consent', {code: cloudInfo.consent_code}); }
    catch (e) { $('cloud-block').hidden = false; $('cloud-block').textContent = e.message; }
    await loadCloud(true);
    if (!pending) status('idle', idleMessage());
  });
  $('cloud-revoke').addEventListener('click', async () => {
    if (pending) return;
    try { await api('/api/cloud/revoke', {}); } catch (e) { status('error', e.message); }
    await loadCloud(true);
    status('idle', idleMessage());
  });

  async function connect() {
    try {
      localInfo=await api('/api/chat');MODES.local.configured=localInfo.configured;
      await loadCloud(false);
      showWhere();
      status(localInfo.configured?'idle':'unconfigured',idleMessage());
      let last=null;try{last=sessionStorage.getItem(MODES.local.key);}catch{}
      const rid=localInfo.active_request_id||last;
      if(rid){
        let turn;
        try{turn=await api('/api/chat/'+rid);}catch(e){if(e.status===404){remember(null);return;}throw e;}
        pending=turn.request;
        MODES.local.history=turn.request.messages.slice(0,-1);
        for(const m of turn.request.messages)message(m.role,m.content);
        status('waiting','Esperando el turno activo de esta sesión');finish(turn);if(pending)poll();
      }
    } catch { status('offline','No se pudo consultar Hermes. Recargá para volver a conectar.'); }
  }
  connect();
})();
