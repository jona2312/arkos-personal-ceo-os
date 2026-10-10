/* Chat uses the same authenticated local API; it never approves or executes work. */
(() => {
  'use strict';
  let history = [], pending = null, configured = false, cancelRequested = false;
  let polling = false, mode = 'unconfigured';
  function remember(rid) { try { if(rid)sessionStorage.setItem('arkos-chat-last-turn',rid);else sessionStorage.removeItem('arkos-chat-last-turn'); } catch { /* history remains in this page */ } }
  const log = $('chat-log'), input = $('chat-input');
  input.addEventListener('keydown',event=>{
    if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('chat-form').requestSubmit();}
  });
  function status(value, message) {
    document.documentElement.dataset.chat = value;
    $('chat-state').textContent = message;
    $('chat-send').disabled = !configured || !!pending;
    input.disabled = !configured || !!pending;
    $('chat-cancel').hidden = !pending;
    $('chat-cancel').disabled = cancelRequested;
    $('chat-new').disabled = !!pending;
  }
  function message(role, text) {
    const row = element('article', 'chat-message '+role);
    row.append(element('strong', '', role === 'user' ? 'Vos' : 'ARKOS'), element('p', '', text));
    log.append(row); return row;
  }
  function proposalCard(rid, proposal, created) {
    const card = element('details', 'chat-proposal'); card.open = true;
    card.append(element('summary', '', 'Propuesta · '+proposal.title), element('pre', '', proposal.text));
    const help = element('p', 'field-help', 'Crear la nota la deja pendiente de tu aprobación. No la ejecuta.');
    const button = element('button', 'secondary', created ? 'Tarea creada' : 'Crear nota pendiente');
    button.disabled = !!created;
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await api('/api/chat/'+rid+'/note', {proposal_id:proposal.proposal_id});
        button.textContent = 'Tarea creada';
        help.textContent = 'Encontrala en Tareas. Su aprobación y ejecución se hacen por separado.';
        await refresh();
      } catch(e) { help.textContent=e.message; button.disabled=false; }
    });
    card.append(help, button); return card;
  }
  function finish(turn) {
    if (!pending || turn.request.request_id !== pending.request_id) return;
    const rid = pending.request_id;
    if (turn.state === 'waiting') return;
    const result = turn.response;
    if (turn.state === 'ok' && result) {
      history = [...turn.request.messages, {role:'assistant',content:result.reply}].filter(m=>m.content.trim());
      const row=message('assistant',result.reply);
      for(const p of result.proposals) row.append(proposalCard(rid,p,turn.created_tasks[p.proposal_id]));
    } else {
      if(turn.state!=='cancelled')input.value=turn.request.messages.at(-1).content;
      log.append(element('p','chat-outcome',turn.state==='cancelled' ? 'Turno cancelado. Sin propuestas ni tareas nuevas.' :
        turn.state==='timeout' ? 'Se agotó el tiempo de espera. Sin propuestas ni tareas nuevas.' :
        'No se pudo completar el turno. Sin propuestas ni tareas nuevas.'));
    }
    pending=null; cancelRequested=false;$('chat-retry').hidden=true;
    status(turn.state,turn.state==='ok'?'Respuesta recibida · ejecución de tareas por separado':
      turn.state==='cancelled'?'Conversación cancelada':turn.state==='timeout'?'Tiempo de espera agotado':'Error de conversación');
    log.scrollTop=log.scrollHeight; input.focus();
  }
  async function poll() {
    if (!pending || polling) return;
    const queried=pending;
    polling=true;
    try {
      const turn=await api('/api/chat/'+queried.request_id);
      if(pending!==queried)return;
      if (cancelRequested && turn.state==='waiting') await api('/api/chat/'+queried.request_id+'/cancel',{});
      finish(turn);
    } catch(e) { if(pending===queried)status('offline','No se puede consultar el turno. Se reintentará la lectura; no se vuelve a enviar.'); }
    finally { polling=false; if(pending)setTimeout(poll,700); }
  }
  $('chat-form').addEventListener('submit',async event=>{
    event.preventDefault();
    if(pending||!configured||!input.value.trim())return;
    const text=input.value;
    const messages=[...history,{role:'user',content:text}];
    if(messages.length>20 || messages.reduce((n,m)=>n+m.content.length,0)>32000){
      status('error','El historial alcanzó su límite. Elegí Nueva conversación.');return;
    }
    pending={v:1,request_id:'ui-'+crypto.randomUUID(),messages};
    const submitted=pending;
    remember(submitted.request_id);
    cancelRequested=false;
    message('user',text);input.value='';
    status('waiting','Esperando a ARKOS · ninguna tarea se está ejecutando por este turno');
    try {
      const turn=await api('/api/chat',submitted);
      if(pending!==submitted)return;
      if(cancelRequested && turn.state==='waiting') await api('/api/chat/'+pending.request_id+'/cancel',{});
      finish(turn);
      if(pending)poll();
    } catch(e) {
      if(pending!==submitted)return;
      if(e.status){
        pending=null;cancelRequested=false;
        input.value=text;
        remember(null);
        log.append(element('p','chat-outcome',e.message));
        status('error',e.message);return;
      }
      // A lost POST response is ambiguous. Query its SAME id before allowing another send.
      try { const turn=await api('/api/chat/'+pending.request_id);finish(turn);if(pending)poll(); }
      catch {
        // Preserve the exact request for an explicit, idempotent retry.
        $('chat-retry').hidden=false;
        status('offline',e.message+' Podés reenviar el mismo turno sin duplicarlo.');
      }
    }
  });
  $('chat-retry').addEventListener('click',async()=>{
    if(!pending)return;
    const submitted=pending;
    $('chat-retry').disabled=true;
    try {
      const turn=await api('/api/chat',submitted);
      if(pending!==submitted)return;
      $('chat-retry').hidden=true;
      if(cancelRequested&&turn.state==='waiting')await api('/api/chat/'+pending.request_id+'/cancel',{});
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
    const cancelled=pending;
    cancelRequested=true;status('waiting','Cancelando conversación…');
    try{finish(await api('/api/chat/'+cancelled.request_id+'/cancel',{}));}
    catch { if(pending===cancelled){status('offline','Cancelación sin confirmar. Se consultará el turno.');poll();} }
  });
  $('chat-new').addEventListener('click',()=>{if(pending)return;history=[];remember(null);log.replaceChildren();status('idle',configured?'Listo para conversar':'Hermes por conectar');input.focus();});
  async function connect() {
    try {
      const info=await api('/api/chat');configured=info.configured;mode=info.mode;
      $('chat-mode').textContent=mode==='synthetic'?'PRUEBA SINTÉTICA · sin modelo real':configured?'Hermes · conversación local':'Hermes por conectar';
      status(configured?'idle':'unconfigured',configured?'Listo para conversar':'Hermes por conectar');
      let last=null;try{last=sessionStorage.getItem('arkos-chat-last-turn');}catch{}
      const rid=info.active_request_id||last;
      if(rid){
        let turn;
        try{turn=await api('/api/chat/'+rid);}catch(e){if(e.status===404){remember(null);return;}throw e;}
        pending=turn.request;
        history=turn.request.messages.slice(0,-1);
        for(const m of turn.request.messages)message(m.role,m.content);
        status('waiting','Esperando el turno activo de esta sesión');finish(turn);if(pending)poll();
      }
    } catch { status('offline','No se pudo consultar Hermes. Recargá para volver a conectar.'); }
  }
  connect();
})();
