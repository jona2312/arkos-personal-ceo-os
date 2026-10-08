/* Task activity must not imply execution merely because work is queued. */
const assert=require('node:assert/strict');
const {activity}=require('../arkos_pilot/web/neural.js');
assert.equal(activity([{state:'running'}],false),'offline');
assert.equal(activity([],true),'idle');
assert.equal(activity([{state:'completed'}],true),'idle');
assert.equal(activity([{state:'awaiting_approval'}],true),'review');
assert.equal(activity([{state:'blocked'}],true),'review');
assert.equal(activity([{state:'queued'}],true),'queued');
assert.equal(activity([{state:'queued'},{state:'running'}],true),'running');
console.log('PASS: offline suppresses activity, queued is not running, old completed tasks do not signal new completion.');
