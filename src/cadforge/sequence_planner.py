"""Explicit 'then' sequencing planned against executed intermediate geometry."""
import re
from .composition import preview_sequence
from .edit_planner import plan_edit, ResizePreservingHoles


def plan_sequence(service,session_id,request,selection,revision,*,use_model=None):
    if not re.search(r'\bthen\b',request,re.I):return None
    suffix=re.search(r'(?:,?\s+(?:while|and))?\s+(?:keep|keeping)\s+(?:all\s+)?(?:mounting\s+)?holes\s+(?:fixed|unchanged)\s+throughout[.!]?$',request,re.I)
    preserve=bool(suffix)
    operation_text=request[:suffix.start()].rstrip(' ,') if suffix else request
    clauses=re.split(r'\s+(?:and\s+)?then\s+',operation_text.strip(),flags=re.I)
    def clarify(message):return {'command':None,'clarification':message,'planner':'sequence_constraint_guard','usage':{'model_requests':0,'input_tokens':0,'output_tokens':0}}
    if preserve and re.search(r"\b(?:not|never|without|don['’]t|rather than|instead of)\s*$",operation_text,re.I):
        return clarify('The hole-preservation condition is negated. State explicitly whether holes may move or must remain fixed before running the sequence.')
    if not 2<=len(clauses)<=8 or any(not c.strip() for c in clauses):return clarify('Use two to eight complete edits separated by “then”.')
    if selection.get('region') or selection.get('point'):
        return clarify('Select a whole object from the object list for a sequence. Moving section or surface references between steps needs an explicit reference contract.')
    if re.search(r'\b(preserv\w*|keep\w*|unchanged|without changing|same position|fixed|pivot\w*)\b',operation_text,re.I):
        return clarify('A constraint that must hold across multiple edits needs a shared invariant contract. Preview this constrained edit separately for now.')
    steps=[{'request':c.strip(),'selection':selection} for c in clauses]
    if preserve and not selection.get('part_id'):return clarify('Select the object whose holes must stay fixed.')
    invariants=[{'kind':'preserve_holes','part_id':selection['part_id']}] if preserve else []
    def plan_step(text,sel,state):
        decision=plan_edit(text,sel,state,use_model=use_model)
        command=decision.get('command')
        if preserve and command and command.get('op')=='resize' and command.get('axis') in ('x','y'):
            # Preserve computed target and use the existing checked rail operation.
            decision['command']=ResizePreservingHoles(op='resize_preserving_holes',axis=command['axis'],target_mm=command['target_mm'],min_wall_mm=1).model_dump(mode='json')
            decision['explanation']='Resize using protected rails; original hole surfaces must remain fixed through every step.'
        return decision
    preview=preview_sequence(service,session_id,steps,revision,planner=plan_step,invariants=invariants)
    usage={key:sum(d.get('usage',{}).get(key,0) for d in preview.get('planning',[])) for key in ('model_requests','input_tokens','output_tokens')}
    return {'command':preview['command'],'preview':preview,'planner':'sequence_planner','clarification':None,
        'usage':usage,'explanation':f'{len(preview["step_outcomes"])} checked steps in one change.'}
