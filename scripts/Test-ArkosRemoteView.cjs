/* Internal display projection tests; no relay/network credentials involved. */
const assert=require('node:assert/strict');
const {validate,labels}=require('../arkos_pilot/web/remote-view.js');
const sample={projection_version:1,sync_status:'current',device_status:'unknown',last_sync:'2026-10-08T01:00:00Z',tasks:[{id:'tsk_example',title:'Nota del celular',state:'unknown',updated_at:'2026-10-08T00:55:00Z',result_summary:'Resultado por revisar',result_availability:'metadata_only'}]};
for(const state of Object.keys(labels)){const result=validate({...sample,tasks:[{...sample.tasks[0],state}]});assert.equal(result.tasks[0].state,state);assert.equal(result.tasks[0].origin,'relay');}
assert.throws(()=>validate({...sample,tasks:[{...sample.tasks[0],state:'blocked'}]}));
assert.throws(()=>validate({...sample,tasks:[sample.tasks[0],sample.tasks[0]]}));
assert.throws(()=>validate({...sample,last_sync:null}));
assert.throws(()=>validate({...sample,last_sync:'not-a-date'}));
assert.throws(()=>validate({...sample,sync_status:'not_configured'}));
assert.throws(()=>validate({...sample,tasks:[{...sample.tasks[0],result_availability:'downloadable'}]}));
const projected=validate({...sample,token:'SECRET',tasks:[{...sample.tasks[0],device_token:'SECRET',absolute_path:'D:\\Private',payload:{text:'hidden'}}]});
assert.equal(JSON.stringify(projected).includes('SECRET'),false);
assert.equal(JSON.stringify(projected).includes('Private'),false);
assert.equal(Object.hasOwn(projected.tasks[0],'payload'),false);
assert.equal(validate({...sample,sync_status:'stale'}).sync_status,'stale');
console.log('PASS: nine distinct remote states, projection field allowlist, invalid dates/duplicates/states, credentials stripped, metadata-only results.');
