#!/usr/bin/env python3
"""Owner workstation lifecycle, native sign-in UI, and private Fusion CLI."""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from fusion_connector import BridgeClient
from fusion_connector.client import ConnectorClient
from fusion_connector.vm import VM

ROOT = Path(__file__).resolve().parent
TARGETS = {'fresh': ('auth-vm.json', 'auth-ssh_config'), 'primary': ('state.json', 'ssh_config')}
# Hosted gateway is part of the Fusion project, but is never needed for local login.
API = {'region': os.environ.get('FUSION_API_REGION', 'us-west-2'),
       'instance_id': os.environ.get('FUSION_API_INSTANCE_ID')}


def target(name):
    state, config = TARGETS[name]
    return VM(ROOT / state, ROOT / config)


def status(vm, name):
    i = vm.describe()
    return {'target': name, 'instance_id': i['InstanceId'], 'state': i['State']['Name']}


def start(vm, timeout=300):
    """Start only this VM, resolve its address, then prove the SSH identity."""
    deadline = time.monotonic() + timeout
    expected = vm.state.get('windows_user', 'Fusion').lower()
    while time.monotonic() < deadline:
        i = vm.describe()
        state = i['State']['Name']
        if state == 'stopped':
            vm.aws('ec2', 'start-instances', '--instance-ids', vm.state['instance_id'])
        elif state == 'running':
            try:
                vm.resolve_address()
                identity = vm.ssh('whoami', timeout=8).strip().lower()
                if identity.rsplit('\\', 1)[-1] != expected:
                    raise ValueError('SSH user does not match the selected Windows profile')
                return
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
        elif state not in ('pending', 'stopping'):
            raise RuntimeError('Cannot start a VM in state ' + state)
        time.sleep(2)
    raise TimeoutError('VM/SSH startup timed out. Check EC2 and Windows SSH ingress for your current IP; host-key verification remains enabled.')


def stop(vm, timeout=180):
    deadline = time.monotonic() + timeout
    requested = False
    while time.monotonic() < deadline:
        state = vm.describe()['State']['Name']
        if state == 'stopped':
            return
        if state == 'running' and not requested:
            vm.aws('ec2', 'stop-instances', '--instance-ids', vm.state['instance_id'])
            requested = True
        elif state not in ('pending', 'running', 'stopping'):
            raise RuntimeError('Cannot stop a VM in state ' + state)
        time.sleep(2)
    raise TimeoutError('Stop requested, but EC2 has not confirmed stopped yet')


def runtime_url():
    try:
        value = json.loads((ROOT / 'private/connector-runtime.json').read_text())['url']
        u = urlsplit(value)
        if (u.scheme != 'http' or u.hostname != '127.0.0.1' or u.port != 18766
                or u.username or u.password or u.query or u.fragment
                or not re.fullmatch(r'/[A-Za-z0-9_-]{32,64}/', u.path)):
            raise ValueError()
        return value
    except (OSError, ValueError, KeyError):
        raise RuntimeError('No valid local connector runtime. Run workstation.py login.') from None


def api(path, body=None):
    req = urllib.request.Request(runtime_url() + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'X-Connector-Request': '1'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)
    except Exception:
        # Never include a capability URL or raw upstream body in CLI errors.
        raise RuntimeError('Local connector request failed. Check the connector process and current auth state.') from None


def connector():
    try:
        if api('v1/health')['api_version'] == '1.0':
            return
    except (RuntimeError, KeyError):
        pass
    private = ROOT / 'private'
    private.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(private / 'connector.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'ab') as log:
        proc = subprocess.Popen([sys.executable, str(ROOT / 'connector-server.py'), '--port', '18766'],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError('Connector did not start. Inspect private/connector.log locally.')
        try:
            if api('v1/health')['api_version'] == '1.0':
                return
        except (RuntimeError, KeyError):
            pass
        time.sleep(.2)
    proc.terminate()
    raise TimeoutError('Local connector startup timed out')


def auth_status():
    state = api('v1/auth')
    return {k: state.get(k) for k in ('phase', 'verified', 'verification_method', 'form', 'error', 'can_retry')}


def verified_bridge(vm):
    if vm.describe()['State']['Name'] != 'running':
        raise RuntimeError('VM is stopped. Run workstation.py login (fresh) or start --target primary explicitly.')
    bridge = BridgeClient(vm.connect())
    if not bridge.call('/ready', timeout=5).get('ready'):
        raise RuntimeError('Fusion is not ready. Complete native sign-in through workstation.py login.')
    return bridge


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='action', required=True)
    for name in ('status', 'stop'):
        sub = commands.add_parser(name)
        sub.add_argument('--target', choices=TARGETS, default='fresh')
        sub.add_argument('--all', action='store_true', help='Configured workstations and optional FUSION_API_INSTANCE_ID only')
    sub = commands.add_parser('start', help='Start one selected VM and wait for SSH; does not prove Autodesk login')
    sub.add_argument('--target', choices=TARGETS, default='fresh')
    sub.add_argument('--timeout', type=float, default=300)
    sub = commands.add_parser('login', help='Start/reuse fresh VM, launch connector, begin observed native sign-in')
    sub.add_argument('--timeout', type=float, default=300)
    sub.add_argument('--open', action='store_true', help='Open local wrapper with terminal-browser')
    sub.add_argument('--browser', help='Existing terminal-browser ID; requires --open')
    commands.add_parser('auth-status', help='Sanitized state; never prints form tokens or URLs')
    for name in ('verify', 'run'):
        sub = commands.add_parser(name)
        sub.add_argument('--target', choices=TARGETS, default='fresh')
        if name == 'run':
            sub.add_argument('command', nargs=argparse.REMAINDER, help='fusion-* tool and arguments; does not start stopped VMs')
    sub = commands.add_parser('capture', help='Publish one completed modeling step to the auto-updating viewer')
    sub.add_argument('--step', required=True)
    sub.add_argument('--key', required=True, help='Stable idempotency key for this capture')
    sub.add_argument('--quality', choices=('low', 'medium', 'high'), default='medium')
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    vm = None
    try:
        if args.action == 'auth-status':
            vm = target('fresh')
            live = status(vm, 'fresh')
            print(json.dumps({**live, **(auth_status() if live['state'] == 'running' else {'phase': 'offline', 'verified': False})}))
        elif args.action in ('status', 'stop'):
            names = ([name for name, (state, _) in TARGETS.items() if (ROOT / state).is_file()]
                     + (['api'] if API['instance_id'] else [])) if args.all else [args.target]
            if not names:
                raise RuntimeError('No workstations configured. See fusion-workstation/README.md.')
            records = []
            for name in names:
                vm = target('fresh' if name == 'api' else name)
                if name == 'api':
                    vm.state = dict(API)
                if args.action == 'stop':
                    stop(vm)
                records.append(status(vm, name))
            print(json.dumps(records, indent=2))
        elif args.action == 'login':
            if args.browser and not args.open:
                p.error('--browser requires --open')
            vm = target('fresh')
            start(vm, args.timeout)
            connector()
            api('v1/auth/start', {})
            if args.open:
                command = ['terminal-browser', 'new-tab']
                if args.browser:
                    command += ['--browser', args.browser]
                # Local capability only; no Autodesk sign-in/callback URL leaves Windows.
                result = subprocess.run([*command, runtime_url()], capture_output=True, timeout=30)
                if result.returncode:
                    raise RuntimeError('Login is running; browser could not open. Select an existing browser with --open --browser ID.')
            print(json.dumps({'target': 'fresh', 'ui_runtime': str(ROOT / 'private/connector-runtime.json'), **auth_status()}))
        elif args.action == 'start':
            vm = target(args.target)
            start(vm, args.timeout)
            print(json.dumps(status(vm, args.target)))
        elif args.action in ('verify', 'run'):
            if args.action == 'run' and (not args.command or not args.command[0].startswith('fusion-')):
                p.error('run requires an existing fusion-* command')
            vm = target(args.target)
            bridge = verified_bridge(vm)
            if args.action == 'verify':
                docs = bridge.call('/list_open_documents', timeout=10)
                caps = bridge.call('/v1/viewer/capabilities', timeout=5)
                print(json.dumps({'target': args.target, 'live_ready': True, 'document_count': docs['count'],
                    'connector_api': caps['api_version'], 'check': 'readiness_and_document_read', 'fresh_login_proof': False}))
            else:
                return subprocess.run([sys.executable, str(ROOT / 'fusion-cli.py'), *args.command],
                    env=dict(os.environ, FUSION_BRIDGE_URL=bridge.endpoint)).returncode
        elif args.action == 'capture':
            vm = target('fresh')
            if vm.describe()['State']['Name'] != 'running' or not auth_status()['verified']:
                raise RuntimeError('Complete workstation.py login before publishing a model step')
            frame = ConnectorClient(runtime_url(), workstation='fresh').capture(args.step, args.quality, args.key)
            print(json.dumps({k: frame.get(k) for k in ('version', 'step_id', 'fusion_epoch')}))
        return 0
    except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
        print(str(exc) if isinstance(exc, (RuntimeError, TimeoutError, ValueError)) else 'Operation failed; check local dependencies and VM connectivity.', file=sys.stderr)
        return 1
    finally:
        if vm:
            vm.close()


if __name__ == '__main__':
    raise SystemExit(main())
