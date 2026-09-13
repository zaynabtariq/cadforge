import base64, gzip, hashlib, json, struct, threading, unittest
from fusion_connector import SceneStore, BridgeError
from fusion_connector.auth import AuthBroker, autodesk_url
from fusion_connector.remote_auth import RemoteAuthBroker, page_phase


class FakeBridge:
    def __init__(self):self.calls=0;self.wait=None;self.corrupt=False
    def call(self,*args,**kwargs):
        self.calls+=1
        if self.wait:self.wait.wait(2)
        raw=b'0'*80+struct.pack('<I',1)+struct.pack('<12fH',*([0.0]*12),0)
        digest=hashlib.sha256(raw).hexdigest()
        return {'epoch':'fusion-epoch','document_key':'document', 'state':{'body_instance_count':1},
            'geometry':{'sha256':'0'*64 if self.corrupt else digest,'raw_bytes':len(raw),'triangles':1,
                        'data_base64':base64.b64encode(gzip.compress(raw)).decode()}}


class Tests(unittest.TestCase):
    def test_idempotency_and_conflict(self):
        b=FakeBridge();s=SceneStore(b)
        first=s.capture(step_id='one',key='unique');first['state']['body_instance_count']=999
        second=s.capture(step_id='one',key='unique')
        self.assertEqual(b.calls,1);self.assertEqual(second['state']['body_instance_count'],1)
        with self.assertRaises(BridgeError):s.capture(step_id='two',key='unique')
    def test_capture_busy(self):
        b=FakeBridge();b.wait=threading.Event();s=SceneStore(b)
        worker=threading.Thread(target=s.capture);worker.start()
        while not b.calls:pass
        with self.assertRaises(BridgeError) as exc:s.capture()
        self.assertEqual(exc.exception.code,'busy');b.wait.set();worker.join()
    def test_integrity_failure_does_not_publish(self):
        b=FakeBridge();s=SceneStore(b);s.capture();b.corrupt=True
        with self.assertRaises(BridgeError):s.capture()
        self.assertEqual(s.latest()['version'],1)
    def test_reconnect_and_retention(self):
        s=SceneStore(FakeBridge(),capacity=2)
        for _ in range(4):s.capture()
        self.assertTrue(s.events(0,s.epoch)['resync_required'])
        self.assertTrue(s.events(4,'previous-process')['resync_required'])
        self.assertFalse(s.events(3,s.epoch)['resync_required'])
        self.assertEqual(len(s.assets),1)
        with self.assertRaises(BridgeError):s.events(-1,s.epoch)
    def test_auth_domains(self):
        for url in ('http://signin.autodesk.com','https://signin.autodesk.com.evil.test','https://evil.test','https://a@signin.autodesk.com'):
            self.assertFalse(autodesk_url(url))
        self.assertTrue(autodesk_url('https://signin.autodesk.com/id?state=123'))
    def test_callback_binding_and_replay(self):
        class VM:
            def __init__(self):self.calls=0
            def ssh(self,*args,**kwargs):self.calls+=1
        import time
        vm=VM();a=AuthBroker(vm)
        with self.assertRaises(ValueError):a.callback('adskidmgr://login?state=one')
        a.login_url='https://signin.autodesk.com/id?state=one';a.issued_at=time.monotonic()
        with self.assertRaises(ValueError):a.callback('adskidmgr://login?state=wrong')
        with self.assertRaises(ValueError):a.callback('file:///C:/Windows/notepad.exe')
        a.callback('adskidmgr://login?state=one');a.callback('adskidmgr://login?state=one')
        self.assertEqual(vm.calls,1)
        with self.assertRaises(ValueError):a.callback('adskidmgr://login?state=one&new=1')
    def test_remote_auth_phase_detection(self):
        self.assertEqual(page_phase({'inputs':[{'type':'password'}]}),'password_required')
        self.assertEqual(page_phase({'inputs':[{'type':'text','name':'email'}]}),'credentials_required')
        self.assertEqual(page_phase({'inputs':[{'type':'text','autocomplete':'one-time-code'}]}),'code_required')


if __name__=='__main__':unittest.main(verbosity=2)
