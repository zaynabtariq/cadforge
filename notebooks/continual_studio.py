import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full", app_title="CADForge · Continual Design Studio")


@app.cell
def _():
    import marimo as mo
    import json
    import sqlite3
    import uuid
    from pathlib import Path
    from dataclasses import asdict, replace
    import cadquery as cq
    from cadforge.materials import EYEWEAR_REFERENCE, HP_MJF_PA12_LEGACY
    from cadforge.schema import DesignSpec
    from cadforge.production_geometry import build_design, export_design, layout
    from cadforge.engineering import assess_geometry, contract_from_public_layout
    from cadforge.robotics import RobotLinkSpec, build_link, widen_link, export_link
    from cadforge.evolve import DEFAULT_DB, evolve
    workspace = Path(__file__).resolve().parents[1]
    return (DEFAULT_DB, DesignSpec, EYEWEAR_REFERENCE, HP_MJF_PA12_LEGACY, Path,
            RobotLinkSpec, asdict, assess_geometry, build_design, build_link,
            contract_from_public_layout, cq, evolve, export_design, export_link,
            json, layout, mo, replace, sqlite3, uuid, widen_link, workspace)


@app.cell
def _(mo):
    mo.md("""
    # Continual Design Studio
    Build editable camera glasses or widen a robot link while checking its pivot interfaces.
    Designs run only when you submit a form. All dimensions are millimeters.

    [View development traces in Weave](https://wandb.ai/zzaynabb-03-radpilot/cadforge-continual/weave)
    · Local persistent learning uses measured CAD experiments. It is **not printer calibration**.
    """)
    return


@app.cell
def _(EYEWEAR_REFERENCE, mo):
    glasses_form = mo.md("""
    ### Camera glasses · MJF PA12 / external USB power
    Reference sizing comes from a commercial 52–18–145 frame; wearer fit is unverified.

    {lens_width} {lens_height} {bridge} {temple_length}

    {wall} {clearance}
    """).batch(
        lens_width=mo.ui.number(35,70,step=.1,value=EYEWEAR_REFERENCE['lens_width_mm'],label="Lens width"),
        lens_height=mo.ui.number(25,60,step=.1,value=EYEWEAR_REFERENCE['lens_height_mm'],label="Lens height"),
        bridge=mo.ui.number(12,26,step=.5,value=EYEWEAR_REFERENCE['bridge_mm'],label="Bridge"),
        temple_length=mo.ui.number(120,170,step=1,value=EYEWEAR_REFERENCE['temple_length_mm'],label="Temple length"),
        wall=mo.ui.number(1,4,step=.1,value=2,label="Wall"),
        clearance=mo.ui.number(.2,2,step=.05,value=.6,label="Component clearance"),
    ).form(submit_button_label="Build glasses and measure gates",show_clear_button=False)
    robot_form = mo.md("""
    ### Robot link · widen while preserving pivots
    This is a two-pivot link, not a complete powered robot arm.

    {center_distance} {width} {new_width} {thickness} {pivot_diameter}
    """).batch(
        center_distance=mo.ui.number(30,200,step=1,value=80,label="Pivot spacing"),
        width=mo.ui.number(16,40,step=1,value=20,label="Original width"),
        new_width=mo.ui.number(16,45,step=1,value=28,label="Requested wider width"),
        thickness=mo.ui.number(3,15,step=.5,value=6,label="Body thickness"),
        pivot_diameter=mo.ui.number(2,8,step=.1,value=4,label="Pivot bore"),
    ).form(submit_button_label="Build link and attempt widening",show_clear_button=False)
    mo.ui.tabs({"Camera glasses":glasses_form,"Robot link widening":robot_form})
    return glasses_form, robot_form


@app.cell
def _(DesignSpec, HP_MJF_PA12_LEGACY, asdict, assess_geometry, build_design,
      contract_from_public_layout, export_design, glasses_form, json, layout,
      mo, replace, uuid, workspace):
    mo.stop(glasses_form.value is None)
    glasses_result = None
    glasses_error = None
    try:
        _spec = DesignSpec(family="glasses",name="continual-studio-glasses",
                           parameters={k:float(v) for k,v in glasses_form.value.items()})
        _out = workspace / "artifacts" / "continual-studio" / ("glasses-"+uuid.uuid4().hex[:12])
        _out.mkdir(parents=True)
        # Persist the external product layout before generating candidate geometry.
        _requirements = layout(_spec)
        _contract = contract_from_public_layout(_requirements,
            wall_mm=_spec.parameters['wall'],clearance_mm=_spec.parameters['clearance'],
            density_g_cm3=HP_MJF_PA12_LEGACY.density_g_cm3,
            material_source=HP_MJF_PA12_LEGACY.source_url+'; legacy nominal screening only')
        _contract = replace(_contract,components=tuple(replace(e,mass_g=12.0 if e.name=='pi' else 4.0) for e in _contract.components))
        (_out/'external_contract.json').write_text(json.dumps(asdict(_contract),indent=2)+'\n')
        _built = build_design(_spec)
        _report = assess_geometry(_built.parts,_contract).model_dump()
        _paths = export_design(_built,_out)
        (_out/'independent_gates.json').write_text(json.dumps(_report,indent=2)+'\n')
        _paths['gates']=str(_out/'independent_gates.json')
        _paths['contract']=str(_out/'external_contract.json')
        glasses_result={'paths':_paths,'report':_report,'spec':_spec.model_dump()}
    except Exception as _error:
        glasses_error=f"{type(_error).__name__}: {_error}"
    return glasses_error, glasses_result


@app.cell
def _(Path, glasses_error, glasses_result, mo):
    mo.stop(glasses_error is not None,mo.callout(glasses_error or "",kind="danger"))
    mo.stop(glasses_result is None)
    _report=glasses_result['report'];_counts=_report['counts']
    _paths=glasses_result['paths']
    _downloads=[mo.download(Path(v).read_bytes(),filename=Path(v).name,label=k.upper())
                for k,v in _paths.items() if k in ('step','stl','python','json','gates','contract')]
    mo.vstack([
        mo.md(f"### Glasses measurements · {_counts['pass']} pass / {_counts['fail']} fail / {_counts['blocked']} blocked"),
        mo.Html(Path(_paths['svg']).read_text()) if _paths.get('svg') else mo.md("Preview unavailable; exported CAD remains available."),
        mo.hstack(_downloads,wrap=True),
        mo.ui.table(_report['gates'],selection=None),
        mo.accordion({'Specification':mo.json(glasses_result['spec']),
                      'Mass / center of gravity':mo.json({'mass_g':_report['mass_g'],'CG_mm':_report['center_of_gravity_mm'],'scope':'Nominal solid material plus two electronics modules; BOM incomplete.'})}),
        mo.callout("Passing geometry gates do not establish wearable safety or production readiness. Material values are legacy nominal data; actual fit, cable termination, fastener strength, thermal behavior and wear trials remain unresolved.",kind="warn")])
    return


@app.cell
def _(RobotLinkSpec, asdict, build_link, cq, export_link, json, mo, robot_form,
      uuid, widen_link, workspace):
    mo.stop(robot_form.value is None)
    robot_result=None
    robot_error=None
    try:
        _values=dict(robot_form.value)
        _new_width=float(_values.pop('new_width'))
        _spec=RobotLinkSpec(**{k:float(v) for k,v in _values.items()})
        _original=build_link(_spec)
        _out=workspace/'artifacts'/'continual-studio'/('robot-'+uuid.uuid4().hex[:12])
        _change=widen_link(_original,_new_width,output_dir=_out)
        _paths=export_link(_change.active_link,_out/'active')
        _svg=_out/'active'/'robot_link.svg'
        cq.exporters.export(_change.active_link.shape,str(_svg))
        _paths['svg']=str(_svg)
        robot_result={'accepted':_change.accepted,'paths':_paths,
            'gates':[{'gate':k,'status':'pass' if v else 'fail'} for k,v in _change.checks.items()],
            'before':asdict(_change.before),'after':asdict(_change.after) if _change.after else None,
            'error':_change.error,'active_version':_change.active_link.version_id,
            'parent_version':_change.previous_version}
    except Exception as _error:
        robot_error=f"{type(_error).__name__}: {_error}"
    return robot_error, robot_result


@app.cell
def _(Path, mo, robot_error, robot_result):
    mo.stop(robot_error is not None,mo.callout(robot_error or "",kind="danger"))
    mo.stop(robot_result is None)
    _paths=robot_result['paths']
    mo.vstack([
        mo.md("### Robot widening accepted" if robot_result['accepted'] else "### Widening rejected · original link retained"),
        mo.callout(robot_result['error'],kind="warn") if robot_result['error'] else mo.md("Pivot invariants measured on actual BRep geometry."),
        mo.Html(Path(_paths['svg']).read_text()),
        mo.hstack([mo.download(Path(v).read_bytes(),filename=Path(v).name,label=k.upper()) for k,v in _paths.items()],wrap=True),
        mo.ui.table(robot_result['gates'],selection=None),
        mo.accordion({'Before / after measurements':mo.json({'before':robot_result['before'],'after':robot_result['after']}),
                      'Version lineage':mo.json({'active':robot_result['active_version'],'parent':robot_result['parent_version']})}),
        mo.callout("Widening changes mass and inertia. Motor torque, bearings, load capacity, fatigue and collision-free robot motion have not been validated.",kind="warn")])
    return


@app.cell
def _(mo):
    learning_form=mo.md("""
    ### Run a persistent learning task
    Execute development fit coupons, infer parameter commands, challenge them on fresh cases,
    and reuse healthy promoted commands. This writes the local learning database and development artifacts.
    It does not access the frozen hidden benchmark.

    {cloud}
    """).batch(cloud=mo.ui.checkbox(value=False,label="Send this development run to configured Weave project")).form(
        submit_button_label="Run intentional learning task",show_clear_button=False)
    audit_refresh=mo.ui.run_button(label="Refresh local learning audit")
    mo.vstack([learning_form,audit_refresh])
    return audit_refresh, learning_form


@app.cell
def _(DEFAULT_DB, evolve, learning_form, mo, workspace):
    mo.stop(learning_form.value is None)
    learning_result=None
    learning_error=None
    try:
        learning_result=evolve(db_path=DEFAULT_DB,output_dir=workspace/'artifacts'/'continual-studio'/'learning',cloud=bool(learning_form.value['cloud']))
    except Exception as _error:
        # Provider exception text can contain request details; show the failure type only.
        learning_error=f"Learning task failed ({type(_error).__name__}); no success is claimed. Review the local development run."
    return learning_error, learning_result


@app.cell
def _(learning_error, learning_result, mo):
    mo.stop(learning_error is not None,mo.callout(learning_error or "",kind="danger"))
    mo.stop(learning_result is None)
    mo.vstack([mo.md("### Executed development learning result"),
        mo.json({k:learning_result[k] for k in ('task_id','learned_this_task','reused_persisted_skills','comparisons','discovery_cad_trials','duration_seconds','evidence_scope') if k in learning_result}),
        mo.callout("Improvements here are measured in ideal CAD geometry. Physical printer offsets and manufactured fit remain uncalibrated.",kind="info")])
    return


@app.cell
def _(DEFAULT_DB, audit_refresh, json, mo, sqlite3):
    audit_refresh.value
    _rows=[];_events=[];_counts={};_audit_error=None
    if DEFAULT_DB.exists():
        try:
            with sqlite3.connect(DEFAULT_DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as _db:
                for _table in ('experiments','candidates','promotions','quarantines','events'):
                    _counts[_table]=_db.execute('SELECT COUNT(*) FROM '+_table).fetchone()[0]
                for _id,_name,_payload,_quarantined in _db.execute('SELECT c.id,c.name,c.payload,q.candidate FROM candidates c JOIN promotions p ON p.candidate=c.id LEFT JOIN quarantines q ON q.candidate=c.id ORDER BY p.created DESC LIMIT 30'):
                    _data=json.loads(_payload)
                    _rows.append({'name':_name,'version':_id[:16],
                        'status':'quarantined' if _quarantined else 'promoted',
                        'commands':json.dumps(_data.get('skill',{}).get('commands',[])),
                        'parents':', '.join(i[:12] for i in _data.get('skill',{}).get('parent_ids',[]))})
                _events=[{'sequence':s,'event':e,'created_unix':t} for s,e,t in _db.execute('SELECT sequence,event,created FROM events ORDER BY sequence DESC LIMIT 20')]
        except Exception as _error:
            _audit_error=f"Read-only audit unavailable ({type(_error).__name__})."
    mo.vstack([mo.md("### Local learning audit · read-only view"),
        mo.callout(_audit_error,kind="warn") if _audit_error else mo.json(_counts),
        mo.ui.table(_rows,selection=None) if _rows else mo.md("No promoted commands visible yet. Run a learning task, then refresh this audit."),
        mo.accordion({'Recent audit events':mo.ui.table(_events,selection=None) if _events else mo.md('No events yet.')}),
        mo.md("Refresh after a learning task to see committed updates. This panel opens SQLite in read-only mode and shows no credentials or hidden benchmark cases.")])
    return


@app.cell
def _(audit_refresh, mo, workspace):
    from cadforge.development_status import development_status
    audit_refresh.value
    _status=development_status(workspace)
    _comparison=_status.get('comparison',{})
    _production=_status.get('production',{})
    mo.vstack([
        mo.md("### Latest retained development evidence"),
        mo.md("This read-only panel checks the comparison summary against its attempt records. Latest failures remain visible; it does not select only successful runs."),
        mo.callout(_comparison['error'],kind='danger') if 'error' in _comparison else
            mo.ui.table(_comparison.get('rows',[]),selection=None),
        mo.md(_comparison.get('scope','No comparison run is available.')),
        mo.md("**Prior tool-pocket run costs** · These are separate executions, including discovery and validation. Online comparison counts above exclude this prior work. Authoring costs are not fully metered."),
        mo.ui.table(_status['tool_access_runs'],selection=None),
        mo.md("**Latest product assessment** · Explicit assumptions differ between packages; geometric passes do not establish physical production readiness."),
        mo.json(_production),
    ])
    return


if __name__ == "__main__":
    app.run()
