# CADForge

CADForge creates editable CAD, measures failures, learns parameterized engineering commands from development experiments, and reuses promoted commands across later tasks. The current local system includes camera glasses, bounded robot-link widening, persistent SQLite learning, independent engineering gates, marimo and live Weave development traces. 

## Open the editing workspace

```sh
uv sync --all-extras
npm install --prefix studio
uv run python -m cadforge.studio_server
# In a second terminal:
npm run dev --prefix studio
```

Open [the 3D editing workspace](http://127.0.0.1:2720). Import STL or STEP, select an object or section, describe a change, inspect its measured preview, then apply or undo. Export the current mesh as STL. The typed language planner uses configured model credentials; any bounded offline fallback is explicitly identified. Unsupported design constraints ask for clarification. Imported STEP source is retained; mesh edits do not reconstruct its native feature tree.

The recorded user-flow test imports an unrelated public STL and exercises real model planning, geometry, commit, undo and downloaded STL verification. See `scripts/test_studio_browser.mjs`.

Use **Save project** to retain the source, applied edits and Undo history in a portable `.cadforge` file, then reopen it through Import or drag-and-drop. Imported historical checks remain reported provenance rather than trusted learning. See [portable projects](docs/PORTABLE_PROJECTS.md) and `scripts/test_project_studio_browser.mjs` for the real save/reopen/continue-editing test.

## Engineering and learning lab

```sh
uv sync --all-extras
uv run marimo run notebooks/continual_studio.py --host 127.0.0.1 --port 2719
```

Open [the marimo learning lab](http://127.0.0.1:2719). Its forms build only after submission:

- **Camera glasses:** Pi Zero 2 W / Camera Module 3 geometry, editable dimensions, separate pass/fail/blocked engineering gates, SVG previews and CAD downloads. Initial dimensions are a representative **52–18–145 mm** frame with **42.4 mm** lens height; they are not wearer measurements.
- **Robot link:** increase a two-pivot link's width while measuring preserved pivot centers, bore diameters, length and thickness. A failed change retains the original version. This is one constrained link operation, not a complete powered arm.
- **Persistent learning:** intentionally run development discovery or reuse, then refresh a read-only audit of promoted commands, quarantine state and recorded events. Optional Weave tracing is explicit.

Outputs include editable Python/JSON, STEP, STL, SVG and measurement records. STEP preserves boundary geometry; procedural history lives in Python/JSON rather than a native Fusion/CATIA feature tree. The earlier [design studio](notebooks/design_studio.py) remains available for the original bounded natural-language prototype.

## Run learning across tasks

```sh
uv run python -m cadforge.evolve
# With an authorized configured W&B account:
uv run python -m cadforge.evolve --weave
```

The default database is `~/.local/share/cadforge/learning.sqlite3`. Each run records immutable experiments, candidate versions, inherited dependencies, validation and promotion evidence. Commands are context-bound and have supported parameter ranges; failed monitoring can quarantine a command and its dependents. Learning uses executed ideal CAD fit coupons, not an assumed physical printer offset. See [current scope and results](docs/CURRENT_STATUS.md).

The measured initial continual discovery used **170 CAD trials**. A subsequent task reused the persisted commands with **zero new discovery trials**; verification and monitoring still execute. On the recorded equal-repair-budget comparison, no learned skills required **32 trials**, nearest retrieved script **1**, and inherited commands **1**. The retrieved and learned methods **tie on success and trial count**. The learned relation supplies the requested fit dimensions; the successful nearest script can be oversized. This single development comparison does not establish general superiority or manufacturing calibration.

## Cooperating tools and tracing

[Live development traces](https://wandb.ai/zzaynabb-03-radpilot/cadforge-continual/weave) record measured operations in the configured project. Tracing covers both the executed CAD trials and the learning decisions they justify: `run_experiment`, `propose_affine_command`, `challenge_candidate`, `promote_command`, `reuse_promoted_command` and `select_latest_command`. Credentials load from a local gitignored `.env` at explicit opt-in entry points only; `enable_weave` still reports disabled when the calling environment carries no credential. Enable tracing explicitly and supply credentials through the environment; never put keys in CAD files or notebook output. Inference and observability are distinct capabilities, and successful tracing alone does not establish model-provider availability.

An MCP server exposes development fit measurement, learning/reuse and glasses generation tools:

```sh
uv run python -m cadforge.mcpserver
# Opt-in Weave tracing for MCP operations:
uv run python -m cadforge.mcpserver --weave
```

The server uses stdio transport. A client can register this command from the repository root. [Integration notes](docs/INTEGRATIONS.md) retain the original setup context; [current status](docs/CURRENT_STATUS.md) supersedes their historical unconfigured-Weave statement. Pydantic AI provides typed model interfaces; it is not the separate TypeSafe.ai service, whose public integration contract remains unavailable.

The original orchestrator coordinated three coding agents and **108 separately instantiated model specialist jobs**, with bounded concurrency. These reviews were advisory, not 108 independently validated engineering designs. See [specialist review](docs/SPECIALIST_REVIEW.md) and [research foundations](docs/RESEARCH.md).

## Archived v1 benchmark — unchanged

The frozen v1 comparison scored **80/100 in all three conditions**: no learned skills, retrieved scripts and learned commands. **No hidden-test learning advantage was demonstrated.** The benchmark has 24 public development cases and 100 private test cases, including 20 unsupported compositions. Its explicitly locked wall/clearance values largely disable the learned corrections, and unsupported composition checking imposes an 80-point ceiling.

The v1 hidden evaluations are completed and single-use. Do not rerun them, inspect private cases, or train on hidden artifacts. Current development does not alter the frozen checker or retroactively change its scores. Further learning-sensitive or new-topology evaluation requires a separately versioned benchmark with fresh hidden cases. [Archived results and costs](docs/RESULTS.md), [frozen contract](docs/BENCHMARK.md), and [independent audit](docs/AUDIT.md) preserve the evidence and limitations.

## Prototype boundaries and verification

The selected manufacturing direction is **MJF PA12 with external USB power**. Nominal mass/stiffness screening uses explicitly versioned material data and official component masses; the complete BOM and actual hardware measurements remain unresolved. Passing geometric checks does not establish printer fit, cable bend/termination, screw retention, thermal behavior, fatigue, optical alignment or comfortable wear. Read [production gates](docs/PRODUCTION_GATES.md), [manufacturing assumptions](docs/MANUFACTURING.md), and [hardware sources](docs/HARDWARE.md).

```sh
uv run pytest -q
uv run marimo check notebooks/continual_studio.py
uv run marimo export html notebooks/continual_studio.py -o /tmp/cadforge-studio.html
```

The supplied CAD Sandboxes code also provides local STL inspection:

```sh
npm ci --prefix cad-sandboxes-main/click-to-ship
uv run python cad-sandboxes-main/cad-preview/preview.py PATH_TO_DESIGN.stl --no-open
```

Generated designs, local traces and private evaluation artifacts are ignored by git. No manufacturing purchase, fabrication acceptance or production release is implied by an exported model.
