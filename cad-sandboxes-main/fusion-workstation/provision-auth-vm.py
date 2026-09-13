#!/usr/bin/env python3
"""Create one owner-only authentication test VM; never change the working VM."""
import json, subprocess
from pathlib import Path
from aws import aws_env
root=Path(__file__).resolve().parent
state_path=root/'auth-vm.json'
source=json.loads((root/'state.json').read_text())
auth_name=source['name']+'-auth'
backup=json.loads((root/'backup.json').read_text())
def aws(*args):
    p=subprocess.run(['aws',*args,'--region',source['region'],'--output','json'],env=aws_env(),capture_output=True,text=True,check=True)
    return json.loads(p.stdout)
if state_path.exists():
    print(json.dumps(json.loads(state_path.read_text()),indent=2));raise SystemExit(0)
image=aws('ec2','describe-images','--image-ids',backup['image_id'])['Images'][0]
assert image['State']=='available' and not image['Public']
instance=aws('ec2','describe-instances','--instance-ids',source['instance_id'])['Reservations'][0]['Instances'][0]
tags=[{'Key':'Name','Value':auth_name},{'Key':'Purpose','Value':'Owner-only fresh-profile authentication test'},{'Key':'DoNotShare','Value':'true'}]
result=aws('ec2','run-instances','--image-id',backup['image_id'],'--instance-type',source['instance_type'],
    '--key-name',source['key_name'],'--iam-instance-profile','Name='+source['instance_profile'],
    '--subnet-id',instance['SubnetId'],'--security-group-ids',source['security_group_id'],
    '--metadata-options','HttpTokens=required,HttpPutResponseHopLimit=1',
    '--block-device-mappings',json.dumps([{'DeviceName':image['RootDeviceName'],'Ebs':{'DeleteOnTermination':True,'Encrypted':True,'VolumeType':'gp3'}}]),
    '--tag-specifications',json.dumps([{'ResourceType':kind,'Tags':tags} for kind in ['instance','volume']]),
    '--client-token',auth_name,'--count','1')
state={**source,'instance_id':result['Instances'][0]['InstanceId'],'name':auth_name,
       'source_backup':backup['image_id'],'windows_user':'FusionAuth','phase':'provisioning',
       'contains_owner_backup':'Owner-only clone, not a generalized fleet image'}
state_path.write_text(json.dumps(state,indent=2)+'\n')
print(json.dumps(state,indent=2))
