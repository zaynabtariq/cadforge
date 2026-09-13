"""Observed VM sign-in state, serialized submissions, and explicit recovery."""
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from .bridge import BridgeClient, BridgeError
from .browser import AutodeskBrowser

FORMS={'credentials_required':'email','password_required':'password','code_required':'code'}
MESSAGES={
 'idle':'Connect to your Fusion workstation.',
 'connecting':'Connecting to the workstation…',
 'credentials_required':'Enter your Autodesk email.',
 'password_required':'Autodesk is ready for your password.',
 'code_required':'Enter the verification code requested by Autodesk.',
 'device_confirmation':'Verification accepted. Completing Autodesk’s device confirmation…',
 'submitting':'Submitting to Autodesk…',
 'waiting_for_autodesk':'Waiting for Autodesk to respond…',
 'session_expired':'This Autodesk sign-in session expired. Start a new sign-in.',
 'stalled':'Autodesk stopped responding. Start a new sign-in.',
 'challenge_required':'Autodesk requires an interactive security check. This form cannot complete it.',
 'connection_lost':'The connection to the VM browser was lost. Reconnect to continue.',
 'opening_fusion':'Autodesk reports success. Waiting for Fusion to open…',
 'verifying':'Checking Fusion can create and close a document…',
 'needs_attention':'The workstation needs attention before sign-in can continue.',
 'ready':'Fusion is signed in and ready to model.'}


def page_phase(page):
    text=page.get('text','').lower()
    if any(s in text for s in ('session ended','session has expired','session expired','unable to access this link')):return 'session_expired'
    if any(s in text for s in ("you're signed in",'you are signed in','successfully signed in','sign-in complete')):return 'opening_fusion'
    if any(b.get('text')=="Don't trust this device" for b in page.get('buttons',[])):return 'device_confirmation'
    if 'captcha' in text or 'security check' in text:return 'challenge_required'
    inputs=page.get('inputs',[])
    for i in inputs:
        if i.get('disabled'):continue
        if i['type']=='password':return 'password_required'
        if i.get('autocomplete')=='one-time-code' or i.get('name','').lower() in ('code','otp','verificationcode','otc') or 'code' in i.get('id','').lower():return 'code_required'
        if i.get('name')=='email' or i['type']=='email':return 'credentials_required'
    return 'waiting_for_autodesk'


def page_error(page):
    # Never return arbitrary DOM text, which can contain account information.
    text=' '.join(page.get('errors',[])).lower()
    if not text:return None
    if 'required' in text or 'enter' in text and 'code' in text:
        if 'code' in text:return 'Enter the complete verification code from your email.'
        if 'password' in text:return 'Enter your Autodesk password.'
        if 'email' in text:return 'Enter your Autodesk email.'
    if 'password' in text:return 'Autodesk did not accept that password. Check it and try again.'
    if 'code' in text:return 'Autodesk did not accept that verification code. Check it and try again.'
    if 'email' in text or 'account' in text:return 'Autodesk could not continue with that email. Check it and try again.'
    return 'Autodesk could not complete this step. Review your entry and try again.'


class RemoteAuthBroker:
    def __init__(self,vm):
        self.vm=vm;self.browser=AutodeskBrowser(vm);self.bridge=None
        self.lock=threading.RLock();self.operation=threading.Lock();self.stop=threading.Event();self.thread=None
        self.epoch=uuid.uuid4().hex;self.attempt=uuid.uuid4().hex
        self.submitted=False;self.auth_observed=False;self.verification_started=False
        self.verification_key='auth-verify-'+uuid.uuid4().hex
        self.phase_since=time.monotonic();self.pending=None;self.requests={};self.failures=0
        self.connect_deadline=time.monotonic()+180
        self.product_open_requested=False
        self.resume_record=None
        try:
            record=json.loads((Path(__file__).resolve().parents[1]/'auth-verification.json').read_text())
            if vm and record.get('verified') is True and record.get('instance_id')==vm.state['instance_id'] and record.get('windows_user')==vm.state['windows_user']:
                self.resume_record=record
        except (OSError,ValueError,KeyError):pass
        self.info={'epoch':self.epoch,'revision':0,'attempt':self.attempt,'phase':'idle','stage':0,
                   'message':MESSAGES['idle'],'verified':False,'form':None,'form_token':None,'error':None,'can_retry':False}
    def status(self):
        with self.lock:return dict(self.info)
    def update(self,phase,**extra):
        with self.lock:
            stage=3 if phase=='ready' else 2 if phase in ('opening_fusion','verifying') else 0 if phase in ('idle','connecting') else 1
            values={'phase':phase,'stage':stage,'message':MESSAGES[phase],
                    'form':FORMS.get(phase),'form_token':None,'error':None,
                    'can_retry':not self.auth_observed and phase in ('session_expired','stalled','connection_lost','needs_attention'),**extra}
            if phase!=self.info['phase']:self.phase_since=time.monotonic()
            if any(self.info.get(k)!=v for k,v in values.items()):
                self.info.update(values);self.info['revision']+=1
    def start(self):
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                self.stop.clear();self.connect_deadline=time.monotonic()+180
                self.update('connecting',verified=False)
                self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()
        return self.status()
    def observe(self,page):
        phase=page_phase(page);error=page_error(page)
        if phase=='opening_fusion':
            # A success page is necessary, but not sufficient for ready.
            if self.submitted:self.auth_observed=True
            self.pending=None;self.update(phase);return phase
        if self.pending:
            before=self.pending['phase']
            if phase in ('waiting_for_autodesk',before) and not error:
                if time.monotonic()-self.pending['at']<30:
                    self.update('submitting',form=self.pending['form']);return 'submitting'
                self.pending=None
                self.update('stalled',error='No confirmation came back from Autodesk. Start a new sign-in before submitting again.');return 'stalled'
            self.pending=None
        if phase=='waiting_for_autodesk' and self.info['phase']=='waiting_for_autodesk' and time.monotonic()-self.phase_since>30:
            self.update('stalled');return 'stalled'
        if phase=='waiting_for_autodesk' and self.info['phase']=='stalled':return 'stalled'
        token=hashlib.sha256((self.attempt+page.get('page_id','')+phase).encode()).hexdigest() if phase in FORMS else None
        self.update(phase,form_token=token,error=error);return phase
    def verify(self):
        if not self.auth_observed:return False
        if not self.vm.tunnel or self.vm.tunnel.poll() is not None:
            self.vm.close();self.bridge=BridgeClient(self.vm.connect())
        ready=self.bridge.call('/ready',timeout=3)
        if not ready.get('ready'):return False
        docs=self.bridge.call('/list_open_documents',timeout=5)
        if docs['count'] and not self.verification_started:
            self.update('needs_attention',error='Close open documents before verifying the fresh workstation.');return False
        self.update('verifying')
        if not docs['count']:
            self.verification_started=True
            self.bridge.call('/new_document',{'name':'Connector authentication verification'},key=self.verification_key,timeout=15)
        created=self.bridge.call('/list_open_documents',timeout=5)
        if created['count']!=1:return False
        self.bridge.call('/close_document',{'document_name':created['active_document'],'save':False},timeout=10)
        caps=self.bridge.call('/v1/viewer/capabilities',timeout=5)
        self.update('ready',verified=True,verification_method='fresh_login',fusion_version=ready.get('version'),connector_api=caps['api_version'])
        record={**self.status(),'instance_id':self.vm.state['instance_id'],'windows_user':self.vm.state['windows_user'],
                'verified_at':time.time(),'method':'vm_browser_credential_relay'}
        (Path(__file__).resolve().parents[1]/'auth-verification.json').write_text(json.dumps(record,indent=2)+'\n')
        self.resume_record=record
        return True
    def poll(self):
        if not self.operation.acquire(blocking=False):return
        try:
            if self.auth_observed:
                if not self.product_open_requested:
                    try:self.product_open_requested=self.browser.confirm('Open Product')
                    except Exception:pass
                try:
                    if self.verify():return
                except Exception:pass
                if self.info['phase'] not in ('verifying','needs_attention'):self.update('opening_fusion')
                return
            try:
                page=self.browser.inspect();self.failures=0;phase=self.observe(page)
                if phase in FORMS:self.resume_record=None
                if phase=='device_confirmation' and not self.pending:
                    # The test workstation doesn't need a 30-day MFA exemption.
                    # Finish native sign-in without enrolling a trusted device.
                    if self.browser.confirm("Don't trust this device"):
                        self.pending={'phase':'device_confirmation','form':None,'at':time.monotonic()}
            except Exception:
                self.failures+=1
                if self.info['phase']=='connecting' and time.monotonic()<self.connect_deadline:return
                if self.failures>=3:self.update('connection_lost')
        finally:self.operation.release()
    def work(self):
        try:self.bridge=BridgeClient(self.vm.connect())
        except Exception:self.update('connection_lost');return
        while not self.stop.is_set() and not self.info['verified']:
            if self.resume_record:
                # SSH can be ready before Fusion. Keep checking live readiness
                # during cold startup; a credential prompt invalidates this path.
                try:
                    ready=self.bridge.call('/ready',timeout=5)
                    if ready.get('ready'):
                        caps=self.bridge.call('/v1/viewer/capabilities',timeout=5)
                        self.update('ready',verified=True,verification_method='restored_session',fusion_version=ready.get('version'),connector_api=caps['api_version'])
                        return
                except Exception:pass
            self.poll();self.stop.wait(2)
    def credentials(self,body):
        # Exactly one visible field per request. Nothing secret is kept for the
        # next screen, retries, background workers, or diagnostic records.
        values={k:body.pop(k,None) for k in ('email','password','code')}
        request_id=body.get('request_id');form_token=body.get('form_token')
        acquired=False
        try:
            if sum(v is not None for v in values.values())!=1:raise BridgeError('invalid_fields','Submit only the field shown in the form.',400)
            kind=next(k for k,v in values.items() if v is not None);value=values[kind]
            if not isinstance(value,str) or not 0<len(value)<=1024:raise BridgeError('invalid_fields','Enter a valid sign-in value.',400)
            if not isinstance(request_id,str) or not 8<=len(request_id)<=80:raise BridgeError('invalid_request','A submission ID is required.',400)
            acquired=self.operation.acquire(timeout=8)
            if not acquired:raise BridgeError('busy','The VM is still responding. Try again shortly.',409)
            if request_id in self.requests:
                if self.requests[request_id]!=(kind,form_token):raise BridgeError('idempotency_conflict','This submission ID belongs to another form.',409)
                return {'accepted':True,'duplicate':True,'state':self.status()}
            state=self.status()
            if state['form']!=kind or not form_token or state['form_token']!=form_token or state['phase'] not in FORMS:
                raise BridgeError('stale_form','The Autodesk screen changed. Review the current step and try again.',409)
            page=self.browser.inspect()
            if page_phase(page)!=state['phase']:
                self.observe(page);raise BridgeError('form_unavailable','Autodesk is not ready for this field. Wait for the current step.',409)
            token=hashlib.sha256((self.attempt+page.get('page_id','')+state['phase']).encode()).hexdigest()
            if token!=form_token:
                self.observe(page);raise BridgeError('stale_form','The Autodesk sign-in session changed. Try the current form.',409)
            self.update('submitting',form=kind)
            result=self.browser.submit(kind,value,page['page_id'])
            if not result.get('submitted'):
                self.observe(self.browser.inspect())
                message={'form_disabled':'Autodesk disabled this form. Wait for it to finish loading.',
                         'invalid_code_length':'Enter all six digits from the verification email.',
                         'incomplete_code':'The verification code did not fill completely. Try again.'}.get(result.get('reason'),'The Autodesk form changed before submission. Try the current step.')
                raise BridgeError(result.get('reason','form_unavailable'),message,409)
            self.pending={'phase':state['phase'],'form':kind,'at':time.monotonic()}
            if kind in ('password','code'):self.submitted=True
            self.requests[request_id]=(kind,form_token)
            if len(self.requests)>32:self.requests.pop(next(iter(self.requests)))
            return {'accepted':True,'state':self.status()}
        except BridgeError:raise
        except Exception:
            # We cannot infer whether a timed-out browser command submitted.
            self.update('connection_lost',error='The VM did not confirm the submission. Reconnect to inspect its state before trying again.')
            raise BridgeError('browser_unavailable','The VM did not confirm the submission. Reconnect to check its state.',502) from None
        finally:
            values.clear();body.clear();value=None
            if acquired:self.operation.release()
    def retry(self):
        if not self.operation.acquire(timeout=8):raise BridgeError('busy','Wait for the current submission to finish.',409)
        try:
            if self.auth_observed:raise BridgeError('already_signed_in','Autodesk is already signed in. Finish Fusion verification.',409)
            if self.info['phase'] not in ('session_expired','stalled','connection_lost','needs_attention'):
                raise BridgeError('not_retryable','The current sign-in is still active.',409)
            try:
                if not self.bridge:raise RuntimeError('No bridge')
                docs=self.bridge.call('/list_open_documents',timeout=3)
            except Exception:
                raise BridgeError('workspace_unknown','Cannot confirm whether Fusion has unsaved documents. Inspect the native workspace before restarting sign-in.',409) from None
            if docs.get('count'):raise BridgeError('documents_open','Close open Fusion documents before restarting sign-in.',409)
            self.update('connecting')
            self.connect_deadline=time.monotonic()+180
            # Relaunch the original desktop flow, never reuse a redirected URL.
            self.vm.ssm("Stop-ScheduledTask -TaskName FusionAuth-BeginSignIn -ErrorAction SilentlyContinue; Stop-ScheduledTask -TaskName FusionAuth-Session; Get-Process Fusion360,AdskIdentityManager,msedge -ErrorAction SilentlyContinue | Stop-Process -Force; Start-ScheduledTask -TaskName FusionAuth-Session; 'Native sign-in requested'",timeout=30)
            self.attempt=uuid.uuid4().hex;self.pending=None;self.submitted=False;self.auth_observed=False;self.failures=0
            self.product_open_requested=False
            self.info['attempt']=self.attempt;self.requests.clear()
        except BridgeError:raise
        except Exception:
            self.update('needs_attention',error='Could not restart Autodesk sign-in on the VM.')
            raise BridgeError('restart_failed','Could not restart Autodesk sign-in on the VM.',502) from None
        finally:self.operation.release()
        self.start();return self.status()
    def close(self):self.stop.set();self.vm.close()
