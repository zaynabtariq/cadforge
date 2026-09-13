#!/usr/bin/env python3
"""Local owner API + terminal-browser authentication wrapper."""
import argparse, hashlib, http.server, json, mimetypes, os, re, secrets, signal
import threading, urllib.parse
from pathlib import Path
from fusion_connector import BridgeClient, BridgeError, SceneStore
from fusion_connector.remote_auth import RemoteAuthBroker as AuthBroker
from fusion_connector.vm import VM

ROOT=Path(__file__).resolve().parent


def serve(port,endpoint):
    token=secrets.token_urlsafe(32)
    runtime=ROOT/'private'/'connector-runtime.json'
    runtime.parent.mkdir(mode=0o700,exist_ok=True)
    if runtime.exists():
        previous=urllib.parse.urlsplit(json.loads(runtime.read_text())['url'])
        if previous.hostname=='127.0.0.1' and previous.port==port:
            candidate=previous.path.strip('/')
            if re.fullmatch('[A-Za-z0-9_-]{32,64}',candidate):token=candidate
    prefix='/'+token
    scene=SceneStore(BridgeClient(endpoint))
    auth=AuthBroker(VM(ROOT/'auth-vm.json',ROOT/'auth-ssh_config'))
    scenes={'primary':scene}
    class Handler(http.server.BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(15)
        def log_message(self,*args):pass
        def send(self,status,data,mime='application/json',headers=None):
            if not isinstance(data,bytes):data=json.dumps(data).encode()
            self.send_response(status);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            for key,value in (headers or {}).items():self.send_header(key,value)
            self.end_headers();self.wfile.write(data)
        def guard(self,write=False):
            if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':
                raise BridgeError('forbidden','Invalid host',403)
            route=urllib.parse.urlsplit(self.path)
            if not route.path.startswith(prefix+'/'):raise BridgeError('not_found','Not found',404)
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':
                raise BridgeError('forbidden','Cross-origin requests are not allowed',403)
            if write and self.headers.get('X-Connector-Request')!='1':raise BridgeError('forbidden','Missing request header',403)
            return route.path[len(prefix):],urllib.parse.parse_qs(route.query)
        def body(self):
            lengths=self.headers.get_all('Content-Length') or []
            if len(lengths)!=1 or not lengths[0].isdigit() or self.headers.get('Transfer-Encoding'):
                raise BridgeError('invalid_body','Content-Length is required',400)
            size=int(lengths[0])
            if not 0<size<=20000:raise BridgeError('invalid_body','Request size exceeds limit',413)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise BridgeError('invalid_body','JSON required',415)
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise BridgeError('invalid_body','JSON object required',400)
            return data
        def frame(self,value):
            if not value:return None
            result=dict(value);result['asset_url']=prefix+'/v1/workstations/'+getattr(self,'workstation','primary')+'/assets/'+value['geometry']['sha256']+'.stl.gz'
            return result
        def target(self,route):
            self.workstation='primary'
            match=re.match(r'^/v1/workstations/(primary|fresh)(/.*)$',route)
            if match:
                self.workstation=match[1];route='/v1'+match[2]
            if self.workstation=='fresh' and 'fresh' not in scenes:
                if not auth.bridge or not auth.status().get('verified'):
                    raise BridgeError('authentication_required','Complete Autodesk sign-in first',409)
                scenes['fresh']=SceneStore(auth.bridge)
            return route,scenes[self.workstation]
        def do_GET(self):
            try:
                route,query=self.guard()
                route,target=self.target(route)
                if route=='/v1/health':self.send(200,{'api_version':'1.0','connector_epoch':scene.epoch})
                elif route=='/v1/scene':self.send(200,{'scene':self.frame(target.latest())})
                elif route=='/v1/events':self.send(200,target.events(int(query.get('after',['0'])[0]),query.get('epoch',[None])[0]))
                elif re.fullmatch('/v1/assets/[a-f0-9]{64}\\.stl\\.gz',route):
                    digest=route.split('/')[-1].split('.')[0]
                    self.send(200,target.asset(digest),'application/gzip',{'ETag':'"'+digest+'"'})
                elif route=='/v1/auth':self.send(200,auth.status())
                elif route=='/':self.send(200,(ROOT/'connector-ui'/'index.html').read_bytes(),'text/html; charset=utf-8')
                elif route=='/theme.css':self.send(200,(ROOT.parent/'click-to-ship'/'web'/'theme.css').read_bytes(),'text/css')
                elif route in ('/app.js','/style.css','/viewer.js'):
                    self.send(200,(ROOT/'connector-ui'/route[1:]).read_bytes(), 'text/javascript' if route.endswith('.js') else 'text/css')
                elif route=='/viewer':self.send(200,(ROOT/'connector-ui'/'viewer.html').read_bytes(),'text/html; charset=utf-8')
                elif route.startswith('/vendor/') and route[8:] in ('three.module.js','three.core.js','STLLoader.js','OrbitControls.js'):
                    self.send(200,(ROOT/'vendor'/route[8:]).read_bytes(),'text/javascript')
                else:raise BridgeError('not_found','Not found',404)
            except BridgeError as exc:self.send(exc.status,{'error':{'code':exc.code,'message':str(exc)}})
            except (ValueError,KeyError):self.send(400,{'error':{'code':'invalid_request','message':'Invalid request'}})
            except Exception:self.send(502,{'error':{'code':'unavailable','message':'Connector operation failed'}})
        def do_POST(self):
            try:
                route,_=self.guard(write=True);route,target=self.target(route);body=self.body()
                if route=='/v1/captures':
                    frame=target.capture(quality=body.get('quality','medium'),step_id=body.get('step_id'),key=self.headers.get('Idempotency-Key'))
                    self.send(201,{'scene':self.frame(frame)})
                elif route=='/v1/auth/start':self.send(202,auth.start())
                elif route=='/v1/auth/retry':self.send(202,auth.retry())
                elif route=='/v1/auth/credentials':self.send(202,auth.credentials(body))
                else:raise BridgeError('not_found','Not found',404)
            except BridgeError as exc:self.send(exc.status,{'error':{'code':exc.code,'message':str(exc)}})
            except (ValueError,KeyError):self.send(400,{'error':{'code':'invalid_request','message':'Invalid request'}})
            except Exception:self.send(502,{'error':{'code':'unavailable','message':'Connector operation failed'}})
    class Server(http.server.ThreadingHTTPServer):
        daemon_threads=True
        def __init__(self,*args):super().__init__(*args);self.slots=threading.BoundedSemaphore(16)
        def process_request(self,request,address):
            if not self.slots.acquire(blocking=False):request.close();return
            try:super().process_request(request,address)
            except Exception:self.slots.release();raise
        def process_request_thread(self,*args):
            try:super().process_request_thread(*args)
            finally:self.slots.release()
    server=Server(('127.0.0.1',port),Handler)
    url=f'http://127.0.0.1:{server.server_port}{prefix}/'
    runtime.write_text(json.dumps({'url':url,'pid':os.getpid(),'api_version':'1.0'}));runtime.chmod(0o600)
    # Main-process hook configuration contains a local capability, never an Autodesk credential.
    hook=(ROOT/'terminal-auth-main.cjs').read_text().replace('__CONNECTOR_URL_JSON__',json.dumps(url))
    path=ROOT/'private'/'terminal-auth-main.cjs';path.write_text(hook);path.chmod(0o600)
    print('Connector ready; local URL stored in private/connector-runtime.json',flush=True)
    try:server.serve_forever()
    finally:auth.close();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18766)
    parser.add_argument('--bridge',default='http://127.0.0.1:18080');args=parser.parse_args()
    serve(args.port,args.bridge)
