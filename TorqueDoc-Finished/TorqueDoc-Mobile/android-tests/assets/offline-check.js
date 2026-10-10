(async () => {
  const checks=[];
  const require=(ok,name)=>{if(!ok)throw new Error(name);checks.push(name);};
  try {
    require(location.origin==='https://appassets.androidplatform.net','Bundled HTTPS origin');
    require(Boolean(window.TorqueDocAndroid),'Native Android bootstrap');
    const health=await (await fetch('/api/health')).json();
    require(health.backend==='ready' && health.documents===4,'4 manuals opened locally in WebAssembly');
    require(health.network_mode==='on_device','On-device search, no Python backend');
    const docs=(await (await fetch('/api/documents?machine=training')).json()).documents;
    require(docs.length===1,'Training machine has one scoped manual');
    const ask=async(question,machine='training',search_only=true)=>
      (await fetch('/api/ask',{method:'POST',body:JSON.stringify({question,machine,search_only})})).json();
    const answer=await ask('What is the cover bolt torque?');
    require(answer.status==='search_only' && answer.matches.some(p=>p.page===2 && p.page_label==='TRAIN-8' && p.text.includes('12 N m')),'Offline FTS search returns original page 2 / TRAIN-8');
    const imageURL=await window.TorqueDocWeb.pageImage(docs[0],2);
    const image=new Image();image.src=imageURL;await image.decode();
    require(image.naturalWidth>0 && image.naturalHeight>0,'Original PDF rasterized entirely on Android');
    const none=await ask('extraterrestrial fluxcapacitance');
    require(none.status==='not_found' && none.matches.length===0,'Unsupported query returns no fabricated answer');
    const other=await ask('cover bolt torque','cat');
    require(!other.matches.some(p=>p.text.includes('12 N m')),'Machine scoping excludes training specifications');
    const fallback=await ask('cover bolt torque','training',false);
    require(fallback.status==='search_only','Missing AI model falls back to labeled keyword search');
    localStorage.setItem('torquedoc-android-acceptance', 'persisted-offline');
    require(localStorage.getItem('torquedoc-android-acceptance')==='persisted-offline','Android local storage writes succeed');
    require(document.documentElement.scrollWidth<=innerWidth+1,'Phone viewport has no horizontal overflow');
    TorqueDocTestResults.complete(JSON.stringify({passed:true,checks,pdf:[image.naturalWidth,image.naturalHeight],userAgent:navigator.userAgent}));
  } catch(error) {TorqueDocTestResults.complete(JSON.stringify({passed:false,checks,error:String(error.stack||error)}));}
})();
