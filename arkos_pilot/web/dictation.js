/* Local PCM capture only. Never Web Speech, storage, auto-send or task execution. */
(() => {
  'use strict';
  const start = $('dictate'), stop = $('dictate-stop'), cancel = $('dictate-cancel');
  const label = $('dictate-status'), input = $('chat-input');
  let configured = false, job = null;
  function show(text) {
    label.textContent = text;
    start.disabled = !configured || !!job || input.disabled || document.documentElement.dataset.processing === 'cloud';
    stop.hidden = !job || job.phase !== 'recording';
    cancel.hidden = !job;
  }
  function release(j) {
    clearTimeout(j.timer);
    if (j.stream) j.stream.getTracks().forEach(t => t.stop());
    if (j.processor) { j.processor.onaudioprocess = null; j.processor.disconnect(); }
    if (j.source) j.source.disconnect();
    if (j.context) j.context.close().catch(() => {});
  }
  function wav(chunks, length) {
    const buffer = new ArrayBuffer(44 + length * 2), view = new DataView(buffer);
    function str(offset, value) { [...value].forEach((c,i) => view.setUint8(offset+i,c.charCodeAt(0))); }
    str(0,'RIFF'); view.setUint32(4,36+length*2,true); str(8,'WAVE'); str(12,'fmt ');
    view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
    view.setUint32(24,16000,true); view.setUint32(28,32000,true);
    view.setUint16(32,2,true); view.setUint16(34,16,true); str(36,'data'); view.setUint32(40,length*2,true);
    let offset=44;
    for (const chunk of chunks) for (const sample of chunk) {
      const n=Math.max(-1,Math.min(1,sample)); view.setInt16(offset,n<0?n*32768:n*32767,true); offset+=2;
    }
    let binary=''; const bytes=new Uint8Array(buffer);
    for(let i=0;i<bytes.length;i+=8192) binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    return btoa(binary);
  }
  async function finish() {
    const j=job;
    if (!j || j.phase !== 'recording') return;
    j.phase='transcribing'; release(j);
    show('Micrófono apagado · transcribiendo en esta PC…');
    try {
      const audio=wav(j.chunks,j.length); j.chunks=[];
      const result=await api('/api/dictation',{request_id:j.id,audio});
      if(job!==j) return;
      // Preserve edits made while recognition was running; do not send anything.
      const combined = input.value + (input.value && result.text ? '\n' : '') + result.text;
      if(combined.length > input.maxLength) throw new Error('El texto supera el espacio del campo. Acortalo y volvé a dictar.');
      input.value = combined;
      input.dispatchEvent(new Event('input',{bubbles:true}));
      job=null; show(result.text ? 'Texto listo para revisar y editar. Enviarlo requiere tu acción.' : 'No se reconoció texto. Podés intentar otra vez.');
      input.focus();
    } catch(e) { if(job===j){job=null;show(e.message);} }
  }
  async function discard() {
    const j=job; if(!j)return;
    job=null; release(j); j.chunks=[];
    show('Micrófono apagado · dictado descartado.');
    if(j.phase==='transcribing') {
      try { await api('/api/dictation/cancel',{request_id:j.id}); }
      catch { show('Micrófono apagado. No se confirmó la cancelación del proceso; finaliza con un límite de 90 segundos.'); }
    }
  }
  start.addEventListener('click',async()=>{
    if(job || !configured || input.disabled || document.documentElement.dataset.processing === 'cloud') return;
    const j={id:'dict-'+crypto.randomUUID(),phase:'permission',chunks:[],length:0}; job=j;
    show('Solicitando permiso de micrófono…');
    try {
      j.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true},video:false});
      if(job!==j){release(j);return;}
      j.context=new AudioContext({sampleRate:16000});
      if(j.context.sampleRate!==16000)throw new Error('Este navegador no ofrece captura a 16 kHz.');
      await j.context.resume();
      if(job!==j){release(j);return;}
      j.source=j.context.createMediaStreamSource(j.stream);
      j.processor=j.context.createScriptProcessor(4096,1,1);
      j.processor.onaudioprocess=event=>{
        if(job!==j||j.phase!=='recording')return;
        const samples=event.inputBuffer.getChannelData(0);
        const chunk=samples.slice(0,Math.min(samples.length,480000-j.length));
        j.chunks.push(chunk);j.length+=chunk.length;
        if(j.length>=480000)finish();
      };
      j.source.connect(j.processor);j.processor.connect(j.context.destination);
      j.phase='recording';show('● MICRÓFONO ACTIVO · solo esta PC · máximo 30 segundos');
      j.timer=setTimeout(finish,30000);
      j.stream.getTracks().forEach(t=>t.addEventListener('ended',()=>{if(job===j&&j.phase==='recording')discard();}));
    } catch { release(j);if(job===j){job=null;show('No se pudo activar el micrófono. Revisá permiso y dispositivo; podés escribir.');} }
  });
  stop.addEventListener('click',finish);
  cancel.addEventListener('click',discard);
  window.addEventListener('pagehide',discard);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)discard();});
  // Sending or switching modes discards outstanding audio; no late transcript in another conversation.
  $('chat-form').addEventListener('submit',discard);
  for(const id of ['chat-new','mode-local','mode-cloud']) $(id).addEventListener('click',discard);
  new MutationObserver(()=>show(label.textContent)).observe(input,{attributes:true,attributeFilter:['disabled']});
  new MutationObserver(()=>show(label.textContent)).observe(document.documentElement,{attributes:true,attributeFilter:['data-processing']});
  api('/api/dictation').then(info=>{
    configured=info.configured && !!navigator.mediaDevices?.getUserMedia;
    show(configured?'Dictado local · audio en memoria, sin guardar.':'Dictado local por configurar. Podés escribir.');
  }).catch(()=>show('Dictado local no disponible. Podés escribir.'));
})();
