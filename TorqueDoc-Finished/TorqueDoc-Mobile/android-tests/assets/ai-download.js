(async()=>{
  const ai=window.TorqueDocWeb.ai;
  try {
    const start=performance.now();let last=-1;
    await ai.refresh();
    ai.onChange(s=>{const percent=Math.floor(s.progress*10)*10;if(s.state!=='downloading'||percent!==last){last=percent;TorqueDocTestResults.progress(JSON.stringify({state:s.state,percent,error:s.error}));}});
    if(ai.state!=='ready'&&ai.state!=='loaded')await ai.download();
    const model=await ai.cached();
    TorqueDocTestResults.complete(JSON.stringify({passed:Boolean(model)&&ai.state==='ready',phase:'model_download',state:ai.state,error:ai.error,seconds:(performance.now()-start)/1000,model:ai.model.label,validation:model?.validate()}));
  } catch(e) {TorqueDocTestResults.complete(JSON.stringify({passed:false,error:String(e.stack||e),state:ai.state,detail:ai.error}));}
})();
