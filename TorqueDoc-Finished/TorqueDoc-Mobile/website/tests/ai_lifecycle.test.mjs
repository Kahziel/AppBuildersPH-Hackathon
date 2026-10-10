import test from 'node:test';
import assert from 'node:assert/strict';
import { OnDeviceAI, MODELS } from '../src/ai.js';
import { validateChoice } from '../src/engine.js';
const passages = [{id:'7',title:'Training',variant:'TD-01',revision:'A',text:'Cover bolts: fictional 12 N m only.',page:2}];
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
function fixture(overrides = {}) {
  const model = {url:MODELS.fast.url,validate:()=> 'valid',remove:async()=>{}};
  const runtime = {modelManager:{getModels:async()=>[model]},loadModel:async()=>{},exit:async()=>{},
    createChatCompletion:async()=>({choices:[{message:{content:'{"status":"supported","passage_ids":["7"]}'}}]}),...overrides};
  const ai = new OnDeviceAI('unused.wasm',{create:()=>runtime});
  return {ai,runtime,model};
}
test('an answer contains original retrieved text and keeps its source metadata', async()=>{
  const {ai}=fixture(); const [result]=await ai.select('cover torque',{},passages);
  assert.deepEqual(result,passages);assert.equal(result[0],passages[0]);assert.equal(ai.busy,false);
});
test('invented IDs and contradictory refusal cannot become a supported answer', async()=>{
  assert.throws(()=>validateChoice({status:'supported',passage_ids:['999']},passages));
  assert.throws(()=>validateChoice({status:'not_found',passage_ids:['7']},passages));
  const {ai}=fixture({createChatCompletion:async()=>({choices:[{message:{content:'12 N m from memory'}}]})});
  assert.equal((await ai.select('torque',{},passages))[0],null);
});
test('cancelling inference releases the engine for the next question', async()=>{
  let started;const began=new Promise(r=>started=r);
  const {ai,runtime}=fixture({createChatCompletion:({abortSignal})=>new Promise((resolve,reject)=>{
    started();abortSignal.addEventListener('abort',()=>reject(new Error('runtime cancelled')),{once:true});
  })});
  const controller=new AbortController();
  const pending=ai.select('torque',{},passages,{signal:controller.signal});
  await began; controller.abort(); await assert.rejects(pending,{name:'AbortError'});
  assert.equal(ai.busy,false);
  runtime.createChatCompletion=async()=>({choices:[{message:{content:'{"status":"supported","passage_ids":["7"]}'}}]});
  assert.equal((await ai.select('torque',{},passages))[0][0],passages[0]);
});
test('cancel during model loading prevents inference from starting', async()=>{
  let finishLoad;let calls=0;
  const {ai}=fixture({loadModel:()=>new Promise(r=>finishLoad=r),createChatCompletion:async()=>{calls++;}});
  const controller=new AbortController();const pending=ai.select('torque',{},passages,{signal:controller.signal});
  while(!finishLoad) await tick();controller.abort();finishLoad();
  await assert.rejects(pending,{name:'AbortError'});assert.equal(calls,0);assert.equal(ai.busy,false);
});
test('busy engine prevents a mid-question model or GPU change', async()=>{
  const {ai}=fixture();ai.busy=true;const previous=ai.choice;const gpu=ai.useGpu;
  await ai.choose('better');await ai.setGpu(!gpu);
  assert.equal(ai.choice,previous);assert.equal(ai.useGpu,gpu);
});
test('a failed model load disposes its worker before retry', async()=>{
  let exits=0;const {ai}=fixture({loadModel:async()=>{throw new Error('out of memory');},exit:async()=>{exits++;}});
  const [answer,message]=await ai.select('torque',{},passages);
  assert.equal(answer,null);assert.match(message,/out of memory/);assert.equal(exits,1);assert.equal(ai.wllama,null);
});
test('a missing cached model can recover on the next request', async()=>{
  const {ai,runtime,model}=fixture();let present=false;
  runtime.modelManager.getModels=async()=>present?[model]:[];
  assert.equal((await ai.select('torque',{},passages))[0],null);
  present=true;await ai.refresh();assert.equal((await ai.select('torque',{},passages))[0][0],passages[0]);
});
test('cancelled download never claims the model is ready', async()=>{
  let started;const began=new Promise(r=>started=r);const {ai,runtime}=fixture();
  runtime.modelManager.downloadModel=(url,{signal})=>new Promise((resolve,reject)=>{
    started();signal.addEventListener('abort',()=>reject(new Error('cancelled')),{once:true});
  });
  const pending=ai.download();await began;ai.cancelDownload();await pending;
  assert.equal(ai.state,'missing');assert.match(ai.error,/cancelled/);assert.equal(ai.downloadController,null);
});
test('numeric questions refuse explicit absence and wrong-component numbers', async()=>{
  const {ai,runtime}=fixture();let calls=0;
  runtime.createChatCompletion=async()=>{calls++;throw new Error('should not run');};
  const negatives=[
    ['coolant capacity','Connector: 12 V. No coolant capacity is supplied.'],
    ['fuel pump torque','Cover bolts: 12 N m.'],
    ['cover bolt torque','Try this question: What is the cover bolt torque? Revision 2026.'],
  ];
  for(const [question,text] of negatives) assert.deepEqual((await ai.select(question,{},[{...passages[0],text}]))[0],[]);
  assert.equal(calls,0);
});
test('an unrelated missing specification does not erase a valid cover specification', async()=>{
  const {ai}=fixture();const text='Cover bolts: 12 N m. No cylinder head torque specification is supplied.';
  assert.equal((await ai.select('cover bolt torque',{},[{...passages[0],text}]))[0][0].text,text);
});
test('a matching hyphenated machine code remains eligible', async()=>{
  const {ai}=fixture();const text='Training rig TD-01. Cover bolts: 12 N m.';
  assert.equal((await ai.select('TD-01 cover bolt torque',{},[{...passages[0],text}]))[0][0].text,text);
});
