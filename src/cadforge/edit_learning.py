"""Persist already executed region-repair outcomes; recommend validated priority.

No geometry is executed here. Preview owns the checks and rollback; this store
records its actual trials and learns a narrowly scoped strategy ordering.
"""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

import numpy as np

DEFAULT_STORE = Path.home() / ".local/share/cadforge/region-learning.json"
_lock = threading.RLock()


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validator_context():
    from . import region_edit
    return hashlib.sha256(Path(region_edit.__file__).read_bytes()).hexdigest()


@contextmanager
def _store(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            state = json.loads(path.read_text()) if path.exists() else {"version": 2, "evidence": [], "skills": [], "quarantines": []}
            state.setdefault("quarantines", [])
            yield state
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _save(path, state):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def _quarantined_families(state):
    """A new evidence-derived ID cannot erase an unresolved counterexample."""
    quarantined = {q['skill_id'] for q in state['quarantines']}
    families = {(s.get('context'), s.get('axis'), s.get('strategy'))
                for s in state['skills'] if s['id'] in quarantined}
    # Counterexamples observed before the first promotion count too. Rigid
    # commands have a different contract and never qualify transition priority.
    for evidence in state['evidence']:
        command = evidence.get('command', {})
        if command.get('op') != 'translate' or command.get('translation_mode') == 'rigid':
            continue
        for trial in evidence.get('trials', []):
            strategy = trial.get('strategy', '')
            if strategy.startswith('interior_transition') and trial.get('accepted') is False:
                families.add((evidence.get('context'), command.get('axis'), strategy))
    return families


def recommend(command, *, path=DEFAULT_STORE):
    context = validator_context()
    if command.get("op") != "translate" or command.get("translation_mode") == "rigid":
        return {"strategy": None, "skill_id": None, "context": context}
    with _store(path) as state:
        quarantined = {q["skill_id"] for q in state["quarantines"]}
        families = _quarantined_families(state)
        for skill in reversed(state["skills"]):
            if (skill.get("context") == context and skill.get("axis") == command.get("axis")
                    and skill["id"] not in quarantined
                    and (context, command.get('axis'), skill['strategy']) not in families):
                return {"strategy": skill["strategy"], "skill_id": skill["id"], "context": context}
    return {"strategy": None, "skill_id": None, "context": context}


def history(*, path=DEFAULT_STORE):
    """Expose retained skills separately from their current reuse eligibility."""
    context = validator_context()
    with _store(path) as state:
        families = _quarantined_families(state)
        skills = []
        for skill in state['skills']:
            if skill.get('context') != context:
                continue
            quarantined = (context, skill.get('axis'), skill.get('strategy')) in families
            skills.append({**skill, 'eligible_for_reuse':not quarantined,
                           'current_status':'quarantined' if quarantined else 'eligible'})
        return {'context':context, 'skills':skills, 'quarantines':state['quarantines'],
                'evidence':[{k:e.get(k) for k in ('id','session_id','preview_id','command','trials','actual_correction','used_skill_id','created','topology','accepted')}
                            for e in state['evidence'] if e.get('context') == context]}


def record_executed(mesh, command, region, trials, accepted, *, session_id, preview_id,
                    hint=None, error=None, path=DEFAULT_STORE, quarantine_only=False):
    """Record a preview once, including failed attempts; never repeat execution."""
    hint = hint or {"context": validator_context(), "skill_id": None, "strategy": None}
    context = hint["context"]
    fingerprint = hashlib.sha256(np.asarray(mesh.vertices).tobytes() + np.asarray(mesh.faces).tobytes()).hexdigest()
    # Different coordinate hashes alone do not qualify small changes to one
    # object as independent topology transfer. This is still a narrow heuristic.
    topology = {"vertices": len(mesh.vertices), "faces": len(mesh.faces), "euler": int(mesh.euler_number)}
    chosen = next((t["strategy"] for t in trials if t.get("accepted")), None)
    failure_seen = False
    corrected = False
    for trial in trials:
        if not trial.get("accepted"):
            failure_seen = True
        elif failure_seen and trial["strategy"] != "sharp":
            corrected = True
            break
    required = {"outside_vertices_exact", "triangle_indices_preserved", "finite_vertices",
                "watertight_positive_volume", "no_collapsed_faces", "no_flipped_faces",
                "no_detected_triangle_intersection", "requested_peak_translation"}
    winner = next((t for t in trials if t.get("accepted")), None)
    measured_success = bool(accepted and winner and
                            required <= {c["name"] for c in winner["checks"] if c["passed"]} and
                            all(c["passed"] for c in winner["checks"]))
    corrected = bool(corrected and measured_success and command.get("op") == "translate")
    evidence = {"session_id": session_id, "preview_id": preview_id, "mesh_sha256": fingerprint,
                "topology": topology, "command": command, "region": region, "context": context,
                "trials": trials, "accepted": bool(accepted), "actual_correction": corrected,
                "measured_success": measured_success, "chosen_strategy": chosen,
                "used_skill_id": hint.get("skill_id"), "error": error, "created": time.time()}
    evidence["id"] = _digest(evidence)
    status, saved, promoted_id = "recorded", None, None
    with _store(path) as state:
        if quarantine_only:
            known = next((s for s in state['skills'] if s['id'] == hint.get('skill_id')
                          and s.get('context') == context and s.get('axis') == command.get('axis')
                          and s.get('strategy') == hint.get('strategy')), None)
            preferred = next((t for t in trials if t['strategy'] == hint.get('strategy')), None)
            if known is None or preferred is None or preferred.get('accepted'):
                return {'status':'not_persisted', 'narrative':'No executed counterexample to a persistent strategy was found.'}
        existing=next((e for e in state['evidence'] if e.get('preview_id')==preview_id and e.get('session_id')==session_id),None)
        receipt_key=f'{session_id}:{preview_id}'
        if existing is not None:
            fields=('mesh_sha256','command','region','context','trials','accepted','used_skill_id','error')
            if any(existing.get(k)!=evidence.get(k) for k in fields):
                raise ValueError('Conflicting evidence for an already recorded preview')
            return {**state.get('receipts',{}).get(receipt_key,{'status':'already_recorded','attempts':len(trials),'evidence_id':existing['id'],'context':context}),
                    'deduplicated':True,'narrative':'This exact preview outcome was already recorded. No geometry or learning promotion was repeated.'}
        state["evidence"].append(evidence)
        if hint.get("skill_id"):
            preferred = next((t for t in trials if t["strategy"] == hint["strategy"]), None)
            if not preferred or not preferred.get("accepted") or not measured_success:
                state["quarantines"].append({"skill_id": hint["skill_id"], "evidence_id": evidence["id"],
                                             "reason": "Preferred repair failed full preview checks"})
                status = "quarantined"
            else:
                status, saved = "reused", hint["strategy"]
        unresolved = (context, command.get('axis'), chosen) in _quarantined_families(state)
        if corrected and status != 'quarantined' and unresolved:
            status = 'quarantined_family'
        if corrected and not quarantine_only and status not in ('quarantined', 'quarantined_family'):
            support = [e for e in state["evidence"] if e.get("actual_correction")
                       and e.get("context") == context and e.get("chosen_strategy") == chosen
                       and e["command"].get("axis") == command.get("axis")]
            diverse = (len({e["mesh_sha256"] for e in support}) >= 2 and
                       len({e.get("session_id") for e in support}) >= 2 and
                       len({_digest(e["topology"]) for e in support}) >= 2)
            if diverse:
                skill = {"operation": "translate", "axis": command["axis"], "strategy": chosen,
                         "context": context, "evidence_ids": [e["id"] for e in support],
                         "supporting_mesh_count": len({e["mesh_sha256"] for e in support}),
                         "scope": "Priority for a peak-displacement interior transition; all preview checks still mandatory."}
                skill["id"] = _digest(skill)
                if not any(s["id"] == skill["id"] for s in state["skills"]):
                    state["skills"].append(skill)
                status, saved, promoted_id = "promoted", chosen, skill["id"]
            else:
                status = "candidate"
        elif not accepted and status == "recorded":
            status = "failed_recorded"
        state.setdefault('receipts',{})[receipt_key]={'status':status,'attempts':len(trials),
            'saved_strategy':saved,'selected_strategy':chosen,'skill_id':promoted_id or hint.get('skill_id'),
            'evidence_id':evidence['id'],'context':context}
        _save(path, state)
    attempts = len(trials)
    narratives = {
        "candidate": "A rejected sharp edit was corrected by a validated interior transition. Saved as a candidate; independent topology/session transfer is still required.",
        "promoted": "The same repair corrected failures on distinct mesh topologies in separate sessions. Saved its strategy priority for later previews.",
        "reused": f"Reused a previously validated strategy priority. This preview passed all checks in {attempts} attempt(s).",
        "quarantined": "The saved strategy failed current checks and was quarantined. The failed evidence is retained.",
        "quarantined_family": "This edit passed, but the same strategy has an unresolved counterexample in this validator context. Evidence was saved without promoting its priority again.",
        "failed_recorded": "All attempted repairs failed. The original geometry is retained and failed trials were saved.",
        "recorded": "Saved the measured preview outcome; this edit did not establish a new learned rule.",
    }
    transition = bool(chosen and chosen.startswith("interior_transition"))
    return {"status": status, "attempts": attempts, "saved_strategy": saved,
            "trial_summary": [{"strategy": t["strategy"], "accepted": t.get("accepted", False),
                               "failed_checks": [c["name"] for c in t.get("checks", []) if not c["passed"]]}
                              for t in trials],
            "selected_strategy": chosen, "skill_id": promoted_id or hint.get("skill_id"),
            "evidence_id": evidence["id"], "context": context, "store": str(Path(path).resolve()),
            "narrative": narratives[status], "transition_semantics": transition,
            "semantics": "Requested displacement is reached at the interior peak; other selected vertices move less. This is not a rigid translation of the entire selected region." if transition else "Sharp edit of selected vertices.",
            "limits": "Local mesh-strategy transfer only; coordinate hashes/topology counts do not prove broad generalization or mechanical validity."}
