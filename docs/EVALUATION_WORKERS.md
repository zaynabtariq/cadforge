# Enforced evaluation workers

`evaluation_process.run_worker` launches an explicitly supplied trusted command with one JSON request, an explicitly supplied environment, and a bounded deadline. It kills the worker process group when the deadline expires, and also cleans up lingering group descendants after normal completion. Reports distinguish completion, timeout, worker failure, oversized output and invalid JSON. Duplicate keys and nonfinite JSON constants are invalid. Raw worker output is not automatically logged.

Nine real-process tests pass. They check environment isolation, timeout cleanup, cleanup after successful parent exit, invalid/non-object reports, duplicate keys, NaN, nonzero exit and oversized output. These are harness tests rather than benchmark design cases.

The public CAD smoke in `scripts/check_evaluation_worker.py` ran the checked public plate recess successfully in 0.8882 seconds with seven geometry checks. The same worker under a 0.01-second deadline was killed after 0.01018 seconds and published no report. Actual records are in `artifacts/evaluation-worker/public-cad-smoke.json`.

This is new infrastructure for the proposed V2 evaluation. It does not modify the archived V1 checker or rerun hidden cases. Deadline cleanup has scheduling overhead and is not an exact real-time guarantee. A process group is not a filesystem/network/security sandbox; a deliberately escaping process requires stronger containment. Output bytes are limited before parsing, not by a hard disk quota. Token, model-request, CAD-attempt, memory and tool limits need separate enforcement in the future agent runner. The proposed benchmark remains unfrozen and unexecuted.

## Candidate accounting

`ExecutionBudget` adds atomic pre-execution charges with a context shared by nested synchronous work. A nested helper cannot replace the active allowance with a fresh budget. Workspace operations and individual region-repair candidates now charge before execution; speculative sequences inherit that same counter. Actual charges and denied attempts are reported separately.

Real geometry tests show a one-candidate sphere edit stopping after its rejected sharp attempt, while two candidates allow the checked repair. The stopped preview retains the actual first trial and original geometry, but does not train on unattempted strategies. A two-step sequence with one candidate available also rolls back without resetting its budget. The combined accounting, learning, composition and recovery suites pass 23 tests.

Coverage is not yet sufficient to freeze V2: individual Boolean repair passes inside other kernels, model requests/tokens, general tool calls and cross-process subagent aggregation still need instrumentation and audits. These counters are not a hostile-code security boundary. The region source change also changes its conservative validator fingerprint, so earlier persisted region strategy priorities are stale until fresh validation supplies evidence in the new context. Tool-pocket dimensional rules use a different context and are unaffected. No hidden evaluation was run.

## Shared model-request enforcement

`cadforge.model_budget.budgeted_model` wraps the Pydantic AI model boundary when an `ExecutionBudget` is active. It charges before each nonstreaming or streaming request, including output-validation retries. The design planner, edit planner, and specialist worker all use this boundary. The specialist scheduler copies the caller's context separately into each worker while sharing the same locked budget object. Edit planning propagates exhaustion instead of hiding it as an offline fallback.

Five new tests exercise real Pydantic AI execution with local provider doubles: a validation retry denied before its second provider invocation, two agent runs sharing one request limit, streaming denied before provider startup, threaded specialist budget inheritance, and edit-planner exhaustion propagation. Together with the execution-budget, scheduler and planner suites, **51 tests pass**. No paid model requests or hidden cases were used for these tests.

This counts logical model invocations at the Pydantic AI provider boundary. SDK-internal transport retries, token reservation before response arrival, complete tool-call accounting and cross-process aggregation remain unfinished. A request counter alone does not make the proposed V2 agent comparison freeze-ready. The archived evaluator is unchanged. The previous installed-wheel acceptance predates this new source change and must not be presented as validation of this wrapper.

## Durable shared counters

`SharedExecutionBudget(path, limits)` creates a new SQLite ledger exclusively. `SharedExecutionBudget(path)` attaches without creating or resetting allowances. Charges use an immediate transaction; denied charges are committed before exhaustion is raised. Existing ContextVar CAD/model hooks work with the shared object. Recreating an existing ledger fails instead of granting fresh budget. Each connection closes after its transaction.

Three focused tests verify eight real processes sharing three allowed charges (three successes, five denials), durable reopening, exclusive creation, and existing context-hook behavior. Eleven shared/model/CAD budget tests passed before a connection-lifetime cleanup; the three shared tests passed again afterward.

`scripts/check_shared_cad_budget.py` then used the actual bounded worker runner for three separate imported-box edit processes sharing two CAD candidates. Two previews passed; the third was denied before deformation; all active workspaces stayed unchanged because previews were not committed. Ledger totals were two used and one denied. Actual evidence: `artifacts/shared-budget/70ca131d21af4212b28d0cb2d4e3d15b/result.json`. Import cost is not included in the candidate counter; no model calls or hidden cases were involved.

This is accounting for trusted workers. Arbitrary filesystem access can tamper with the ledger, and an untrusted agent can bypass wrappers. An external broker and isolated worker permissions are still required for adversarial benchmark containment. Token reservation, SDK transport retries and complete tool accounting remain unresolved. The V2 evaluation is still not frozen or scored.
