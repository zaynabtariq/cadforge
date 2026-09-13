"""Regression tests for the failure modes that can duplicate or cross-wire CAD work."""
import concurrent.futures,http.client,importlib.util,json,socket,threading,time,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('transport',Path(__file__).with_name('vm_transport.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class DispatchTests(unittest.TestCase):
 def test_timeout_does_not_allow_overlapping_mutations(self):
  started=threading.Event();release=threading.Event();calls=[]
  def mutate(body):started.set();release.wait(2);calls.append(body);return {'ok':True}
  d=m.Dispatcher(lambda jid:True,{'/mutate':mutate})
  a=d.submit('/mutate',{'a':1},'first');worker=threading.Thread(target=d.execute,args=(a['id'],));worker.start();self.assertTrue(started.wait(1))
  self.assertEqual(d.response(a,.01)[0],202)
  with self.assertRaises(m.Rejected) as conflict:d.submit('/mutate',{'a':2})
  self.assertEqual(conflict.exception.body['code'],'busy')
  self.assertIs(d.submit('/mutate',{'a':1},'first'),a)
  release.set();worker.join();self.assertEqual(calls,[{'a':1}]);self.assertEqual(d.response(a,0)[1],{'ok':True})
 def test_expired_event_cannot_execute_a_later_request(self):
  calls=[];d=m.Dispatcher(lambda jid:True,{'/mutate':lambda b:calls.append(b)},queue_timeout=.01)
  a=d.submit('/mutate',{'a':1});time.sleep(.02);self.assertEqual(d.response(a,0)[1]['code'],'queue_expired')
  b=d.submit('/mutate',{'a':2});d.execute(a['id']);d.execute(b['id']);self.assertEqual(calls,[{'a':2}])
 def test_duplicate_key_conflict_and_handler_failure(self):
  d=m.Dispatcher(lambda jid:True,{'/x':lambda b:1/0});a=d.submit('/x',{},'same');d.execute(a['id'])
  self.assertEqual(d.inspect(a['id'])['state'],'failed');self.assertIs(d.submit('/x',{},'same'),a)
  with self.assertRaises(m.Rejected):d.submit('/x',{'different':1},'same')
 def test_shutdown_cancels_queued_work(self):
  calls=[];d=m.Dispatcher(lambda jid:True,{'/x':lambda b:calls.append(b)});a=d.submit('/x',{});d.stop();d.execute(a['id']);self.assertFalse(calls)
  with self.assertRaises(m.Rejected):d.submit('/x',{})
 def test_concurrent_submissions_accept_only_one(self):
  d=m.Dispatcher(lambda jid:True,{'/x':lambda b:b})
  def submit(i):
   try:return d.submit('/x',{'i':i})['id']
   except m.Rejected:return None
  with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:results=list(pool.map(submit,range(32)))
  self.assertEqual(sum(x is not None for x in results),1)

class HTTPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.calls=[]
  cls.d=m.Dispatcher(lambda jid: threading.Thread(target=cls.d.execute,args=(jid,)).start() or True,{'/echo':lambda b:cls.calls.append(b) or b,'/__ready':lambda b:{'ready':True}})
  cls.server=m.BoundedServer(('127.0.0.1',0),m.Handler,cls.d)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.port=cls.server.server_port
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
 def request(self,body='{}',headers=None,path='/echo',method='POST'):
  conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=2)
  try:
   conn.request(method,path,body=body,headers=headers if headers is not None else {'Content-Type':'application/json'})
   r=conn.getresponse();return r.status,json.loads(r.read()),dict(r.getheaders())
  finally:conn.close()
 def test_malformed_and_browser_input_rejected(self):
  before=len(self.calls)
  for body,headers,code in [('{',{'Content-Type':'application/json'},400),('[]',{'Content-Type':'application/json'},400),('{"n":NaN}',{'Content-Type':'application/json'},400),('{}',{'Content-Type':'text/plain'},415),('{}',{'Content-Type':'application/json','Origin':'https://evil.example'},403),('{}',{'Content-Type':'application/json','Host':'evil.example'},403),('{}',{'Content-Type':'application/json','Content-Length':str(m.MAX_BODY+1)},413)]:
   with self.subTest(body=body,headers=headers):self.assertEqual(self.request(body,headers)[0],code)
  self.assertEqual(before,len(self.calls))
 def test_duplicate_submission_returns_same_id_and_runs_once(self):
  before=len(self.calls);headers={'Content-Type':'application/json','Idempotency-Key':'http-test'}
  a=self.request('{"hello":1}',headers);b=self.request('{"hello":1}',headers)
  self.assertEqual(a[0],200);self.assertEqual(a[2]['X-Request-ID'],b[2]['X-Request-ID']);self.assertEqual(len(self.calls)-before,1)
  status,job,_=self.request('',{},'/requests/'+a[2]['X-Request-ID'],'GET');self.assertEqual(job['result'],{'hello':1})
 def test_health_and_ready(self):
  self.assertEqual(self.request('',{},'/health','GET')[1]['status'],'listening')
  self.assertTrue(self.request('',{},'/ready','GET')[1]['ready'])
 def test_slow_client_does_not_block_health(self):
  sock=socket.create_connection(('127.0.0.1',self.port))
  try:
   sock.sendall(b'POST /echo HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{')
   self.assertEqual(self.request('',{},'/health','GET')[0],200)
  finally:sock.close()

if __name__=='__main__':unittest.main(verbosity=2)
