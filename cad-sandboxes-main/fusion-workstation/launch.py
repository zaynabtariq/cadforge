import json,subprocess,base64
from pathlib import Path
from aws import aws_env
root=Path(__file__).resolve().parent
state=json.loads((root/'state.json').read_text())
if state.get('instance_id'): raise SystemExit('Instance already created: '+state['instance_id'])
request={
 'ImageId':state['ami_id'],'InstanceType':state.get('instance_type','m6i.xlarge'),'MinCount':1,'MaxCount':1,
 'KeyName':state['key_name'],'IamInstanceProfile':{'Name':state['instance_profile']},
 'NetworkInterfaces':[{'DeviceIndex':0,'SubnetId':state['subnet_id'],'AssociatePublicIpAddress':True,'Groups':[state['security_group_id']]}],
 'BlockDeviceMappings':[{'DeviceName':'/dev/sda1','Ebs':{'VolumeSize':100,'VolumeType':'gp3','Encrypted':True,'DeleteOnTermination':False}}],
 'MetadataOptions':{'HttpTokens':'required','HttpEndpoint':'enabled'},
 'UserData':(root/'bootstrap.ps1').read_text(),
 'ClientToken':state['name'],
 'TagSpecifications':[{'ResourceType':kind,'Tags':[{'Key':'Name','Value':state['name']},{'Key':'Project','Value':'fusion-agent-workstation'}]} for kind in ['instance','volume']]
}
p=subprocess.run(['aws','ec2','run-instances','--cli-binary-format','raw-in-base64-out','--cli-input-json',json.dumps(request),'--region',state['region'],'--output','json'],env=aws_env(),capture_output=True,text=True)
if p.returncode:raise SystemExit(p.stderr)
i=json.loads(p.stdout)['Instances'][0];state['instance_id']=i['InstanceId'];state['instance_type']=i['InstanceType'];(root/'state.json').write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(state,indent=2))
