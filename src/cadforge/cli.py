from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile

def main():
    parser=argparse.ArgumentParser(description='Editable CAD and honest self-improvement experiments')
    sub=parser.add_subparsers(dest='command',required=True)
    design=sub.add_parser('design'); design.add_argument('request',nargs='?',default='Glasses housing a camera and Raspberry Pi')
    design.add_argument('--spec',type=Path);design.add_argument('--output',type=Path,default=Path('artifacts/design'))
    design.add_argument('--llm',action='store_true');design.add_argument('--enhanced',action='store_true')
    design.add_argument('--production',action='store_true',help='Use sourced glasses geometry, persistent fit commands, and independent release gates')
    learn=sub.add_parser('discover');learn.add_argument('--output',type=Path,default=Path('artifacts/discovery'))
    bench=sub.add_parser('benchmark');bench.add_argument('--split',choices=['development','hidden'],default='development')
    bench.add_argument('--skills',type=Path,default=Path('artifacts/discovery'))
    bench.add_argument('--output',type=Path,default=Path('artifacts/benchmark.json'))
    bench.add_argument('--llm',action='store_true')
    bench.add_argument('--mode',choices=['none','retrieved','learned'])
    sub.add_parser('status')
    args=parser.parse_args()
    if args.command=='design':
        from .schema import DesignSpec
        from .planner import parse_request,plan_with_model
        from .pipeline import run_design
        from .telemetry import enable_weave,trace_development
        model_usage=None
        if args.spec:
            spec=DesignSpec.model_validate_json(args.spec.read_text())
        elif args.llm:
            enable_weave()
            spec,model_usage=trace_development(plan_with_model)(args.request)
        else:
            spec=parse_request(args.request)
        if args.production:
            from .product import run_production
            result=run_production(spec,args.output)
        else:
            result=run_design(spec,args.output,enhanced=args.enhanced)
        print(json.dumps({k:v for k,v in result.items() if k not in ('build','spec')},indent=2))
        if model_usage: print(json.dumps({'planner_usage':model_usage}))
    elif args.command=='discover':
        from .pipeline import discover
        print(json.dumps(discover(args.output),indent=2))
    elif args.command=='benchmark':
        from .benchmark import PUBLIC,Budget,evaluate_cases,evaluate_hidden
        from .pipeline import run_design
        from .planner import parse_request,plan_with_model
        from .skills import SkillLibrary
        from .schema import DesignSpec
        library=SkillLibrary.load(args.skills/'skills.json')
        child=json.loads((args.skills/'discovery.json').read_text())['composed_skill_id']
        import ast
        script_tree=ast.parse((args.skills/'retrieved-script.py').read_text())
        assignment=next(node for node in script_tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SPEC' for t in node.targets))
        script_spec=ast.literal_eval(assignment.value)
        retrieved={k:script_spec['parameters'][k] for k in ('wall','clearance')}
        model_totals={'input_tokens':0,'output_tokens':0,'requests':0,'failures':0}
        # The runner receives public request text only. No learner, trace, or cloud calls.
        def runner(brief,mode,budget):
            out=Path(artifact_root)/f'{mode}-{brief["id"]}'
            if brief['family']=='composite':
                return {'spec':None,'cost':{'attempts':1,'tool_calls':0,'model_tokens':0},'status':'unsupported_composition'}
            model_usage={}
            if args.llm:
                try:
                    spec,model_usage=plan_with_model(brief['request'])
                except Exception as error:
                    model_usage=getattr(error,'cadforge_usage',{})
                    for key in ('input_tokens','output_tokens','requests'):
                        model_totals[key]+=model_usage.get(key,0)
                    model_totals['failures']+=1
                    return {'spec':None,'cost':{'attempts':1,'tool_calls':0,'model_tokens':model_usage.get('input_tokens',0)+model_usage.get('output_tokens',0)},'status':'planner_failed'}
                for key in ('input_tokens','output_tokens','requests'):
                    model_totals[key]+=model_usage.get(key,0)
            else:
                spec=parse_request(brief['request'])
            candidate=run_design(spec,out,mode=mode,library=library,skill_id=child,retrieved=retrieved,max_attempts=budget.attempts,max_tool_calls=budget.tool_calls,trace=False)
            candidate['cost']['model_tokens']=model_usage.get('input_tokens',0)+model_usage.get('output_tokens',0)
            return candidate
        with tempfile.TemporaryDirectory(prefix='cadforge-evaluation-') as artifact_root:
            if args.split=='hidden':
                # Disable remote automatic traces; hidden details never go to cloud telemetry.
                import os
                os.environ['WEAVE_DISABLED']='true'
                result=evaluate_hidden(runner,modes=(args.mode,) if args.mode else ('none','retrieved','learned'))
            else:
                cases=json.loads((PUBLIC/'development.json').read_text())
                result={'results':[evaluate_cases(cases,runner,mode,Budget(),feedback=True) for mode in ((args.mode,) if args.mode else ('none','retrieved','learned'))]}
        result['planner']='pydantic_ai_llm' if args.llm else 'bounded_offline_parser'
        result['model_usage']=model_totals
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    else:
        import os, shutil
        from .telemetry import enable_weave
        print(json.dumps({'cad_backend':'CadQuery','weave_credentials':bool(os.getenv('WANDB_API_KEY')),'weave_project':bool(os.getenv('CADFORGE_WEAVE_PROJECT')),'model_credentials':bool(os.getenv('OPENAI_API_KEY')),'calculix':shutil.which('ccx'),'typesafe':'No public API contract found; integration unavailable'},indent=2))

if __name__=='__main__': main()
