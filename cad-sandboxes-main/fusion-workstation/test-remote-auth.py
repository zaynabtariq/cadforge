import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from fusion_connector.remote_auth import RemoteAuthBroker, page_phase, page_error
from fusion_connector.bridge import BridgeError


def page(kind='password',disabled=False,errors=None):
    return {'page_id':'test-page','inputs':[{'type':kind if kind=='password' else 'text','name':kind,'disabled':disabled}],
            'errors':errors or []}

class Browser:
    def __init__(self):self.current=page();self.calls=0;self.failure=False
    def inspect(self):return self.current
    def submit(self,*args):
        self.calls+=1
        if self.failure:raise RuntimeError('Internal detail must not escape')
        return {'submitted':True}

class Tests(unittest.TestCase):
    def test_full_fresh_flow_requires_native_success_and_document_roundtrip(self):
        a=self.broker();a.vm=Mock();a.vm.state={'instance_id':'synthetic-vm','windows_user':'FusionAuth'}
        a.vm.tunnel.poll.return_value=None;a.bridge=Mock()
        for number,kind in enumerate(('email','password','code')):
            a.browser.current=page(kind);a.observe(a.browser.current)
            a.credentials({kind:'123456' if kind=='code' else 'synthetic-value',
                'form_token':a.status()['form_token'],'request_id':f'fresh-step-{number}'})
            self.assertFalse(a.status()['verified'])
        a.observe({'inputs':[],'buttons':[{'text':"Don't trust this device"}]})
        self.assertFalse(a.verify())
        a.observe({'inputs':[],'text':"You're signed in"})
        a.bridge.call.side_effect=[{'ready':True,'version':'test'},{'count':0},{'success':True},
            {'count':1,'active_document':'Synthetic verification'},{'success':True},{'api_version':'1.0'}]
        with tempfile.TemporaryDirectory() as tmp,patch('fusion_connector.remote_auth.Path') as path:
            path.return_value.resolve.return_value.parents=[Path(tmp),Path(tmp)]
            self.assertTrue(a.verify())
            record=json.loads((Path(tmp)/'auth-verification.json').read_text())
            self.assertEqual(record['verification_method'],'fresh_login')
            self.assertEqual(record['instance_id'],'synthetic-vm')
            self.assertEqual(a.resume_record,record)
        self.assertEqual([call.args[0] for call in a.bridge.call.call_args_list],
            ['/ready','/list_open_documents','/new_document','/list_open_documents','/close_document','/v1/viewer/capabilities'])
        self.assertEqual(a.bridge.call.call_args_list[4].args[1],{'document_name':'Synthetic verification','save':False})
    def test_resume_waits_for_cold_fusion_and_preserves_documents(self):
        a=self.broker();a.vm=Mock();a.resume_record={'verified':True};a.stop=Mock()
        a.stop.is_set.return_value=False;a.poll=Mock()
        bridge=Mock();bridge.call.side_effect=[RuntimeError('starting'),{'ready':True,'version':'test'},{'api_version':'1.0'}]
        with patch('fusion_connector.remote_auth.BridgeClient',return_value=bridge):a.work()
        self.assertTrue(a.status()['verified']);self.assertEqual(a.status()['verification_method'],'restored_session')
        self.assertEqual([c.args[0] for c in bridge.call.call_args_list],['/ready','/ready','/v1/viewer/capabilities'])
    def test_native_credential_prompt_invalidates_resume_proof(self):
        a=self.broker();a.resume_record={'verified':True};a.poll()
        self.assertIsNone(a.resume_record);self.assertFalse(a.status()['verified'])
    def test_retry_cannot_kill_an_unknown_workspace(self):
        a=self.broker();a.vm=Mock();a.bridge=Mock();a.bridge.call.side_effect=RuntimeError('offline')
        a.update('connection_lost')
        with self.assertRaises(BridgeError) as e:a.retry()
        self.assertEqual(e.exception.code,'workspace_unknown');a.vm.ssm.assert_not_called()
    def test_retry_cannot_discard_open_documents(self):
        a=self.broker();a.vm=Mock();a.bridge=Mock();a.bridge.call.return_value={'count':1}
        a.update('stalled')
        with self.assertRaises(BridgeError) as e:a.retry()
        self.assertEqual(e.exception.code,'documents_open');a.vm.ssm.assert_not_called()
    def test_device_confirmation_is_progress_after_code(self):
        a=self.broker();a.browser.current=page('code');a.observe(a.browser.current)
        a.credentials({'code':'123456','form_token':a.status()['form_token'],'request_id':'code-step-1'})
        a.observe({'inputs':[],'buttons':[{'text':"Don't trust this device"}], 'text':'Trust this device to skip codes?'})
        self.assertEqual(a.status()['phase'],'device_confirmation')
        self.assertIsNone(a.pending);self.assertEqual(a.status()['stage'],1)
        self.assertFalse(a.status()['can_retry'])
    def test_missing_code_is_not_reported_as_rejected_code(self):
        self.assertEqual(page_error({'errors':['Code is required.']}),'Enter the complete verification code from your email.')
        self.assertIn('did not accept',page_error({'errors':['Incorrect code.']}))
    def broker(self):
        a=RemoteAuthBroker(None);a.browser=Browser();a.observe(a.browser.current);return a
    def body(self,a,**extra):return {'password':'synthetic-test-value','form_token':a.status()['form_token'],'request_id':'submission-1',**extra}
    def test_disabled_field_is_not_a_password_prompt(self):
        self.assertEqual(page_phase(page(disabled=True)),'waiting_for_autodesk')
    def test_submission_stays_pending_until_observed_transition(self):
        a=self.broker();body=self.body(a);a.credentials(body)
        self.assertEqual(body,{})
        for p in (page(),page(disabled=True),{'inputs':[]}):
            a.observe(p);self.assertEqual(a.status()['phase'],'submitting');self.assertEqual(a.status()['stage'],1)
        a.observe(page('code'));self.assertEqual(a.status()['form'],'code')
    def test_no_progress_from_credential_submission_alone(self):
        a=self.broker();a.credentials(self.body(a));self.assertFalse(a.verify());self.assertFalse(a.auth_observed)
        a.observe({'text':"You're signed in",'inputs':[]});self.assertTrue(a.auth_observed)
        self.assertEqual(a.status()['stage'],2);self.assertFalse(a.status()['verified'])
    def test_stale_form_cannot_send_password(self):
        a=self.broker();body=self.body(a,form_token='stale')
        with self.assertRaises(BridgeError) as e:a.credentials(body)
        self.assertEqual(e.exception.code,'stale_form');self.assertEqual(a.browser.calls,0);self.assertEqual(body,{})
    def test_disabled_remote_form_cannot_send_password(self):
        a=self.broker();body=self.body(a);a.browser.current=page(disabled=True)
        with self.assertRaises(BridgeError):a.credentials(body)
        self.assertEqual(a.browser.calls,0);self.assertEqual(a.status()['phase'],'waiting_for_autodesk')
    def test_duplicate_submission_does_not_replay(self):
        a=self.broker();body=self.body(a);duplicate=dict(body);a.credentials(body);a.credentials(duplicate)
        self.assertEqual(a.browser.calls,1)
    def test_error_is_sanitized_and_secrets_are_released(self):
        a=self.broker();a.browser.failure=True;body=self.body(a)
        with self.assertRaises(BridgeError) as e:a.credentials(body)
        self.assertNotIn('Internal detail',str(e.exception));self.assertEqual(body,{})
        self.assertNotIn('synthetic-test-value',repr(vars(a)));self.assertEqual(a.status()['phase'],'connection_lost')
        self.assertTrue(a.operation.acquire(blocking=False));a.operation.release()
    def test_expiry_and_stall_require_explicit_recovery(self):
        a=self.broker();a.credentials(self.body(a));a.pending['at']-=31;a.observe(page(disabled=True))
        self.assertEqual(a.status()['phase'],'stalled');self.assertTrue(a.status()['can_retry'])
        a.observe({'text':'Your session ended because there was no activity.'});self.assertEqual(a.status()['phase'],'session_expired')
    def test_validation_error_does_not_mark_authentication_complete(self):
        a=self.broker();a.credentials(self.body(a));a.observe(page(errors=['Incorrect password']))
        self.assertEqual(a.status()['phase'],'password_required');self.assertIn('did not accept',a.status()['error'])
        self.assertEqual(a.status()['stage'],1);self.assertFalse(a.auth_observed)
    def test_poll_cannot_overwrite_in_flight_submission(self):
        a=self.broker();before=a.status();a.operation.acquire()
        try:a.poll();self.assertEqual(a.status(),before)
        finally:a.operation.release()

if __name__=='__main__':unittest.main(verbosity=2)
