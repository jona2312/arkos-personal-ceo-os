/* Internal read-only UI projection. Not the relay's snapshot wire contract. */
(function(root){
  'use strict';
  const labels={awaiting_approval:'Por aprobar',approved:'En cola',claimed:'Reservada por la PC',running:'Ejecutando',succeeded:'Terminada',failed:'Falló',unknown:'Resultado incierto · requiere revisión',rejected:'Rechazada',cancelled:'Cancelada'};
  const syncLabels={not_configured:'Conexión pendiente',current:'Copia sincronizada',stale:'Datos desactualizados',unavailable:'Sin información disponible',offline:'Relay sin conexión · copia local',unauthorized:'Acceso revocado · volver a vincular',never_synced:'Todavía no se sincronizó'};
  function text(value,max){if(typeof value!=='string'||value.length>max)throw new Error('Texto remoto inválido');return value;}
  function timestamp(value){if(typeof value!=='string'||!Number.isFinite(Date.parse(value)))throw new Error('Fecha remota inválida');return value;}
  function validate(value){
    if(!value||value.projection_version!==1||!Object.hasOwn(syncLabels,value.sync_status)||!['unknown','online','offline'].includes(value.device_status)||!Array.isArray(value.tasks)||value.tasks.length>500)throw new Error('Proyección remota inválida');
    const lastSync=value.last_sync===null?null:timestamp(value.last_sync);
    if(value.sync_status==='current'&&!lastSync)throw new Error('Falta fecha de sincronización');
    if(value.sync_status==='not_configured'&&value.tasks.length)throw new Error('Conexión pendiente con tareas');
    const ids=new Set();
    const tasks=value.tasks.map(task=>{
      if(!task||!Object.hasOwn(labels,task.state)||!['metadata_only','not_available'].includes(task.result_availability))throw new Error('Estado remoto inválido');
      const id=text(task.id,160);if(!id||ids.has(id))throw new Error('Identificador remoto inválido');ids.add(id);
      return {id,origin:'relay',title:text(task.title,180),state:task.state,updated_at:timestamp(task.updated_at),result_summary:text(task.result_summary,2000),result_availability:task.result_availability};
    });
    // Only allowlisted display fields survive. Credentials and payloads are never needed here.
    return {projection_version:1,sync_status:value.sync_status,device_status:value.device_status,last_sync:lastSync,truncated:value.truncated===true,tasks};
  }
  function render(container,input){
    const view=validate(input);container.replaceChildren();
    const make=(tag,cls,content)=>{const node=document.createElement(tag);node.className=cls;node.textContent=content;return node;};
    const status=make('p','remote-sync-state',syncLabels[view.sync_status]);
    if(view.last_sync)status.append(make('span','remote-sync-time','Última copia: '+new Date(view.last_sync).toLocaleString('es-AR')));
    container.append(status);
    if(view.truncated)container.append(make('p','remote-warning','Copia parcial: las tareas activas tienen prioridad.'));
    const device={unknown:'Estado de la PC remota: desconocido',online:'PC remota informada como conectada',offline:'PC remota informada como desconectada'};
    container.append(make('p','field-help',device[view.device_status]));
    if(!view.tasks.length){container.append(make('p','remote-empty',view.sync_status==='not_configured'?'Cuando conectemos el relay, tus encargos aparecerán acá.':'No hay tareas en la copia disponible.'));return;}
    const list=document.createElement('div');list.className='remote-task-grid';
    for(const task of view.tasks){
      const card=document.createElement('article');card.className='remote-task-card';card.dataset.remoteId=task.id;
      card.append(make('span','origin-pill','Del celular · relay'),make('h3','',task.title),make('span','status-pill remote-'+task.state,labels[task.state]));
      if(task.state==='unknown')card.append(make('p','remote-warning','No se reintenta automáticamente. La resolución requiere revisión en el relay.'));
      if(task.state==='claimed')card.append(make('p','field-help','Reservada no significa que el trabajo haya empezado.'));
      if(task.result_summary)card.append(make('p','remote-result',task.result_summary));
      card.append(make('small','field-help',task.result_availability==='metadata_only'?'Resultado: solo información; archivo no descargable aquí.':'Archivo no disponible en esta vista.'));
      list.append(card);
    }
    container.append(list);
  }
  const api={validate,render,labels};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.ArkosRemoteView=api;
})(typeof window!=='undefined'?window:globalThis);
