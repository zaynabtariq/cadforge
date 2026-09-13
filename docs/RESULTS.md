# Measured results — 2026-09-12

**The full research objective is not complete.** CADForge is a working local prototype with editable CAD generation, real specialist model calls, feedback repair, persisted inherited commands, a marimo interface, tests and a sealed comparison. All three model-driven hidden conditions scored **80/100**. No advantage of learned commands over retrieved scripts was established. No product is physically validated or ready for manufacture.

## Frozen model-driven hidden comparison

| Condition | Strict passes | Attempts | CAD tool calls | Model requests | Input tokens | Output tokens | Sum of case wall time |
|---|---:|---:|---:|---:|---:|---:|---:|
| No learned skills | 80/100 | 100 | 240 | 80 | 25,172 | 4,465 | 146.63 s |
| Retrieved successful script | 80/100 | 100 | 240 | 80 | 25,172 | 4,459 | 140.95 s |
| Learned inherited commands | 80/100 | 100 | 240 | 80 | 25,172 | 4,453 | 143.80 s |

Every condition used `openai:gpt-4.1-mini-2025-04-14`, the same prompt, geometry backend and repair controller. Each case had the same maximum 4 attempts, 12 CAD tool calls, 12,000 model tokens and 120 seconds. The three conditions ran concurrently in separate processes; wall-time differences are not causal evidence. Twenty composite requests are explicitly unsupported and consume one attempted dispatch each, without a model call. Eighty supported requests receive model interpretation and geometry execution. The results therefore include 240 actual hidden inference requests. These are single-run outcomes, not replicated statistical evidence.

Hidden instances were generated before optimization and never inspected by the main orchestrator, coding agents or learner. Evaluators passed only public request text to the model runner and returned aggregate results. Temporary candidate directories were deleted after grading. No hidden feedback was used to update code or commands. SHA-256 benchmark commitment: `8647cb2f225ccb05b7c10f6fefb7edab9b5357f5213f88bd79018c2731b59467`. Frozen checker and candidate/skill/script hashes verified unchanged after all three evaluations. Raw aggregate evidence: `artifacts/hidden-summary.json`; candidate snapshot: `artifacts/candidate-freeze.json`.

**Interpretation limits:** all hidden briefs explicitly specify wall and clearance, so those dimensions are locked against the current learned/retrieved corrections. The hidden benchmark is consequently a constrained generation test with weak sensitivity to these learned commands. The 20 composite cases have an unavailable checker as well as unsupported generation, imposing an 80-point ceiling; 100/100 is impossible in this version. We did not erase these failures or weaken checks. Geometric probing and source structure checks remain incomplete engineering oracles. See [audit](AUDIT.md) and [benchmark contract](BENCHMARK.md).

## How the system corrected itself

1. **Automatic development discovery:** a 0.4 mm wall and 0.05 mm clearance triggered measured BRep failures. The common repair controller searched by +0.4 mm wall and +0.2 mm clearance increments. Passing values were 1.2 mm and 0.45 mm. Two separate development regressions per primitive command passed before promotion.
2. **Inheritance:** a glasses design failing both checks motivated a third command inheriting both validated parents. A separate combined regression passed. All commands have content hashes and evidence records; only development evidence is accepted.
3. **Transfer probe:** with a changed board length and lens width and the same initially weak unconstrained parameters, no memory required 3 attempts/7 CAD calls. Retrieved script settings and learned inherited commands each required 1 attempt/3 calls. All three ultimately passed. This is one development transfer probe, not unfamiliar topology or a hidden-test learning advantage.
4. **Orchestrated code correction:** the frozen development benchmark initially scored 18/24 in every mode because actual screw holes were missing. A coding agent added exterior mounting lugs and real through-bores while preserving the cavity. The unchanged development checks then scored 24/24 in every mode; a separate model-driven development run also scored 24/24. This engineering code change was orchestrated during development, not automatically distilled by the runtime learner.

The final discovery run used **12 CAD attempts, 32 CAD tool calls, zero model tokens, and 2.70 seconds** of measured run time, including independent regression runs. Its three later transfer runs used another 5 attempts and 13 CAD calls. An earlier discovery run also used 12 attempts/32 calls. Unit tests repeat small experiments; those are validation costs, not included in the above discovery tally. Artifact records are under `artifacts/discovery-final/`.

## Agent execution and costs

The root coordinated **three coding subagents and 108 separately instantiated model specialist jobs**, with four runtime workers. 107 specialist jobs completed; one failed after exhausting structured-output retries. The jobs made **114 requests, 23,186 input tokens and 29,707 output tokens**. The failed job consumed 2,034 tokens and remains recorded. The reviews were advisory and shared through a synthesized development backlog; they are not 108 independent measured CAD solutions. No claim is made of 100 concurrent Codex agents or autonomous code editors. [Specialist findings](SPECIALIST_REVIEW.md) records conflicting dimensions and repeated advice rather than treating votes as physical evidence.

Using the published [GPT-4.1 mini list prices](https://developers.openai.com/api/docs/models/gpt-4.1-mini) of $0.40/M input and $1.60/M output, the specialist run is approximately **$0.0568** and the three hidden conditions together approximately **$0.0516**, assuming uncached standard input billing. These are estimates from counted tokens, not invoice totals. The model-driven development sweep used 8,802 total tokens. The successful final demo planner used 255 input/20 output tokens. One earlier planner request succeeded at the provider but hit a local SDK usage-access error; its token counts were not retained. That bug was fixed and covered by a typed-model test. Coding-agent token usage, dependency downloads, research/tool calls, that unretained request, test recomputation and manual review time are **not** included in these monetary estimates. Total project/discovery expenditure is therefore not fully measured.

## Delivered CAD and verification

The enhanced glasses demo includes separate Pi and camera pockets, lens aperture, seated removable lids, six enclosure screws and a seventh frame fastener. Actual BRep checks cover cavities, openings, contact, collisions and fastener voids. Editable JSON/Python, STEP, STL, SVG and four STL-derived views are in `artifacts/glasses-llm/`. The generated Python was executed to regenerate the STEP; a board-width edit changed measured geometry and retained validity. The larger enhanced demo is distinct from the smaller frozen benchmark contract; its successful geometry checks are not counted as hidden benchmark passes.

Verification completed: **42 repository tests passed**, then **one additional executable-editability test passed**; **8 supplied CAD Sandboxes offline tests passed**. Strict marimo checking and HTML export passed. Both local studio and STL viewer returned HTTP 200. No live manufacturing quotation/upload or remote deployment was performed.

## Integration status and remaining work

- **marimo:** working form-based design studio, dimension controls, SVG preview, validation table, downloadable editable CAD.
- **Pydantic AI:** working typed model planner and actual specialist worker execution. This is distinct from TypeSafe.ai.
- **W&B Weave and Serverless Inference:** installed adapters, local JSONL traces and configuration checks; live cloud tracing/inference unverified because `WANDB_API_KEY` and project are not configured.
- **TypeSafe.ai:** public site is a stealth-lab waitlist; no public API contract/access found. No vendor compatibility was invented.
- **Unfamiliar designs:** primitive parameter inheritance works; novel operation synthesis and assembled cross-family commands do not. A stronger next benchmark needs genuinely independent compatible-interface checks and cases where learned procedures can affect outcomes. It must be newly versioned and sealed, not a rerun on the exposed evaluation.
- **Physical product:** assumed component envelopes require actual vendor footprints, PCB supports, connectors/cable routing, threads/preload, power/battery accommodation, heat paths, optical alignment and ergonomic design. CalculiX/FEA is absent and no structural, fatigue, thermal or wearer validation was performed.
- **Research rigor:** separate-account/container hidden evaluator, stronger geometry checks, full accounting, replicated trials and open-domain natural-language/composition coverage remain necessary.
