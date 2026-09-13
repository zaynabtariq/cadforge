import asyncio
import pytest
from pydantic import ValidationError
from cadforge.review_json import ReviewInput

TOOL={'name':'driver','origin':[0,0,20],'axis':[0,0,1],'radius_mm':3,'length_mm':20,'source':'Declared prototype tool assumption'}

@pytest.mark.parametrize('change',[{'radius_mm':True},{'radius_mm':'3'},{'origin':[0,0,float('inf')]},{'extra':1},{'source':'  '}])
def test_nested_bad_inputs_rejected(change):
    with pytest.raises(ValidationError):ReviewInput.model_validate({'tool_access':[TOOL|change]})


def test_hardware_override_and_incomplete_material_rejected():
    with pytest.raises(ValidationError):ReviewInput.model_validate({'components':[]})
    with pytest.raises(ValueError):ReviewInput.model_validate({'density_g_cm3':1.0}).contracts()
    with pytest.raises(ValueError):ReviewInput.model_validate({'tool_access':[TOOL|{'axis':[0,0,0]}]}).contracts()


def test_mcp_passes_typed_review_without_changing_hardware(monkeypatch,tmp_path):
    from cadforge import product,mcpserver
    seen=[]
    def receive(spec,path,*,review_inputs):
        seen.append(review_inputs)
        return {'production_ready':False}
    monkeypatch.setattr(product,'run_production',receive);monkeypatch.setattr(mcpserver,'ARTIFACTS',tmp_path)
    response=asyncio.run(mcpserver.create_server().call_tool('create_camera_glasses',{'parameters':{},'review_inputs':{'tool_access':[TOOL]}}))
    assert not response.is_error
    assert seen[0]['tool_access'][0].radius_mm==3
    assert 'components' not in seen[0]
