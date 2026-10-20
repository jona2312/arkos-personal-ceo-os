/* Deterministic capture lifecycle tests; physical microphone acceptance is separate. */
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const code=fs.readFileSync(path.join(__dirname,'../arkos_pilot/web/dictation.js'),'utf8');
const tick=()=>new Promise(r=>setImmediate(r));
function harness({deny=false}={}){
  const nodes={},events={},calls=[],tracks=[];
  function node(id){
    return nodes[id]??=(Object.assign(new EventTarget(),{disabled:false,hidden:false,value:'',maxLength:8000,textContent:'',focus(){}}));
  }
  let processor, resolveTranscript, active=0, requests=0;
  const html={dataset:{processing:'local'}};
  class AudioContext{
    constructor(){this.sampleRate=16000;active++;}
    async resume(){}
    async close(){active--;}
    createMediaStreamSource(){return {connect(){},disconnect(){}};}
    createScriptProcessor(){return processor={connect(){},disconnect(){}};}
  }
  const sandbox={console,Event,Float32Array,Uint8Array,ArrayBuffer,DataView,AudioContext,
    crypto:{randomUUID:()=> '01234567-1234-1234-1234-0123456789ab'},
    btoa:s=>Buffer.from(s,'binary').toString('base64'),setTimeout:()=>1,clearTimeout(){},
    MutationObserver:class{observe(){}},
    $:node,document:{documentElement:html,hidden:false,addEventListener:(n,f)=>{events[n]=f;}},
    window:{addEventListener:(n,f)=>{events[n]=f;}},
    navigator:{mediaDevices:{async getUserMedia(){
      requests++;if(deny)throw Error('permission');
      const track={stopped:false,stop(){this.stopped=true;},addEventListener(){}};tracks.push(track);
      return {getTracks:()=>[track]};
    }}},
    api:async(route,data)=>{
      calls.push({route,data});
      if(!data)return {configured:true};
      if(route.endsWith('/cancel'))return {cancelled:true};
      return new Promise(r=>{resolveTranscript=r;});
    },
  };
  vm.runInNewContext(code,sandbox);
  return {nodes,events,calls,tracks,html,
    click:async id=>{node(id).dispatchEvent(new Event('click'));await tick();},
    sample(){processor.onaudioprocess({inputBuffer:{getChannelData:()=>new Float32Array(4096)}});},
    resolve(text){resolveTranscript({text});},
    get active(){return active;},get requests(){return requests;}};
}
(async()=>{
  let h=harness();await tick();
  assert.equal(h.requests,0);assert.equal(h.nodes.dictate.disabled,false);
  await h.click('dictate');assert.match(h.nodes['dictate-status'].textContent,/MICRÓFONO ACTIVO/);
  h.sample();await h.click('dictate-stop');assert.ok(h.tracks.every(t=>t.stopped));assert.equal(h.active,0);
  assert.equal(h.calls[1].route,'/api/dictation');
  const wav=Buffer.from(h.calls[1].data.audio,'base64');
  assert.equal(wav.toString('ascii',0,4),'RIFF');assert.equal(wav.readUInt32LE(24),16000);
  h.nodes['chat-input'].value='Edición durante la transcripción';
  h.resolve('<script>texto, no HTML</script>');await tick();
  assert.equal(h.nodes['chat-input'].value,'Edición durante la transcripción\n<script>texto, no HTML</script>');
  assert.equal(h.calls.filter(c=>c.route.startsWith('/api/chat')||c.route.startsWith('/api/tasks')).length,0);
  h=harness();await tick();await h.click('dictate');h.sample();await h.click('dictate-cancel');
  assert.equal(h.calls.length,1);assert.ok(h.tracks.every(t=>t.stopped));assert.equal(h.active,0);
  h=harness();await tick();await h.click('dictate');h.sample();await h.click('dictate-stop');
  await h.click('dictate-cancel');h.resolve('Respuesta tardía');await tick();
  assert.equal(h.nodes['chat-input'].value,'');assert.equal(h.calls.at(-1).route,'/api/dictation/cancel');
  h=harness({deny:true});await tick();await h.click('dictate');
  assert.match(h.nodes['dictate-status'].textContent,/No se pudo activar/);assert.equal(h.active,0);
  h=harness();await tick();await h.click('dictate');h.events.pagehide();await tick();
  assert.ok(h.tracks.every(t=>t.stopped));assert.equal(h.active,0);
  h=harness();await tick();h.html.dataset.processing='cloud';await h.click('dictate');assert.equal(h.requests,0);
  console.log('PASS: explicit permission, PCM bounds, stop/discard/pagehide, late result, editable plain text, no auto-send, Cloud blocked.');
})().catch(e=>{console.error(e);process.exitCode=1;});
