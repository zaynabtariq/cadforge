"""Local audit events, with opt-in Weave tracing of public development work."""
from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock

_lock = Lock()

def record(path: Path, event: str, **payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, path.open('a') as stream:
        stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), 'event': event, **payload}, default=str) + '\n')

def enable_weave(project: str | None = None):
    """Explicit opt-in only. Never call from sealed evaluation."""
    project = project or os.getenv('CADFORGE_WEAVE_PROJECT')
    if not project:
        return {'enabled': False, 'reason': 'CADFORGE_WEAVE_PROJECT not configured'}
    if not os.getenv('WANDB_API_KEY'):
        return {'enabled': False, 'reason': 'WANDB_API_KEY not configured'}
    import weave
    weave.init(project)
    return {'enabled': True, 'project': project}

def trace_development(fn):
    if os.getenv('CADFORGE_WEAVE_PROJECT') and os.getenv('WANDB_API_KEY'):
        import weave
        return weave.op()(fn)
    return fn
