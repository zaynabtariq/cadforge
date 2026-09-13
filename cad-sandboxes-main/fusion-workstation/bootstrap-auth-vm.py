#!/usr/bin/env python3
import json,subprocess,time,re
from pathlib import Path
from fusion_connector.vm import VM

root=Path(__file__).resolve().parent
v=VM(root/'auth-vm.json')
deadline=time.monotonic()+600
while time.monotonic()<deadline:
    try:
        out=v.ssm("'SSM ready'",timeout=30);break
    except RuntimeError as exc:
        if 'InvalidInstanceId' not in str(exc):raise
        time.sleep(10)
else:raise RuntimeError('Fresh VM did not register with SSM')
print('Fresh VM SSM ready',flush=True)
ip=v.describe()['PublicIpAddress']
# The owner recovery image initially has the pinned owner SSH host key.
subprocess.run(['scp','-F',str(root/'ssh_config'),'-o','HostName='+ip,
    str(root/'bridge-package.zip'),'fusion-workstation:C:/FusionWorkstation/User/auth-bridge-package.zip'],check=True)
v.ssm("New-Item C:\\FusionWorkstation\\Auth -ItemType Directory -Force | Out-Null; Copy-Item C:\\FusionWorkstation\\User\\auth-bridge-package.zip C:\\FusionWorkstation\\Auth\\bridge-package.zip -Force")
begin=(root/'begin-signin.ps1').read_text()
v.ssm("$script=@'\n"+begin+"\n'@\n$script | Set-Content C:\\FusionWorkstation\\Auth\\Begin-SignIn.ps1")
notice=(root/'dismiss-first-run.ps1').read_text()
v.ssm("$script=@'\n"+notice+"\n'@\n$script | Set-Content C:\\FusionWorkstation\\Auth\\Dismiss-FirstRun.ps1")
out=v.ssm((root/'prepare-auth-profile.ps1').read_text(),timeout=300)
v.ssm((root/'remote-auth-policy.ps1').read_text())
host_key=next(line.strip() for line in out.splitlines() if line.startswith('ssh-ed25519 '))
known=root/'private'/'auth-known-hosts';known.write_text('fusion-auth '+ ' '.join(host_key.split()[:2])+'\n');known.chmod(0o600)
config=re.sub(r'(?m)^(\s*)HostName\s+\S+',lambda m:m[1]+'HostName '+ip,(root/'ssh_config').read_text())
config=re.sub(r'(?m)^(\s*)User\s+\S+',r'\1User FusionAuth',config)
config=re.sub(r'(?m)^(\s*)HostKeyAlias\s+\S+',r'\1HostKeyAlias fusion-auth',config)
config=re.sub(r'(?m)^(\s*)UserKnownHostsFile\s+.+',lambda m:m[1]+'UserKnownHostsFile '+str(known),config)
(root/'auth-ssh_config').write_text(config)
v.ssm("shutdown.exe /r /t 5 /c \"Start fresh Fusion authentication profile\"; 'Reboot scheduled'")
state=json.loads(v.state_file.read_text());state.update(phase='fresh_profile_configured',public_ip=ip)
v.state_file.write_text(json.dumps(state,indent=2)+'\n')
print('Fresh profile configured, reboot scheduled, new SSH key pinned',flush=True)
