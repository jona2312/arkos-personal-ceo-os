/* Real browser -> task center -> HTTP gateway -> official SDK -> local FAKE Messages API.
   No real keys, no paid calls. Requires requirements-cloud.txt in ARKOS_TEST_PYTHON. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require(require.resolve('playwright',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES||process.cwd(),...require.resolve.paths('playwright')]}));
const root=path.resolve(__dirname,'..');
const state=fs.mkdtempSync(path.join(os.tmpdir(),'arkos-cloud-ui-'));
const evidence=process.env.ARKOS_TEST_EVIDENCE||path.join(root,'docs','task-center','cloud-screenshots');
fs.mkdirSync(evidence,{recursive:true});
const server=spawn(process.env.ARKOS_TEST_PYTHON||'python',['-B','scripts/Run-ArkosCloudTrial.py','--state-dir',state,'--no-browser','--control'],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
let browser, stderr='';
server.stderr.on('data',b=>{stderr+=b;});
async function main(){
  const {url,control}=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Trial startup timeout: '+stderr.slice(-400))),20000);
    server.stdout.on('data',b=>{output+=b;const m=output.match(/\{"url".*\}/);if(m){clearTimeout(timer);resolve(JSON.parse(m[0]));}});
    server.on('exit',()=>{clearTimeout(timer);reject(Error('Trial stopped: '+stderr.slice(-400)));});
  });
  const ctrl=async(p,body={})=>{const r=await fetch(control+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});assert.ok(r.ok,p);return r.json();};
  browser=await chromium.launch({headless:process.env.ARKOS_TEST_HEADED!=='1',chromiumSandbox:!process.env.ARKOS_TEST_CHROMIUM,executablePath:process.env.ARKOS_TEST_CHROMIUM||undefined,timeout:15000});
  const results={status:'FAIL',provider:'fake Messages API on loopback via official SDK',steps:[]};
  const step=name=>results.steps.push(name);
  const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
  const page=await context.newPage();page.setDefaultTimeout(10000);
  const errors=[],mutations=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')mutations.push(new URL(r.url()).pathname);});
  await page.goto(url);
  await page.getByText('Listo para conversar',{exact:true}).waitFor();
  const html=page.locator('html');
  const where=()=>page.locator('#processing-where').textContent();
  const send=async text=>{await page.getByLabel('Escribile a ARKOS',{exact:true}).fill(text);await page.getByRole('button',{name:'Enviar →',exact:true}).click();};
  const finished=async()=>page.waitForFunction(()=>!['waiting','offline'].includes(document.documentElement.dataset.chat)&&!document.getElementById('chat-send').disabled);
  const settled=async()=>page.waitForFunction(()=>!['waiting','offline'].includes(document.documentElement.dataset.chat));
  // 1. Local by default; Cloud is not selected and nothing goes out.
  assert.equal(await html.getAttribute('data-processing'),'local');
  assert.equal(await page.locator('#mode-local').getAttribute('aria-checked'),'true');
  assert.match(await where(),/esta PC/);
  assert.equal((await ctrl('/requests')).count,0);
  await send('Dato local privado: la alarma es 4321');await finished();
  assert.equal(await page.locator('.chat-message.assistant').count(),1);
  step('local by default, Cloud not selected');
  // 2. Consent with provider, model, data, both retentions and spending limits.
  await page.getByRole('radio',{name:'Cloud',exact:true}).click();
  await page.locator('#cloud-consent').waitFor();
  const terms=await page.locator('#cloud-terms').textContent();
  for(const expected of ['anthropic · claude-haiku-5-5','PRUEBA con proveedor falso','Qué se envía','0 h','SIN VERIFICAR','USD 0.20 por usuario por día','USD 1.00 global por día','USD 10.00 global por mes','puede cobrarse igual','Nunca automáticos'])
    assert.ok(terms.includes(expected),'consent terms missing: '+expected);
  assert.equal(await page.locator('#chat-input').isDisabled(),true);
  assert.equal(await page.locator('#cloud-accept').isDisabled(),true);
  assert.equal(await page.locator('.chat-message').count(),0);  // local conversation not carried over
  await page.screenshot({path:path.join(evidence,'desktop-cloud-consent.png')});
  await page.getByLabel(/Entiendo qué se envía/).check();
  await page.getByRole('button',{name:'Aceptar y usar Cloud',exact:true}).click();
  await page.getByText('Listo para conversar por Cloud',{exact:true}).waitFor();
  assert.match(await where(),/Cloud de prueba · gateway ARKOS con proveedor falso/);
  assert.match(await page.locator('#chat-mode').textContent(),/CLOUD DE PRUEBA/);
  assert.match(await page.locator('#chat-input').getAttribute('placeholder'),/Cloud de prueba/);
  step('explicit consent with provider, model, data, retention and limits');
  // 3. Conversation and proposal -> pending task only. No local history sent.
  await send('Anotá comprar café');await finished();
  let seen=await ctrl('/requests');
  assert.deepEqual(seen.messages,[1]);
  assert.ok(!JSON.stringify(seen.contents).includes('alarma'),'local history leaked to Cloud');
  for(const forbidden of ['tools','tool_choice','cache_control','stream'])assert.ok(!seen.keys.includes(forbidden));
  assert.equal(await page.locator('.chat-proposal').count(),1);
  await page.getByRole('button',{name:'Crear nota pendiente',exact:true}).evaluate(b=>{b.click();b.click();});
  await page.getByRole('button',{name:'Tarea creada',exact:true}).waitFor();
  const tasks=await page.evaluate(async()=>await api('/api/tasks'));
  assert.equal(tasks.tasks.length,1);assert.equal(tasks.tasks[0].state,'awaiting_approval');assert.equal(tasks.tasks[0].approved_fingerprint,null);
  await send('Y también leche');await finished();
  assert.deepEqual((await ctrl('/requests')).messages,[1,3]);
  await page.screenshot({path:path.join(evidence,'desktop-cloud-conversation.png')});
  step('conversation, Cloud-only history, proposal -> pending task');
  // 4. Cancel: stops waiting, may still be billed.
  await ctrl('/script',{action:'hold',release:true});
  await send('Esperá un momento');
  await page.waitForFunction(()=>document.documentElement.dataset.chat==='waiting');
  assert.match(await page.locator('#cloud-cancel-note').textContent(),/puede cobrarse igual/);
  await page.getByRole('button',{name:'Cancelar respuesta',exact:true}).click();
  await page.getByText(/Cancelado: dejaste de esperar\. Si el pedido ya había llegado al proveedor, puede cobrarse igual/).waitFor();
  assert.equal(await html.getAttribute('data-cloud-outcome'),'cancelled');
  await ctrl('/release');
  let ledger;for(let i=0;i<50;i++){ledger=(await ctrl('/ledger')).calls;if(ledger.some(c=>c.state==='cancelled'&&c.charged>0))break;await new Promise(r=>setTimeout(r,100));}
  assert.ok(ledger.some(c=>c.state==='cancelled'&&c.charged>0),'cancelled call should record its cost');
  await page.screenshot({path:path.join(evidence,'desktop-cloud-cancelled.png')});
  step('cancel explains possible charge; cost recorded');
  // 5. Cut between gateway and provider: uncertain, never retried.
  const before=(await ctrl('/requests')).count;
  await ctrl('/script',{action:'drop'});
  await send('Este pedido se corta');await settled();
  assert.equal(await html.getAttribute('data-cloud-outcome'),'outcome_uncertain');
  await page.getByText(/Resultado incierto: el pedido pudo procesarse y cobrarse/).waitFor();
  await page.waitForTimeout(2000);
  assert.equal((await ctrl('/requests')).count,before+1,'uncertain result must not be retried');
  await page.getByRole('button',{name:'Consultar estado',exact:true}).click();
  await page.getByText(/Sigue incierto/).waitFor();
  assert.equal((await ctrl('/requests')).count,before+1);
  await page.screenshot({path:path.join(evidence,'desktop-cloud-uncertain.png')});
  step('cut after sending: uncertain, check status, no automatic retry');
  // 6. Gateway down: not sent.
  await ctrl('/gateway/stop');
  await send('Sin gateway');await settled();
  assert.equal(await html.getAttribute('data-cloud-outcome'),'provider_unavailable');
  await page.getByText(/No enviado o rechazado antes de procesarse/).waitFor();
  assert.equal(await page.locator('#chat-input').inputValue(),'Sin gateway');
  assert.equal((await ctrl('/requests')).count,before+1);
  await ctrl('/gateway/start');
  step('gateway down: not sent, text kept');
  // 7. Budget exhausted: nothing sent.
  await ctrl('/exhaust');
  await page.getByLabel('Escribile a ARKOS',{exact:true}).fill('Con el presupuesto agotado');
  await page.getByRole('button',{name:'Enviar →',exact:true}).click();await settled();
  assert.equal(await html.getAttribute('data-cloud-outcome'),'budget_exhausted');
  await page.getByText(/Presupuesto agotado: no se envió nada/).waitFor();
  assert.equal((await ctrl('/requests')).count,before+1);
  await page.screenshot({path:path.join(evidence,'desktop-cloud-budget.png')});
  await ctrl('/restore-budget');
  step('budget exhausted: not sent');
  // 8. Switching keeps sessions apart; revoking requires consent again.
  await page.getByRole('radio',{name:'Local',exact:true}).click();
  assert.match(await where(),/esta PC/);
  let shown=await page.locator('#chat-log').textContent();
  assert.ok(shown.includes('alarma')&&!shown.includes('comprar café'),'local view must hold only the local session');
  await page.getByRole('radio',{name:'Cloud',exact:true}).click();
  shown=await page.locator('#chat-log').textContent();
  assert.ok(shown.includes('comprar café')&&!shown.includes('alarma'),'Cloud view must hold only the Cloud session');
  await page.getByRole('button',{name:'Revocar consentimiento Cloud',exact:true}).click();
  await page.locator('#cloud-consent').waitFor();
  assert.equal(await page.locator('#chat-input').isDisabled(),true);
  step('mode switch keeps histories apart; revoke');
  // 9. Mobile: consent and conversation, no horizontal scroll.
  const mobileContext=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1});
  const mobile=await mobileContext.newPage();mobile.setDefaultTimeout(10000);
  mobile.on('pageerror',e=>errors.push(e.message));
  await mobile.goto(url);await mobile.getByText('Listo para conversar',{exact:true}).waitFor();
  await mobile.getByRole('radio',{name:'Cloud',exact:true}).click();
  await mobile.locator('#cloud-consent').waitFor();
  await mobile.locator('#cloud-consent').scrollIntoViewIfNeeded();
  const mobileGeometry=await mobile.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(mobileGeometry.scroll<=mobileGeometry.width,JSON.stringify(mobileGeometry));
  await mobile.screenshot({path:path.join(evidence,'mobile-cloud-consent.png')});
  await mobile.getByLabel(/Entiendo qué se envía/).check();
  await mobile.getByRole('button',{name:'Aceptar y usar Cloud',exact:true}).click();
  await mobile.getByText('Listo para conversar por Cloud',{exact:true}).waitFor();
  await mobile.getByLabel('Escribile a ARKOS',{exact:true}).fill('Desde el celular: anotá pagar la luz');
  await mobile.getByRole('button',{name:'Enviar →',exact:true}).click();
  await mobile.waitForFunction(()=>document.documentElement.dataset.chat==='ok');
  await mobile.locator('#processing-where').scrollIntoViewIfNeeded();
  await mobile.screenshot({path:path.join(evidence,'mobile-cloud-conversation.png')});
  for(const width of [360,390]){
    const c=await browser.newContext({viewport:{width,height:800}});const p=await c.newPage();await p.goto(url);
    await p.getByText('Listo para conversar',{exact:true}).waitFor();
    await p.getByRole('radio',{name:'Cloud',exact:true}).click();await p.waitForTimeout(300);
    const g=await p.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
    assert.ok(g.scroll<=g.width,'overflow at '+width);await c.close();
  }
  step('mobile consent and conversation, no horizontal overflow');
  assert.deepEqual(errors,[]);
  assert.equal(mutations.some(p=>/\/(approve|run)$/.test(p)),false);
  results.status='PASS';results.providerRequests=(await ctrl('/requests')).count;results.mobileGeometry=mobileGeometry;results.errors=errors;results.autoExecutionRequests=0;
  fs.writeFileSync(path.join(evidence,'browser-results.json'),JSON.stringify(results,null,2));
  console.log('PASS: Cloud consent, conversation, proposal pending, cancel (may bill), uncertain without retry, gateway down, budget exhausted, separate histories, mobile.');
}
main().catch(e=>{console.error(String(e.stack).replace(/#key=[\w-]+/g,'#key=[redacted]'));process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  if(server.exitCode===null){server.kill();await new Promise(r=>server.once('exit',r));}
});
