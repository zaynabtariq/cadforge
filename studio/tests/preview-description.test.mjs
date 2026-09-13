import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {describePreview} from '../src/preview-description.js';
const result={explanation:'The whole object moves exactly 1 mm.',command:{op:'translate',axis:'x',amount_mm:1},preview:{accepted:true,selection:{region:{}},repair_trials:[{strategy:'sharp',accepted:false},{strategy:'interior_transition_power_1',accepted:true}]}};
test('checked taper overrides misleading intent even when learning save fails',()=>{
 const r=structuredClone(result);r.preview.learning={status:'audit_failed'};
 assert.match(describePreview(r),/up to 1 mm.*tapering/);
 assert.doesNotMatch(describePreview(r),/whole object/);
});
test('rejected geometry never reports proposed success',()=>{
 const r=structuredClone(result);r.preview.accepted=false;
 assert.match(describePreview(r),/did not pass/);
});
test('sharp translation preserves direction and selection scope',()=>{
 const r=structuredClone(result);r.command.amount_mm=-2;r.preview.repair_trials=[{strategy:'sharp',accepted:true}];
 assert.match(describePreview(r),/Selected vertices move 2 mm.*negative X/);
});
test('actual recorded discovery and learned reuse have the same geometry semantics',()=>{
 const data=JSON.parse(fs.readFileSync(new URL('./fixtures/recorded-region-outcomes.json',import.meta.url)));
 for(const row of data)assert.match(describePreview(row),/tapering toward its boundary/);
});
test('region resizing states checked selected extent',()=>{
 const r=structuredClone(result);r.preview.command={op:'resize',axis:'y',target_mm:20};
 assert.match(describePreview(r),/selected vertices span 20 mm along Y/);
});
test('missing trial provenance does not invent rigid or tapered semantics',()=>{
 const r=structuredClone(result);r.preview.repair_trials=[];
 assert.equal(describePreview(r),'The section edit passed its checks. Review the geometry and operation details before applying.');
});
