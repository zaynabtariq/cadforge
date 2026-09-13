"""Exercise local geometry parsing/rendering with browse; no provider sessions or orders."""
import json
from pathlib import Path
import re
import struct
import time
import uuid
import zipfile

from quote import Browser, ROOT


def fixtures():
    folder = ROOT / 'artifacts/preview-tests'
    folder.mkdir(parents=True, exist_ok=True)
    ascii_file = ROOT / 'fixtures/cube-20mm.stl'
    source = ascii_file.read_text()
    vertices = [tuple(map(float, v)) for v in re.findall(r'vertex\s+(\S+)\s+(\S+)\s+(\S+)', source)]
    normals = [tuple(map(float, v)) for v in re.findall(r'facet normal\s+(\S+)\s+(\S+)\s+(\S+)', source)]
    binary_file = folder / 'cube-binary.stl'
    with binary_file.open('wb') as f:
        f.write(b'Binary STL preview test'.ljust(80, b'\0'))
        f.write(struct.pack('<I', len(normals)))
        for i, normal in enumerate(normals):
            f.write(struct.pack('<12fH', *normal, *(n for v in vertices[i*3:i*3+3] for n in v), 0))
    obj_file = folder / 'cube.obj'
    obj_file.write_text('\n'.join('v '+' '.join(map(str,v)) for v in vertices)+'\n'+
                        '\n'.join(f'f {i+1} {i+2} {i+3}' for i in range(0,len(vertices),3)))
    mf_file = folder / 'inch-cube.3mf'
    xml_vertices = ''.join(f'<vertex x="{x/20}" y="{y/20}" z="{z/20}"/>' for x,y,z in vertices)
    xml_triangles = ''.join(f'<triangle v1="{i}" v2="{i+1}" v3="{i+2}"/>' for i in range(0,len(vertices),3))
    with zipfile.ZipFile(mf_file,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/model.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/model.model',f'<model unit="inch" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources><object id="1" type="model"><mesh><vertices>{xml_vertices}</vertices><triangles>{xml_triangles}</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')
    step_file = ROOT / 'node_modules/occt-import-js/test/testfiles/cube-units/cube-in.step'
    return folder, [(ascii_file,[20,20,20]),(binary_file,[20,20,20]),(obj_file,[20,20,20]),
                    (mf_file,[25.4,25.4,25.4]),(step_file,[1000,None,None])]


def main():
    folder, cases = fixtures()
    b = Browser('viewer-test-'+uuid.uuid4().hex[:8])
    results=[]
    try:
        b.call('open','http://127.0.0.1:8766','--local')
        b.call('eval', '''(() => {
          draft={technology:'SLA',material:'9600 Resin',color:null,quantity:1,category:'blocks',description:'Preview test'};
          document.getElementById('description').value=draft.description;
          render();
          const input=document.createElement('input');input.type='file';input.id='preview-fixture';document.body.append(input);
          input.onchange=()=>{previewInfo=null;selectedAt=performance.now();document.getElementById('preview-error').textContent='';document.getElementById('preview-error').hidden=true;preview(input.files[0]);};
          return true;
        })()''')
        for file, expected in cases:
            b.snapshot()
            b.call('upload','#preview-fixture',str(file))
            deadline=time.monotonic()+65
            while time.monotonic()<deadline:
                result=b.call('eval','({info:previewInfo,error:document.getElementById("preview-error").textContent,canvas:!!document.querySelector("#viewer canvas")})')['result']
                if result['error']:
                    raise AssertionError(f'{file.name}: {result["error"]}')
                if result['info']:
                    break
                time.sleep(.5)
            else:
                raise AssertionError(f'Preview timed out: {file.name}')
            assert result['canvas'], file.name
            for actual,wanted in zip(result['info']['dimensions_mm'],expected):
                if wanted is not None:
                    assert abs(actual-wanted)<.01,(file.name,actual,wanted)
            results.append({'file':file.name,**result['info']})
            print(file.name,'PASS',result['info']['dimensions_mm'],result['info']['ready_ms'],'ms',flush=True)
        b.snapshot()
        b.call('click','#wireframe')
        assert b.call('eval','document.getElementById("wireframe").getAttribute("aria-pressed")')['result']=='true'
        b.call('click','#reset-view')
        b.call('screenshot','--path',str(folder/'step-preview.png'))
        (folder/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    finally:
        b.call('stop')


if __name__ == '__main__':
    main()
