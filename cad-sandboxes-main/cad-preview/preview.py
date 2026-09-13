#!/usr/bin/env python3
"""Watch one local STL and open an interactive terminal-browser preview."""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT.parent / 'click-to-ship/node_modules/three'
VENDOR_FILES = {
    'three.module.js': 'build/three.module.js',
    'three.core.js': 'build/three.core.js',
    'STLLoader.js': 'examples/jsm/loaders/STLLoader.js',
    'OrbitControls.js': 'examples/jsm/controls/OrbitControls.js',
}
RUNTIME = ROOT / '.runtime'
MAX_SIZE = 32 * 1024 * 1024


def request(url):
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.load(response)


def serve(path, registry):
    token = secrets.token_urlsafe(24)
    lock = threading.Lock()
    state = {'revision': '', 'name': path.name, 'error': 'Waiting for STL', 'bytes': 0}
    content = b''

    def watch():
        nonlocal content
        last = None
        while True:
            try:
                stat = path.stat()
                signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
                if signature != last:
                    if not 0 < stat.st_size <= MAX_SIZE:
                        raise ValueError('STL must be between 1 byte and 32 MiB')
                    time.sleep(.2)
                    with path.open('rb') as source:
                        raw = source.read(MAX_SIZE + 1)
                    if len(raw) > MAX_SIZE:
                        raise ValueError('STL exceeds 32 MiB')
                    after = path.stat()
                    if signature != (after.st_ino, after.st_size, after.st_mtime_ns):
                        continue
                    binary = len(raw) >= 84 and len(raw) == 84 + 50 * struct.unpack_from('<I', raw, 80)[0]
                    ascii_stl = raw.lstrip().startswith(b'solid') and b'endsolid' in raw and raw.count(b'vertex') >= 3 and raw.count(b'vertex') % 3 == 0
                    if not binary and not ascii_stl:
                        raise ValueError('Waiting for a complete STL export')
                    digest = hashlib.sha256(raw).hexdigest()
                    with lock:
                        content = raw
                        state.update(revision=digest, bytes=len(raw), error='')
                    last = signature
            except (OSError, ValueError) as exc:
                with lock:
                    state['error'] = str(exc)
            time.sleep(.3)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                self.send_error(403)
                return
            route = urllib.parse.urlsplit(self.path)
            prefix = '/' + token + '/'
            if not route.path.startswith(prefix):
                self.send_error(404)
                return
            name = route.path[len(prefix):]
            mime = 'application/json'
            with lock:
                if name == 'state':
                    data = json.dumps(state).encode()
                elif name == 'model':
                    if urllib.parse.parse_qs(route.query).get('revision', [''])[0] != state['revision']:
                        self.send_error(409)
                        return
                    data, mime = content, 'application/octet-stream'
                elif name == 'shutdown':
                    data = b'{"stopped":true}'
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                elif name == '':
                    data, mime = (ROOT / 'viewer.html').read_bytes(), 'text/html'
                elif name.startswith('vendor/') and name[7:] in VENDOR_FILES:
                    data, mime = (VENDOR / VENDOR_FILES[name[7:]]).read_bytes(), 'text/javascript'
                else:
                    self.send_error(404)
                    return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(data)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/{token}/'
    temporary = registry.with_suffix('.tmp')
    temporary.write_text(json.dumps({'url': url, 'file': str(path), 'pid': os.getpid()}))
    temporary.replace(registry)
    threading.Thread(target=watch, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        registry.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--watch', action='store_true', help='Watch for changes (always enabled)')
    parser.add_argument('--split', choices=['right', 'left', 'down', 'up'])
    parser.add_argument('--no-open', action='store_true', help='Start server and print URL only')
    parser.add_argument('--stop', action='store_true', help='Stop the server for this file')
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    path = args.file.expanduser().resolve()
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    registry = RUNTIME / (hashlib.sha256(str(path).encode()).hexdigest()[:20] + '.json')
    if args.serve:
        serve(path, registry)
        return
    url = None
    try:
        saved = json.loads(registry.read_text())
        request(saved['url'] + 'state')
        url = saved['url']
    except (OSError, ValueError):
        pass
    if args.stop:
        if url:
            request(url + 'shutdown')
        print('Preview server stopped' if url else 'Preview server is not running')
        return
    if path.suffix.lower() != '.stl' or not path.is_file():
        parser.error('Provide an existing .stl file')
    if not all((VENDOR / relative).is_file() for relative in VENDOR_FILES.values()):
        parser.error('Viewer dependencies are missing; run npm ci in click-to-ship/')
    browser = shutil.which('terminal-browser')
    if not args.no_open and not browser:
        parser.error('terminal-browser is missing; install with: brew install terminal-browser')
    if not url:
        with registry.with_suffix('.log').open('ab') as log:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(path), '--serve'],
                                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(60):
            try:
                saved = json.loads(registry.read_text())
                request(saved['url'] + 'state')
                url = saved['url']
                break
            except (OSError, ValueError):
                if child.poll() is not None:
                    raise SystemExit('Preview server failed; inspect ' + str(registry.with_suffix('.log')))
                time.sleep(.1)
        if not url:
            raise SystemExit('Preview server did not start')
    print(url, flush=True)
    if args.no_open:
        return
    command = [browser, 'open', url, '--app-mode']
    if args.split:
        command.extend(['--split', args.split])
    if os.environ.get('TERM_PROGRAM') in ('ghostty', 'WezTerm') or os.environ.get('KITTY_WINDOW_ID'):
        subprocess.run(command, check=True)
    elif sys.platform == 'darwin':
        # A desktop-agent tool call has no visible terminal. Give it its own window.
        if args.split:
            print('No parent terminal pane; opening a separate Ghostty window.', file=sys.stderr)
            command = command[:-2]
        subprocess.run(['open', '-na', 'Ghostty', '--args', '-e', *command], check=True)
    else:
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
