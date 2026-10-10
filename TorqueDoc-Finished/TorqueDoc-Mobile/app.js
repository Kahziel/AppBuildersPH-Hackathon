import { icon } from './icons.js';
import { renderWiring, renderDiagnostics } from './technical.js';
import { renderLibrary } from './library.js';
import { createMvp } from './mvp.js';

const $ = (selector, parent=document) => parent.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const machineNames = {'cat':'CAT 320D · Unit-41','deere':'John Deere 850K · Unit-08','volvo':'Volvo EC220D · Unit-16','training':'Training rig · TD-01 (fictional)'};
const nav = [{id:'assistant',name:'Technical assistant',short:'Assistant',icon:'assistant'},{id:'wiring',name:'Wiring & pinouts',short:'Wiring',icon:'circuit'},{id:'diagnostics',name:'Troubleshooting',short:'Diagnose',icon:'activity'},{id:'library',name:'Offline library',short:'Library',icon:'book'}];
const sampleDocuments = [
 {id:'sample-engine',title:'Engine service reference',type:'manual',size:'2.4 MB',revision:'DEMO · Rev. C',pages:184,status:'ready',demo:true},
 {id:'sample-wiring',title:'Electrical & wiring schematics',type:'schematic',size:'1.8 MB',revision:'DEMO · Rev. B',pages:62,status:'ready',demo:true},
 {id:'sample-operations',title:'Operation & maintenance reference',type:'manual',size:'3.1 MB',revision:'DEMO · Rev. A',pages:246,status:'ready',demo:true},
 {id:'sample-bulletin',title:'Valve lash · Bulletin TB-2022-11',type:'bulletin',size:'240 KB',revision:'DEMO · Addendum',pages:3,status:'conflict',demo:true}
];
let persistent = {};
try {persistent = JSON.parse(localStorage.getItem('torquedoc-workspace-v1') || '{}') || {};} catch { /* Start with a clean session if storage is unavailable. */ }
const state = {
 screen:nav.some(n=>n.id===location.hash.slice(1)) ? location.hash.slice(1) : 'assistant',
 machine:/^[a-z0-9][a-z0-9_-]{0,39}$/.test(persistent.machine||'') ? persistent.machine : 'cat',
 progress:persistent.progress || {}, logs:Array.isArray(persistent.logs) ? persistent.logs : [],
 saved:Boolean(persistent.saved), selectedPin:1, selectedBolt:1, diagnosticProgress:persistent.diagnosticProgress||{}, checkedSteps:(persistent.diagnosticProgress||{})[machineNames[persistent.machine]?persistent.machine:'cat']||[],
 query:'',answer:'torque',libraryQuery:'',libraryFilter:'all',imports:[],zoom:1,
 storageAvailable:true,cacheReady:false,usedBytes:0,quota:0
};
let dbPromise,toastTimer,previousFocus,objectUrls=[];
if(!machineNames[state.machine])machineNames[state.machine]=state.machine;
// Machines come from the built-in library catalog once the backend answers.
function applyMachines(list){
 if(!Array.isArray(list)||!list.length)return;
 const before=JSON.stringify(machineNames);
 Object.keys(machineNames).forEach(key=>delete machineNames[key]);
 list.forEach(m=>{machineNames[m.id]=m.name;});
 if(!machineNames[state.machine]){state.machine=list[0].id;state.checkedSteps=state.diagnosticProgress[state.machine]||[];persist();}
 return before!==JSON.stringify(machineNames);
}
let modalType=null;
const mvp=createMvp({icon,esc,getMachine:()=>state.machine,machineNames,applyMachines,getQuery:()=>state.query,setQuery:q=>{state.query=q;},render,toast,openModal,closeModal,navigate,db,readImports});
function previewNote(){return `<div class="live-note design-preview-note"><div><strong>DESIGN PREVIEW · FICTIONAL SERVICE DATA</strong><p>This screen is not connected to your uploaded manuals. Use the assistant to search your actual documentation.</p></div><button class="button button-secondary" data-action="navigate" data-screen="assistant">Search my manuals</button></div>`;}

function persist(){
 try {localStorage.setItem('torquedoc-workspace-v1',JSON.stringify({machine:state.machine,progress:state.progress,diagnosticProgress:state.diagnosticProgress,logs:state.logs,saved:state.saved}));return true;}
 catch {state.storageAvailable=false;toast('Storage unavailable. This change is kept for this session only.');return false;}
}
function db(){
 if(!dbPromise) dbPromise=new Promise((resolve,reject)=>{const request=indexedDB.open('torquedoc-local',1);request.onupgradeneeded=()=>request.result.createObjectStore('documents',{keyPath:'id'});request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
 return dbPromise;
}
async function readImports(){try {const database=await db();const records=await new Promise((resolve,reject)=>{const request=database.transaction('documents').objectStore('documents').getAll();request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});state.imports=records.filter(r=>!mvp.live.documents.some(d=>d.id===localStorage.getItem(`torquedoc-migrated-${r.id}`))).map(({blob,...metadata})=>({...metadata,status:'legacy'}));}catch{state.storageAvailable=false;}}
async function updateStorage(){try {const estimate=await navigator.storage.estimate();state.usedBytes=estimate.usage||0;state.quota=estimate.quota||0;}catch{}}
function formatBytes(bytes){if(bytes<1024*1024)return `${Math.max(1,Math.round(bytes/1024))} KB`;if(bytes<1024*1024*1024)return `${(bytes/1024/1024).toFixed(1)} MB`;return `${(bytes/1024/1024/1024).toFixed(1)} GB`;}
function machineProgress(){return state.progress[state.machine] || [];}
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('visible'),4200);}
function render(){
 const current=nav.find(n=>n.id===state.screen);
 $('#app').innerHTML=`<div class="app-shell">
 <div class="nav-scrim" data-action="close-menu"></div>
 <aside class="sidebar" aria-label="Workspace navigation">
  <a class="brand" href="#assistant" aria-label="TorqueDoc home"><img src="./icon.svg" alt=""/><div><div class="brand-name">Torque<span>Doc</span></div><div class="brand-sub">BUILT FOR THE FIELD</div></div></a>
  <div class="workspace-label eyebrow">Workspace <span>01</span></div>
  <nav class="primary-nav">${nav.map(n=>`<button class="nav-item ${state.screen===n.id?'active':''}" data-action="navigate" data-screen="${n.id}" ${state.screen===n.id?'aria-current="page"':''}>${icon(n.icon)}<span>${n.name}</span>${n.id==='library'?`<span class="nav-count">${mvp.documents().length+state.imports.length}</span>`:''}</button>`).join('')}</nav>
  <div class="sidebar-rule"></div><div class="recent-section"><div class="eyebrow">Field references</div><button class="recent-item" data-action="recent-torque">${icon('history',15)}<span>Manual Q&amp;A<small>Your indexed documents</small></span></button><button class="recent-item" data-action="go-wiring">${icon('history',15)}<span>Fuel pressure sensor<small>Electrical system · demo</small></span></button></div>
  <div class="sidebar-bottom"><div class="edge-card"><div class="edge-card-title">${icon('chip',17)}Your field knowledge. Local.</div><p>Reference files stay on this device.<br/>Ready when the network isn’t.</p><div class="storage-track"><i></i></div><div class="edge-line"><span>${mvp.storedBytes()} in manuals</span><span><i class="dot"></i> LOCAL</span></div></div><button class="sidebar-settings" data-action="settings">${icon('settings',17)}<span>Workspace settings</span><i class="dot"></i></button></div>
 </aside>
 <div class="main-shell"><header class="topbar"><button class="icon-button mobile-menu" data-action="open-menu" aria-label="Open navigation">${icon('menu')}</button><div class="breadcrumb"><span>Field workspace</span>${icon('chevron-right',12)}<strong>${current.name}</strong></div><div class="topbar-right"><span class="offline-badge"><i class="dot"></i>${mvp.status()}</span><span class="local-label">${icon('chip',13)}LOCAL WORKSPACE</span><div class="topbar-divider"></div><button class="avatar" data-action="settings" aria-label="Technician workspace settings">FT</button></div></header>
 <div class="contextbar"><div class="machine-select"><span class="machine-icon">${icon('excavator',21)}</span><label class="sr-only" for="machine-selector">Select fleet machine</label><select id="machine-selector">${Object.entries(machineNames).map(([id,name])=>`<option value="${id}" ${id===state.machine?'selected':''}>${name}</option>`).join('')}</select><span class="machine-chevron">${icon('chevron-down',13)}</span></div><div class="context-meta"><span class="context-engine">${machineNames[state.machine]}</span><span class="mono">FIELD MODE</span><span class="demo-chip">${['wiring','diagnostics'].includes(state.screen)?'DESIGN PREVIEW':'LOCAL MVP'}</span></div></div>
 <main class="main-content" id="main-content">${renderScreen()}<footer class="application-footer"><span>${icon('shield',12)}LOCAL DOCUMENTS. ON-DEVICE PROCESSING.</span><span>TORQUEDOC <span style="color:#99a2ad">/</span> FIELD EDITION 01</span></footer></main>
 </div><nav class="mobile-nav" aria-label="Mobile navigation">${nav.map(n=>`<button class="${state.screen===n.id?'active':''}" data-action="navigate" data-screen="${n.id}" ${state.screen===n.id?'aria-current="page"':''}>${icon(n.icon)}<span>${n.short}</span></button>`).join('')}</nav></div>`;
 bindScreen();
}
function renderScreen(){
 if(state.screen==='wiring')return previewNote()+renderWiring({icon,selectedPin:state.selectedPin});
 if(state.screen==='diagnostics')return previewNote()+renderDiagnostics({icon,checkedSteps:state.checkedSteps});
 if(state.screen==='library')return renderLibrary({icon,documents:[...mvp.documents(),...state.imports],logs:state.logs.filter(l=>l.machine===state.machine),query:state.libraryQuery,filter:state.libraryFilter,machineName:machineNames[state.machine]});
 return mvp.assistant();
}
function navigate(screen){if(!nav.some(n=>n.id===screen))return;state.screen=screen;state.zoom=1;if(location.hash!==`#${screen}`)history.pushState(null,'',`#${screen}`);render();window.scrollTo({top:0,behavior:'instant'});}
function bindScreen(){
 mvp.bind();
 $('#machine-selector')?.addEventListener('change',e=>{state.machine=e.target.value;state.checkedSteps=state.diagnosticProgress[state.machine]||[];mvp.reset();persist();render();toast(`Manuals scoped to ${machineNames[state.machine]}.`);});
 $('#query-form')?.addEventListener('submit',e=>{e.preventDefault();submitQuery($('#technical-query').value);});
 $('#library-search')?.addEventListener('input',e=>{const value=e.target.value,position=e.target.selectionStart;state.libraryQuery=value;render();const input=$('#library-search');input.focus();input.setSelectionRange(position,position);});
 const drop=$('#drop-zone');
 if(drop){drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('drag-over');});drop.addEventListener('dragleave',()=>drop.classList.remove('drag-over'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('drag-over');importFiles([...e.dataTransfer.files]);});}
}
function submitQuery(raw){return mvp.ask(raw);}
function openModal(title,subtitle,body,footer='',wide=false){
 previousFocus=document.activeElement;
 $('#modal-root').innerHTML=`<div class="modal-backdrop"><section class="modal ${wide?'modal-wide':''}" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-header"><div><h2 id="modal-title">${esc(title)}</h2>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div><button class="icon-button" data-action="close-modal" aria-label="Close dialog">${icon('close',18)}</button></div><div class="modal-body">${body}</div>${footer?`<div class="modal-footer">${footer}</div>`:''}</section></div>`;
 document.body.style.overflow='hidden';
 setTimeout(()=>{const input=$('input,textarea,select',$('#modal-root'));(input||$('.modal-header button'))?.focus();},0);
}
function closeModal(){ $('#modal-root').innerHTML='';document.body.style.overflow='';objectUrls.forEach(url=>URL.revokeObjectURL(url));objectUrls=[];modalType=null;if(previousFocus?.isConnected)previousFocus.focus();}
function openSource(docId='sample-engine'){
 const doc=sampleDocuments.find(d=>d.id===docId)||sampleDocuments[0];
 let source;
 if(doc.id==='sample-wiring'||state.screen==='wiring'||state.screen==='diagnostics')source=`<div class="eyebrow">Sample electrical reference / B41</div><h2>Fuel delivery pressure sensor</h2><p>This is a locally bundled demonstration reference. It is not a manufacturer-approved wiring document.</p><table class="source-table"><thead><tr><th>Pin</th><th>Circuit</th><th>Illustrative test</th></tr></thead><tbody><tr><td>1</td><td>703-OR-18 · +5V</td><td>5.0 ± 0.2 VDC</td></tr><tr><td>2</td><td>412-BU-18 · Signal</td><td>0.5–4.5 VDC</td></tr><tr><td>3</td><td>200-BK-14 · Ground</td><td>≤ 5.0 Ω</td></tr></tbody></table><p>Use the exact engine serial-number-specific schematic before probing any connector. The demo does not establish actual connector orientation or safe test conditions.</p>`;
 else if(doc.id==='sample-bulletin')source=`<div class="eyebrow">Sample revision notice / TB-2022-11</div><h2>Conflicting valve lash references</h2><p>The sample document index demonstrates an addendum overriding an earlier manual revision. <mark>No valve lash specification is provided here.</mark></p><p>When a local engine is connected, conflict resolution should retain both source passages, publication dates, and serial-number applicability. Confirm the latest approved OEM bulletin before maintenance.</p>`;
 else if(doc.id==='sample-operations')source=`<div class="eyebrow">Sample operations reference / field procedure</div><h2>Before starting service</h2><p>This sample reference demonstrates page-level offline reading. It is not a substitute for the operation and maintenance manual for your equipment.</p><p>Confirm the machine, engine variant, service procedure, and safety instructions in your imported OEM manual. Imported PDFs remain available in the local document library.</p>`;
 else source=`<div class="eyebrow">TorqueDoc sample service reference / § 3.2</div><h2>Cylinder head installation</h2><p>The following values are illustrative design data. <strong>Do not use this sample as a service instruction.</strong></p><p>Tighten the cylinder head bolts in the numbered sequence to <mark>40 N·m, then 80 N·m, then 120 N·m.</mark> Turn each bolt an additional <mark>90°</mark> in the same sequence.</p><table class="source-table"><thead><tr><th>Pass</th><th>Metric</th><th>Imperial</th></tr></thead><tbody><tr><td>01 · Snug</td><td>40 N·m</td><td>29.5 lb·ft</td></tr><tr><td>02 · Equalize</td><td>80 N·m</td><td>59.0 lb·ft</td></tr><tr><td>03 · Pre-load</td><td>120 N·m</td><td>88.5 lb·ft</td></tr><tr><td>04 · Angle</td><td>+90°</td><td>¼ turn</td></tr></tbody></table><p>Actual values depend on engine variant, bolt condition, thread preparation, and the applicable OEM service procedure.</p>`;
 const page=doc.id==='sample-engine'?42:doc.id==='sample-wiring'?18:1;
 openModal('Offline reference reader','Bundled demo document · available without a connection',`<div class="modal-note">${icon('info',18)}This is an illustrative reference, not an OEM manual. Import your own PDF to open the original document offline.</div><article class="document-page">${source}<div class="document-footer"><span>DEMO-01 · ${esc(doc.revision)}</span><span>PAGE ${page} / ${doc.pages}</span></div></article>`,`<button class="button button-secondary" data-action="import-documents">${icon('upload',16)}Add an update</button><button class="button button-primary" data-action="close-modal">Done</button>`,true);
}
function openLog(kind='note'){
 modalType=kind;
 const title=kind==='torque'?'Cylinder head torque check':kind==='fault'?'SPN 94 · FMI 3 verification':kind==='reading'?`B41 sensor · Pin ${state.selectedPin} reading`:'';
 const note=kind==='torque'?`Demo torque progression: ${machineProgress().length}/4 passes checked. `:kind==='fault'?`Sample diagnostic checklist: ${state.checkedSteps.length}/4 steps checked. `:kind==='reading'?`Sample circuit B41 · Pin ${state.selectedPin}\nMeasured value: \nTest conditions: \nTechnician notes: `:'';
 openModal('Add maintenance log',`${machineNames[state.machine]} · stored on this device`,`${kind!=='note'?`<div class="modal-note">${icon('info',18)}This check uses sample service data. The log records your progress in the prototype.</div>`:''}<form id="log-form"><label class="form-field">Log title<input name="title" id="log-title" value="${esc(title)}" placeholder="e.g. Replaced fuel pressure sensor" required maxlength="120"/></label><label class="form-field">Technician notes<textarea name="note" id="log-note" placeholder="Record measurements, parts, and work performed…" maxlength="4000">${esc(note)}</textarea><small>Saved locally. Export logs when back at the shop.</small></label></form>`,`<button class="button button-secondary" data-action="close-modal">Cancel</button><button class="button button-primary" type="submit" form="log-form">${icon('check',16)}Save log locally</button>`);
 $('#log-form').addEventListener('submit',e=>{e.preventDefault();saveLog();});
}
function saveLog(){
 const title=$('#log-title').value.trim();if(!title){$('#log-title').focus();return;}
 state.logs.unshift({id:crypto.randomUUID(),title,note:$('#log-note').value.trim(),machine:state.machine,time:new Date().toISOString(),kind:modalType||'note',syncStatus:'pending-export'});
 const saved=persist();closeModal();render();toast(saved?'Maintenance log saved on this device. Ready to export.':'Log retained for this session. Local storage is unavailable.');
}
function showHistory(){
 const logs=state.logs.filter(l=>l.machine===state.machine);
 openModal('Service history',`${machineNames[state.machine]} · ${logs.length} local record${logs.length===1?'':'s'}`,logs.length?logs.map(log=>`<div class="history-entry">${icon('wrench',18)}<div><h3>${esc(log.title)}</h3><p>${esc(log.note)}</p><small>${new Date(log.time).toLocaleString('en-PH',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Manila'})} · On-device · Pending export</small></div></div>`).join(''):`<div class="empty-answer" style="padding:20px 0;margin:0">${icon('history',32)}<h2>A clean service record.</h2><p>Torque checks, diagnostic measurements, and repair notes for this machine will appear here.</p></div>`,`<button class="button button-secondary" data-action="export-logs">${icon('download',16)}Export logs</button><button class="button button-primary" data-action="add-log">${icon('plus',16)}Add a log</button>`);
}
async function showSettings(){await mvp.refresh(false);mvp.settings();}
async function importFiles(files){return mvp.importFiles(files);}
async function openDocument(id){
 if(mvp.live.documents.some(d=>d.id===id)){mvp.source(id);return;}
 if(id.startsWith('sample-')){openSource(id);return;}
 try{
  const database=await db();const item=await new Promise((resolve,reject)=>{const request=database.transaction('documents').objectStore('documents').get(id);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
  if(!item){toast('This file is no longer in local storage. Import it again.');return;}
  const url=URL.createObjectURL(item.blob);objectUrls.push(url);
  const content=String(item.mime||'').startsWith('image/')?`<img src="${url}" alt="${esc(item.title)}" style="width:100%;height:auto;display:block;border-radius:4px"/>`:`<iframe class="pdf-frame" title="${esc(item.title)}" src="${url}#page=1"></iframe>`;
  openModal(item.title,'Original file · read directly from on-device storage',content,`<a class="button button-secondary" href="${url}" download="${esc(item.title)}">${icon('download',16)}Save a copy</a><button class="button button-ghost button-danger" data-action="delete-legacy" data-id="${esc(id)}">Remove browser copy</button>${String(item.title||'').toLowerCase().endsWith('.pdf')?`<button class="button button-primary" data-action="index-legacy" data-id="${esc(id)}">Index this PDF</button>`:''}<button class="button button-secondary" data-action="close-modal">Done</button>`,true);
 }catch{toast('Unable to open the local document.');}
}
function confirmDeleteLegacy(id){
 const item=state.imports.find(i=>i.id===id);
 openModal('Remove browser copy?',item?.title||'Earlier browser import',`<div class="live-note">${icon('alert',18)}<span>This deletes the copy saved in this browser by the earlier prototype. Manuals already indexed by the backend are not affected. Keep your own copy of the PDF if you may need it again.</span></div>`,`<button class="button button-secondary" data-action="close-modal">Keep it</button><button class="button button-primary button-danger" data-action="confirm-delete-legacy" data-id="${esc(id)}">Remove permanently</button>`);
}
async function deleteLegacy(id){
 try{
  const database=await db();
  await new Promise((resolve,reject)=>{const tx=database.transaction('documents','readwrite');tx.objectStore('documents').delete(id);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});
  try{localStorage.removeItem(`torquedoc-migrated-${id}`);}catch{}
  await readImports();closeModal();render();toast('Browser copy removed.');
 }catch{toast('Unable to remove the browser copy.');}
}
let lastRefresh=Date.now();
function refreshWhenVisible(){
 // Pick up a backend or Ollama that was started after this page opened.
 if(document.visibilityState!=='visible'||mvp.live.asking||mvp.live.importing||Date.now()-lastRefresh<5000)return;
 lastRefresh=Date.now();
 const before=`${mvp.live.backend}|${mvp.live.health?.engine?.state}|${mvp.live.documents.length}`;
 mvp.refresh(false).then(readImports).then(()=>{if(`${mvp.live.backend}|${mvp.live.health?.engine?.state}|${mvp.live.documents.length}`!==before&&!$('#modal-root').firstChild&&!document.activeElement?.matches('input,textarea,select'))render();});
}
function importLogs(){
 const input=document.createElement('input');input.type='file';input.accept='application/json,.json';
 input.addEventListener('change',async()=>{
  const file=input.files[0];if(!file)return;
  try{
   const data=JSON.parse(await file.text());
   const incoming=(Array.isArray(data)?data:data.logs)||[];
   const valid=incoming.filter(l=>l&&typeof l.title==='string'&&l.title.trim()&&typeof l.machine==='string').map(l=>({id:String(l.id||crypto.randomUUID()),title:l.title.slice(0,120),note:String(l.note||'').slice(0,4000),machine:l.machine.slice(0,40),time:String(l.time||new Date().toISOString()),kind:String(l.kind||'note').slice(0,20),syncStatus:'pending-export'}));
   const known=new Set(state.logs.map(l=>l.id)),added=valid.filter(l=>!known.has(l.id));
   if(!valid.length){toast('No maintenance logs found in that file. Choose a TorqueDoc log export.');return;}
   state.logs=[...state.logs,...added].sort((a,b)=>String(b.time).localeCompare(String(a.time)));
   const saved=persist();closeModal();render();
   toast(added.length?`Imported ${added.length} maintenance log${added.length===1?'':'s'}${valid.length>added.length?` (${valid.length-added.length} already present)`:''}.${saved?'':' Storage is unavailable; kept for this session.'}`:'All logs in that file are already here.');
  }catch{toast('That file could not be read. Choose a TorqueDoc log export (.json).');}
 });
 input.click();
}
async function exportLogs(){
 if(!state.logs.length){toast('No maintenance logs to export yet.');return;}
 const fileName=`torquedoc-maintenance-${new Date().toISOString().slice(0,10)}.json`;
 if(window.TorqueDocWeb){try{if(await window.TorqueDocWeb.saveFile(fileName,JSON.stringify({application:'TorqueDoc',version:1,exportedAt:new Date().toISOString(),edition:"phone",machines:machineNames,logs:state.logs},null,2))){toast(`Exported ${state.logs.length} maintenance log${state.logs.length===1?'':'s'}.`);return;}}catch(error){if(!/cancel/i.test(String(error?.message||error))){toast('Could not export the logs on this phone.');}return;}}
 const blob=new Blob([JSON.stringify({application:'TorqueDoc',version:1,exportedAt:new Date().toISOString(),edition:"core-mvp",machines:machineNames,logs:state.logs},null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`torquedoc-maintenance-${new Date().toISOString().slice(0,10)}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(`Exported ${state.logs.length} maintenance log${state.logs.length===1?'':'s'}.`);
}
document.addEventListener('click',async e=>{
 const target=e.target.closest('[data-action]');if(!target)return;
 const action=target.dataset.action;
 if(await mvp.action(action,target))return;
 if(action==='navigate')navigate(target.dataset.screen);
 else if(action==='open-menu'){$('.sidebar').classList.add('open');$('.nav-scrim').classList.add('visible');}
 else if(action==='close-menu'){$('.sidebar').classList.remove('open');$('.nav-scrim').classList.remove('visible');}
 else if(action==='suggest')submitQuery(target.dataset.query);
 else if(action==='recent-torque')navigate('assistant');
 else if(action==='go-wiring')navigate('wiring');
 else if(action==='toggle-torque'){const n=Number(target.dataset.step),steps=machineProgress();state.progress[state.machine]=steps.includes(n)?steps.filter(i=>i!==n):[...steps,n];persist();render();$(`[data-action="toggle-torque"][data-step="${n}"]`)?.focus({preventScroll:true});}
 else if(action==='select-bolt'){state.selectedBolt=Number(target.dataset.bolt);render();$(`[data-bolt="${state.selectedBolt}"]`)?.focus({preventScroll:true});}
 else if(action==='next-bolt'){state.selectedBolt=state.selectedBolt%10+1;render();$('[data-action="next-bolt"]')?.focus({preventScroll:true});}
 else if(action==='open-source')openSource(state.screen==='assistant'?'sample-engine':'sample-wiring');
 else if(action==='open-document')openDocument(target.dataset.id);
 else if(action==='close-modal')closeModal();
 else if(action==='history')showHistory();
 else if(action==='add-log'){closeModal();openLog();}
 else if(action==='log-torque')openLog('torque');
 else if(action==='log-fault')openLog('fault');
 else if(action==='record-reading')openLog('reading');
 else if(action==='settings')showSettings();
 else if(action==='save-reference'){state.saved=!state.saved;persist();render();toast(state.saved?'Reference bookmarked on this device.':'Bookmark removed.');}
 else if(action==='copy-answer'){
  const text=mvp.copyText();if(!text){toast('No source-backed passages to copy.');return;}
  try{await navigator.clipboard.writeText(text);toast('Original passages and citations copied.');}catch{toast('Clipboard unavailable. Select and copy the visible passages.');}
 }
 else if(action==='voice')openModal('Offline voice input','Voice controls are represented in this prototype.',`<div class="modal-note">${icon('mic',19)}No offline speech model is connected. Your microphone is not activated, and audio is not sent to a cloud service.</div><p class="muted" style="font-size:13px">Use the question field or a quick ask to explore the local sample references.</p>`,`<button class="button button-primary" data-action="close-modal">Use keyboard</button>`);
 else if(action==='select-pin'){state.selectedPin=Number(target.dataset.pin);render();}
 else if(action==='check-step'){const n=Number(target.dataset.step);state.checkedSteps=state.checkedSteps.includes(n)?state.checkedSteps.filter(s=>s!==n):[...state.checkedSteps,n];state.diagnosticProgress[state.machine]=state.checkedSteps;persist();render();$(`[data-action="check-step"][data-step="${n}"]`)?.focus({preventScroll:true});}
 else if(action==='zoom-in'||action==='zoom-out'){state.zoom=Math.min(1.8,Math.max(.8,state.zoom+(action==='zoom-in'?.2:-.2)));const group=$('#wiring-circuit-content');if(group){group.style.transformOrigin='50% 50%';group.style.transform=`scale(${state.zoom})`;}const zoom=$('[data-zoom-label]');if(zoom)zoom.textContent=`${Math.round(state.zoom*100)}%`;}
 else if(action==='library-filter'){state.libraryFilter=target.dataset.filter;render();}
 else if(action==='import-documents')$('#file-input').click();
 else if(action==='scan-document')toast('OCR is not included in this MVP. Import a PDF with searchable text; scanned pages can still be viewed.');
 else if(action==='export-logs')exportLogs();
 else if(action==='import-logs')importLogs();
 else if(action==='delete-legacy')confirmDeleteLegacy(target.dataset.id);
 else if(action==='confirm-delete-legacy'){target.disabled=true;deleteLegacy(target.dataset.id);}
 else if(action==='protect-storage'){try{const allowed=await navigator.storage.persist();toast(allowed?'Persistent storage enabled for this browser.':'The browser did not grant persistent storage. Export important records as a backup.');}catch{toast('Persistent storage requests are unavailable. Export logs to keep a backup.');}}
});
document.addEventListener('keydown',e=>{
 if(e.key==='Escape'){if($('#modal-root').firstChild)closeModal();else{$('.sidebar')?.classList.remove('open');$('.nav-scrim')?.classList.remove('visible');}}
 if((e.key==='Enter'||e.key===' ')&&e.target.matches('g[role="button"]')){e.preventDefault();e.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}
 if(e.key==='Tab'&&$('#modal-root').firstChild){const focusable=[...$('#modal-root').querySelectorAll('button:not(:disabled),a[href],input,textarea,select,[tabindex="0"]')];const first=focusable[0],last=focusable[focusable.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
});
$('#file-input').addEventListener('change',e=>importFiles([...e.target.files]));
document.addEventListener('visibilitychange',refreshWhenVisible);
window.addEventListener('focus',refreshWhenVisible);
setInterval(()=>{if(mvp.live.backend!=='ready')refreshWhenVisible();},15000);
window.addEventListener('hashchange',()=>{const id=location.hash.slice(1);if(nav.some(n=>n.id===id)){state.screen=id;render();}});
window.addEventListener('popstate',()=>{const id=location.hash.slice(1)||'assistant';if(nav.some(n=>n.id===id)){state.screen=id;render();}});
render();
mvp.refresh().then(readImports).then(()=>{if(!$('#modal-root').firstChild)render();});
if('serviceWorker' in navigator&&!window.TorqueDocWeb){navigator.serviceWorker.register('./sw.js').then(async registration=>{await navigator.serviceWorker.ready;state.cacheReady=true;}).catch(()=>{state.cacheReady=false;});}
