import json, subprocess, urllib.request, base64
from pathlib import Path
from aws import aws_env
from settings import deployment
root=Path(__file__).resolve().parent
state_path=root/'state.json'
if state_path.exists(): raise SystemExit('state.json already exists; inspect existing deployment before creating resources')
config=deployment()
state={'region':config['region'],'name':config['name'],'subnet_id':config['subnet_id'],'instance_type':config.get('instance_type','m6i.xlarge')}
def save(): state_path.write_text(json.dumps(state,indent=2)+'\n')
def call(*args):
 p=subprocess.run(['aws',*args,'--region',state['region'],'--output','json'],env=aws_env(),capture_output=True,text=True)
 if p.returncode: raise RuntimeError(p.stderr)
 return json.loads(p.stdout) if p.stdout.strip() else {}
name=state['name']; save()
ip=urllib.request.urlopen('https://checkip.amazonaws.com').read().decode().strip();state['allowed_ip']=ip+'/32'
state['security_group_id']=call('ec2','create-security-group','--group-name',name,'--description','Fusion workstation desktop access from operator IP','--vpc-id',config['vpc_id'])['GroupId'];save()
call('ec2','authorize-security-group-ingress','--group-id',state['security_group_id'],'--ip-permissions',json.dumps([{'IpProtocol':proto,'FromPort':port,'ToPort':port,'IpRanges':[{'CidrIp':state['allowed_ip'],'Description':'Operator workstation'}]} for proto,port in [('tcp',8443),('udp',8443),('tcp',3389)]]))
state['key_name']=name
key=call('ec2','create-key-pair','--key-name',name)
p=root/'private';p.mkdir(mode=0o700,exist_ok=True)
k=p/'workstation.pem';k.write_text(key['KeyMaterial']);k.chmod(0o600);save()
state['role_name']=name
trust={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':'ec2.amazonaws.com'},'Action':'sts:AssumeRole'}]}
call('iam','create-role','--role-name',name,'--assume-role-policy-document',json.dumps(trust));save()
call('iam','attach-role-policy','--role-name',name,'--policy-arn','arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore')
policy={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':'s3:GetObject','Resource':'arn:aws:s3:::dcv-license.'+state['region']+'/*'}]}
call('iam','put-role-policy','--role-name',name,'--policy-name','DCVLicense','--policy-document',json.dumps(policy))
call('iam','create-instance-profile','--instance-profile-name',name);state['instance_profile']=name;save()
call('iam','add-role-to-instance-profile','--instance-profile-name',name,'--role-name',name)
state['ami_id']=call('ssm','get-parameter','--name','/aws/service/ami-windows-latest/Windows_Server-2025-English-Full-Base')['Parameter']['Value'];save()
print('Prerequisites created:',json.dumps(state))
