"""W&B development tracing with credentials kept out of CAD specifications."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys

SETTINGS=Path.home()/'.config'/'cadforge'/'settings.json'

def credential():
    from .telemetry import load_env
    load_env()
    if os.getenv('WANDB_API_KEY'):
        return os.environ['WANDB_API_KEY']
    if sys.platform=='darwin':
        r=subprocess.run(['security','find-generic-password','-a','cadforge','-s','cadforge-wandb','-w'],capture_output=True,text=True)
        if r.returncode==0:
            return r.stdout.strip()
    raise RuntimeError('W&B credential unavailable in environment or CADForge Keychain entry')

def init_development(project=None):
    """Explicit development entry point. Never called by archived heldout evaluator."""
    from .telemetry import load_env
    load_env()
    if project is None and SETTINGS.exists():
        project=json.loads(SETTINGS.read_text()).get('weave_project')
    project=project or os.getenv('CADFORGE_WEAVE_PROJECT')
    if not project:
        raise RuntimeError('Set CADFORGE_WEAVE_PROJECT or local CADForge settings')
    os.environ['WANDB_API_KEY']=credential()
    import weave
    client=weave.init(project)
    return client

def settings():
    return json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
