import numpy as np
import pytest
import trimesh
from cadforge.workspace import PythonWorkspace
from cadforge.edit_planner import plan_edit

@pytest.fixture
def hole_selection(tmp_path):
    stock=trimesh.creation.box(extents=[30,30,10])
    bore=trimesh.creation.cylinder(radius=2,height=12,sections=48)
    mesh=trimesh.boolean.difference([stock,bore],engine='manifold')
    source=tmp_path/'part.stl';mesh.export(source)
    service=PythonWorkspace(tmp_path/'ws',region_learning_path=tmp_path/'learning.json')
    state=service.import_file(source)
    return service,state,{'part_id':state['parts'][0]['id'],'point':[2.1,0,5],'normal':[0,0,1]}


def test_rim_click_anchors_counterbore_to_actual_hole(hole_selection):
    _,state,selection=hole_selection
    result=plan_edit('Counterbore this hole to 8 mm diameter and 2 mm deep',selection,state,use_model=False)
    command=result['command']
    assert command['op']=='counterbore' and command['radius_mm']==4 and command['depth_mm']==2
    np.testing.assert_allclose(command['entry'],[0,0,5],atol=1e-6)
    assert result['usage']['model_requests']==0


@pytest.mark.parametrize('prompt',[
    'Counterbore this hole to 8 mm diameter and 2 mm deep then move it',
    'Counterbore this hole to 8 mm diameter and 2 mm deep and rotate it',
    'Counterbore this hole to 8 mm diameter and 2 mm deep except the left side',
    'Do not counterbore this hole to 8 mm diameter and 2 mm deep',
    'Counterbore this hole to 8 mm diameter',
    'Counterbore this hole to >8 mm diameter and <2 mm deep',
    'Counterbore this hole to 8 mm diameter and depth 1/0 mm',
])
def test_additional_intent_is_not_silently_dropped(hole_selection,prompt):
    _,state,selection=hole_selection
    result=plan_edit(prompt,selection,state,use_model=False)
    assert result['command'] is None and result['clarification']
