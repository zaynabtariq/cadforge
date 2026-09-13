const $ = id => document.getElementById(id);
let state=null, stream=null, draft=null, sending=false, connected=false, step=1;
let catalog={}, pendingAction=null, sendTimer=null, viewer=null, previewInfo=null, selectedAt=0;
const labels={SLA:'SLA · resin printing',FDM:'FDM · plastic printing',MJF:'MJF · nylon printing',SLS:'SLS · nylon printing',SLM:'SLM · metal printing',WJP:'WJP · resin printing',BJ:'BJ · metal printing'};
const money=n=>n===null||n===undefined?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(n));
async function api(path,options={}){const res=await fetch(path,options);const data=await res.json();if(!res.ok){const e=new Error(data.error||'Request failed');e.state=data.state;throw e;}return data;}
function persist(){if(state&&draft)localStorage.setItem('part-quote-flow',JSON.stringify({id:state.id,draft,step,pendingAction}));}
function readDraft(){if(!draft)return;for(const k of ['quantity','description','category'])draft[k]=k==='quantity'?Number($(k).value):$(k).value;draft.description=draft.description.trim();persist();}
function valid(){return draft&&Number.isInteger(draft.quantity)&&draft.quantity>=1&&draft.quantity<=100000;}
function matches(config,baseline=false){return config&&['technology','material','color','quantity',...(baseline?[]:['category','description'])].every(k=>(config[k]??null)===(draft[k]??null));}
function fillOptions(id,values,selected,defaultLabel){
  const el=$(id),sig=JSON.stringify([values,selected]);if(el.dataset.signature===sig)return;el.replaceChildren();
  if(defaultLabel){const o=document.createElement('option');o.value='';o.textContent=defaultLabel;el.append(o);}
  if(selected&&!values.some(v=>v.value===selected))values=[{value:selected,label:selected+' · checking'},...values];
  for(const v of values){const o=document.createElement('option');o.value=v.value;o.textContent=v.label;o.disabled=!!v.disabled;el.append(o);}el.value=selected??'';el.dataset.signature=sig;
}
function apply(next){
  if(state&&(next.id!==state.id||next.seq<state.seq))return;state=next;
  if(!draft){draft={...next.desired};for(const k of ['quantity','description','category'])$(k).value=draft[k];}
  if(next.options_revision===next.revision&&next.observed?.technology===draft.technology&&!pendingAction){
    if(!draft.material)draft.material=next.observed.material;
    if(!draft.color&&next.observed.material===draft.material)draft.color=next.observed.color;
  }
  render();persist();if(pendingAction&&!sending)drain();
}

function agentText(){
  if(state?.closed)return 'This session is closed. Start a new quote whenever you’re ready.';
  if(state?.error)return 'This choice needs a second look. You can adjust it below and I’ll check again.';
  if(!state?.bootstrapped)return step===1?'I’m uploading your model while you check the preview. Your choices will be saved as you go.':step===2?'Go ahead and choose a material. I’ll check it against your model as soon as the upload finishes.':'Your choices are saved. I’ll price them as soon as the model is ready.';
  if(state.busy)return state.message;
  if(step===1)return 'The model is ready. Check the dimensions and tell me what we’re making.';
  if(step===2)return 'Choose a material and color. I’ll check availability while you explore the options.';
  return state.quote&&!state.quote.baseline&&matches(state.quote.config)?'Your estimate is ready. You can go back and compare another material.':'Review your choices, and I’ll put the estimate together.';
}
function render(){
  if(!draft)return;
  $('workspace').hidden=false;$('upload-panel').hidden=true;$('reset').hidden=false;
  document.querySelectorAll('[data-panel]').forEach(e=>e.hidden=Number(e.dataset.panel)!==step);
  document.querySelectorAll('[data-step]').forEach(e=>{if(Number(e.dataset.step)===step)e.setAttribute('aria-current','step');else e.removeAttribute('aria-current');});
  $('agent-message').textContent=agentText();$('pulse').className='pulse'+(!state?.bootstrapped||state?.busy||pendingAction?' busy':'')+(state?.error?' error':'');
  $('connection').textContent=state?.closed?'Session closed':connected?'Live updates connected':state?'Reconnecting…':'Starting your quote…';
  const sameTech=state?.observed?.technology===draft.technology;
  const live=sameTech?state.options:null;const cached=catalog[draft.technology];
  const fields=live||cached?.options||{};
  const opts=field=>(field?.options||[]).map(v=>({value:v.label,label:v.label,disabled:v.disabled}));
  fillOptions('technology',Object.entries(labels).map(([value,label])=>({value,label})),draft.technology);
  fillOptions('material',opts(fields.Material),draft.material,'Use the process default');
  const sameMaterial=sameTech&&state?.observed?.material===draft.material;
  const colorField=sameMaterial?state.options?.Color:cached?.colors?.[draft.material];
  fillOptions('color',opts(colorField),draft.color,'Use the material default');
  for(const id of ['technology','material','color'])$(id).disabled=!!state?.closed;
  const checked=state&&state.options_revision===state.revision&&sameMaterial&&state.observed.quantity===draft.quantity&&!pendingAction&&!sending&&!state.warnings.length;
  $('options-note').textContent=checked?'Checked against your model.':fields.Material?'Previously seen options · your agent is checking this model.':'Choose a process now; its material options will appear after the model check.';
  $('options-note').parentElement.classList.toggle('verified',!!checked);
  const finish=fields['Surface Finish']?.values?.filter(Boolean).join(', ');
  $('defaults').textContent=live?`Provider defaults: ${finish||'standard finish'} · ${fields.Thread?.selected?.[0]==='No'?'no threads':'threads as selected'} · ${fields['Package Box']?.selected?.join(', ')||'standard packaging'}`:'Standard finish and packaging. The agent will confirm these with JLC3DP.';
  const q=state?.quote;const current=q&&q.revision===state.revision&&matches(q.config,q.baseline)&&!pendingAction&&!sending;
  $('quote-badge').textContent=!q?'Checking your choices':q.baseline?'Initial estimate · default settings':!current?'Previous estimate · settings changed':q.shipping_status==='pending'?'Manufacturing ready · shipping pending':'Estimate up to date';
  $('quote-badge').className='badge'+(!current||q?.baseline||q?.shipping_status==='pending'?' pending':'');
  $('quote-config').textContent=q?`${q.config.quantity} × ${q.config.material}${q.config.color?' · '+q.config.color:''}`:'Your estimate will appear here as soon as it is checked.';
  $('manufacturing').textContent=money(q?.manufacturing);$('shipping').textContent=q?.shipping_status==='pending'?'Checking…':money(q?.shipping);$('total').textContent=money(q?.estimated_total);
  $('build-time').textContent=q?.build_time?`Manufacturing · ${q.build_time}`:'Build time will arrive with your estimate.';
  $('shipping-details').textContent=q?.shipping_status==='estimated'?(q.shipping_details||'').split('\n').filter(x=>!x.startsWith('$')&&!x.startsWith('Weight')&&!x.includes(' kg')).join(' · '):'';
  $('mini-label').textContent=!q?'Your agent is preparing the first estimate':q.baseline?'Initial estimate · default material':current?'Manufacturing estimate':'Previous manufacturing estimate';
  $('mini-price').textContent=q?money(q.manufacturing):'Working in the background';
  $('review-summary').textContent=`${draft.quantity} × ${draft.description||'your part'} · ${draft.material||labels[draft.technology]+' default'} · ${draft.color||'default color'}`;
  $('quote-button').disabled=!valid()||!draft.description||!!state?.closed;
  $('quote-button').textContent=sending||pendingAction?'Saving choices…':state?.busy?'Update my choices':'Refresh estimate';
  $('next-review').disabled=!!state?.closed;
  const warnings=[...(state?.warnings||[]),state?.error].filter(Boolean);
  if(previewInfo?.dimensions_mm&&q?.dimensions_mm){const a=[...previewInfo.dimensions_mm].sort((x,y)=>x-y),b=[...q.dimensions_mm].sort((x,y)=>x-y);if(a.some((v,i)=>Math.abs(v-b[i])>Math.max(.1,b[i]*.01)))warnings.push('The preview size differs from JLC3DP’s dimensions. Check the file units before relying on this quote.');}
  $('warning-panel').hidden=!warnings.length;$('warning-message').textContent=warnings.join('\n');
  if(!previewInfo&&q?.dimensions_mm)$('dimensions').textContent=q.dimensions_mm.map(n=>Number(n.toFixed(2))).join(' × ')+' mm · JLC3DP';
  $('activity').replaceChildren();for(const item of (state?.history||[]).slice(-6).reverse()){const li=document.createElement('li');li.textContent=item.message;$('activity').append(li);}
  $('debug').textContent=JSON.stringify({session:state?.id,event:state?.seq,revision:state?.revision,optionsRevision:state?.options_revision,quoteRevision:q?.revision,quoteMatchesDraft:!!current,step,phase:state?.phase,bootstrapped:state?.bootstrapped,pendingAction,preview:previewInfo,desired:state?.desired,draft,observed:state?.observed},null,2);
  window.quoteUI={state,draft:{...draft},current:!!current,connected,step,preview:previewInfo,pendingAction};
}
function connect(id){
  stream?.close();stream=new EventSource(`/api/sessions/${id}/events`);
  stream.addEventListener('open',()=>{connected=true;render();});
  stream.addEventListener('state',e=>{apply(JSON.parse(e.data));if(state.closed){stream.close();connected=false;render();}});
  stream.addEventListener('error',()=>{connected=false;render();});
}
async function preview(file){
  $('filename').textContent=file.name;$('file-info').textContent=file.name.split('.').pop().toUpperCase()+' · '+(file.size<1024*1024?Math.max(1,Math.round(file.size/1024))+' KB':(file.size/1024/1024).toFixed(1)+' MB');
  try{
    const module=await import('/viewer.js');viewer?.dispose();
    viewer=await module.mountViewer($('viewer'),file,info=>{
      previewInfo={...info,ready_ms:Math.round(performance.now()-selectedAt)};
      $('preview-badge').textContent='Interactive preview';$('dimensions').textContent=info.dimensions_mm.map(n=>Number(n.toFixed(2))).join(' × ')+' mm';
      $('unit-note').textContent=info.unitNote+'. Geometry preview; material and color are selected separately.';
      $('reset-view').disabled=false;$('wireframe').disabled=false;render();
    });
  }catch(e){$('preview-badge').textContent='Preview unavailable';$('preview-error').textContent=e.message;$('preview-error').hidden=false;$('viewer').replaceChildren();const p=document.createElement('p');p.className='viewer-placeholder';p.textContent='You can keep building your quote while JLC3DP checks this file.';$('viewer').append(p);render();}
}
async function start(file,demo=false){
  if(file.size>20*1024*1024){$('global-error').textContent='Choose a file smaller than 20 MB.';return;}
  selectedAt=performance.now();state=null;step=1;previewInfo=null;
  draft={technology:'SLA',material:'9600 Resin',color:null,quantity:1,category:'blocks',description:demo?'20 mm resin test cube':''};
  for(const k of ['quantity','category','description'])$(k).value=draft[k];
  $('global-error').textContent='';$('demo').disabled=true;$('file').disabled=true;render();preview(file);
  try{const initial=await api(demo?'/api/sessions/demo':`/api/sessions?filename=${encodeURIComponent(file.name)}`,{method:'POST',body:demo?'':file});apply(initial);localStorage.setItem('part-quote-session',initial.id);persist();connect(initial.id);if(pendingAction)drain();}
  catch(e){$('global-error').textContent=e.message;}
  finally{$('demo').disabled=false;$('file').disabled=false;}
}
function schedule(action='inspect',delay=250){pendingAction=action;clearTimeout(sendTimer);sendTimer=setTimeout(drain,delay);persist();render();}
async function drain(){
  if(sending||!state||!pendingAction||state.closed)return;
  readDraft();if(!valid())return;
  const action=pendingAction;if(action==='quote'&&!draft.description){setStep(1);return;}
  pendingAction=null;sending=true;const config={...draft};render();$('global-error').textContent='';
  try{const result=await api(`/api/sessions/${state.id}/commands`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command_id:crypto.randomUUID(),expected_revision:state.revision,action,config})});apply(result.state);}
  catch(e){if(e.state)apply(e.state);$('global-error').textContent=e.message;}
  finally{sending=false;persist();render();if(pendingAction)drain();}
}
function setStep(next){
  readDraft();
  if(next>1&&(!valid()||!draft.description)){step=1;render();if(!$('description').reportValidity())return;if(!$('quantity').reportValidity())return;return;}
  step=next;persist();render();if(innerWidth<800)document.querySelector('.guide-card').scrollIntoView({behavior:'smooth',block:'start'});
  if(next===2&&(!state?.observed||!matches(state.observed)||state.error))schedule('inspect',0);
  if(next===3&&(pendingAction||!state?.quote||state.quote.baseline||state.quote.revision!==state.revision||!matches(state.quote.config)))schedule('quote',0);
}
$('demo').addEventListener('click',async()=>{try{const r=await fetch('/fixtures/cube-20mm.stl');if(!r.ok)throw new Error('Could not load the test cube');await start(new File([await r.blob()],'cube-20mm.stl'),'demo');}catch(e){$('global-error').textContent=e.message;}});
$('file').addEventListener('change',e=>{if(e.target.files[0])start(e.target.files[0]);});
$('technology').addEventListener('change',e=>{readDraft();draft.technology=e.target.value;draft.material=null;draft.color=null;schedule(step===3?'quote':'inspect');});
$('material').addEventListener('change',e=>{readDraft();draft.material=e.target.value||null;draft.color=null;schedule(step===3?'quote':'inspect');});
$('color').addEventListener('change',e=>{draft.color=e.target.value||null;schedule(step===3?'quote':'inspect');});
for(const k of ['quantity','category','description'])$(k).addEventListener('input',()=>{readDraft();schedule(step===3?'quote':'inspect',500);});
$('next-material').addEventListener('click',()=>setStep(2));$('next-review').addEventListener('click',()=>setStep(3));
for(const e of document.querySelectorAll('[data-step]'))e.addEventListener('click',()=>setStep(Number(e.dataset.step)));
for(const e of document.querySelectorAll('[data-back]'))e.addEventListener('click',()=>setStep(Number(e.dataset.back)));
$('settings-form').addEventListener('submit',e=>{e.preventDefault();if(step===1)setStep(2);else if(step===2)setStep(3);else schedule('quote',0);});
$('reset-view').addEventListener('click',()=>viewer?.reset());$('wireframe').addEventListener('click',()=>{if(viewer)$('wireframe').setAttribute('aria-pressed',String(viewer.wireframe()));});
$('reset').addEventListener('click',async()=>{try{if(state)await api(`/api/sessions/${state.id}`,{method:'DELETE'});}catch(e){$('global-error').textContent=e.message;return;}stream?.close();viewer?.dispose();localStorage.removeItem('part-quote-session');localStorage.removeItem('part-quote-flow');location.reload();});
api('/api/catalog').then(data=>{catalog=data.technologies;render();}).catch(()=>{});
(async()=>{
  const id=localStorage.getItem('part-quote-session');if(!id)return;
  try{
    const restored=await api(`/api/sessions/${id}`);let flow=null;try{flow=JSON.parse(localStorage.getItem('part-quote-flow'));}catch{}
    if(flow?.id===id){draft=flow.draft;step=flow.step||1;pendingAction=flow.pendingAction;for(const k of ['quantity','description','category'])$(k).value=draft[k];}
    apply(restored);connect(id);selectedAt=performance.now();const r=await fetch(`/api/sessions/${id}/model`);if(r.ok)preview(new File([await r.blob()],restored.file));
  }catch(e){localStorage.removeItem('part-quote-session');localStorage.removeItem('part-quote-flow');$('global-error').textContent='The previous session has ended. Upload a model to begin again.';}
})();
