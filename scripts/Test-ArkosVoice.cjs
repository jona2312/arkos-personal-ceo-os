/* Synthetic browser state machine acceptance. Does not certify microphone/speaker hardware. */
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const code=fs.readFileSync(require('node:path').join(__dirname,'../arkos_pilot/web/voice.js'),'utf8');
const tick=()=>new Promise(r=>setImmediate(r));
class CustomEvent extends Event {constructor(n,o={}){super(n);this.detail=o.detail;}}
function harness({deny=false,delayedPermission=false}={}) {
  const win=new EventTarget(),doc=new EventTarget(),nodes={},calls=[],tracks=[];
  doc.documentElement={dataset:{processing:'local',chat:'ok'}};doc.hidden=false;
  let clock=0, processor, player, turns=0, resolvePermission, nextText='Hola, esto es una prueba';
  const $=id=>nodes[id]??=Object.assign(new EventTarget(),{value:'',disabled:false,hidden:false,textContent:'',
    click(){this.dispatchEvent(new Event('click'));},focus(){}});
  $('chat-form').requestSubmit=()=>{
    turns++;const requestId='ui-'+turns;doc.documentElement.dataset.chat='waiting';$('chat-input').value='';
    win.dispatchEvent(new CustomEvent('arkos-chat-state',{detail:{state:'waiting',mode:'local',requestId}}));
    $('chat-form').dispatchEvent(new Event('submit'));
    setImmediate(()=>{doc.documentElement.dataset.chat='ok';win.dispatchEvent(new CustomEvent('arkos-chat-result',
      {detail:{requestId,mode:'local',state:'ok',reply:'Una respuesta local completa.'}}));});
  };
  class AudioContext {
    constructor(){this.sampleRate=16000;this.closed=false;}
    async resume(){} async close(){this.closed=true;}
    createMediaStreamSource(){return {connect(){},disconnect(){}};}
    createScriptProcessor(){return processor={connect(){},disconnect(){}};}
    async decodeAudioData(){return {};}
    createBufferSource(){return player={connect(){},start(){},stop(){this.stopped=true;this.onended?.();}};}
  }
  const permission=()=>{const t={stopped:false,stop(){this.stopped=true;},addEventListener(){}};tracks.push(t);return {getTracks:()=>[t]};};
  const sandbox={console,Event,CustomEvent,Float32Array,Uint8Array,ArrayBuffer,DataView,AudioContext,
    crypto:require('node:crypto').webcrypto,performance:{now:()=>clock},setTimeout,clearTimeout,
    btoa:s=>Buffer.from(s,'binary').toString('base64'),atob:s=>Buffer.from(s,'base64').toString('binary'),
    MutationObserver:class{observe(){}},$: $,window:win,document:doc,
    navigator:{mediaDevices:{async getUserMedia(){if(deny)throw Error('denied');
      if(delayedPermission)return new Promise(r=>{resolvePermission=()=>r(permission());});return permission();}}},
    api:async(route,data)=>{calls.push({route,data});
      if(!data)return {configured:true};
      if(route.endsWith('transcribe'))return {text:nextText,worker_ms:3};
      if(route.endsWith('speak'))return {audio:'AAAA',worker_ms:3};
      return {ready:true};},
  };
  vm.runInNewContext(code,sandbox);
  return {nodes,calls,tracks,win,doc,
    async click(id){$(id).click();for(let i=0;i<8;i++)await tick();},
    async samples(value,count){for(let i=0;i<count;i++){clock+=64;processor?.onaudioprocess?.({inputBuffer:{getChannelData:()=>new Float32Array(1024).fill(value)}});}for(let i=0;i<8;i++)await tick();},
    async finishAudio(){player.onended();for(let i=0;i<8;i++)await tick();},
    async permission(){resolvePermission();await tick();await tick();},
    set transcript(t){nextText=t;},get turns(){return turns;},get player(){return player;}};
}
(async()=>{
  const h=harness();await tick();assert.equal(h.tracks.length,0);
  await h.click('voice-start');await h.samples(0,15);
  assert.match(h.nodes['voice-status'].textContent,/Escuchando/);
  assert.equal(h.calls.filter(c=>c.route.endsWith('transcribe')).length,0,'silence never creates a turn');
  for(let i=0;i<5;i++){
    await h.samples(.05,8);await h.samples(0,13);
    assert.equal(h.turns,i+1);assert.match(h.nodes['voice-status'].textContent,/Hablando/);
    await h.finishAudio();assert.match(h.nodes['voice-status'].textContent,/Escuchando/);
  }
  await h.samples(.05,8);await h.samples(0,13);const playing=h.player;
  h.transcript='Pará y resumilo';await h.samples(.07,8);assert.equal(playing.stopped,true);
  await h.samples(0,13);assert.equal(h.turns,7,'barge-in routes through same chat');
  const speaking=h.player;h.transcript='Una respuesta local completa';
  await h.samples(.07,8);await h.samples(0,13);
  assert.equal(h.turns,7,'echo transcript not submitted');assert.equal(speaking.stopped,true);
  await h.click('voice-stop');assert.ok(h.tracks.every(t=>t.stopped));assert.equal(h.nodes['voice-stop'].hidden,true);
  assert.ok(h.calls.every(c=>!c.route.includes('/tasks')),'no approvals/execution');
  assert.equal(JSON.parse(h.nodes['voice-metrics'].textContent).length,7);
  const denied=harness({deny:true});await tick();await denied.click('voice-start');assert.match(denied.nodes['voice-status'].textContent,/no se pudo/);
  const late=harness({delayedPermission:true});await tick();await late.click('voice-start');await late.click('voice-stop');await late.permission();assert.ok(late.tracks.every(t=>t.stopped));
  const hidden=harness();await tick();await hidden.click('voice-start');hidden.doc.hidden=true;hidden.doc.dispatchEvent(new Event('visibilitychange'));await tick();assert.ok(hidden.tracks.every(t=>t.stopped));
  console.log('PASS synthetic: five turns, interruption, echo rejection, silence, stop, denied/late permission, hidden page, no task calls.');
})().catch(e=>{console.error(e);process.exitCode=1;});
