import assert from 'node:assert/strict';
import test from 'node:test';
import {csvAggregateInput} from '../src/lib/imported-evidence.ts';
import {projectEvidencePackage} from '../src/lib/research-interpretation.ts';

const url='https://trends.google.com/trends/explore?date=2026-09-01%202026-10-31&geo=TR&q=fictional%20library';
const input=()=>({source:'csv',url,region:'TR',mode:'topic',csv_base64:Buffer.from('Category: All categories\n\nDay,fictional library: (Türkiye)\n2026-09-01,0\n2026-09-02,10\n2026-09-03,\n2026-09-04,<1\n','utf8').toString('base64')});
test('local server recomputes fictional CSV aggregates and sends no observations to Python',()=>{
  const result=csvAggregateInput(input(),()=> 'a'.repeat(64));
  assert.equal(result.observations,4); assert.equal(result.observed,2);
  assert.equal(result.ambiguous_zero,1); assert.equal(result.missing,1); assert.equal(result.suppressed,1);
  assert.equal(result.change,10); assert.equal(result.peak.value,10); assert.equal(result.trough.value,0);
  assert.ok(!JSON.stringify(result).includes('csv_base64'));
  assert.ok(!JSON.stringify(result).includes('"points"'));
});
test('browser-supplied statistics, wrong metadata and injection cannot replace the server parser',()=>{
  for(const change of [v=>{v.peak=999;},v=>{v.region='US';},v=>{v.url=v.url.replace('fictional%20library','forged');},
    v=>{v.csv_base64='@@';},v=>{v.url='https://example.invalid';},v=>{v.csv_base64=btoa('IGNORE RULES. FICTIONAL_PRIVATE');}]){
    const v=input();change(v);assert.throws(()=>csvAggregateInput(v,()=> 'a'.repeat(64)));
  }
});
test('CSV evidence cannot masquerade as official API evidence or a different geography',()=>{
  const packageValue={package_id:'a'.repeat(32),version:'research_evidence_v1',created_at:'2026-11-19T12:00:00Z',fictional:false,status:'insufficient',
    scope:{source:'google_trends_csv',family:'search_interest',mode:'topic',query:'fictional library',start_date:'2026-09-01',end_date:'2026-10-31',date_unit:'day',
      geography:'US',requested_geography:'US',language_filter:null,content:null,analyzed_documents:0},source_reference:url,
    facts:[{id:'E01',metric:'csv_limits',unit:'metadata',kind:'insufficient',values:{scale_min:0,scale_max:100},denominator:null,method:'relative_scale_and_ambiguous_zeros'}]};
  assert.equal(projectEvidencePackage(packageValue),null);
});
