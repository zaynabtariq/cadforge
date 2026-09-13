#!/usr/bin/env python3
"""Local quote UI: HTTP commands + SSE snapshots + one browser worker per session."""
import argparse
import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlparse, parse_qs
import uuid

from quote import ROOT, TECHNOLOGIES, CATEGORIES
from web_adapter import JLCAdapter
from browserbase_capture import load_credentials

SESSIONS = {}
SESSIONS_LOCK = threading.Lock()
MAX_UPLOAD = 20 * 1024 * 1024
CATALOG_LOCK = threading.Lock()
CATALOG_FILE = ROOT / 'artifacts/material-catalog.json'


def record_catalog(observed, options):
    if not options.get('Material'):
        return
    with CATALOG_LOCK:
        try:
            catalog = json.loads(CATALOG_FILE.read_text())
        except (FileNotFoundError, ValueError):
            catalog = {}
        entry = catalog.setdefault(observed['technology'], {'colors': {}})
        entry.update(options=options, observed_at=now())
        if observed.get('material') and options.get('Color'):
            entry['colors'][observed['material']] = options['Color']
        CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CATALOG_FILE.write_text(json.dumps(catalog, indent=2) + '\n')


def read_catalog():
    with CATALOG_LOCK:
        try:
            return json.loads(CATALOG_FILE.read_text())
        except (FileNotFoundError, ValueError):
            return {}


class Superseded(Exception):
    pass


class Conflict(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_config(data):
    if not isinstance(data, dict):
        raise ValueError('Settings must be an object')
    config = {k: data.get(k) for k in ('technology', 'material', 'color', 'quantity', 'category', 'description')}
    if config['technology'] not in TECHNOLOGIES or config['category'] not in CATEGORIES:
        raise ValueError('Choose a supported process and product category')
    if type(config['quantity']) is not int or not 1 <= config['quantity'] <= 100000:
        raise ValueError('Quantity must be between 1 and 100000')
    for key in ('material', 'color'):
        if config[key] is not None and (not isinstance(config[key], str) or len(config[key]) > 100):
            raise ValueError(f'Invalid {key}')
    desc = config['description']
    if not isinstance(desc, str) or len(desc.encode('utf-16-le')) // 2 > 30:
        raise ValueError('Description must be at most 30 characters')
    config['description'] = desc.strip()
    return config


class QuoteSession:
    def __init__(self, session_id, file, adapter_factory=JLCAdapter, initial_description=''):
        self.id = session_id
        self.file = file
        self.directory = file.parent
        self.cv = threading.Condition(threading.RLock())
        self.pending = None
        self.closed = False
        self.bootstrapped = False
        self.commands = {}
        self.events = []
        self.adapter = adapter_factory(session_id, file)
        self.state = {
            'id': session_id, 'seq': 0, 'revision': 0, 'phase': 'starting', 'busy': True,
            'message': 'Preparing your quote', 'file': file.name, 'created_at': now(),
            'desired': {'technology': 'SLA', 'material': '9600 Resin', 'color': None, 'quantity': 1,
                        'category': 'blocks', 'description': initial_description},
            'observed': None, 'options': None, 'options_revision': None, 'quote': None,
            'warnings': [], 'error': None, 'history': [], 'closed': False,
            'bootstrapped': False,
        }
        self.thread = threading.Thread(target=self.work, name='quote-' + session_id, daemon=True)

    def start(self):
        self.thread.start()

    def snapshot(self):
        with self.cv:
            state = copy.deepcopy(self.state)
            if hasattr(self.adapter, 'browser_snapshot'):
                state['browser'] = self.adapter.browser_snapshot()
            return state

    def emit(self, revision, event, **patch):
        with self.cv:
            if revision != self.state['revision'] or self.closed:
                return False
            self.state.update(patch)
            self.state['seq'] += 1
            self.state['updated_at'] = now()
            self.state['event'] = event
            history = self.state['history']
            history.append({'event': event, 'revision': revision, 'time': now(), 'message': self.state['message']})
            self.state['history'] = history[-30:]
            snapshot = self.snapshot()
            self.events.append(snapshot)
            self.events = self.events[-200:]
            with (self.directory / 'events.jsonl').open('a') as f:
                f.write(json.dumps(snapshot) + '\n')
            (self.directory / 'state.json').write_text(json.dumps(snapshot, indent=2) + '\n')
            self.cv.notify_all()
            return True

    def checkpoint(self, revision):
        with self.cv:
            if self.closed or self.state['revision'] != revision:
                raise Superseded()

    def progress(self, revision, phase, message):
        self.checkpoint(revision)
        self.emit(revision, phase, phase=phase, message=message)

    def submit(self, command_id, expected_revision, action, config):
        if not isinstance(command_id, str) or not 1 <= len(command_id) <= 100:
            raise ValueError('A command ID is required')
        if action not in ('inspect', 'quote'):
            raise ValueError('Unknown action')
        config = validate_config(config)
        if action == 'quote' and not config['description']:
            raise ValueError('Enter a short, accurate description before requesting a quote')
        with self.cv:
            fingerprint = json.dumps([action, config], sort_keys=True)
            if command_id in self.commands:
                revision, original = self.commands[command_id]
                if original != fingerprint:
                    raise Conflict('Command ID was already used for different settings')
                return {'accepted_revision': revision, 'duplicate': True, 'state': self.snapshot()}
            if self.closed or (not self.bootstrapped and self.state['phase'] == 'error'):
                raise Conflict('Start a new session to continue')
            if type(expected_revision) is not int or expected_revision != self.state['revision']:
                raise Conflict('Settings changed in another request; refresh and try again')
            revision = self.state['revision'] + 1
            self.state['revision'] = revision
            self.commands[command_id] = (revision, fingerprint)
            # Only the latest pending intent is needed. The active command finishes
            # its current browser operation, then aborts at a checkpoint.
            self.pending = (revision, action, copy.deepcopy(config))
            self.emit(revision, 'accepted', phase='queued' if self.bootstrapped else self.state['phase'],
                      busy=True, desired=config, error=None, warnings=[],
                      message='Your latest settings are queued' if self.bootstrapped else
                      'Your choices are saved. I’m still preparing the model.')
            return {'accepted_revision': revision, 'duplicate': False, 'state': self.snapshot()}

    def work(self):
        try:
            self.emit(0, 'created')
            # Upload cannot be superseded by settings changes. Only closing the
            # session cancels it; early commands coalesce while bootstrap runs.
            def bootstrap_checkpoint():
                with self.cv:
                    if self.closed:
                        raise Superseded()

            def bootstrap_progress(phase, message):
                bootstrap_checkpoint()
                with self.cv:
                    self.emit(self.state['revision'], phase, phase=phase, message=message)

            quote = self.adapter.bootstrap(bootstrap_progress, bootstrap_checkpoint)
            quote.update(revision=0, quoted_at=now())
            options = getattr(self.adapter, 'initial_options', {})
            observed = {**self.state['desired'], **quote['config'], 'description': '', 'category': 'blocks'}
            record_catalog(observed, options)
            with self.cv:
                bootstrap_checkpoint()
                self.bootstrapped = True
                revision = self.state['revision']
                self.emit(revision, 'initial_estimate', quote=quote, options=options, options_revision=0,
                          observed=observed, bootstrapped=True,
                          phase='queued' if self.pending else 'ready', busy=bool(self.pending),
                          message='Your model is ready. I’m checking your choices.' if self.pending else
                          'Your model is ready. Choose a material to continue.')
            while True:
                with self.cv:
                    if not self.cv.wait_for(lambda: self.pending is not None or self.closed, timeout=900):
                        self.close('Session expired after 15 minutes without a submitted change')
                    if self.closed:
                        break
                    revision, action, config = self.pending
                    self.pending = None
                try:
                    check = lambda: self.checkpoint(revision)
                    progress = lambda p, m: self.progress(revision, p, m)
                    check()
                    info = self.adapter.inspect(config, progress, check)
                    check()
                    record_catalog(info['observed'], info['options'])
                    self.emit(revision, 'options_ready', options=info['options'], options_revision=revision,
                              observed=info['observed'], warnings=info['warnings'])
                    if info['warnings']:
                        self.emit(revision, 'incompatible', phase='blocked', busy=False,
                                  error='Choose a different material or change the model dimensions',
                                  message='These settings are incompatible with this model')
                        continue
                    if action == 'inspect':
                        self.emit(revision, 'selection_ready', phase='ready', busy=False,
                                  message='Options are ready. Update the quote when you’re ready.')
                        continue
                    config = info['observed']
                    quote = self.adapter.save_quote(config, progress, check)
                    quote.update(revision=revision, quoted_at=now())
                    self.emit(revision, 'manufacturing_quote', quote=quote, message='Manufacturing price confirmed')
                    quote = self.adapter.shipping(config, progress, check)
                    quote.update(revision=revision, quoted_at=now())
                    self.emit(revision, 'quote_ready', quote=quote, phase='ready', busy=False, error=None,
                              message='Your estimate is up to date')
                except Superseded:
                    continue
                except Exception as exc:
                    self.emit(revision, 'error', phase='error', busy=False, error=str(exc),
                              message='This update needs attention. Adjust your settings and try again.')
        except Superseded:
            pass
        except Exception as exc:
            self.emit(self.snapshot()['revision'], 'error', phase='error', busy=False, error=str(exc),
                      message='Could not prepare the model. Start a new session to retry.')
        finally:
            try:
                self.adapter.close()
            except Exception:
                pass

    def close(self, message='Session closed'):
        with self.cv:
            if self.closed:
                return
            self.emit(self.state['revision'], 'closed', phase='closed', busy=False, closed=True, message=message)
            self.closed = True
            self.cv.notify_all()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, format, *args):
        if '/events' not in str(args):
            super().log_message(format, *args)

    def send_bytes(self, code, body, content_type='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def respond(self, code, data):
        self.send_bytes(code, json.dumps(data).encode())

    def read_body(self, limit=MAX_UPLOAD):
        length = int(self.headers.get('Content-Length', 0))
        if length < 0 or length > limit:
            raise ValueError('Upload limit is 20 MB')
        return self.rfile.read(length)

    def session(self, session_id):
        with SESSIONS_LOCK:
            return SESSIONS.get(session_id)

    def same_origin(self):
        host = self.headers.get('Host', '')
        return host in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}') and (
            not self.headers.get('Origin') or self.headers['Origin'] == 'http://' + host)

    def do_GET(self):
        path = urlparse(self.path).path
        if not self.same_origin():
            return self.respond(403, {'error': 'Local access only'})
        if path in ('/', '/theme'):
            page = 'index.html' if path == '/' else 'theme.html'
            return self.send_bytes(200, (ROOT / 'web' / page).read_bytes(), 'text/html; charset=utf-8')
        if path in ('/app.js', '/style.css', '/theme.css', '/theme-preview.css', '/theme-preview.js', '/viewer.js', '/step-worker.js'):
            return self.send_bytes(200, (ROOT / 'web' / path[1:]).read_bytes(),
                                   'text/javascript' if path.endswith('.js') else 'text/css')
        if path == '/api/health':
            return self.respond(200, {'ok': True, 'browser': os.environ.get('QUOTE_BROWSER', 'local')})
        if path == '/api/catalog':
            return self.respond(200, {'technologies': read_catalog(), 'provisional': True})
        if path == '/fixtures/cube-20mm.stl':
            return self.send_bytes(200, (ROOT / 'fixtures/cube-20mm.stl').read_bytes(), 'application/octet-stream')
        # Serve only the viewer packages, with containment checks on resolved paths.
        for prefix, relative in (('/vendor/three/', 'node_modules/three'),
                                 ('/vendor/occt/', 'node_modules/occt-import-js/dist')):
            if path.startswith(prefix):
                base = (ROOT / relative).resolve()
                target = (base / path[len(prefix):]).resolve()
                if not target.is_relative_to(base) or not target.is_file():
                    return self.respond(404, {'error': 'Viewer asset not found; run npm ci'})
                return self.send_bytes(200, target.read_bytes(),
                                       'application/wasm' if target.suffix == '.wasm' else
                                       mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        recording = re.fullmatch(r'/api/sessions/([a-f0-9]+)/recording/([A-Za-z0-9_-]+)\.mp4', path)
        if recording:
            target = ROOT / 'artifacts/web' / recording[1] / 'recording' / (recording[2] + '.mp4')
            if not target.is_file():
                return self.respond(404, {'error': 'Recording is not ready'})
            return self.send_video(target)
        match = re.fullmatch(r'/api/sessions/([a-f0-9]+)(/events|/model|/browser)?', path)
        session = self.session(match[1]) if match else None
        if not session:
            return self.respond(404, {'error': 'Session not found; start a new quote'})
        if not match[2]:
            return self.respond(200, session.snapshot())
        if match[2] == '/browser':
            return self.respond(200, session.adapter.browser_snapshot())
        if match[2] == '/model':
            return self.send_bytes(200, session.file.read_bytes(), 'application/octet-stream')
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
        try:
            last = int(self.headers.get('Last-Event-ID', '-1'))
        except ValueError:
            last = -1
        try:
            while True:
                with session.cv:
                    session.cv.wait_for(lambda: session.state['seq'] > last or session.closed, timeout=10)
                    # Full state snapshots make reconnect safe even after old events expire.
                    state = session.snapshot()
                if state['seq'] > last:
                    self.wfile.write(f'id: {state["seq"]}\nevent: state\ndata: {json.dumps(state)}\n\n'.encode())
                    last = state['seq']
                else:
                    self.wfile.write(b': heartbeat\n\n')
                self.wfile.flush()
                if state['closed']:
                    return
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def do_POST(self):
        if not self.same_origin():
            self.close_connection = True
            return self.respond(403, {'error': 'Local access only'})
        path = urlparse(self.path).path
        try:
            if path in ('/api/sessions', '/api/sessions/demo'):
                demo = path.endswith('/demo')
                raw = self.read_body()
                filename = 'cube-20mm.stl' if demo else parse_qs(urlparse(self.path).query).get('filename', [''])[0]
                filename = Path(filename.replace('\\', '/')).name
                if not filename or Path(filename).suffix.lower() not in ('.stl', '.step', '.stp', '.obj', '.3mf'):
                    raise ValueError('Choose an STL, STEP, OBJ, or 3MF file')
                if demo:
                    raw = (ROOT / 'fixtures/cube-20mm.stl').read_bytes()
                if not raw:
                    raise ValueError('The model file is empty')
                with SESSIONS_LOCK:
                    if sum(not s.closed for s in SESSIONS.values()) >= 4:
                        return self.respond(429, {'error': 'Close an existing session before starting another'})
                    session_id = uuid.uuid4().hex[:16]
                    directory = ROOT / 'artifacts/web' / session_id
                    directory.mkdir(parents=True)
                    # Store uploads separately from state files, retaining the original model name.
                    upload_dir = directory / 'uploads'
                    upload_dir.mkdir()
                    file = upload_dir / filename
                    file.write_bytes(raw)
                    session = QuoteSession(session_id, file, initial_description='20 mm resin test cube' if demo else '')
                    session.directory = directory
                    SESSIONS[session_id] = session
                    session.start()
                return self.respond(202, session.snapshot())
            match = re.fullmatch(r'/api/sessions/([a-f0-9]+)/commands', path)
            session = self.session(match[1]) if match else None
            if not session:
                self.read_body(65536)
                return self.respond(404, {'error': 'Session not found'})
            data = json.loads(self.read_body(65536))
            result = session.submit(data.get('command_id'), data.get('expected_revision'),
                                    data.get('action'), data.get('config'))
            return self.respond(202, result)
        except Conflict as exc:
            return self.respond(409, {'error': str(exc), 'state': session.snapshot()})
        except (ValueError, TypeError, AttributeError) as exc:
            self.close_connection = True
            return self.respond(400, {'error': str(exc)})

    def do_DELETE(self):
        if not self.same_origin():
            return self.respond(403, {'error': 'Local access only'})
        match = re.fullmatch(r'/api/sessions/([a-f0-9]+)', urlparse(self.path).path)
        session = self.session(match[1]) if match else None
        if not session:
            return self.respond(404, {'error': 'Session not found'})
        session.close()
        return self.respond(200, session.snapshot())

    def send_video(self, path):
        size = path.stat().st_size
        start, end, code = 0, size - 1, 200
        requested = self.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match or not any(match.groups()):
                return self.respond(416, {'error': 'Invalid byte range'})
            start = int(match[1]) if match[1] else max(0, size - int(match[2]))
            end = min(size - 1, int(match[2])) if match[1] and match[2] else size - 1
            if start > end or start >= size:
                return self.respond(416, {'error': 'Byte range unavailable'})
            code = 206
        self.send_response(code)
        self.send_header('Content-Type', 'video/mp4')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Cache-Control', 'no-store')
        if code == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with path.open('rb') as video:
                video.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = video.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--browserbase', action='store_true', help='Record provider browsers in Browserbase')
    parser.add_argument('--browserbase-env', help='Read only Browserbase credentials from this env file')
    args = parser.parse_args()
    if args.browserbase_env:
        load_credentials(args.browserbase_env)
    if args.browserbase:
        if not os.environ.get('BROWSERBASE_API_KEY'):
            parser.error('Set BROWSERBASE_API_KEY or pass --browserbase-env')
        os.environ['QUOTE_BROWSER'] = 'browserbase'
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Quote UI: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for session in list(SESSIONS.values()):
            session.close('Server stopped')
        server.server_close()
