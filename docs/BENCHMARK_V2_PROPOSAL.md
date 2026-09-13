# Proposed V2 benchmark: editable imported CAD and learned engineering commands

**Status: proposal for review, not frozen, generated, or executed.** This document creates no hidden instances and reports no V2 score. It does not modify or reopen V1. V1 remains 80/100 in all three conditions, with no demonstrated hidden-test learning advantage. The current four-case public region comparison shows a learned/retrieved tie and does not amortize discovery cost.

## Question and scope

Can an agent fulfill a natural-language edit request on an unfamiliar imported model, recover from measured failures, and reuse a parameterized command or inherited command composition to reduce total work without weakening geometry, intent, or editability checks?

The evaluation unit is a complete user task: source artifact, natural-language request, permitted selection information, engineering constraints, and a required portable editable result. Imported mesh history must be described as mesh-operation history; preserving the original STEP does not establish that an edited mesh has an editable native feature tree. Manufacturing release, comfort, strength and thermal safety are outside this geometric benchmark unless separately instrumented and explicitly reported.

## Proposed 100-case composition

Use 100 independently authored tasks, not 100 parameter perturbations of a few scripts. No task is dropped because the current engine cannot solve it.

| Object family | Cases | Required challenge coverage |
|---|---:|---|
| Plates and mechanical interfaces | 22 | Hole patterns, counterbores, slots, interface-relative widening, off-axis drilling, protected mating surfaces |
| Electronics housings | 18 | Internal pockets, lid interfaces, connector access, wall witnesses, ribs and local clearance edits |
| Fixtures and brackets | 16 | Oblique faces, nonrectangular stock, fastening patterns, edge margins, several protected interfaces |
| Links and articulated mechanisms | 16 | Pivot center distances, asymmetric profiles, joint clearance, local stiffening and parameter propagation |
| Curved parts and wearable structures | 14 | Curved shells, nonplanar references, explicit rigid versus transition semantics, local thickness and openings |
| Multi-object assemblies | 14 | Relative transforms, noninterference, shared interface constraints, atomic multi-step edits and component identity |
| **Total** | **100** | |

Cross-cutting quotas are assigned jointly before generation, rather than counted as additional cases:

- 90 tasks require an accepted editable design. Ten of these begin with a material ambiguity and supply a fixed evaluator-authored answer to a relevant clarification. The other 80 contain enough information to proceed.
- Ten tasks require evidence-based non-execution: six contradictory geometric contracts and four malformed or insufficient source/reference inputs. Mere lack of an implementation is never a correct rejection of a solvable task. These ten tasks have explicit oracle reasons and require the original project to remain intact.
- Within the 90 design tasks: at least 30 involve two to four operations, at least 25 preserve two or more independent constraints, at least 20 use rotated or non-axis-aligned references, and at least 15 involve curved/nonprismatic geometry. Quotas overlap and their intersections are published as counts.
- At least 30 tasks require a composition whose operation order/dependency structure is absent from development. At least 30 use source topologies or geometric constructions absent from development. These are designated separately; new dimensions alone do not count as structural novelty.
- Source representations: 60 STL and 40 STEP tasks, distributed across families. Twenty STEP design tasks additionally require a reconstructed or retained parameterized BRep editing workflow. Their requirements cannot be satisfied by exporting a tessellated mesh plus untouched original STEP.

No more than two hidden tasks may share a source construction template. Changing only dimensions or wording does not create a new template. Each case has at least two independently necessary acceptance conditions beyond validity and successful file writing. An external reviewer audits duplicates, actual solvability and difficulty before the freeze. Current unsupported features—such as general curved-surface edits and native BRep parameter propagation—remain requirements and expected blockers until implemented.

## Public development and independent hidden creation

Create 36 public development tasks covering the six families, including meaningful failures, counterexamples, ambiguous requests, and malformed inputs. Publish their source artifacts, requests, checks and reference witnesses. Development may generate additional experiments, but every generated coupon, search and unsuccessful trial belongs in the discovery ledger.

A separate evaluator author creates the hidden 100 using separate constructions, source provenance and random seeds. This author must not supply implementations or examples to the candidate-learning process. Cases can use licensed public CAD sources, but public accessibility is not evidence against contamination: record source URLs/licenses, content hashes, template ancestry and likely pretraining exposure. Include evaluator-authored novel geometry to reduce reliance on memorized files. Split by source lineage and feature/dependency structure before numeric sampling.

No hidden case creation or inspection occurs under this proposal. Before creation, approve the family allocation, task-type allocation, common tool API, representation requirements, check algorithms, numeric policies and budget. Pilot cost and runtime limits exclusively on public development. If pilots require a budget change, change this proposal before any hidden run.

## Acceptance oracle

The evaluator reopens final exported artifacts in a clean process and computes acceptance from the original source and evaluator-authored contract. It must not trust candidate-reported measurements, check results, generated reference geometry or claimed learning provenance.

For every applicable design task require:

1. **Intent and dimensions:** requested absolute/relative dimensions, unit conversions, depth, direction and reference frame meet fixed tolerances. A rigid request cannot pass through a peak-displacement transition. A transition-permitted request must disclose its deformation semantics.
2. **Protected geometry:** identified interfaces retain required centers, diameters, profile sections, clearance or distances. Exact-geometry contracts compare canonical oriented surface patches and coordinates. Dimensional contracts permit alternative triangulation and topology. Do not require exact reference-mesh equality for ordinary shape changes.
3. **Material and topology:** finite coordinates, valid positive-volume solids/closed meshes, no forbidden intersections or disconnected fragments, required floor/through-hole topology, local wall witnesses and stock engagement. Independently test small voids and narrow breakouts that aggregate-volume tolerance can hide. Distinguish numerical predicates from exact certification.
4. **Assembly and sequence invariants:** required identities and relative placements survive; constraints designated “throughout” hold after every committed operation in the returned history, not just at the endpoint. A move-then-restore sequence cannot evade them.
5. **Transactional behavior:** preview leaves the committed source unchanged; failure leaves it unchanged; a compound change commits once and Undo restores exact prior source bytes where the representation promises byte restoration.
6. **Editability:** import the delivered `.cadforge` or specified parameterized BRep package into a fresh empty workspace, preserve original source, restore ancestry, and execute a contract-defined follow-up parameter edit. Recheck invariants on the modified result. For mesh tasks, replay documented typed operations from the source and compare resulting geometry; a decorative command log or static STL alone fails. For BRep tasks, independently regenerate the requested parameterized geometry. Follow-up values are evaluator-held and never returned as optimization feedback.

Each case fixes numerical tolerances from source precision and contract purpose before evaluation. An input-normalization policy must record its actual displacement and protect small features; do not silently flatten or snap away counterexamples. Follow-up edits and witnesses are validated on positive references and adversarial negative controls before freeze. More than one valid solution should be accepted where the request permits alternatives.

No weighted averaging hides a broken mandatory gate: a design task passes only if every applicable mandatory requirement passes. Report geometric completion, editability, clarification accuracy and correct non-execution separately. The headline score is tasks solved/100, accompanied by design tasks solved/90 and non-execution tasks correct/10. Also report false rejection of solvable tasks and unsafe acceptance. Diagnostic partial credit is secondary and never rounds a failure into success.

## Three equal-budget conditions

Freeze the common base-tool repertoire before arm-specific discovery; do not fold newly learned implementations into the shared baseline after training. Use the same model/version, system instructions, role topology, tool permissions, context limits, source artifacts and case ordering policy in all conditions. Cooperating roles—planner, geometry operator and independent critic—are available equally; decorative extra agent calls are not an advantage unique to the learned condition. All internal subagent calls count against the task budget.

- **No learned skills:** common low-level tools and documentation, ephemeral within-task reasoning, but no cross-task learned-command or script library. It may correct failures within its budget.
- **Strong retrieved scripts:** a versioned searchable corpus from the same allowed public sources and development executions. Give it working retrieval, source metadata, dependency inspection and permission to adapt retrieved scripts within budget. The corpus includes successful development repairs, not deliberately weak or obsolete examples. Freeze retrieval prompts, index, top-k limits and source hashes.
- **Learned commands with inheritance:** the same base tools and allowed corpus plus the development-produced parameterized command library, applicability predicates, dependency graph and versioned validation evidence. Freeze the promoted library, rejected candidates and quarantine state. An inherited command counts only when the invoked dependency chain and parameters appear in the execution trace.

Provisional **per-case cap**: 24,000 billed input-plus-output model tokens (including all roles and cached input), 16 model requests, 64 tool calls, 24 actual CAD candidate executions, and 180 seconds elapsed under a supervisor-enforced deadline. Charge nested repairs, failed booleans, speculative sequence steps and retries individually. No helper may hide an unmetered search. Oracle-only final verification is separated from agent budget and available identically to every arm. A refused/failed call still costs a call. The cap is equal; actual expenditure is also reported.

Provisional **development allowance per arm**: 2,000,000 total model tokens and 2,000 CAD candidates, with equal access to the 36 public tasks. Human-authored code and scripts are logged as separate costs; hours of unmetered human intervention cannot be represented as autonomous discovery. Shared harness construction is accounted separately. Freeze development policies and arm assets before hidden execution. If repeating stochastic conditions, approve three independent seeds per arm prospectively and run all nine jobs without intervening analysis; do not rerun selectively after seeing results.

## Evidence of self-correction and learning

For every attempted task retain the request, source hash, typed command, model/tool usage, actual candidate artifacts, failed checks, repair rationale, dependency invocations and final outcome. Measure:

- Initial success and eventual success under the same budget; which measured failures were corrected and which persisted.
- CAD candidates/tokens/time to first valid editable result, including censored failures and the full cap spent on them.
- Conditional transfer on structurally new tasks, recovery when an applicability condition fails, and invalid-skill quarantine without erasing evidence.
- Learned versus retrieved differences in success and cost. A tie is a tie. Reusing a fixed script or choosing an already implemented strategy is not new operator invention.
- Full discovery cost, failed experiments, promotion/monitoring costs, library construction and evaluation spend. Report cumulative cost and a measured break-even curve; do not report amortization before savings exceed discovery cost.

Use paired task outcomes and paired uncertainty intervals across arms, with the prespecified seeds and family strata. Report raw denominators and uncertainty, not only averaged percentages. The ten non-execution tasks cannot conceal poor design completion. Do not stop a run when it reaches a flattering score or continue hidden optimization toward 100/100. Further improvements use public development or a future fresh benchmark version.

## Freeze, isolation and execution architecture

1. Freeze this protocol, all oracle code and negative-control tests, evaluator container/dependencies, schemas, numeric policies, budget supervisor and scoring/report code. Persist hashes and a signed or externally timestamped commitment.
2. Independently generate and review hidden sources/contracts inside a separate evaluator account/container. Commit their manifest/Merkle root without disclosing case contents. Mere owner-only files under the agent's own OS account are insufficient isolation.
3. Freeze candidate code, base-tool versions, each library/index, model identifier and prompts. Keep library volumes read-only. Snapshot their hashes before and after every run. Initialize a clean ephemeral context/workspace per case; provide no previous hidden outcomes or artifacts to subsequent tasks.
4. Run all arms against the same task packets via a restricted tool bridge. The existing studio/workspace can supply imports, selections, previews, atomic composition, project export and Undo. `plan_edit`/`plan_sequence` can be components, but an instrumented agent loop must own real retries and tool choices. The existing deterministic parser or priority ablation alone is not the proposed autonomous benchmark.
5. Public diagnostic checks may return useful failures equally to every arm. Hidden final witnesses and editability challenges run only after submission and release no case-level feedback to candidates or developers. Scripted clarification answers contain only the approved missing user information. No network access to evaluator storage; restrict candidate filesystem/process access, secrets and outbound telemetry.
6. Final evaluator logs and artifacts remain evaluator-controlled. During runs release only operational health, not case identities or failures. Development Weave/marimo views must not ingest hidden briefs or geometry; evaluation telemetry is private and may export redacted aggregate usage afterward. Imported project history remains untrusted and cannot promote learning.
7. Release aggregate results only after every precommitted run finishes. Preserve failures and consumed budgets on crashes. A harness defect invalidates the affected comparison under a documented incident protocol; correcting a checker creates a new version with fresh hidden cases. Never adapt an oracle or rerun a corrected candidate against exposed hidden tasks and present it as the same frozen evaluation.

## Implementation blockers before a freeze

The existing project already supplies useful transactional mesh editing, protected-hole checks, planar surface drilling, rigid/transition contracts, portable history, local recovery receipts, typed planning and bounded composition. The new `evaluation_process.py` supplies one JSON request/report per trusted worker process, an explicit environment allowlist, process-group timeout termination, and distinct exit/invalid-report/oversize statuses. It is useful supervisor infrastructure, not a filesystem/network sandbox or a complete V2 runner; it has no hard disk/RSS quota, and token/tool accounting still depends on the worker. It does **not** yet establish the following required capabilities:

- A clean evaluator security boundary, independently authored hidden corpus, validated oracle witnesses and adversarial editability challenges.
- A single enforceable meter spanning model roles, helper-level CAD trials, nested compositions and retrieval, integrated with the available wall-clock process supervisor and resource quotas.
- A genuinely equivalent strong retrieved-script baseline and prospectively costed development pipelines for all arms.
- Replayable portable operation histories across imported project/branch identities, plus a tested parameterized BRep workflow for the designated STEP tasks.
- General curved/nonplanar feature editing, broader interface invariants, richer assemblies and robust applicability predicates for structurally new compositions.
- A verified model-controlled tool/retry loop and model availability. Current provider credentials, model autonomy and cancellation behavior must be tested, not assumed from a typed API or successful Weave connection.
- Independent evidence that learned parameter relations and inherited compositions improve beyond nearest scripts/strategy priority, with discovery costs included.

These are blockers to executing this proposal, not reasons to reduce its denominator. Review the public protocol, implement the harness and validate public cases first; then authorize a separate V2 freeze. No V2 score or anticipated path to 100/100 is claimed here.
