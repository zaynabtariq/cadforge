import json
import urllib.request
import urllib.parse
import urllib.error
import uuid


class ConnectorClient:
    """Public owner API client; obtain base_url from the local launcher's runtime."""
    def __init__(self,base_url,workstation='primary'):
        if workstation not in ('primary','fresh'):raise ValueError('Unknown workstation')
        self.base_url=base_url.rstrip('/')+'/';self.workstation=workstation

    def request(self,path,body=None,key=None):
        headers={'Content-Type':'application/json','X-Connector-Request':'1'}
        if body is not None:headers['Idempotency-Key']=key or str(uuid.uuid4())
        request=urllib.request.Request(self.base_url+'v1/workstations/'+self.workstation+'/'+path,
            data=None if body is None else json.dumps(body).encode(),headers=headers)
        with urllib.request.urlopen(request,timeout=160) as response:return json.load(response)

    def capture(self,step_id,quality='medium',key=None):
        return self.request('captures',{'step_id':step_id,'quality':quality},key)['scene']

    def scene(self):return self.request('scene')['scene']

    def events(self,after=0,epoch=''):
        return self.request('events?'+urllib.parse.urlencode({'after':after,'epoch':epoch}))
