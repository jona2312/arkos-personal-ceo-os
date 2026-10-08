'use strict';
const $ = (id) => document.getElementById(id);
const state = {tasks: [], status: {}, online: false, page: 'home', refreshing: false, review: null, proposal: '', artifact: null};
const labels = {awaiting_approval: 'Por aprobar', queued: 'En cola', running: 'Ejecutando', completed: 'Completada', blocked: 'Revisar bloqueo', cancelled: 'Cancelada'};
const pages = {home: 'Hoy', conversation: 'Conversación', tasks: 'Tareas', results: 'Resultados', connections: 'Conexiones'};
const storage = {get(k) {try {return localStorage.getItem(k);} catch {return null;}}, set(k,v) {try {localStorage.setItem(k,v);} catch { /* preferences remain session-only */ }}};
let key = new URLSearchParams(location.hash.slice(1)).get('key');
try { if (key) sessionStorage.setItem('arkos-session-key', key); else key = sessionStorage.getItem('arkos-session-key'); } catch { /* keep key only in memory */ }
if (location.hash.startsWith('#key=')) history.replaceState(null, '', location.pathname);
let toastTimer;
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => {$('toast').hidden = true;}, 5500); }
function element(tag, className, content) {const node = document.createElement(tag); if (className) node.className = className; if (content !== undefined) node.textContent = content; return node;}
async function api(path, data) {
  const options = {headers: {'X-Arkos-Key': key || ''}, cache: 'no-store'};
  if (data !== undefined) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(data); }
  let response;
  try {response = await fetch(path, options);} catch {throw new Error('No se pudo contactar a ARKOS. Actualizá las tareas antes de reintentar: el último pedido podría haberse guardado.');}
  if (!response.ok) {const body = await response.json().catch(() => ({})); throw new Error(body.error || 'No se pudo completar el pedido.');}
  return response.json();
}
function matches(task, filter) {if (filter === 'review') return ['awaiting_approval','blocked'].includes(task.state); if (filter === 'active') return ['queued','running'].includes(task.state); return filter === 'all' || task.state === filter;}
function title(task) {return task.payload.action === 'note' ? (task.payload.text.trim().split('\n')[0].slice(0,70) || 'Nota') : 'Recorte de video';}
function description(task) {return task.payload.action === 'note' ? task.payload.text : `${task.payload.source}\nDesde ${task.payload.start} s · ${task.payload.duration} s de duración`;}
function statusPill(task) {return element('span', 'status-pill ' + task.state, labels[task.state] || task.state);}
function taskCard(task, results = false) {
  const card = element('article', 'task-card'); card.dataset.taskId = task.id; card.dataset.state = task.state;
  const top = element('div', 'card-top'); top.append(element('span', 'card-type', task.payload.action === 'note' ? '▧' : '▷'), element('span', '', new Date(task.created * 1000).toLocaleDateString('es-AR', {day:'numeric',month:'short'})));
  card.append(top, element('span','origin-pill','Solo esta PC'), element('h3','',title(task)), element('p','excerpt',description(task)), statusPill(task));
  const action = element('button','secondary card-action', task.state === 'completed' ? 'Abrir resultado ↗' : task.state === 'queued' ? 'Revisar y ejecutar →' : 'Ver tarea →');
  action.disabled = !state.online;
  action.addEventListener('click', () => {if (task.state === 'completed') openArtifact(task).catch(e => toast(e.message)); else review(task);});
  card.append(action); return card;
}
function empty(target, heading, message) {const block = element('div','empty-state');block.append(element('strong','',heading),element('span','',message));target.append(block);}
function render() {
  $('stat-review').textContent = state.tasks.filter(t => matches(t,'review')).length;
  $('stat-active').textContent = state.tasks.filter(t => t.state === 'queued').length;
  $('stat-running').textContent = state.tasks.filter(t => t.state === 'running').length;
  $('stat-completed').textContent = state.tasks.filter(t => matches(t,'completed')).length;
  $('nav-count').textContent = state.tasks.filter(t => !['completed','cancelled'].includes(t.state)).length;
  const board = $('home-board'); board.replaceChildren();
  for (const [filter,label,hint] of [['review','Por revisar','Tus próximas decisiones aparecen acá.'],['queued','En cola','Aprobadas. Vos elegís cuándo empezar.'],['running','Ejecutando','Las tareas en curso aparecerán acá.'],['completed','Terminadas','Cada resultado tendrá su lugar.']]) {
    const tasks = state.tasks.filter(t => matches(t,filter)).reverse(); const column = element('div','board-column');
    const heading = element('div','column-heading'); heading.append(element('strong','',label),element('span','',tasks.length));column.append(heading);
    if (!tasks.length) column.append(element('div','column-empty',hint)); else tasks.slice(0,3).forEach(t => column.append(taskCard(t)));
    board.append(column);
  }
  const list = $('tasks-list'); list.replaceChildren();
  const query = $('task-search').value.toLocaleLowerCase();
  const tasks = state.tasks.filter(t => matches(t,$('task-filter').value) && description(t).toLocaleLowerCase().includes(query)).reverse();
  tasks.forEach(t => list.append(taskCard(t))); if (!tasks.length) empty(list,'Un espacio para tu próximo paso','Creá una tarea o cambiá los filtros.');
  const results = $('results-list'); results.replaceChildren();
  state.tasks.filter(t => t.state === 'completed').reverse().forEach(t => results.append(taskCard(t,true)));
  if (!results.children.length) empty(results,'Los resultados empiezan con una idea','Creá, revisá y ejecutá tu primera nota.');
  renderConnections();
  renderInbox();
  renderNeuralActivity();
  document.querySelectorAll('.new-task-button,.new-note-button,#quick-clip,#proposal-form button[type=submit]').forEach(b => b.disabled = !state.online);
}
function renderConnections() {
  const container = $('connections-grid'); container.replaceChildren();
  const items = [
    ['▧','Notas y documentos','Guardá contenido en Markdown desde una tarea revisada.',state.online ? 'Disponible en esta PC' : 'Sin conexión local'],
    ['▷','Video · FFmpeg','Recortes locales con inicio y duración; se conserva el original.',state.status.ffmpeg ? 'Detectado · requiere revisión' : 'FFmpeg no detectado'],
    ['◌','Hermes','El motor conversacional del piloto. Su conexión con este panel todavía falta.','Integración pendiente'],
    ['✉','Correo','Lectura, organización y respuestas desde una cuenta autorizada.','Conexión pendiente'],
    ['▦','Calendario','Agenda, disponibilidad y eventos en tu cuenta.','Conexión pendiente'],
    ['◉','WhatsApp','Mensajes autorizados y encargos desde el teléfono.','Conexión pendiente'],
    ['⌁','Celular y PC','Encargos compartidos, dispositivos vinculados y resultados sincronizados.','Sincronización pendiente'],
    ['◷','Actividad de la PC','Arranque, tiempo activo y resumen diario. Hoy solo se mide esta pestaña.','Agente de actividad pendiente'],
    ['A↔','Traductor','Traducción de texto y voz con revisión antes de enviar.','Integración pendiente'],
    ['⌘','Equipo e invitados','Mensajes y tareas compartidas con permisos por espacio.','Integración pendiente']
  ];
  for (const [symbol,name,copy,status] of items) {const card=element('article','connection-card');card.append(element('div','connection-symbol',symbol),element('h2','',name),element('p','',copy),element('span','status-pill',status));container.append(card);}
}
// Read-only display adapter to the configured snapshot; no execution authority.
let remoteView={projection_version:1,sync_status:'not_configured',device_status:'unknown',last_sync:null,tasks:[]};
function remoteUnavailable(){remoteView={...remoteView,sync_status:remoteView.last_sync?'stale':'unavailable',device_status:'unknown'};ArkosRemoteView.render($('remote-view'),remoteView);}
async function refreshRemote(){try{remoteView=ArkosRemoteView.validate(await api('/api/remote-view'));ArkosRemoteView.render($('remote-view'),remoteView);}catch{remoteUnavailable();}}
async function refresh() {
  if (state.refreshing) return; state.refreshing = true;
  try {
    const [status, tasks] = await Promise.all([api('/api/status'),api('/api/tasks')]);
    state.status = status; state.tasks = tasks.tasks; state.online = true;
    $('connection-banner').hidden = true; $('device-label').textContent = 'Esta PC · conectada'; $('device-dot').classList.remove('offline');
    await refreshRemote();
    $('last-sync').textContent = 'Actualizado ' + new Date().toLocaleTimeString('es-AR',{hour:'2-digit',minute:'2-digit'});
  } catch (e) {
    remoteUnavailable();
    state.online = false; $('connection-banner').textContent = e.message; $('connection-banner').hidden = false;
    $('device-label').textContent = 'Sin conexión local'; $('device-dot').classList.add('offline'); $('last-sync').textContent = 'Datos sin actualizar';
  } finally {state.refreshing = false; render();}
}
function page(name) {
  if (!pages[name]) return; state.page = name;
  document.querySelectorAll('.page').forEach(p => p.hidden = p.id !== 'page-' + name);
  document.querySelectorAll('[data-page]').forEach(b => {b.classList.toggle('active',b.dataset.page === name); if(b.dataset.page===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  $('breadcrumb-page').textContent = pages[name]; window.scrollTo({top:0});
}
function setKind(kind) {$('task-kind').value = kind; $('note-fields').hidden = kind !== 'note'; $('clip-fields').hidden = kind !== 'clip'; $('note-text').required = kind === 'note'; $('clip-source').required = kind === 'clip';}
function newTask(kind='note', content='') {if (!state.online) return toast('Abrí ARKOS local para guardar tareas.');$('task-form').reset();$('create-error').textContent='';setKind(kind);$('note-text').value=content;$('task-dialog').showModal();(kind==='note'?$('note-text'):$('clip-source')).focus();}
function review(task) {
  state.review = task; $('review-title').textContent = title(task); $('review-content').textContent = description(task);
  $('review-state').replaceWith(Object.assign(statusPill(task),{id:'review-state'})); $('review-error').textContent='';
  const detail = task.state==='awaiting_approval' ? 'Aprobar habilita esta tarea por 24 horas. La ejecución se inicia por separado.' : task.state==='blocked' ? 'Revisá el error y cualquier salida anterior antes de volver a aprobar. '+ (task.result || 'La aprobación venció o el contenido cambió.') : task.state==='queued' ? 'La ejecución usa exactamente el contenido aprobado. Vence: '+ new Date(task.approval_until*1000).toLocaleString('es-AR') : task.state==='running' ? 'La tarea está ejecutándose. Este piloto no cancela una ejecución en curso. Si el proceso se interrumpió, Codex debe revisar las salidas antes de recuperarla.' : 'Esta tarea se conserva en el historial.';
  $('review-detail').textContent=detail;
  const actions=$('review-actions');actions.replaceChildren();
  const add=(text,cls,fn)=>{const b=element('button',cls,text);b.disabled=!state.online;b.addEventListener('click',fn);actions.append(b);};
  if(['awaiting_approval','blocked','queued'].includes(task.state)) add('Cancelar tarea','danger',()=>act('cancel',{}));
  if(['awaiting_approval','blocked'].includes(task.state)) add('Aprobar esta tarea','primary',()=>act('approve',{fingerprint:task.fingerprint}));
  if(task.state==='queued') {add('Ejecutar esta tarea','primary',()=>act('run',{})); if(state.status.worker_busy) {actions.lastChild.disabled=true;$('review-detail').textContent+=' Otra tarea está en ejecución.';}}
  if (!$('review-dialog').open) $('review-dialog').showModal();
}
async function act(action,data) {
  const task = state.review; $('review-actions').querySelectorAll('button').forEach(b=>b.disabled=true);
  try {await api('/api/tasks/'+task.id+'/'+action,data);$('review-dialog').close();await refresh();toast(action==='approve'?'Tarea aprobada. Ya podés ejecutarla.':action==='run'?'Ejecución solicitada. El tablero mostrará el resultado.':'Tarea cancelada.');}
  catch(e){$('review-error').textContent=e.message;await refresh();/* Reopen review from fresh board; don't automatically repeat uncertain actions. */}
}
async function openArtifact(task) {
  const response=await fetch('/api/tasks/'+task.id+'/artifact',{headers:{'X-Arkos-Key':key||''},cache:'no-store'});
  if(!response.ok){const b=await response.json();throw new Error(b.error||'Resultado no disponible.');}
  state.artifact={blob:await response.blob(),name:'arkos-'+task.id.slice(0,8)+(task.payload.action==='note'?'.md':'.mp4')};
  $('result-title').textContent=title(task);
  $('result-text').textContent=task.payload.action==='note'?await state.artifact.blob.text():'Video generado. Descargalo para abrirlo en tu reproductor.';
  $('result-dialog').showModal();
}
$('download-result').addEventListener('click',()=>{if(!state.artifact)return;const url=URL.createObjectURL(state.artifact.blob);const a=document.createElement('a');a.href=url;a.download=state.artifact.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('result-dialog').addEventListener('close',()=>{state.artifact=null;});
$('task-form').addEventListener('submit',async(event)=>{
  event.preventDefault();const submit=event.submitter;submit.disabled=true;$('create-error').textContent='';
  try {const body=$('task-kind').value==='note'?{action:'note',text:$('note-text').value}:{action:'clip',source:$('clip-source').value.trim(),start:Number($('clip-start').value),duration:Number($('clip-duration').value)};await api('/api/tasks',body);$('task-dialog').close();await refresh();toast('Tarea guardada. Revisala para aprobar su ejecución.');}
  catch(e){$('create-error').textContent=e.message;}finally{submit.disabled=false;}
});
$('proposal-form').addEventListener('submit',async(event)=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const goal=$('goal').value;const result=await api('/api/propose',{goal});state.proposal=goal;$('proposal-next').textContent=result.next_step;$('proposal-tools').replaceChildren();for(const t of result.tools)$('proposal-tools').append(element('span','tool-chip',t.name+' · '+(t.status==='ready'?'disponible':t.status==='detected'?'detectada':'requiere preparación')));$('proposal-result').hidden=false;}catch(e){toast(e.message);}finally{button.disabled=!state.online;}});
$('save-proposal').addEventListener('click',()=>newTask('note',state.proposal));
$('task-kind').addEventListener('change',()=>setKind($('task-kind').value));
$('task-search').addEventListener('input',render);$('task-filter').addEventListener('change',render);
$('refresh-button').addEventListener('click',refresh);
document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>page(b.dataset.page)));
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>page(b.dataset.go)));
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{$('task-filter').value=b.dataset.filter;render();page('tasks');}));
document.querySelectorAll('.new-task-button,.new-note-button').forEach(b=>b.addEventListener('click',()=>newTask()));
$('quick-clip').addEventListener('click',()=>newTask('clip'));
document.querySelectorAll('.close-dialog').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
function theme(kind,value){if(kind==='theme'&&!['dark','light'].includes(value))value='dark';if(kind==='accent'&&!['neural','blue','red','violet','mono'].includes(value))value='neural';document.documentElement.dataset[kind]=value;storage.set('arkos-'+kind,value);document.querySelectorAll('[data-'+kind+'-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset[kind+'Choice']===value)));}
$('appearance-button').addEventListener('click',()=>$('appearance-dialog').showModal());
const mobileAppearance=element('button','icon-button','◐');mobileAppearance.setAttribute('aria-label','Personalizar apariencia');mobileAppearance.addEventListener('click',()=>$('appearance-dialog').showModal());document.querySelector('.top-actions').prepend(mobileAppearance);
document.querySelectorAll('[data-theme-choice]').forEach(b=>b.addEventListener('click',()=>theme('theme',b.dataset.themeChoice)));
document.querySelectorAll('[data-accent-choice]').forEach(b=>b.addEventListener('click',()=>theme('accent',b.dataset.accentChoice)));
// Notices are derived from the actual task snapshot; no messages are invented.
const noticeText = {awaiting_approval:'Necesita tu aprobación', queued:'Lista para ejecutar', running:'ARKOS está trabajando', completed:'Tu resultado está listo', blocked:'Hay una tarea que revisar'};
let seenNotices = new Set();
try {const saved=JSON.parse(storage.get('arkos-seen-notices')||'[]');if(Array.isArray(saved))seenNotices=new Set(saved.filter(v=>typeof v==='string').slice(-1000));} catch { /* Ignore malformed browser preferences. */ }
function noticeKey(task){return task.id+':'+task.state+':'+task.updated;}
function notices(){return state.tasks.filter(t=>noticeText[t.state]).slice().sort((a,b)=>b.updated-a.updated);}
function saveSeen(){storage.set('arkos-seen-notices',JSON.stringify([...seenNotices].slice(-1000)));}
function renderInbox(){
  const list=$('personal-inbox');list.replaceChildren();const tasks=notices();
  $('inbox-count').textContent=tasks.filter(t=>!seenNotices.has(noticeKey(t))).length;
  $('inbox-read').disabled=!state.online||!tasks.some(t=>!seenNotices.has(noticeKey(t)));
  if(!tasks.length){empty(list,'Todo en su lugar','Los avisos aparecerán cuando crees una tarea.');return;}
  for(const task of tasks.slice(0,5)){
    const unseen=!seenNotices.has(noticeKey(task));const item=element('button','notice notice-'+task.state+' '+(unseen?'unseen':'seen'));
    const copy=element('span','notice-copy');copy.append(element('strong','',noticeText[task.state]),element('p','',title(task)),element('small','',new Date(task.updated*1000).toLocaleString('es-AR',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})));
    item.append(element('span','notice-symbol',task.state==='completed'?'✓':task.state==='blocked'?'!':'◇'),copy);
    if(unseen)item.append(element('span','notice-unread'));item.disabled=!state.online;
    item.addEventListener('click',()=>{seenNotices.add(noticeKey(task));saveSeen();renderInbox();if(task.state==='completed')openArtifact(task).catch(e=>toast(e.message));else review(task);});list.append(item);
  }
}
$('inbox-read').addEventListener('click',()=>{notices().forEach(t=>seenNotices.add(noticeKey(t)));saveSeen();renderInbox();});
const features={
  voice:['Voz en vivo','El modo voz permitirá hablar, escuchar e interrumpir a ARKOS. Todavía no está conectado; este botón no enciende el micrófono.','Siguiente paso: integrar transcripción, Hermes y síntesis de voz, con indicador de escucha y botón de detener.'],
  activity:['Actividad de tu PC','El contador actual mide el tiempo desde que abriste esta pestaña. No mide el arranque de Windows, horas trabajadas ni actividad de otras aplicaciones.','Siguiente paso: un agente local que distinga PC encendida, sesión activa y pausas, con tu configuración y sin registrar teclas ni contenido.'],
  weather:['Clima y temperatura','Todavía no hay una fuente meteorológica conectada ni una ciudad seleccionada. No mostramos temperatura estimada.','Siguiente paso: elegir ciudad manualmente y autorizar la consulta; mostrar fuente, hora de actualización y último dato disponible.'],
  news:['Noticias para tu día','La selección de noticias está pendiente. Los titulares deberán tener fuente, fecha y enlace al original.','Siguiente paso: elegir temas, conectar fuentes y separar los hechos publicados del resumen de ARKOS.'],
  team:['Equipo e invitados','Los mensajes de equipo y las tareas compartidas requieren cuentas e invitaciones. Esta bandeja solo muestra avisos de tus tareas locales.','Siguiente paso: espacios compartidos, permisos por miembro, responsables y comentarios. Ninguna invitación da acceso a tus archivos personales.'],
  translator:['Traductor de idiomas','La traducción de texto y voz está prevista, pero todavía no hay un motor conectado.','Siguiente paso: idioma de origen y destino, original junto a la traducción y revisión antes de enviar. Identificar cuándo se procesa localmente o en un servicio externo.']
};
document.querySelectorAll('[data-feature]').forEach(button=>button.addEventListener('click',()=>{const [name,copy,next]=features[button.dataset.feature];$('feature-title').textContent=name;$('feature-copy').textContent=copy;$('feature-next').textContent=next;$('feature-dialog').showModal();}));
$('feature-connections').addEventListener('click',()=>$('feature-dialog').close());
$('writing-mode').addEventListener('click',()=>$('goal').focus());
const panelOpened=performance.now();
function updateTime(){
  const now=new Date();$('local-clock').textContent=now.toLocaleTimeString('es-AR',{hour:'2-digit',minute:'2-digit',hour12:false});$('local-clock').dateTime=now.toISOString();
  $('local-date').textContent=now.toLocaleDateString('es-AR',{weekday:'long',day:'numeric',month:'long'});
  const elapsed=Math.floor((performance.now()-panelOpened)/1000);$('panel-duration').textContent=[Math.floor(elapsed/3600),Math.floor(elapsed/60)%60,elapsed%60].map(n=>String(n).padStart(2,'0')).join(':');
}
function motion(value){document.documentElement.dataset.motion=value==='off'?'off':'on';storage.set('arkos-motion',document.documentElement.dataset.motion);document.querySelectorAll('[data-motion-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.motionChoice===document.documentElement.dataset.motion)));}
document.querySelectorAll('[data-motion-choice]').forEach(b=>b.addEventListener('click',()=>motion(b.dataset.motionChoice)));
motion(storage.get('arkos-motion')||'on');
function pageVisibility(){document.documentElement.dataset.pageVisible=String(!document.hidden);if(!document.hidden)updateTime();}
pageVisibility();document.addEventListener('visibilitychange',pageVisibility);updateTime();setInterval(()=>{if(!document.hidden)updateTime();},1000);

theme('theme',storage.get('arkos-theme')||'dark');theme('accent',storage.get('arkos-accent')||'neural');
ArkosNeural.mount($('neural-backdrop'));
const networkLabels={offline:'Actividad local: sin actualizar · pulsos detenidos',running:'Actividad local: hay tareas ejecutándose',queued:'Actividad local: tareas en cola · esperando ejecución',review:'Actividad local: tareas por revisar',idle:'Actividad local: en reposo',completed:'Actividad local: una tarea acaba de terminar'};
let observedStates=null,completionUntil=0;
function renderNeuralActivity(){
  if(state.online){
    if(observedStates)for(const task of state.tasks)if(task.state==='completed'&&observedStates.has(task.id)&&observedStates.get(task.id)!=='completed')completionUntil=Date.now()+10000;
    observedStates=new Map(state.tasks.map(t=>[t.id,t.state]));
  }
  let value=ArkosNeural.activity(state.tasks,state.online);
  if(state.online&&value!=='running'&&Date.now()<completionUntil)value='completed';
  document.documentElement.dataset.activity=value;
  const label=networkLabels[value];if($('network-status').textContent!==label)$('network-status').textContent=label;
}
function visualPreference(kind,value){
  const options=kind==='glow'?['low','medium','high','off']:['lite','full'];
  if(!options.includes(value))value=options[0];
  document.documentElement.dataset[kind]=value;storage.set('arkos-'+kind,value);
  document.querySelectorAll('[data-'+kind+'-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset[kind+'Choice']===value)));
}
for(const kind of ['glow','quality'])document.querySelectorAll('[data-'+kind+'-choice]').forEach(b=>b.addEventListener('click',()=>visualPreference(kind,b.dataset[kind+'Choice'])));
visualPreference('glow',storage.get('arkos-glow')||'low');
visualPreference('quality',storage.get('arkos-quality')||(matchMedia('(max-width:760px)').matches?'lite':'full'));
refresh();setInterval(()=>{if(!document.hidden&&!document.querySelector('dialog[open]'))refresh();},3000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
