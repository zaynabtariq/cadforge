"""Run the objective-focused recurring checks and emit a single evidence bundle."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from json import JSONDecoder


ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv/bin/python"
OUT_DIR = ROOT / "artifacts" / "objective-audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str], *, env=None, timeout=180):
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - started
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_seconds": elapsed,
    }


def _load_json(path: str):
    data = json.loads(Path(path).read_text())
    return data


def _parse_last_json_text(output: str):
    """Return the last complete top-level JSON object in arbitrary mixed output.

    Some scripts print banner text or debug logs before/after JSON. This parser
    tolerates that and returns the last valid object by scanning for the start of
    object delimiters.
    """
    text = output.strip()
    if not text:
        raise ValueError("No JSON object found in output")

    decoder = JSONDecoder()
    last_payload = None
    # Fast path: most scripts print a single JSON payload at the top.
    try:
        parsed, end = decoder.raw_decode(text)
        if end == len(text) or text[end:].strip() == "":
            return parsed
    except json.JSONDecodeError:
        pass

    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[i:])
            if isinstance(parsed, dict) and (i + end == len(text) or text[i + end :].strip() == ""):
                last_payload = parsed
                # Continue scanning in case an earlier parse is overwritten by a later
                # full JSON payload (for scripts that stream multiple objects).
                # Ignore the end position; continue at i+1 to catch subsequent objects.
        except json.JSONDecodeError:
            continue
    if last_payload is None:
        raise ValueError("No JSON object found in output")
    return last_payload
def objective_audit():
    started = datetime.now(timezone.utc).isoformat()
    results = {
        "started_at": started,
        "runs": {},
    }

    # Public strategy comparison (no model calls).
    region = _run([str(PYTHON), "scripts/evaluate_region_contract_transfer.py"], timeout=240)
    results["runs"]["region_contract_transfer"] = region
    region_summary = None
    if region["returncode"] == 0:
        try:
            region_summary = _parse_last_json_text(region["stdout"])
            if "path" in region_summary:
                contract_path = ROOT / region_summary["path"] / "results.json"
                if contract_path.exists():
                    region_summary["results_file"] = str(contract_path)
                    region_summary["results"] = _load_json(str(contract_path))
        except (json.JSONDecodeError, ValueError):
            region_summary = {"parse_error": "json decode failed", "raw": region["stdout"]}
    results["runs"]["region_contract_transfer"]["summary"] = region_summary

    access = _run([str(PYTHON), "scripts/evaluate_access_retrieval.py"], timeout=240)
    results["runs"]["access_retrieval"] = access
    access_summary = None
    if access["returncode"] == 0:
        try:
            access_summary = _parse_last_json_text(access["stdout"])
            if "directory" in access_summary:
                summary_path = ROOT / access_summary["directory"] / "summary.json"
                if summary_path.exists():
                    access_summary["summary_file"] = str(summary_path)
                    access_summary["summary"] = _load_json(str(summary_path))
        except (json.JSONDecodeError, ValueError):
            access_summary = {"parse_error": "json decode failed", "raw": access["stdout"]}
    results["runs"]["access_retrieval"]["summary"] = access_summary

    tool_access = _run([str(PYTHON), "scripts/learn_tool_access.py"], timeout=120)
    results["runs"]["tool_access"] = tool_access
    tool_access_summary = None
    if tool_access["returncode"] == 0:
        try:
            tool_access_summary = _parse_last_json_text(tool_access["stdout"])
            results["runs"]["tool_access"]["summary"] = tool_access_summary
        except (json.JSONDecodeError, ValueError):
            results["runs"]["tool_access"]["summary"] = {"parse_error": "json decode failed", "raw": tool_access["stdout"]}

    evolve = _run([str(PYTHON), "-m", "cadforge.evolve"], timeout=120)
    results["runs"]["evolve"] = evolve
    if evolve["returncode"] == 0:
        try:
            results["runs"]["evolve"]["summary"] = _parse_last_json_text(evolve["stdout"])
        except (json.JSONDecodeError, ValueError):
            pass

    tests = _run([str(PYTHON), "-m", "pytest", "-q", "tests/test_learning.py", "tests/test_learning_recovery.py", "tests/test_region_edit.py", "tests/test_protected_edit.py", "--maxfail=1"], timeout=240)
    results["runs"]["tests"] = tests

    marimo = _run([str(PYTHON), "-m", "marimo", "check", "notebooks/continual_studio.py"], timeout=180)
    results["runs"]["marimo_continual"] = marimo

    # Compute a compact scorecard for the objective run.
    score = {
        "status": "in_progress",
        "self_correction_observed": False,
        "equal_budget_trials": None,
        "discovered_improvement": None,
    }
    if results["runs"]["region_contract_transfer"].get("summary"):
        arm = results["runs"]["region_contract_transfer"]["summary"].get("arms", {})
        if all(isinstance(v, dict) for v in arm.values()):
            score["equal_budget_trials"] = {k: v.get("candidate_trials") for k, v in arm.items()}
            score["self_correction_observed"] = arm.get("learned_priority", {}).get("accepted", 0) >= arm.get("retrieved_transition_script", {}).get("accepted", 0)
    if results["runs"]["tool_access"].get("summary") and isinstance(results["runs"]["tool_access"]["summary"], dict):
        comparison = results["runs"]["tool_access"]["summary"].get("comparisons", {})
        learned_trials = comparison.get("learned", {}).get("cad_trials") if isinstance(comparison, dict) else None
        no_skill_trials = comparison.get("no_skills", {}).get("cad_trials") if isinstance(comparison, dict) else None
        if learned_trials is not None and no_skill_trials is not None:
            score["discovered_improvement"] = (learned_trials <= no_skill_trials)

    if all(r["returncode"] == 0 for r in (marimo, tests, evolve, access, tool_access, region)):
        score["status"] = "ok"

    results["scorecard"] = score
    output = OUT_DIR / f"objective-audit-{int(time.time())}.json"
    output.write_text(json.dumps(results, indent=2))
    return {
        "output": str(output),
        "scorecard": score,
    }


if __name__ == "__main__":
    print(json.dumps(objective_audit(), indent=2))
