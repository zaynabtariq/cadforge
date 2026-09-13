# Persistent experimental learning

`cadforge.continual.ContinualLearning` persists measured development experiments, affine command hypotheses, inheritance dependencies, held-out development evidence, immutable promotions, and regression quarantines in SQLite. It is a reusable learning service across tasks; it does not silently ingest the frozen v1 benchmark or its test cases.

## What is learned

`propose_affine()` fits the relation

```text
measured_target = intercept + factor_1 * source_1 + ... + factor_n * source_n
```

The target comes from the execution callback's `Measurement.measurements[target_parameter]`, not from the planner's proposed value. For a bore, an execution callback can search candidate bore sizes, run a screw swept-volume collision check at each size, and return the smallest successful measured size. Discovery must include at least one diagnosed failure. The service requires at least `source_count + 2` distinct development experiments, full-rank inputs, identical context and a maximum absolute residual within the declared tolerance. It rejects underdetermined or inconsistent affine hypotheses.

The learned factors become existing `ParameterCommand` objects: a target `set` for the intercept followed by `add` commands referencing source parameters. This supports relationships such as a hardware diameter plus twice a radial clearance, an outer boss diameter derived from bore diameter and wall thickness, or a sum of separately measured clearance allowances. Such relations are examples, not hard-coded regression answers.

The deterministic fitter does not establish causality, discover arbitrary programs, or prove a universal engineering law. Inputs must be deliberately varied and measurements independent of the proposed repair. A future model can propose experiment dimensions and hypotheses; promotion still requires the same executed evidence. Synthetic callbacks in unit tests verify the service mechanics only and are not physical or BRep evidence.

## API and lifecycle

```python
from cadforge.continual import Case, Context, Measurement, ContinualLearning

service = ContinualLearning("artifacts/continual/learning.sqlite")
context = Context(
    environment="ideal CAD geometry on the recorded host",
    material="geometric fit only; no calibrated manufacturing process",
    tool_versions={"cadquery": "RECORD_INSTALLED_VERSION"},
    validator_version="SHA256_OR_VERSION_OF_EXECUTED_VALIDATOR",
    recipe_version="SHA256_OR_VERSION_OF_EXECUTED_RECIPE",
)

# execute(parameters, case_id) must run the CAD experiment/checks and return:
# Measurement(passed, measurements, failure_codes, checks, artifact_digests)
# Store all search trials separately and include their SHA256 artifact digest.
experiment_id = service.run_experiment(
    Case("unique-dev-case", "source-task", parameters, history_digest),
    execute, stage="discovery", context=context,
)

# Collect at least n+2 independently varied discovery measurements first.
candidate_id = service.propose_affine(
    "drill_clearance", "bore_diameter",
    ["fastener_diameter", "radial_clearance"], experiment_ids,
    tolerance=1e-6,
)
service.validate_candidate(candidate_id, challenge_cases, execute,
                           stage="counterexample", context=context)
service.validate_candidate(candidate_id, heldout_development_cases, execute,
                           stage="transfer", context=context)
skill = service.promote(candidate_id)
parameters = service.apply("drill_clearance", new_parameters, context=context)
service.close()
```

The sequence is discovery → candidate → counterexample challenge → held-out development transfer → promotion. The counterexample stage must precede transfer. At least one challenge and two transfer cases must pass; transfer task IDs must differ from discovery task IDs. Case IDs cannot be reused from discovery, prior validation, or an inherited parent's discovery/validation. Each case includes a SHA256 task-history digest. These identity checks require the orchestrator to assign honest task/case labels; merely renaming a known example does not make it an independent transfer.

`Measurement.checks` must contain executed boolean checks; `passed` must equal their conjunction, and failure codes must agree. Exceptions and malformed callback results are stored as failed experiments. The service never converts an exception into a pass. An optional `artifact_digests` mapping records filenames/identifiers and SHA256 values for the callback's retained trials and geometry. The service records these references but does not itself verify external artifact bytes.

## Inheritance and reuse

Pass `parent_ids=(previous_skill_id,)` to `propose_affine()` when a new fitted operation uses a previous command's output. For example, a boss command can inherit the bore command. Alternatively:

```python
combined_id = service.propose_composition(
    "drilled_mount", [bore_skill_id, boss_skill_id], new_discovery_experiment_ids,
)
```

A composition introduces no new numeric fit. It learns an ordered inherited recipe whose compatibility must pass fresh challenge and transfer checks. Parents must already be promoted and healthy in the same environment/material/tool context. Only earlier stored versions can be parents, preventing new cycles; execution also checks cycles and executes a shared ancestor once. Composition does not automatically satisfy a new design family: the execution callback must validate its actual artifacts.

`apply()` selects the latest healthy promoted version by name in the exact recorded context. It rejects source values outside each operation's observed discovery ranges, including inherited operations. These are marginal observed ranges, not proof that every combination inside the bounding box works. New geometry, loads, manufacturing behavior and unseen interactions still require executed checks. `allow_extrapolation=True` is explicit exploratory behavior and must not be reported as validated production reuse. A context change requires a newly discovered and validated version.

## Regressions, persistence and audit

`latest_id(name, context=context)` resolves the active persistent version for monitoring, with the same healthy/context selection rules as `apply()`.

Use `validate_candidate(..., stage="monitor")` on fresh development cases after promotion. The first failed challenge, transfer, or monitor experiment quarantines that version and its transitive descendants; the remaining cases in that call are not executed. Reuse then falls back to the previous healthy promoted version with the same name and context, if one exists. If none exists, `apply()` fails. `quarantine(skill_id, reason)` also supports an explicit evidence-backed rollback. Quarantined versions are never silently reinstated or edited; create a new version with the new evidence.

SQLite contains `experiments`, `candidates`, `dependencies`, `validations`, `promotions`, `quarantines` and ordered `events`. Experiments have content hashes; candidate IDs use the existing immutable `SkillLibrary` content hash, incorporating experiment-linked evidence. Database triggers reject updates/deletes to experiments, candidates and promotion snapshots. SQLite transactions and WAL preserve completed records across restarts. Use one service instance per process/thread. `audit()` reports record counts; token costs, physical trial costs and rich experiment-search ledgers belong to the execution orchestrator and should be linked as hashed artifacts.

This is a local provenance contract, not an operating-system security boundary. A caller with database/file access can defeat local controls. `split` must be `development` and `corpus` must be `continual-development`; hidden or v1 ingestion is rejected before callback execution. The orchestrator must continue to keep sealed benchmark material outside discovery callbacks and external tracing. Neither affine fit success nor ideal-CAD transfer certifies production readiness: manufacturing calibration, vendor dimensions, load/thermal performance and physical assembly remain independent evidence requirements.
