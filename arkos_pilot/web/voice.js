/* Explicit local voice session. Uses the existing chat form/history, never task APIs.
   Hardware AEC is requested, not assumed. Transcript echo rejection is a second guard.
   RMS endpointing is intentionally labelled experimental until physical acceptance. */
(() => {
  'use strict';
  const start=$('voice-start'), stop=$('voice-stop'), label=$('voice-status');
  const input=$('chat-input');
  let configured=false, session=null;
  const rows=[];
  const now=()=>performance.now();
  const id=()=> 'voice-'+crypto.randomUUID();
  function state(s, phase, text) {
    if(session!==s)return;
    s.phase=phase;
    document.documentElement.dataset.voice=phase;
    label.textContent=text+(s.stream && phase==='processing'?' · micrófono activo':'');
  }
  function refreshButton() {
    start.disabled=!configured || !!session || input.disabled || document.documentElement.dataset.processing==='cloud';
    stop.hidden=!session;
  }
  function pcm(chunks) {
    const length=chunks.reduce((n,c)=>n+c.length,0), buffer=new ArrayBuffer(44+length*2), v=new DataView(buffer);
    const str=(o,t)=>[...t].forEach((c,i)=>v.setUint8(o+i,c.charCodeAt(0)));
    str(0,'RIFF');v.setUint32(4,36+length*2,true);str(8,'WAVE');str(12,'fmt ');v.setUint32(16,16,true);
    v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,16000,true);v.setUint32(28,32000,true);
    v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,length*2,true);
    let p=44;
    for(const c of chunks)for(const sample of c){const x=Math.max(-1,Math.min(1,sample));v.setInt16(p,x<0?x*32768:x*32767,true);p+=2;}
    let binary='';const b=new Uint8Array(buffer);
    for(let i=0;i<b.length;i+=8192)binary+=String.fromCharCode(...b.subarray(i,i+8192));
    return btoa(binary);
  }
  function echo(text, spoken) {
    const norm=t=>t.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9 ]/g,' ').replace(/\s+/g,' ').trim();
    const a=norm(text),b=norm(spoken),words=a.split(' ');
    if(a.length<10 || words.length<3)return false; // keep short intentional interruptions
    if(b.includes(a))return true;
    const other=new Set(b.split(' '));
    return words.filter(w=>other.has(w)).length/words.length>=0.8;
  }
  function call(s,op,extra={}) {
    // One bounded voice worker. Serialize prefetch and recognition, without blocking task polling.
    const promise=s.chain.catch(()=>{}).then(()=>{
      if(session!==s)throw Error('Sesión detenida.');
      return api('/api/voice/'+op,{session_id:s.id,request_id:id(),...extra});
    });
    s.chain=promise;
    return promise;
  }
  function cut(s) {
    s.epoch++;
    if(s.player){try{s.player.stop();}catch{}s.player=null;}
    if(s.playDone){s.playDone();s.playDone=null;}
  }
  function release(s) {
    cut(s);clearTimeout(s.idle);
    s.stream?.getTracks().forEach(t=>t.stop());
    if(s.processor){s.processor.onaudioprocess=null;s.processor.disconnect();}
    s.source?.disconnect();
    s.context?.close().catch(()=>{});
    s.chunks=[];s.pre=[];
  }
  async function end(message='Pausado · micrófono apagado.') {
    const s=session;if(!s)return;
    session=null;release(s);
    // Cancel only the turn this session submitted; never tasks or someone else's conversation.
    if(s.rid && document.documentElement.dataset.chat==='waiting')$('chat-cancel').click();
    document.documentElement.dataset.voice='paused';label.textContent=message;refreshButton();
    try {await api('/api/voice/cancel',{session_id:s.id,request_id:id()});}
    catch {label.textContent=message+' No se confirmó el cierre del worker; tiene timeout y liberación por inactividad.';}
  }
  function listen(s) {
    s.chunks=[];s.pre=[];s.started=0;s.above=0;
    state(s,'listening','● Escuchando · micrófono activo · solo esta PC');
  }
  function saveMetric(s) {
    if(!s.metric)return;
    rows.push({...s.metric});if(rows.length>50)rows.shift();
    $('voice-metrics').textContent=JSON.stringify(rows,null,2);s.metric=null;
  }
  async function utterance(s) {
    const epoch=s.epoch;
    const audio=pcm(s.chunks), ended=s.lastVoice;
    s.chunks=[];s.started=0;s.pre=[];
    state(s,'processing','Procesando tu voz en esta PC…');
    try {
      const result=await call(s,'transcribe',{audio});
      if(session!==s || s.epoch!==epoch)return;
      const transcriptAt=now();
      if(!result.text.trim() || (transcriptAt-s.spokeAt<15000 && echo(result.text,s.spoken))){
        listen(s);return;
      }
      // Cancellation settles through the existing chat, never a parallel bridge.
      const deadline=now()+5000;
      while(input.disabled && now()<deadline && session===s)await new Promise(r=>setTimeout(r,100));
      if(session!==s)return;
      if(input.disabled || input.value.trim()) {
        if(!input.value.trim())input.value=result.text;
        await end('Pausado · revisá el texto en el chat antes de continuar.');return;
      }
      s.metric={turn:rows.length+1,voice_end_to_transcript_ms:Math.round(transcriptAt-ended),
        stt_worker_ms:result.worker_ms,first_model_fragment_ms:null,audible_audio_ms:null};
      s.transcriptAt=transcriptAt;
      input.value=result.text;
      s.submitting=true;$('chat-form').requestSubmit();s.submitting=false;
      if(!s.rid){await end('Pausado · el chat no pudo aceptar el turno.');return;}
      state(s,'processing','Procesando · esperando al modelo local. Ninguna tarea se ejecuta.');
    } catch(e) {if(session===s)await end('Pausado · '+e.message);}
  }
  async function speak(s,text) {
    const epoch=s.epoch, textAt=now();
    if(s.metric)s.metric.transcript_to_complete_text_ms=Math.round(textAt-s.transcriptAt);
    // The bridge provides a validated complete reply. Split for TTS only, not fake model streaming.
    const phrases=(text.match(/[^.!?\n]+[.!?\n]*/g)||[text]).flatMap(p=>p.match(/[\s\S]{1,600}(?:\s|$)|[\s\S]{1,600}/g)||[]).filter(p=>p.trim());
    if(phrases.length>40){await end('Pausado · respuesta demasiado larga para voz; leela en el chat.');return;}
    s.spoken=text;s.spokeAt=now();
    state(s,'processing','Preparando respuesta hablada local…');
    try {
      let ready=call(s,'speak',{text:phrases[0]});
      for(let i=0;i<phrases.length;i++) {
        const result=await ready;
        if(session!==s||s.epoch!==epoch)return;
        const bytes=Uint8Array.from(atob(result.audio),c=>c.charCodeAt(0));
        const buffer=await s.context.decodeAudioData(bytes.buffer);
        if(session!==s||s.epoch!==epoch)return;
        const player=s.context.createBufferSource();player.buffer=buffer;player.connect(s.context.destination);s.player=player;
        state(s,'speaking','Hablando · podés interrumpir · micrófono activo');
        s.spokeAt=now();
        if(i===0 && s.metric){s.metric.complete_text_to_playback_start_ms=Math.round(now()-textAt);saveMetric(s);}
        // Synthesize the next whole phrase while this one plays. No parallel worker or network.
        if(i+1<phrases.length) {ready=call(s,'speak',{text:phrases[i+1]});ready.catch(()=>{});}
        await new Promise(resolve=>{s.playDone=resolve;player.onended=resolve;player.start();});
        s.playDone=null;if(s.player===player)s.player=null;
        if(session!==s||s.epoch!==epoch)return;
      }
      listen(s);
    } catch(e){if(session===s && s.epoch===epoch)await end('Pausado · '+e.message);}
  }
  function samples(s,chunk) {
    if(session!==s || !['listening','speaking','processing'].includes(s.phase))return;
    // Don't create competing transcription while an utterance is being decoded/synthesized.
    if(s.phase==='processing' && !s.rid)return;
    const t=now(), rms=Math.sqrt(chunk.reduce((n,v)=>n+v*v,0)/chunk.length);
    // Calibrate only quiet samples. Treating the user's first words as the noise
    // floor can make all subsequent speech unreachable (especially at startup).
    if(!s.started && !s.player && rms<0.012)s.floor=s.floor*0.95+rms*0.05;
    const threshold=Math.min(0.08,Math.max(s.player?0.035:0.012,s.floor*3.5));
    const loud=rms>threshold;
    if(!s.started){
      s.pre.push(chunk);if(s.pre.length>6)s.pre.shift();
      s.above=loud?s.above+chunk.length/16:0;
      if(s.above<192)return;
      s.started=t;s.lastVoice=t;s.chunks=s.pre.slice();s.pre=[];
      if(s.phase!=='listening'){
        cut(s);
        if(s.rid && document.documentElement.dataset.chat==='waiting')$('chat-cancel').click();
        s.rid=null;
        state(s,'listening','● Te escucho · respuesta interrumpida');
      }
    } else s.chunks.push(chunk);
    if(loud)s.lastVoice=t;
    if(t-s.lastVoice>=750 || s.chunks.reduce((n,c)=>n+c.length,0)>=470000)utterance(s);
  }
  start.addEventListener('click',async()=>{
    if(session || start.disabled)return;
    if(input.value.trim()){label.textContent='Primero enviá o borrá el texto editable del chat.';return;}
    const s={id:id(),chain:Promise.resolve(),phase:'starting',epoch:0,floor:0.002,created:now(),
      pre:[],chunks:[],started:0,above:0,spoken:'',spokeAt:0,rid:null};session=s;
    refreshButton();state(s,'processing','Preparando Whisper y Piper locales…');
    window.dispatchEvent(new Event('arkos-voice-start'));
    try {
      // Start permission within user activation; stop also handles a late permission grant.
      s.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:false},video:false});
      if(session!==s){release(s);return;}
      state(s,'processing','Preparando Whisper y Piper locales…');
      s.context=new AudioContext({sampleRate:16000});await s.context.resume();
      if(s.context.sampleRate!==16000)throw Error('Captura de 16 kHz no disponible.');
      if(session!==s){release(s);return;}
      await call(s,'warm');if(session!==s)return;
      s.source=s.context.createMediaStreamSource(s.stream);s.processor=s.context.createScriptProcessor(1024,1,1);
      s.processor.onaudioprocess=e=>samples(s,e.inputBuffer.getChannelData(0).slice());
      s.source.connect(s.processor);s.processor.connect(s.context.destination);
      s.stream.getTracks().forEach(t=>t.addEventListener('ended',()=>{if(session===s)end('Pausado · micrófono desconectado.');}));
      s.created=now();listen(s);
    } catch(e){if(session===s)await end('Pausado · no se pudo iniciar: '+e.message);}
  });
  stop.addEventListener('click',()=>end());
  window.addEventListener('arkos-chat-state',e=>{
    const s=session;if(!s)return;
    if(s.submitting && e.detail.state==='waiting')s.rid=e.detail.requestId;
    if(e.detail.mode!=='local' || ['error','offline'].includes(e.detail.state))end('Pausado · revisá el estado del chat.');
  });
  window.addEventListener('arkos-chat-result',e=>{
    const s=session;if(!s || e.detail.requestId!==s.rid)return;
    s.rid=null;
    if(e.detail.state==='ok' && e.detail.reply.trim())speak(s,e.detail.reply);
    else end('Pausado · turno cancelado o sin respuesta.');
  });
  $('chat-form').addEventListener('submit',()=>{if(session&&!session.submitting)end();});
  for(const button of ['chat-new','mode-cloud','mode-local'])$(button).addEventListener('click',()=>end());
  window.addEventListener('arkos-dictation-start',()=>end());
  window.addEventListener('pagehide',()=>end());
  document.addEventListener('visibilitychange',()=>{if(document.hidden)end();});
  new MutationObserver(refreshButton).observe(input,{attributes:true,attributeFilter:['disabled']});
  new MutationObserver(()=>{refreshButton();if(document.documentElement.dataset.processing==='cloud')end();}).observe(document.documentElement,{attributes:true,attributeFilter:['data-processing']});
  api('/api/voice').then(info=>{configured=info.configured&&!!navigator.mediaDevices?.getUserMedia;refreshButton();
    label.textContent=configured?'Voz local experimental · Whisper + Piper · audio sin guardar.':'Voz local por configurar. Dictado editable disponible por separado.';
  }).catch(()=>{label.textContent='Voz local no disponible.';});
})();
