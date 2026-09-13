"""Bounded local evaluation workers. Process isolation is not a security sandbox."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


@dataclass(frozen=True)
class WorkerResult:
    status: str
    elapsed_seconds: float
    returncode: int
    report: dict | None
    output_bytes: int


def _strict_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate report key')
        result[key]=value
    return result


def _invalid_constant(value):
    raise ValueError('Nonfinite report number')


def run_worker(argv, request, *, timeout_seconds, cwd, env, maximum_output_bytes=1_000_000):
    """Run a trusted worker command with one JSON input and one JSON report.

    Caller supplies the complete environment and command; neither is generated
    from model output. No hidden report content is logged here. Wall timeout is
    enforced for the worker process group. Token/tool accounting remains the
    worker's separate responsibility. Output size is checked before JSON load.
    """
    if not math.isfinite(timeout_seconds) or timeout_seconds<=0:
        raise ValueError('Positive finite worker deadline required')
    if type(maximum_output_bytes) is not int or maximum_output_bytes<=0:
        raise ValueError('Positive output byte limit required')
    if not isinstance(argv,(list,tuple)) or not argv or not all(isinstance(x,str) for x in argv):
        raise ValueError('Explicit worker argument list required')
    payload=json.dumps(request,allow_nan=False).encode()
    if len(payload)>1_000_000:raise ValueError('Worker request exceeds input limit')
    started=time.monotonic()
    with tempfile.TemporaryFile() as incoming, tempfile.TemporaryFile() as outgoing, tempfile.TemporaryFile() as errors:
        incoming.write(payload);incoming.seek(0)
        process=subprocess.Popen(argv,cwd=Path(cwd),env=dict(env),stdin=incoming,
            stdout=outgoing,stderr=errors,start_new_session=True)
        expired=False
        try:
            process.wait(timeout=max(0,timeout_seconds-(time.monotonic()-started)))
        except subprocess.TimeoutExpired:
            expired=True
        finally:
            # Also reap descendants after a worker exits normally; a lingering
            # CAD subprocess must not consume the next case's resource budget.
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait()
        elapsed=time.monotonic()-started
        size=outgoing.tell()+errors.tell()
        if expired:return WorkerResult('timeout',elapsed,process.returncode,None,size)
        if size>maximum_output_bytes:return WorkerResult('output_limit',elapsed,process.returncode,None,size)
        if process.returncode!=0:return WorkerResult('worker_failed',elapsed,process.returncode,None,size)
        outgoing.seek(0)
        try:report=json.load(outgoing,parse_constant=_invalid_constant,object_pairs_hook=_strict_object)
        except (ValueError,UnicodeDecodeError):return WorkerResult('invalid_report',elapsed,process.returncode,None,size)
        if not isinstance(report,dict):return WorkerResult('invalid_report',elapsed,process.returncode,None,size)
        return WorkerResult('completed',elapsed,process.returncode,report,size)
