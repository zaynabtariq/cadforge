const $=id=>document.getElementById(id);
let current=null,busy=false,renderedForm=null,polling=false,requestGeneration=0,localError='';
const labels={email:'Continue',password:'Sign in',code:'Verify code'};
const copy={
 idle:['Your workspace.','Connect Autodesk Fusion to get started.','Ready to connect'],
 connecting:['Getting ready.','Opening your private workstation.','Connecting…'],
 credentials_required:['Welcome back.','Sign in to Autodesk.','Secure connection'],
 password_required:['Welcome back.','Continue with your Autodesk account.','Secure connection'],
 code_required:['Check your email.','Enter your 6-digit verification code.','Waiting for verification'],
 device_confirmation:['Almost there.','Finishing your Autodesk sign-in.','Confirming your device…'],
 submitting:['Signing in.','One moment.','Submitting to Autodesk…'],
 waiting_for_autodesk:['One moment.','Waiting for Autodesk.','Signing in…'],
 opening_fusion:['Opening Fusion.','Your workspace is on its way.','Autodesk connected'],
 verifying:['One last check.','Making sure everything is ready.','Checking Fusion…'],
 ready:["Connected.",'',''],
 session_expired:['Let’s try again.','Your Autodesk session expired.','Session expired'],
 stalled:['Let’s reconnect.','Autodesk didn’t finish this step.','Sign-in paused'],
 connection_lost:['Connection lost.','Reconnect to continue.','Workstation unavailable'],
 needs_attention:['One more step.','Your workstation needs attention.','Connection paused'],
 challenge_required:['One more step.','Autodesk needs a security check.','Action required']
};
function render(state){
 if(!state)return;
 if(current?.epoch===state.epoch && state.revision<current.revision)return;
 if(current&&state.form_token&&state.form_token!==current.form_token)localError='';
 current=state;
 const submitting=busy||state.phase==='submitting';
 const field=submitting?(renderedForm||state.form):state.form;
 const words=copy[state.phase]||['One moment.','',state.message];
 document.body.dataset.phase=state.phase;
 if(!submitting||!renderedForm){$('auth-title').textContent=words[0];$('subtitle').textContent=words[1];}
 $('status').textContent=busy?'Submitting to Autodesk…':words[2];
 $('status').setAttribute('aria-busy',String(submitting));
 $('form-error').textContent=localError||state.error||'';
 $('connect').classList.toggle('hidden',state.phase!=='idle');
 $('retry').classList.toggle('hidden',!state.can_retry);$('retry').disabled=busy;
 $('auth-form').classList.toggle('hidden',!field);
 for(const kind of ['email','password','code']){
  $(kind+'-field').classList.toggle('hidden',kind!==field);
  $(kind).disabled=submitting||kind!==field;$(kind).required=kind===field;
 }
 $('submit-auth').disabled=submitting||!state.form_token;
 $('submit-auth').textContent=submitting?'Submitting…':labels[field]||'Continue';
 if(field!==renderedForm&&!submitting){
  if(renderedForm==='password')$('password').value='';
  if(renderedForm==='code')$('code').value='';
  renderedForm=field;
  if(field)requestAnimationFrame(()=>$(field).focus());
 }
 $('open-viewer').classList.toggle('hidden',!state.verified);
 $('steps').classList.toggle('hidden',!!state.verified);
 document.querySelector('.auth-footer').classList.toggle('hidden',!!state.verified);
 $('waiting-indicator').classList.toggle('hidden',!!field||state.verified||state.phase==='idle'||state.can_retry||state.phase==='challenge_required');
 const stage=state.stage;
 document.querySelectorAll('#steps li').forEach((li,i)=>{
  li.classList.toggle('active',i===stage);li.classList.toggle('done',i<stage);
  if(i===stage)li.setAttribute('aria-current','step');else li.removeAttribute('aria-current');
  li.querySelector('b').textContent=i<stage?'✓':'';
 });
}
async function poll(){
 if(polling||busy)return;polling=true;const generation=requestGeneration;
 try{
  const r=await fetch('v1/auth',{cache:'no-store'});if(!r.ok)throw Error();const state=await r.json();
  if(generation===requestGeneration&&!busy)render(state);
 }catch{
  if(!busy){$('status').textContent='Connection interrupted. Checking the workstation…';$('submit-auth').disabled=true;}
 }finally{polling=false;}
}
async function post(path,body){
 const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Connector-Request':'1'},body:JSON.stringify(body)});
 const result=await r.json();
 if(!r.ok){const error=Error(result.error?.message||'The connector could not complete this request.');error.code=result.error?.code;throw error;}
 return result;
}
async function control(path){
 if(busy)return;busy=true;requestGeneration++;localError='';$('connect').disabled=true;render(current);
 try{const state=await post(path,{});busy=false;render(state)}
 catch(error){busy=false;localError=error.message;render(current)}
 finally{$('connect').disabled=false;await poll()}
}
$('connect').onclick=()=>control('v1/auth/start');
$('retry').onclick=()=>control('v1/auth/retry');
$('auth-form').onsubmit=async event=>{
 event.preventDefault();if(busy||current?.phase==='submitting'||!current?.form_token)return;
 const kind=current.form;if(!kind)return;
 let body={[kind]:$(kind).value,request_id:crypto.randomUUID(),form_token:current.form_token};
 busy=true;requestGeneration++;localError='';render(current);
 try{
  const result=await post('v1/auth/credentials',body);
  // Clear secrets only after the VM has acknowledged the submission. A
  // pre-submission validation error leaves the field available to correct.
  if(kind!=='email')$(kind).value='';
  busy=false;render(result.state);
 }catch(error){
  busy=false;localError=error.message;
  if(error.code==='browser_unavailable'&&kind!=='email')$(kind).value='';
  render(current);
 }finally{body=null;await poll()}
};
poll();setInterval(poll,1500);
