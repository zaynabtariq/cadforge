# Current continual system

This document describes the ongoing local system after the archived v1 evaluation. It does not replace v1 scores or declare the full research objective complete.

## What runs

The primary editing workspace is the 3D studio on port 2720 with its local API on 2721. Users import CAD, select parts or regions, preview natural-language edits, Apply/Undo, and save portable `.cadforge` projects. See [workspace behavior](WORKSPACE.md) and [portable projects](PORTABLE_PROJECTS.md). `notebooks/continual_studio.py`, served on 2719, remains the marimo learning/engineering lab. Its learning form invokes `cadforge.evolve`; a read-only SQLite panel shows persisted promotions, quarantines and audit events. The notebook never opens hidden benchmark files or displays credentials.

`python -m cadforge.evolve` executes the persistent development workflow. It records diagnosed failures, fits parameterized relationships from measured coupon outcomes, challenges candidate commands with fresh cases, tests transfer, promotes passing versions and monitors later reuse. Dependencies compose previously promoted behavior. Unsupported contexts or parameter ranges do not silently inherit a successful claim. This is a bounded, deliberately structured numerical learning system; it does not invent arbitrary CAD operators or learn model weights.

The current MCP stdio entry is `python -m cadforge.mcpserver`. It exposes measured fit and learning tools and editable camera-glasses generation. `--weave` enables explicit development tracing. The [configured live Weave project](https://wandb.ai/zzaynabb-03-radpilot/cadforge-continual/weave) supersedes the earlier archived report's unconfigured tracing state. This change concerns development observability, not private evaluation or an inference-provider guarantee.

## Recorded improvement and costs

| Development measurement | Actual recorded result | Interpretation |
|---|---:|---|
| Initial continual discovery | 170 CAD trials | Executed numerical experiments used to discover bore and bearing-material relationships |
| Subsequent task discovery | 0 new discovery trials | Persisted healthy commands reused; monitoring/verification still incurs work |
| No-skills comparison | 32 repair trials, successful | Same bounded repair policy eventually fixes the request |
| Nearest retrieved script | 1 trial, successful | Strong successful baseline; retrieved dimensions may be oversized |
| Inherited learned commands | 1 trial, successful | Requested fit relation reused; tied with retrieval on trials and final success |
| Learning-loop persistence demo | `artifacts/learning-restart-browser/learning-improvement-loop.mp4` | Real browser loop: sharp candidate fails, transition strategy passes and is promoted, then reused in 1 attempt after backend restart with unchanged persisted store |

These are development measurements, not held-out results or a replicated statistical study. Discovery counts omit engineering code authoring, prior research, orchestration, UI work, test recomputation and human review. Zero new discovery is not zero execution cost. A more exact fit is a geometric distinction and must not be advertised as a demonstrated safety or reliability improvement in manufactured parts.

The glasses development also produced a concrete geometry correction: an independent full-bore check found material intruding into a camera fastener aperture that a smaller builder probe missed. Preserving the specified interface voids removed the interference without relaxing the independent gate. This was an orchestrated implementation repair with measured evidence, separate from the runtime coupon learner.

## Cross-object scope

Learned fastener-fit relations can initialize compatible geometric features on other supported objects within their validated context and numerical ranges. Robot widening then applies a distinct versioned operation that preserves measured pivot geometry and rolls back rejected changes. Applying a fit command before fixing the pivot contract is different from changing a pivot diameter during an allegedly invariant-preserving width edit.

The robot module handles a parameterized two-pivot link. It does not yet design an entire articulated robot, select motors/bearings, plan collision-free motion, certify torque or fatigue, or interpret arbitrary imported assemblies. Parameter-command inheritance and bounded feature transfer do not demonstrate unrestricted new-family synthesis.

## Product status

The nominal glasses reference is 52 mm lens width, 18 mm bridge, 145 mm temples and 42.4 mm lens height. This comes from one official commercial eyewear listing and is not individual fit data. Pi Zero 2 W and Camera Module 3 are the intended hardware. The user-selected process is MJF PA12 with external USB power. Public drawings and nominal masses support preliminary contracts; actual populated assemblies, cables, fasteners, lenses and final BOM must still be verified.

The rebuilt reference has 24.39 g of nominal printed material and a 40.39 g known-inventory subtotal including the two catalog electronics entries. It excludes unweighed installed hardware and is not measured worn mass. [The mass screen](MASS_SCREENING.md) retains source qualifications and also documents the repaired nonfinite-support false pass.

Independent gates distinguish pass, fail and blocked evidence. Physical manufacturing qualification, global feature/process validation, real cable bend and connector termination, fastener strength, powered thermal behavior, optical performance and wear comfort remain unresolved. Legacy nominal PA12 density/modulus enable clearly labeled screening only. There is no printer calibration, certified material allowable, FEA validation or production-release claim.

The current UI passed marimo checking and HTML export. Submitted-cell smoke tests generated glasses artifacts and accepted a supported 20-to-28 mm link widening. Those smoke tests validate example execution, not all allowed form values or a physical product. The main run report should carry the latest full-suite results rather than inheriting older test counts.

## Archived evidence remains separate

V1 hidden scores remain **80/100 for all three arms**, with no established learning advantage. Its 20 compositions are unsupported and the checker is frozen. No hidden artifact inspection or retraining forms part of this ongoing development. See [archived measured results](RESULTS.md), [benchmark contract](BENCHMARK.md), and [audit](AUDIT.md). A new benchmark must be designed and frozen separately before testing broader learning or composition claims.

### Rigid movement and current-validator learning

Explicit rigid selected-section movement now forbids tapered repairs and verifies every selected displacement vector. The current public development comparison retains candidate→promotion→reuse, with 6 candidate trials for default priority versus 4 each for learned and retrieved priority across four cases. All arms accept three edits and reject the large rigid shear; learning does not outperform retrieval here. Eighteen focused learning/rigid tests pass, including incompatible-request rejection without spurious skill quarantine. See `RIGID_TRANSLATION.md` and `REGION_CONTRACT_TRANSFER.md`. These results do not alter frozen v1 scores or establish physical release readiness.

### Integration verification

The latest broad Python run passes 430 tests (102.04 seconds, 14 warnings), excluding `tests/test_benchmark.py`; this is regression evidence, not a new benchmark evaluation. Twelve focused learning/history tests also pass after the eligibility-reporting change. A real isolated Pydantic 2.11 schema-generation failure led to correcting the declared floor to 2.12; that minimum passes the identical probe. See `DEPENDENCY_VALIDATION.md`. Physical release gates and broader agent-benchmark limitations remain unresolved.

### Clean bundled installation

A new Python 3.11 environment installed the bundled wheel with studio/agents/observability extras and 163 compatible packages. Outside-checkout smoke checks passed workspace edit/save/reopen, typed planning, registration of 10 MCP tools, and native glasses export. Engineering remains 43 pass / 0 fail / 11 blocked for that reference build. See `CLEAN_INSTALL.md`; remote inference/tracing and cross-platform installation are separate evidence requirements.

The wheel was subsequently rebuilt with sequence composition and counterexample-preserving learning and reinstalled into that environment without changing dependencies. The expanded outside-checkout workspace probe also checks offline natural-language intermediate targets, one-step Undo restoring exact STL bytes, and serving the bundled UI. The learning history API now reports current reuse eligibility independently of retained historical skill records, including quarantined aliases. Native glasses and remote inference were not rerun in this packaging update.
