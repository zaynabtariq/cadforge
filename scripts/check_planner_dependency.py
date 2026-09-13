"""Schema/serialization probe usable in an isolated minimal Pydantic install."""
import json
import pydantic
from cadforge.edit_planner import EditDecision,Translate
result={'pydantic':pydantic.__version__}
try:
    EditDecision.model_json_schema()
    ordinary=Translate(op='translate',axis='x',amount_mm=1).model_dump()
    rigid=Translate(op='translate',axis='x',amount_mm=1,translation_mode='rigid').model_dump()
    assert 'translation_mode' not in ordinary
    assert rigid['translation_mode']=='rigid'
    result.update(passed=True,ordinary=ordinary,rigid=rigid)
except Exception as exc:result.update(passed=False,error=f'{type(exc).__name__}: {exc}')
print(json.dumps(result,indent=2))
