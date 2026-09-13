"""Relay Autodesk's own desktop login, with no password intake endpoint."""
import hashlib
import json
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

from .bridge import BridgeClient

READ_REQUEST = r'''
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
Add-Type -AssemblyName System.Security
$folder=Join-Path $env:LOCALAPPDATA 'FusionWorkstation\Auth'
$file=Join-Path $folder 'request.dpapi'
try {
 $processes=Get-CimInstance Win32_Process -Filter "name='msedge.exe'"
 foreach($process in $processes){
  if($process.CommandLine -notlike '*FusionWorkstation\EdgeAuth*'){continue}
  foreach($match in [regex]::Matches($process.CommandLine,'https://[^\s"]+')){
   $u=[Uri]$match.Value
   if($u.Host -eq 'developer.api.autodesk.com' -and $u.AbsolutePath -eq '/authentication/v2/authorize'){
    @{url=$match.Value;age_seconds=([DateTime]::UtcNow-$process.CreationDate.ToUniversalTime()).TotalSeconds;source='native_edge_launch'} | ConvertTo-Json -Compress
    exit 0
   }
  }
 }
} catch {}
try {
 $tabs=Invoke-RestMethod 'http://127.0.0.1:9222/json/list' -TimeoutSec 2
 $tab=$tabs | Where-Object { $_.type -eq 'page' -and ([Uri]$_.url).Host -in 'signin.autodesk.com','accounts.autodesk.com' -and ([Uri]$_.url).Query.Length -gt 0 } | Select-Object -First 1
 if($tab){
  $started=Join-Path $folder 'signin-start.txt'
  $age=if(Test-Path $started){([DateTime]::UtcNow-(Get-Item $started).LastWriteTimeUtc).TotalSeconds}else{99999}
  @{url=$tab.url;age_seconds=$age;source='native_edge'} | ConvertTo-Json -Compress;exit 0
 }
} catch {}
if(Test-Path $file){
 $bytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($file),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
 try { @{url=[Text.Encoding]::UTF8.GetString($bytes);age_seconds=([DateTime]::UtcNow-(Get-Item $file).LastWriteTimeUtc).TotalSeconds} | ConvertTo-Json -Compress }
 finally {[Array]::Clear($bytes,0,$bytes.Length)}
} else {'{}'}
'''

STORE_CALLBACK = r'''
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
Add-Type -AssemblyName System.Security
$text=[Console]::In.ReadToEnd()
if($text.Length -gt 16384 -or ([Uri]$text).Scheme -ne 'adskidmgr'){exit 2}
$bytes=[Text.Encoding]::UTF8.GetBytes($text)
try {
 $folder=Join-Path $env:LOCALAPPDATA 'FusionWorkstation\Auth'
 $cipher=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
 [IO.File]::WriteAllBytes((Join-Path $folder 'callback.tmp'),$cipher)
 Move-Item (Join-Path $folder 'callback.tmp') (Join-Path $folder 'callback.dpapi') -Force
 '{"accepted":true}'
} finally {[Array]::Clear($bytes,0,$bytes.Length);$text=$null}
'''


def autodesk_url(value):
    if not isinstance(value,str) or len(value)>16384: return False
    p=urllib.parse.urlsplit(value)
    allowed=p.hostname in ('signin.autodesk.com','accounts.autodesk.com') or (p.hostname=='developer.api.autodesk.com' and p.path=='/authentication/v2/authorize')
    return p.scheme=='https' and allowed and not p.username and not p.password and p.port in (None,443)


class AuthBroker:
    def __init__(self,vm):
        self.vm=vm;self.bridge=None;self.lock=threading.RLock();self.thread=None
        self.stop=threading.Event();self.login_url=None;self.callback_hash=None
        self.callback_received=False;self.issued_at=0
        self.verification_key='auth-verify-'+uuid.uuid4().hex
        self.verification_started=False
        self.info={'phase':'idle','message':'Connect a fresh Fusion workstation','verified':False}

    def update(self,phase,message,**extra):
        with self.lock:self.info.update(phase=phase,message=message,**extra)

    def status(self):
        with self.lock:return dict(self.info)

    def start(self):
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                self.stop.clear();self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()
        return self.status()

    def work(self):
        self.update('connecting','Connecting to your private workstation…')
        deadline=time.monotonic()+1200
        try:
            self.bridge=BridgeClient(self.vm.connect())
            while time.monotonic()<deadline and not self.stop.is_set():
                # A native desktop callback must be observed before claiming a
                # fresh sign-in succeeded. Existing readiness is not auth proof.
                if self.callback_received:
                    try:
                        if not self.vm.tunnel or self.vm.tunnel.poll() is not None:
                            self.vm.close();self.bridge=BridgeClient(self.vm.connect())
                        ready=self.bridge.call('/ready',timeout=4)
                        if ready.get('ready'):
                            self.update('verifying','Checking Fusion can create a document…')
                            docs=self.bridge.call('/list_open_documents')
                            if docs['count'] and not self.verification_started:
                                self.update('needs_attention','Close open documents before the fresh-login verification.');return
                            if not docs['count']:
                                self.verification_started=True
                                self.bridge.call('/new_document',{'name':'Connector authentication verification'},key=self.verification_key)
                            created=self.bridge.call('/list_open_documents')
                            assert created['count']==1
                            self.bridge.call('/close_document',{'document_name':created['active_document'],'save':False})
                            capabilities=self.bridge.call('/v1/viewer/capabilities')
                            self.update('ready','Fusion is signed in and ready to model.',verified=True,
                                fusion_version=ready.get('version'),connector_api=capabilities['api_version'])
                            record={**self.status(),'instance_id':self.vm.state['instance_id'],
                                    'windows_user':self.vm.state['windows_user'],'verified_at':time.time()}
                            (Path(__file__).resolve().parents[1]/'auth-verification.json').write_text(json.dumps(record,indent=2)+'\n')
                            self.login_url=None;return
                    except Exception:
                        self.update('verifying','Autodesk callback delivered. Waiting for Fusion to finish signing in…')
                else:
                    try:
                        result=json.loads(self.vm.ssh(READ_REQUEST,timeout=12))
                        url=result.get('url')
                        if url and autodesk_url(url) and result.get('age_seconds',9999)<600:
                            with self.lock:
                                if url!=self.login_url:self.login_url=url;self.issued_at=time.monotonic()
                            self.update('sign_in_required','Sign in with Autodesk. Complete any verification on their page.')
                        elif url:
                            self.update('needs_attention','The sign-in request expired or uses an unsupported Autodesk host.')
                        else:
                            self.login_url=None
                            self.update('waiting_for_fusion','Waiting for Fusion to open its sign-in page…')
                    except Exception:
                        self.update('connecting','Waiting for the fresh Windows session and secure connection…')
                self.stop.wait(2)
            if not self.stop.is_set():self.update('expired','Sign-in timed out. Start a new sign-in request.')
        except Exception:
            self.update('needs_attention','Could not connect to the authentication workstation.')

    def callback(self,value):
        if not isinstance(value,str) or len(value)>16384 or any(ord(c)<32 for c in value):raise ValueError('Invalid callback')
        uri=urllib.parse.urlsplit(value)
        if uri.scheme!='adskidmgr' or uri.username or uri.password:raise ValueError('Unsupported callback')
        with self.lock:
            if not self.login_url or time.monotonic()-self.issued_at>600:raise ValueError('No active sign-in request')
            digest=hashlib.sha256(value.encode()).hexdigest()
            if self.callback_hash:
                if digest==self.callback_hash:return {'accepted':True,'duplicate':True}
                raise ValueError('A callback was already submitted')
            # Validate OAuth state when exposed directly in the launch URL. The
            # Identity Manager owns additional nonce/PKCE validation internally.
            expected=urllib.parse.parse_qs(urllib.parse.urlsplit(self.login_url).query).get('state')
            received=urllib.parse.parse_qs(uri.query).get('state')
            if expected and received!=expected:raise ValueError('Login state mismatch')
            self.vm.ssh(STORE_CALLBACK,stdin=value)
            self.callback_hash=digest;self.callback_received=True
            self.update('verifying','Sign-in received. Connecting Autodesk to Fusion…')
            return {'accepted':True}

    def close(self):
        self.stop.set();self.vm.close()
