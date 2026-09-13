"""Execute persisted learned fit on a new robot link and trace measured edits."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import time
import uuid

from cadforge.cloud import init_development
from cadforge.continual import Case, ContinualLearning
from cadforge.evolve import DEFAULT_DB, context
from cadforge.robotics import (
    RobotLinkSpec, apply_learned_fit, build_link, export_link,
    measure_link, robot_fit_executor, widen_link,
)
import cadforge.robotics as robotics_module


def run(database: Path = DEFAULT_DB, output: Path = Path("artifacts/robot-transfer")):
    client = init_development()
    import weave

    task_id = "robot-transfer-" + uuid.uuid4().hex[:12]
    destination = output / task_id
    destination.mkdir(parents=True, exist_ok=True)
    service = ContinualLearning(database)
    learned_context = context()
    before_audit = service.audit()
    code_digests = {str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    str(Path(robotics_module.__file__).resolve()): hashlib.sha256(Path(robotics_module.__file__).read_bytes()).hexdigest()}
    prior_failures = []
    for artifact in output.glob("*/widen-30/change-*.json"):
        data = json.loads(artifact.read_text())
        if not data["accepted"]:
            prior_failures.append({"artifact": str(artifact.resolve()), "error": data["error"],
                                   "checks": data["checks"]})

    @weave.op()
    def robot_transfer_run(task_id: str) -> dict:
        started = time.monotonic()
        active_id = service.latest_id("supported_fastener", context=learned_context)
        original_spec = RobotLinkSpec(min_edge_distance=1.5)
        parameters = {"fastener_diameter": 2.5, "radial_clearance": .15, "min_wall": 1.5,
                      "bore_diameter": original_spec.pivot_diameter,
                      "boss_outer_diameter": original_spec.boss_outer_diameter}
        fitted = apply_learned_fit(original_spec, service, learned_context,
                                   hardware_diameter=2.5, radial_clearance=.15, min_wall=1.5)
        callback = robot_fit_executor(original_spec, destination / "fit-evidence")

        @weave.op()
        def measured_robot_fit(parameters: dict, case_id: str):
            measured = callback(parameters, case_id)
            return replace(measured, artifact_digests=measured.artifact_digests | code_digests)

        history = {"task": task_id, "request": "Apply persisted bore/boss factors to a two-pivot robot link, widen 20 to 30 mm preserving 80 mm pivot spacing; reject width 50 mm.",
                   "source_skill": active_id, "code_digests": code_digests, "parameters": parameters}
        history_digest = hashlib.sha256(json.dumps(history, sort_keys=True).encode()).hexdigest()
        (destination / "task-history.json").write_text(json.dumps(history, indent=2) + "\n")
        case = Case(task_id + "-robot-fit", task_id, parameters, history_digest)
        experiment_ids = service.validate_candidate(active_id, [case], measured_robot_fit,
                                                     stage="monitor", context=learned_context)
        fit_payload = service._payload("experiments", experiment_ids[0])
        if not fit_payload["measurement"]["passed"]:
            raise RuntimeError("Robot fit failed; persisted skill quarantined. See SQLite experiment " + experiment_ids[0])
        before = build_link(fitted)
        before_paths = export_link(before, destination / "before")
        widened = widen_link(before, 30., output_dir=destination / "widen-30")
        if not widened.accepted:
            raise RuntimeError("Width transfer failed: " + str(widened.error))
        rejected = widen_link(widened.active_link, 50., output_dir=destination / "reject-50")
        rollback_ok = not rejected.accepted and rejected.active_link.version_id == widened.active_link.version_id
        if not rollback_ok:
            raise RuntimeError("Out-of-envelope width did not roll back")
        return {
            "task_id": task_id, "database": str(database.resolve()),
            "source_skill_id": active_id, "new_skills_trained": 0,
            "persistent_robot_experiment_ids": experiment_ids,
            "fit_passed": fit_payload["measurement"]["passed"],
            "fit_checks": fit_payload["measurement"]["checks"],
            "fit_measurements": fit_payload["measurement"]["measurements"],
            "artifact_digest_count": len(fit_payload["measurement"]["artifact_digests"]),
            "fitted_spec": asdict(fitted), "before": asdict(measure_link(before.shape)),
            "after": asdict(widened.after), "widen_accepted": widened.accepted,
            "widen_checks": widened.checks,
            "before_version": before.version_id, "after_version": widened.active_link.version_id,
            "rejected_width": 50., "rejection_reason": rejected.error,
            "rollback_preserved_version": rollback_ok,
            "before_exports": before_paths,
            "widen_exports_directory": str((destination / "widen-30" / widened.active_link.version_id).resolve()),
            "before_audit": before_audit, "after_audit": service.audit(),
            "source_learning_context": asdict(learned_context),
            "transfer_execution_code_digests": code_digests,
            "duration_seconds": time.monotonic() - started,
            "model_requests": 0, "model_tokens": 0,
            "production_ready": False,
            "scope": "Actual two-pivot robot-link BRep transfer and width invariants. No dynamics, manufacturing calibration, strength, fatigue, or universal-object claim.",
            "prior_failed_width_operations": prior_failures,
        }

    try:
        summary, call = robot_transfer_run.call(task_id)
        client.flush()
        recorded = client.get_call(call.id)
        if summary is None:
            failed = {"task_id": task_id, "passed": False, "error": recorded.exception,
                      "weave_call_id": call.id, "server_readback_verified": recorded.id == call.id,
                      "database_audit": service.audit(), "code_digests": code_digests}
            (destination / "summary.json").write_text(json.dumps(failed, indent=2) + "\n")
            (output / "latest.json").write_text(json.dumps(failed, indent=2) + "\n")
            raise RuntimeError("Robot transfer failed; retained trace and summary: " + str(recorded.exception))
        summary["weave"] = {"call_id": call.id, "server_readback_verified": recorded.id == call.id,
                            "server_exception": recorded.exception}
        if recorded.id != call.id or recorded.exception:
            raise RuntimeError("Weave transfer trace readback failed")
        (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        (output / "latest.json").write_text(json.dumps(summary, indent=2) + "\n")
        return summary
    finally:
        service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=Path("artifacts/robot-transfer"))
    args = parser.parse_args()
    print(json.dumps(run(args.database, args.output), indent=2))
