(async()=>{
  const ai=window.TorqueDocWeb.ai,measurements=[];
  const mark=(phase,data={})=>TorqueDocTestResults.progress(JSON.stringify({phase,...data}));
  try {
    await ai.refresh();
    if(ai.state!=='ready')throw new Error('Downloaded model was not available after Android process restart: '+ai.state+' '+ai.error);
    mark('model_found',{model:ai.model.label,isolated:crossOriginIsolated,cores:navigator.hardwareConcurrency});
    let start=performance.now();await ai.load();
    measurements.push({phase:'cold_load',seconds:(performance.now()-start)/1000});mark('model_loaded',measurements[0]);
    for(const question of ['What is the cover bolt torque?','What is the coolant capacity?']) {
      start=performance.now();mark('inference_started',{question});
      const result=await (await fetch('/api/ask',{method:'POST',body:JSON.stringify({question,machine:'training',search_only:false})})).json();
      const record={question,status:result.status,evidence:result.evidence?.map(p=>({id:p.id,page:p.page,label:p.page_label,text:p.text})),message:result.message,seconds:(performance.now()-start)/1000,run:ai.lastRun};
      measurements.push(record);mark('inference_complete',{question,status:result.status,seconds:record.seconds,run:ai.lastRun});
      if(question.includes('bolt') && !(result.status==='supported'&&result.evidence.some(p=>p.page===2&&p.text.includes('12 N m'))))throw new Error('Actual AI did not choose the supported torque source');
      if(question.includes('coolant') && result.status!=='not_found')throw new Error('Actual AI selected an unsupported coolant capacity answer');
    }
    TorqueDocTestResults.complete(JSON.stringify({passed:true,phase:'offline_real_inference',measurements,state:ai.state,userAgent:navigator.userAgent}));
  } catch(e) {TorqueDocTestResults.complete(JSON.stringify({passed:false,error:String(e.stack||e),state:ai.state,detail:ai.error,measurements,run:ai.lastRun}));}
})();
