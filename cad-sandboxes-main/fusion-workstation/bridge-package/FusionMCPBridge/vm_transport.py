"""Bounded loopback HTTP transport; all Fusion access stays on its main thread."""
import collections
import hashlib
import json
import logging
import logging.handlers
import re
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 2 * 1024 * 1024
MAX_RESULT = 8 * 1024 * 1024
EVENT_ID = 'FusionMCPCommandEvent'

class Rejected(Exception):
    def __init__(self, status, code, message, **extra):
        self.status = status
        self.body = dict(error=True, code=code, message=message, **extra)
        super().__init__(message)

class Dispatcher:
    def __init__(self, fire, routes, logger=None, queue_timeout=10, retention=600, history=32):
        self.fire, self.routes = fire, routes
        self.logger = logger or (lambda data: None)
        self.queue_timeout, self.retention, self.history = queue_timeout, retention, history
        self.lock = threading.Lock()
        self.jobs = collections.OrderedDict()
        self.keys = {}
        self.active = None
        self.session_id = str(uuid.uuid4())
        self.started = time.monotonic()
        self.stopping = False

    def _remove(self, job_id):
        job = self.jobs.pop(job_id)
        if job['key']:
            self.keys.pop(job['key'], None)

    def _prune(self):
        now = time.monotonic()
        for jid, job in list(self.jobs.items()):
            if jid != self.active and (now-job['created'] > self.retention or len(self.jobs) >= self.history):
                self._remove(jid)

    def _complete(self, job, state, result):
        job['state'], job['result'] = state, result
        job['finished'] = time.monotonic()
        job['body'] = None
        if self.active == job['id']:
            self.active = None
        job['done'].set()
        self.logger({'request_id':job['id'],'route':job['route'],'state':state,
                     'duration_ms':round((job['finished']-job['created'])*1000,1)})

    def submit(self, route, body, key=None):
        if route not in self.routes:
            raise Rejected(404, 'unknown_route', 'Unknown route')
        digest = hashlib.sha256((route+'\n'+json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False)).encode()).hexdigest()
        with self.lock:
            self._prune()
            if self.stopping:
                raise Rejected(503, 'stopping', 'Bridge is stopping')
            if key and key in self.keys:
                job = self.jobs[self.keys[key]]
                if job['digest'] != digest:
                    raise Rejected(409,'idempotency_conflict','Idempotency key was used with a different command')
                return job
            if self.active:
                active = self.jobs[self.active]
                if active['state']=='queued' and time.monotonic()-active['created'] > self.queue_timeout:
                    self._complete(active,'cancelled',dict(error=True,code='queue_expired',message='Command expired before execution; it will not run'))
                else:
                    raise Rejected(409,'busy','Another command is still queued or running',request_id=self.active)
            jid = str(uuid.uuid4())
            job = dict(id=jid,key=key,digest=digest,route=route,body=body,state='queued',
                       created=time.monotonic(),done=threading.Event(),result=None)
            self.jobs[jid] = job
            if key:self.keys[key] = jid
            self.active = jid
        try:
            if self.fire(jid) is False:
                raise RuntimeError('Fusion did not accept the custom event')
        except Exception as exc:
            self.logger({'request_id':jid,'route':route,'dispatch_exception':str(exc)})
            with self.lock:
                if job['state']=='queued':
                    self._complete(job,'failed',dict(error=True,code='dispatch_failed',message='Unable to queue command in Fusion'))
        return job

    def execute(self, jid):
        # Called ONLY by Fusion's custom event handler, or by test main-thread simulation.
        with self.lock:
            job = self.jobs.get(jid)
            if not job or job['state']!='queued':return
            if self.stopping or time.monotonic()-job['created'] > self.queue_timeout:
                self._complete(job,'cancelled',dict(error=True,code='queue_expired',message='Command expired before execution; it will not run'))
                return
            job['state']='running'
        try:
            result = self.routes[job['route']](job['body'])
            encoded = json.dumps(result,allow_nan=False).encode()
            if len(encoded)>MAX_RESULT:
                result=dict(error=True,code='result_too_large',message='Operation completed, but result exceeded 8 MiB; inspect state before retrying')
            state = 'completed'
        except Exception as exc:
            result=dict(error=True,code='handler_error',message=str(exc))
            state='failed'
        with self.lock:
            self._complete(job,state,result)

    def response(self, job, wait=30):
        job['done'].wait(wait)
        with self.lock:
            if job['state']=='queued' and time.monotonic()-job['created'] > self.queue_timeout:
                self._complete(job,'cancelled',dict(error=True,code='queue_expired',message='Command expired before execution; it will not run'))
            if job['done'].is_set():return 200,job['result']
            return 202,dict(error=True,code='pending',message='Command is still running; poll its request ID instead of resubmitting',request_id=job['id'],session_id=self.session_id)

    def inspect(self, jid):
        with self.lock:
            job = self.jobs.get(jid)
            if not job:raise Rejected(404,'unknown_request','Request not retained in this bridge process')
            result=dict(request_id=jid,state=job['state'],route=job['route'],session_id=self.session_id)
            if job['done'].is_set():result['result']=job['result']
            return result

    def health(self):
        with self.lock:
            active=self.jobs.get(self.active)
            return dict(status='stopping' if self.stopping else 'listening',session_id=self.session_id,
                        uptime_seconds=round(time.monotonic()-self.started,3),
                        active_request=None if not active else dict(request_id=active['id'],route=active['route'],state=active['state'],age_seconds=round(time.monotonic()-active['created'],3)))

    def stop(self):
        with self.lock:
            self.stopping=True
            if self.active:
                job=self.jobs[self.active]
                if job['state']=='queued':
                    self._complete(job,'cancelled',dict(error=True,code='stopping',message='Bridge stopped before command execution'))

class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8
    def __init__(self,address,handler,dispatcher):
        self.dispatcher=dispatcher
        self.slots=threading.BoundedSemaphore(8)
        super().__init__(address,handler)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()
    def handle_error(self,request,address):pass

class Handler(BaseHTTPRequestHandler):
    server_version='FusionBridge/1'
    sys_version=''
    def setup(self):
        self.request.settimeout(5)
        super().setup()
    def log_message(self,*args):pass
    def reply(self,status,data,jid=None):
        payload=json.dumps(data,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Connection','close')
        self.send_header('X-Bridge-Session',self.server.dispatcher.session_id)
        if jid:self.send_header('X-Request-ID',jid)
        self.end_headers()
        try:self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError,socket.timeout):pass
        self.close_connection=True
    def guard(self):
        host=self.headers.get('Host','').lower()
        if not re.fullmatch(r'(localhost|127\.0\.0\.1)(:\d{1,5})?',host):
            raise Rejected(403,'invalid_host','Only loopback Host headers are accepted')
        if 'Origin' in self.headers or self.headers.get('Sec-Fetch-Site') not in (None,'none'):
            raise Rejected(403,'browser_request','Browser-origin requests are not accepted')
        if self.headers.get('Transfer-Encoding'):
            raise Rejected(400,'unsupported_encoding','Transfer-Encoding is not supported')
        if not re.fullmatch(r'/[A-Za-z0-9_/-]*',self.path):
            raise Rejected(400,'invalid_path','Use a plain route path without query or fragment')
    def do_GET(self):
        try:
            self.guard();d=self.server.dispatcher
            if self.path=='/health':self.reply(200,d.health())
            elif self.path=='/ready':
                job=d.submit('/__ready',{})
                status,result=d.response(job,3)
                self.reply(200 if status==200 and not result.get('error') else 503,result,job['id'])
            elif self.path.startswith('/requests/'):
                self.reply(200,d.inspect(self.path.removeprefix('/requests/')))
            else:raise Rejected(404,'unknown_route','Unknown route')
        except Rejected as exc:self.reply(exc.status,exc.body)
    def do_POST(self):
        try:
            self.guard()
            if self.path=='/__ready':raise Rejected(404,'unknown_route','Use GET /ready')
            if self.headers.get_content_type()!='application/json':
                raise Rejected(415,'content_type','Content-Type must be application/json')
            lengths=self.headers.get_all('Content-Length',[])
            if len(lengths)!=1 or not re.fullmatch(r'\d+',lengths[0]):
                raise Rejected(400,'content_length','One non-negative Content-Length is required')
            length=int(lengths[0])
            if length>MAX_BODY:raise Rejected(413,'body_too_large','Maximum request size is 2 MiB')
            try:
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError()
                body=json.loads(raw,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite number')))
                if not isinstance(body,dict):raise ValueError()
            except (ValueError,UnicodeError,RecursionError):raise Rejected(400,'invalid_json','Request body must be a finite JSON object')
            key=self.headers.get('Idempotency-Key')
            if key is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',key):
                raise Rejected(400,'invalid_key','Invalid Idempotency-Key')
            job=self.server.dispatcher.submit(self.path,body,key)
            status,result=self.server.dispatcher.response(job)
            self.reply(status,result,job['id'])
        except Rejected as exc:self.reply(exc.status,exc.body)
        except (socket.timeout,TimeoutError):self.reply(408,dict(error=True,code='read_timeout',message='Request body timed out'))
        except (ValueError,RecursionError):self.reply(400,dict(error=True,code='invalid_json',message='Invalid JSON object'))


def make_logger(path):
    logger=logging.getLogger('fusion-workstation-requests')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler=logging.handlers.RotatingFileHandler(path,maxBytes=1024*1024,backupCount=2,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        logger.addHandler(handler)
    return lambda record: logger.info(json.dumps(record,separators=(',',':')))
