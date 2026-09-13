# Final benchmark and learning audit

This audit reviewed only `cli.py`, `pipeline.py`, `planner.py`, `benchmark.py`, `skills.py`, and documentation. It did not inspect hidden fixtures, hidden artifacts, evaluation logs, process output, or scores. No candidate, checker, or protocol source was changed. Consequently this document makes no claim about the actual hidden outcome. The points below are limitations of the visible implementation, not explanations reverse-engineered from held-out failures.

## What the comparison can establish

The three conditions share the model planner, deterministic CAD backend, local repair policy and maximum budgets. Only the development-derived initialization changes: no initializer, literal settings extracted from a successful script, or inherited parameter commands. This supports a narrow comparison of reuse mechanisms within one fixed design system. It does not compare independently designed general-purpose autonomous CAD agents.

The hidden simple-family briefs specify wall and clearance explicitly. `run_design` locks every parameter emitted in the typed specification. Both the retrieved baseline and the learned library change only unlocked parameters, and the discovered commands concern wall and clearance. Those reuse mechanisms are therefore expected to be inactive when the planner preserves explicit requirements correctly. Differences between arms would not, by themselves, demonstrate learned engineering improvement. Development transfer probes with intentionally weak, unspecified settings are the direct test of whether reuse avoids repair attempts; they must remain separately labeled as development evidence.

The retrieved condition parses one successful script and extracts two literal settings. It does not retrieve from a substantial script corpus, use semantic ranking, adapt arbitrary source, or execute the retrieved program. A learned-versus-retrieved tie cannot settle whether command inheritance outperforms a strong script-retrieval agent.

The model receives the same system instructions in all arms; it is not shown learned commands. Its output is a typed family and parameter map. The local runner performs repairs without asking the model to diagnose CAD failures. The demonstrated self-correction is thus deterministic feedback-directed numerical search, with model-based request interpretation at the front, rather than a language model repeatedly redesigning geometry from tool feedback.

## Limits of learning and unfamiliar-design claims

Discovery starts from hand-selected weak wall/clearance values and uses hand-authored increments, recognized failure codes, and a small operator grammar. It learns successful thresholds through executed geometry checks; it does not invent the repair vocabulary or learn model weights. Parent composition applies existing commands in dependency order, with deduplication. It does not synthesize a new geometric construction recipe, attachment interface, CAD operator or unsupported part family.

Promotion requires passing development evidence with identifiers distinct from discovery identifiers. This is an auditability guard, not proof of statistical independence: evidence carries no immutable request/geometry hash or trusted evaluator signature, and independence is checked by case name. The frozen run relies on the trusted discovery pipeline supplying truthful evidence. The stored skill content hash covers commands, discovery evidence and parent identifiers, while promotion/regression provenance requires separate validation. No hostile skill supplier is evaluated here.

Twenty composite cases are rejected by explicit routing policy before model planning and also fail closed in the checker. Under the frozen implementation, 100/100 is therefore impossible even for an otherwise perfect geometric candidate. This is an honest unsupported-capability denominator, but it is not a test in which a successful novel assembly can earn credit. Keep this benchmark unchanged for the current run; a future separately versioned assembly evaluator must define attachment and functional checks before new hidden cases are drawn.

The default benchmark runner invokes the original backend. An enhanced demonstration selected through the separate design CLI flag is not automatically part of the evaluated condition. Product-demo improvements and benchmark-agent improvements must be identified separately.

## Validity of the geometric oracle

Checks operate on imported STEP and STL, which is stronger than trusting an agent's reported pass flag. The oracle nevertheless checks selected geometric witnesses and aggregate properties. It does not independently recover and verify every requested dimension on every named component. A matching parameter map is not sufficient evidence that all dimensions were manufactured correctly.

In particular, the screw check counts cylindrical faces of the required radius. It does not prove that those surfaces are empty through-holes, correspond to distinct usable fasteners, align with the lid, or have adequate surrounding material. Cylindrical bosses or a split cylindrical surface can satisfy a face-count heuristic. Camera and lens probes establish clear openings for slightly inset probes, not exact aperture diameter, retention or optical alignment. Bounding-box coverage, a minimum solid count, material-volume threshold and a few wall witnesses do not establish that all required parts are connected or correctly named. Additional pathological geometry can remain outside the sampled checks.

Editable-source validation checks a literal `SPEC` assignment against the candidate specification. It does not execute regeneration, compare regenerated STEP with the submitted STEP, or test a parameter edit. A separate demonstration of regeneration supports that example only; it should not be described as an independently executed regeneration check on every hidden candidate.

These weaknesses do not authorize changes to the already frozen checker or retroactive score adjustments. Report the measured score under its exact contract and record stronger independent dimensional, feature and regeneration checks as requirements for a future benchmark version. The typed-spec-only candidate interface narrows opportunities for arbitrary artifact manipulation, but it does not turn this oracle into a complete engineering validator.

## Fairness, costs and separation

A single pass per condition cannot separate sampling variation, provider failures, transient latency or resource contention from treatment effects. Temperature zero is not a guarantee of identical model behavior. Concurrent arms also share local CAD/CPU resources. Report actual token/request counts, execution errors and elapsed costs; do not attribute a small score or timing difference exclusively to skill learning.

The model planner has its own tighter request/token caps within the benchmark maxima. Geometry tool counters are local accounting units, not a complete count of all library calls or external model requests. The elapsed per-case check includes evaluator work and applies a post-run deadline; it does not preempt an overlong process. Those choices are common to all arms, but performance conclusions must state their accounting scope.

Discovery cost is a sum of selected executed evidence runs. It does not capture the human/orchestrator effort used to design the repair grammar, write the engine, develop the benchmark, review papers, run earlier checks, or create specialist plans. Report these as unmeasured setup costs rather than implying that the recorded discovery attempts are the entire cost of acquiring the capability.

The same process account can read the private fixture. The runner receives only public request fields and has no model-callable filesystem/tools; these are useful boundaries, but they are not an independent evaluator security domain. Model-based evaluation sends held-out request text to the configured model provider for inference. Disabling Weave avoids those telemetry traces; it does not mean no external service sees the requests. No API retention or provider training-policy claim is established by this audit.

Single-use ledgers and temporary artifact cleanup reduce accidental iterative use of hidden feedback. Library evidence rejects a literal non-development split, but split labels alone cannot prevent relabeling hidden information. Current separation depends on the documented trusted workflow, frozen input state and the prohibition on hidden artifact inspection. Aggregate results should not be used to tune a candidate and then rerun the same hidden benchmark.

## Appropriate conclusion language

A supported conclusion is that the system executes typed parameterized CAD construction, diagnoses specific geometry failures, discovers reusable numerical fixes, validates them on additional development cases, and composes inherited fixes to reduce repeated repair work in the tested development setting. Any hidden score measures the separately frozen geometry contract. It does not establish general engineering intelligence, learned new-family synthesis, a learning advantage on explicitly locked hidden parameters, broad superiority to script retrieval, or a fabrication-ready camera/Raspberry Pi wearable.
