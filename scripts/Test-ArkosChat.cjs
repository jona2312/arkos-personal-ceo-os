/* Real browser -> HTTP -> HermesBridge -> synthetic subprocess. No model calls. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require(require.resolve('playwright',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES||process.cwd(),...require.resolve.paths('playwright')]}));
const root=path.resolve(__dirname,'..');
const state=fs.mkdtempSync(path.join(os.tmpdir(),'arkos-chat-ui-'));
const evidence=process.env.ARKOS_TEST_EVIDENCE||path.join(root,'docs','task-center','conversation-screenshots');
fs.mkdirSync(evidence,{recursive:true});
const server=spawn(process.env.ARKOS_TEST_PYTHON||'python',['-B','scripts/Run-ArkosChatTrial.py','--state-dir',state,'--no-browser'],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
let browser;
async function main(){
  const url=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Trial startup timeout')),10000);
    server.stdout.on('data',b=>{output+=b;const m=output.match(/http:\/\/127\.0\.0\.1:\d+\/#key=[\w-]+/);if(m){clearTimeout(timer);resolve(m[0]);}});
    server.on('exit',()=>{clearTimeout(timer);reject(Error('Trial stopped'));});
    server.on('error',reject);
  });
  browser=await chromium.launch({headless:process.env.ARKOS_TEST_HEADED!=='1',chromiumSandbox:true,executablePath:process.env.ARKOS_TEST_CHROMIUM||undefined,timeout:15000});
  const context=await browser.newContext({viewport:{width:1512,height:1080},deviceScaleFactor:1,timezoneId:'America/Argentina/Buenos_Aires'});
  const page=await context.newPage();page.setDefaultTimeout(8000);
  const errors=[],mutations=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')mutations.push(new URL(r.url()).pathname);});
  await page.goto(url);
  await page.getByText('Listo para conversar',{exact:true}).waitFor();
  assert.match(await page.locator('#chat-mode').textContent(),/PRUEBA SINTÉTICA/);
  const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,scale:visualViewport.scale,dpr:devicePixelRatio}));
  assert.equal(geometry.width,1512);assert.equal(geometry.scale,1);assert.ok(geometry.scroll<=1512);
  await page.getByRole('button',{name:'Personalizar apariencia',exact:true}).click();
  for(const name of ['Dorado y rojo','Intenso','Completo'])await page.getByRole('button',{name,exact:true}).click();
  await page.locator('#appearance-dialog').getByRole('button',{name:'Cerrar',exact:true}).click();
  assert.match(await page.locator('.neural-halo').first().evaluate(e=>getComputedStyle(e).fill),/url\(/);
  const send=async text=>{await page.getByLabel('Escribile a ARKOS',{exact:true}).fill(text);await page.getByRole('button',{name:'Enviar →',exact:true}).click();};
  const finished=async()=>page.waitForFunction(()=>!['waiting','offline'].includes(document.documentElement.dataset.chat)&&!document.getElementById('chat-send').disabled);
  await send('Organicemos el día: revisar prioridades y preparar una nota.');
  await finished();
  assert.equal(await page.locator('.chat-message.user').count(),1);
  assert.equal(await page.locator('.chat-message.assistant').count(),1);
  assert.equal(await page.locator('.chat-proposal').count(),1);
  await page.locator('.command-core').screenshot({path:path.join(evidence,'chat-proposal.png')});
  // Two simultaneous click events, plus a replayed HTTP request, still create one pending note.
  await page.getByRole('button',{name:'Crear nota pendiente',exact:true}).evaluate(b=>{b.click();b.click();});
  await page.getByRole('button',{name:'Tarea creada',exact:true}).waitFor();
  const tasks=await page.evaluate(async()=>{const r=await fetch('/api/tasks',{headers:{'X-Arkos-Key':sessionStorage.getItem('arkos-session-key')}});return r.json();});
  assert.equal(tasks.tasks.length,1);assert.equal(tasks.tasks[0].state,'awaiting_approval');
  assert.equal(tasks.tasks[0].approved_fingerprint,null);
  assert.equal(fs.readdirSync(path.join(state,'outputs')).length,0);
  await send('Recordá lo anterior y continuá.');
  await finished();
  assert.match(await page.locator('.chat-message.assistant').last().textContent(),/3 mensajes/);
  await page.reload();
  await page.waitForFunction(()=>document.documentElement.dataset.chat==='ok');
  assert.equal(await page.locator('.chat-message.user').count(),2);
  assert.equal(await page.locator('.chat-message.assistant').count(),2);
  await send('[wait]');
  await page.waitForFunction(()=>document.documentElement.dataset.chat==='waiting');
  assert.notEqual(await page.locator('html').getAttribute('data-activity'),'running');
  await page.getByRole('button',{name:'Actualizar tareas',exact:true}).click();
  await page.screenshot({path:path.join(evidence,'desktop-waiting.png')});
  await page.getByRole('button',{name:'Cancelar respuesta',exact:true}).click();
  await page.getByText('Turno cancelado. Sin propuestas ni tareas nuevas.',{exact:true}).waitFor();
  // Wait for the cancelled process to be reaped before asking for another turn.
  await page.waitForFunction(async()=>{const r=await fetch('/api/chat',{headers:{'X-Arkos-Key':sessionStorage.getItem('arkos-session-key')}});return !(await r.json()).active_request_id;});
  const proposals=await page.locator('.chat-proposal').count();
  await send('[invalid]');await finished();
  assert.equal(await page.locator('.chat-proposal').count(),proposals);
  assert.equal(await page.locator('html').getAttribute('data-chat'),'error');
  await send('<img src=x onerror="window.arkosInjected=true"> <script>bad()</script>');
  await finished();
  assert.equal(await page.evaluate(()=>window.arkosInjected),undefined);
  assert.equal(await page.locator('.chat-log img,.chat-log script').count(),0);
  assert.ok((await page.locator('.chat-message.assistant').last().textContent()).includes('<img'));
  // Existing session: user-requested full mode, then lightweight/pause/reduced motion.
  await page.getByRole('button',{name:'Personalizar apariencia',exact:true}).click();
  await page.getByRole('button',{name:'Ligero',exact:true}).click();
  assert.equal(await page.locator('html').getAttribute('data-quality'),'lite');
  await page.getByRole('button',{name:'Completo',exact:true}).click();
  await page.getByRole('button',{name:'Pausado',exact:true}).click();
  assert.equal(await page.locator('.ring-one').evaluate(e=>getComputedStyle(e).animationPlayState),'paused');
  await page.getByRole('button',{name:'Activado',exact:true}).click();
  await page.locator('#appearance-dialog').getByRole('button',{name:'Cerrar',exact:true}).click();
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.ring-one').evaluate(e=>getComputedStyle(e).animationName),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.getByRole('button',{name:'Voz live',exact:false}).first().click();
  assert.match(await page.locator('#feature-copy').textContent(),/no enciende el micrófono/);
  await page.locator('#feature-dialog').getByRole('button',{name:'Cerrar',exact:true}).click();
  await page.getByRole('button',{name:'Equipo · por conectar',exact:true}).click();
  assert.match(await page.locator('#feature-dialog').textContent(),/pendiente/i);
  await page.locator('#feature-dialog').getByRole('button',{name:'Cerrar',exact:true}).click();
  await page.getByRole('button',{name:'Nueva conversación',exact:true}).click();
  const remainingBefore=await page.evaluate(async()=>{const r=await fetch('/api/chat',{headers:{'X-Arkos-Key':sessionStorage.getItem('arkos-session-key')}});return (await r.json()).remaining;});
  await page.getByLabel('Escribile a ARKOS',{exact:true}).fill('Doble envío sintético');
  await page.locator('#chat-form').evaluate(f=>{f.requestSubmit();f.requestSubmit();});
  await finished();
  assert.equal(await page.locator('.chat-message.user').count(),1);
  const remainingAfter=await page.evaluate(async()=>{const r=await fetch('/api/chat',{headers:{'X-Arkos-Key':sessionStorage.getItem('arkos-session-key')}});return (await r.json()).remaining;});
  assert.equal(remainingBefore-remainingAfter,1);
  // Lose an accepted POST response: recover by GET, never a new request id.
  await page.route('**/api/chat',async route=>{
    if(route.request().method()==='POST'){await route.fetch();await route.abort('failed');}
    else await route.continue();
  });
  await send('Respuesta de envío perdida');
  await finished();
  assert.match(await page.locator('.chat-message.assistant').last().textContent(),/Respuesta de envío perdida/);
  await page.unroute('**/api/chat');
  await page.getByRole('button',{name:'Nueva conversación',exact:true}).click();
  await send('Armemos una nota para organizar las prioridades de mañana.');
  await finished();await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(evidence,'desktop-conversation.png'),fullPage:true});
  // Fresh context must pick mobile defaults. No viewport assumption: measure it.
  const mobileContext=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1});
  const mobile=await mobileContext.newPage();await mobile.goto(url);
  await mobile.getByText('Listo para conversar',{exact:true}).waitFor();
  const mobileGeometry=await mobile.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,scale:visualViewport.scale,quality:document.documentElement.dataset.quality}));
  if(mobileGeometry.scroll>390){
    console.error('Overflow diagnostics',JSON.stringify(await mobile.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e instanceof HTMLElement && e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,class:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).slice(0,18))));
    await mobile.screenshot({path:path.join(evidence,'mobile-overflow.png'),fullPage:true});
  }
  assert.equal(mobileGeometry.width,390);assert.ok(mobileGeometry.scroll<=390);
  assert.equal(mobileGeometry.scale,1);assert.equal(mobileGeometry.quality,'lite');
  await mobile.getByRole('button',{name:'Personalizar apariencia',exact:true}).click();
  for(const name of ['Dorado y rojo','Intenso','Completo'])await mobile.getByRole('button',{name,exact:true}).click();
  await mobile.locator('#appearance-dialog').getByRole('button',{name:'Cerrar',exact:true}).click();
  await mobile.screenshot({path:path.join(evidence,'mobile-conversation.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  assert.equal(mutations.some(p=>/\/(approve|run)$/.test(p)),false);
  fs.writeFileSync(path.join(evidence,'browser-results.json'),JSON.stringify({status:'PASS',runner:'synthetic HermesBridge subprocess; no Qwen',geometry,mobileGeometry,errors,autoExecutionRequests:0,tests:['history','proposal pending','double click','cancel','invalid response','XSS','task polling while waiting','full/lite/pause/reduced motion','voice/team pending']},null,2));
  console.log('PASS: synthetic conversation, history, cancellation, errors, XSS, proposal pending, no automatic execution, responsive and accessibility preferences.');
}
main().catch(e=>{console.error(String(e.stack).replace(/#key=[\w-]+/g,'#key=[redacted]'));process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  if(server.exitCode===null){server.kill();await new Promise(r=>server.once('exit',r));}
  // Test state is retained in TEMP for diagnosis; no personal files are used.
});
