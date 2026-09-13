# Learning a tool-pocket command

`scripts/learn_tool_access.py` uses the existing persistent `ContinualLearning` service with a new BRep executor. Five independently varied tool/clearance requests start with obstructed approaches. Bounded scalar searches measure the first passing pocket diameter, preserving the lower stock. Affine fitting recovers approximately `pocket_diameter = tool_diameter + 2 * radial_clearance`; coefficients come from the measured boundaries, rather than being supplied as the command. This elementary relationship is not a novel engineering discovery.

Promotion requires a fresh challenge and two distinct development transfers, here a bracket and round coupon. Context hashes include both the coupon executor and engineering evaluator. Reuse is restricted to the observed parameter ranges (tool diameter 4–8 mm, radial clearance 0.1–0.3 mm), and each execution is still checked. The persistent database is `~/.local/share/cadforge/tool-access.sqlite3`.

Two separate process runs produced the same skill ID, `e2c71f8190b71c848d904e0fdfd2b2ab7614f7d647f9d45fbdb59f7136d57e85`. The first required 25 discovery trials and four validation/monitor trials. The second required zero discovery and one monitor trial. Each run also compared three scalar policies with the same 20-trial repair cap on a 6.5 mm tool and 0.25 mm radial clearance: no skills took six trials, nearest literal script took seven, and learned initialization took one. All reached a passing 7 mm pocket within floating-point tolerance.

The measured campaign totals 58 CAD executions: 32 attributable to discovery, validation and learned execution, 12 to no-skills execution, and 14 to nearest-script execution. Thus discovery has **not amortized** across these two requests. Test executions and code-authoring costs are additional and not included. A more capable parameterized retrieval baseline could remove this apparent per-request advantage; this is not an equal-budget LLM-agent benchmark. No model inference or new Weave trace was used for these runs, and frozen benchmark data was not accessed.

Artifacts are under `artifacts/tool-access-learning/979bd35e00324de4a71bf5071d8d51ec/` and `bafc1e852e6b4403a39124232dafb2be/`. Per-trial audits retain parameters and checks. Fifteen access-experiment, tool-access and continual-service tests pass. The relation now initializes dimensions for the editor's bounded [counterbore operation](COUNTERBORES.md), which applies separate mesh checks. It does not establish actual tool availability, assembly fit or manufacturing qualification.

## Exception-safe experiment audit

The tool-access executor previously wrote its audit only after the search loop. A caught kernel exception could therefore lose all earlier trials while the outer learning service recorded only an execution failure. It now records each attempted parameter set before execution, validates returned measurements, and writes the full trial list and attempted count in `finally`. Caught exceptions return a failed measurement carrying both cost and audit hashes. Nonfinite observations cannot become fitted evidence. This protects caught execution errors; it does not yet provide a durable checkpoint against process termination or filesystem failure.

Eighteen focused access, engineering and continual-learning tests pass. A controlled regression injects an exception on the second call after a real failed tool-clearance measurement, then verifies two attempted trials, the retained original failure, the failing parameters and the audit file's hash. Another rejects an injected nonfinite result. These are fault-injection tests, not claims of naturally occurring kernel crashes.

Changing the executor invalidated its prior exact context. New run `b038c59641624a648177ed371ba914f8` spent 25 discovery + 4 validation + 14 comparison candidates. A separate-process rerun `5b8b61f77efe448b841f189efbaf1cf6` spent zero discovery + 1 monitor + 14 comparison candidates. **58 additional CAD attempts** were spent across these runs. The healthy rule is `2fe895571894dd99a5a18880bbfbf0d71c3545a848b5834f912a46e50f4e2b3e`, with the same fitted relation `pocket_diameter = tool_diameter + 2 * radial_clearance` within existing support. Earlier contexts and evidence remain retained.

Each probe comparison again used 6 attempts without skills, 7 with the nearest literal script, and 1 with the learned rule. This small scalar-search experiment remains weaker than the required equal-budget agent benchmark. The discovery cost is not amortized, these coupon runs did not emit Weave traces, and process-level authoring costs are not fully metered. No frozen or hidden benchmark was read or changed.

## Stronger retrieval/adaptation control

`scripts/evaluate_access_retrieval.py` retrieves the full current-context discovery corpus and fits an affine parameterization from its measured successful boundaries. It does not copy the learned candidate's coefficients, hardcode the tool-clearance relation, or promote evaluation outcomes. It intentionally uses the same hypothesis class as learning; this is a stronger deterministic adaptation control, not a claim that a production retrieval agent has been implemented.

The script writes the public case contract, corpus hash and retrieved records before evaluation. Each arm has the same pre-execution limit of 20 CAD candidates per case and the same geometric validator. Actual run `artifacts/access-retrieval-comparison/80bafe03737a477d9b347d6363853c81` produced:

| Arm | Passed | Online CAD attempts |
|---|---:|---:|
| No skills | 4/4 | 20 |
| Retrieved corpus with affine adaptation | 4/4 | 4 |
| Persisted learned rule | 4/4 | 4 |

All 28 online attempts are retained. Prior discovery cost is additional: the current context required 25 discovery trials, and learned promotion/monitoring consumed another five across its preceding runs. These are shared-history development results, not amortized totals or an equal-budget LLM benchmark. The learned rule **ties** the stronger control. The four cases use familiar coupon families; this does not establish unfamiliar-topology transfer. No hidden benchmark or learning store observation was added by evaluation. These local executions made no model calls and were not traced to Weave.

## Verified Weave comparison trace

Run `python scripts/evaluate_access_retrieval.py --weave` to opt into tracing these public development cases. Existing Keychain/environment configuration initializes Weave; credentials never enter operation arguments or artifacts. The root operation returns online CAD cost and explicitly reports zero model requests. Each nested candidate includes case, arm, attempt index, actual parameters and measured checks. The CLI flushes the trace and compares the server's root output with the local result.

Actual traced run `d261c0fd9e5c4b64bd89b61b925c2d87` again spent 28 CAD attempts: 20 without skills, four with adapted retrieval, four with the learned rule. These are **28 additional executions**, not retroactive traces for earlier runs. Server readback separately verified all 28 distinct candidate children, including 16 rejected candidates and 12 accepted candidates. Local `weave-receipt.json` and `weave-children.json` retain the verification.

[Verified Weave run](https://wandb.ai/zzaynabb-03-radpilot/cadforge-continual/r/call/01a09976-8b11-76e9-96d1-107f0c0d6cae)

This adds measured development observability, not model-training evidence or a hidden-benchmark result. Prior discovery and authoring costs are not included in the online trace's CAD total. Local mode remains the default; the sealed evaluator does not call this entry point.
