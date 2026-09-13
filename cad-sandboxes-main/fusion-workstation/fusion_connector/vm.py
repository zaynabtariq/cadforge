import base64
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from aws import aws_env

ROOT=Path(__file__).resolve().parents[1]


class VM:
    def __init__(self, state_file, ssh_config=None):
        self.state_file=Path(state_file)
        try:
            self.state=json.loads(self.state_file.read_text())
        except (OSError,ValueError):
            raise RuntimeError('Workstation configuration is missing. Copy and fill the matching *.example.json; see README.md.') from None
        if not self.state.get('instance_id') or not self.state.get('region'):
            raise RuntimeError('Configure instance_id and region in the workstation state file.')
        self.ssh_config=Path(ssh_config or ROOT/'ssh_config')
        self.tunnel=None
        self.browser_tunnel=None
        self.browser_port=None
        self.address=None

    def connect_browser(self):
        if self.browser_tunnel and self.browser_tunnel.poll() is None:
            return f'http://127.0.0.1:{self.browser_port}'
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));self.browser_port=sock.getsockname()[1]
        self.browser_tunnel=subprocess.Popen(['ssh',*self.ssh_options(),
            '-o','ExitOnForwardFailure=yes','-N','-L',f'127.0.0.1:{self.browser_port}:127.0.0.1:9222','fusion-workstation'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(50):
            if self.browser_tunnel.poll() is not None:raise RuntimeError('Browser SSH tunnel failed')
            try:
                with socket.create_connection(('127.0.0.1',self.browser_port),timeout=.1):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Browser SSH tunnel did not start')
        return f'http://127.0.0.1:{self.browser_port}'

    def aws(self,*args):
        proc=subprocess.run(['aws',*args,'--region',self.state['region'],'--output','json'],
            env=aws_env(),capture_output=True,text=True,timeout=60)
        if proc.returncode: raise RuntimeError(proc.stderr.strip())
        return json.loads(proc.stdout) if proc.stdout.strip() else {}

    def describe(self):
        return self.aws('ec2','describe-instances','--instance-ids',self.state['instance_id'])['Reservations'][0]['Instances'][0]

    def ssm(self,script,timeout=300):
        result=self.aws('ssm','send-command','--instance-ids',self.state['instance_id'],
            '--document-name','AWS-RunPowerShellScript','--parameters',
            json.dumps({'commands':[script],'executionTimeout':[str(timeout)]}),
            '--comment','Fusion connector setup (no Autodesk credentials)')
        command_id=result['Command']['CommandId'];deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:result=self.aws('ssm','get-command-invocation','--instance-id',self.state['instance_id'],'--command-id',command_id)
            except RuntimeError as exc:
                if 'InvocationDoesNotExist' not in str(exc):raise
                time.sleep(1);continue
            if result['Status']=='Success':return result['StandardOutputContent']
            if result['Status'] in ('Failed','Cancelled','TimedOut'):
                raise RuntimeError(result.get('StandardErrorContent') or 'VM setup failed')
            time.sleep(1)
        raise TimeoutError('VM setup timed out')

    def ssh(self,script,stdin='',timeout=30):
        command='powershell.exe -NoProfile -NonInteractive -OutputFormat Text -ExecutionPolicy Bypass -EncodedCommand '+base64.b64encode(script.encode('utf-16-le')).decode()
        proc=subprocess.run(['ssh',*self.ssh_options(),'fusion-workstation',command],
            input=stdin,capture_output=True,text=True,timeout=timeout)
        # Neither SSH stdin nor error text is surfaced: it can contain auth URLs.
        if proc.returncode:raise RuntimeError('VM SSH operation failed')
        return proc.stdout.strip()

    def resolve_address(self):
        instance=self.describe()
        if instance['State']['Name']!='running':raise RuntimeError('VM must be running')
        field='PrivateIpAddress' if os.environ.get('FUSION_USE_PRIVATE_IP')=='1' else 'PublicIpAddress'
        self.address=instance.get(field)
        if not self.address:raise RuntimeError('VM has no reachable address yet')
        return self.address

    def ssh_options(self):
        return ['-F',str(self.ssh_config),'-o','HostName='+(self.address or self.resolve_address())]

    def connect(self):
        self.resolve_address()
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.tunnel=subprocess.Popen(['ssh',*self.ssh_options(),
            '-o','ExitOnForwardFailure=yes','-N','-L',f'127.0.0.1:{port}:127.0.0.1:8080','fusion-workstation'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(50):
            if self.tunnel.poll() is not None:raise RuntimeError('SSH tunnel could not start')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.1):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('SSH tunnel did not start')
        return f'http://127.0.0.1:{port}'

    def close(self):
        for proc in (self.tunnel,self.browser_tunnel):
            if proc:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill()
