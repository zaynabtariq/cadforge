// Runs in terminal-browser's Electron main process, not in Autodesk's page.
const {app,webContents}=require('electron');
const home=__CONNECTOR_URL_JSON__;
const homeURL=new URL(home);
const bound=new Set(),installed=new WeakSet();
function belongs(url){try{const u=new URL(url);return u.origin===homeURL.origin && u.pathname.startsWith(homeURL.pathname)}catch{return false}}
function autodesk(url){try{return ['signin.autodesk.com','accounts.autodesk.com'].includes(new URL(url).hostname)}catch{return false}}
function attach(contents){
 if(installed.has(contents))return;installed.add(contents);
 const intercept=(event,url)=>{
  url=typeof url==='string'?url:event.url;
  if(belongs(contents.getURL())||belongs(url))bound.add(contents.id);
  if(!bound.has(contents.id))return;
  let parsed;try{parsed=new URL(url)}catch{return}
  if(parsed.protocol!=='adskidmgr:')return;
  event.preventDefault();
  if(!autodesk(contents.getURL()))return;
  fetch(new URL('v1/auth/callback',home),{method:'POST',headers:{'Content-Type':'application/json','X-Connector-Request':'1'},body:JSON.stringify({callback:url})})
   .then(r=>{if(!r.ok)throw Error('Callback rejected');return contents.loadURL(home)})
   .catch(()=>contents.loadURL(home));
 };
 contents.on('will-navigate',intercept);
 contents.on('will-redirect',intercept);
 contents.on('will-frame-navigate',intercept);
 contents.on('dom-ready',()=>{if(belongs(contents.getURL())){
  bound.add(contents.id);contents.executeJavaScript('window.__fusionAuthHookReady=true').catch(()=>{});
 }});
 contents.on('did-navigate',(_,url)=>{if(belongs(url))bound.add(contents.id)});
 contents.on('destroyed',()=>bound.delete(contents.id));
}
app.on('web-contents-created',(_,contents)=>attach(contents));
for(const contents of webContents.getAllWebContents())attach(contents);
