# Natural-language CAD workspace

The main interface is `http://127.0.0.1:2720`. The marimo notebook on port 2719 is an engineering and learning lab; glasses and robot links are example recipes.

## Workflow

1. Import an STL or STEP file. Declare STL units because the format has no reliable unit metadata. STEP units are normalized by OpenCascade.
2. Click an object, or choose Section and click a local area / drag a selection rectangle. The orange box is the actual three-dimensional edit region; rectangle selection extends through the model. Hold Alt while dragging to orbit in Section mode.
3. Describe the change. Examples include “make this 2 cm wider,” “move this 3 cm to the right,” and “add a 10 by 10 by 5 mm box here.” A surface click supplies the location for additions and cuts.
4. Review the candidate and its checks. Apply commits a new version; Discard preserves the saved version. Undo restores a previous version. Export downloads the active STL.

The planner produces validated command data, never executable model-generated code. X is width/right, Y depth/back and Z height/up. A numeric guard checks unit conversions and relative dimensions. Ambiguous references or unsupported invariant requirements ask for clarification. Actual model use, offline grammar, and provider-error fallback are identified separately.

## Supported edits and boundaries

Whole-part translation, axis resizing, box/cylinder union, and cylindrical subtraction operate on the imported mesh. Region translation/resizing preserves vertices outside the selected AABB and triangle indices. Geometric checks include positive watertight geometry, collapsed/flipped faces, bounded numerical triangle-intersection checks and requested displacement/extent. Failed candidates are retained as evidence and cannot be committed.

A repaired region translation may use a smooth interior transition. It reaches the requested movement at the interior peak while tapering toward the selected boundary. This is explicitly shown before Apply; it is not a rigid translation of every selected vertex. Numerical checks do not prove arbitrary self-intersection absence, mechanical performance, minimum wall thickness or original design intent.

STL files remain faceted meshes. Original STEP files are preserved, but edited meshes do not recover their original parametric feature trees. Arbitrary imported assemblies do not automatically acquire pivot, bearing, lever-arm or mechanical invariants. The separate robot-link operation carries those explicit constraints for its supported recipe.

## How learning changes a later attempt

The region preview records the actual strategies tried and their check results. A direct edit may fail; an interior transition may pass the same checks. One correction is only a candidate. Correction on different mesh topology counts in separate sessions can promote a strategy priority. A later compatible-axis edit tries that saved priority first and still runs all checks. A failing preferred strategy is quarantined. Validator code hashes prevent silently reusing evidence after checker changes.

This is learning which existing geometric repair to try first, not model-weight training or unrestricted invention of new CAD operations. Counts and hashes are limited provenance heuristics, not proof of broad transfer. Persistent evidence is in `~/.local/share/cadforge/region-learning.json`; the UI history reads it without resetting knowledge.

The earlier deterministic engineering-factor learner remains separate in `cadforge.continual`. Its historical discovery cost was 170 geometry trials. An audit/validator version change required another 170 trials; both histories are retained. Subsequent reuse in each matching context incurred zero new discovery but did run verification. The strong retrieved-script baseline tied the learned factor method at one verification/repair trial.

## Actual acceptance evidence

`scripts/test_studio_browser.mjs` uses installed Chrome through Playwright and the live local server. It uploads the unchanged public `mikedh/trimesh` 20 mm XYZ STL through the file input, clicks the canvas, submits a natural-language request to the real Pydantic AI planner, commits, undoes and downloads STL outputs. It checks output dimensions, watertightness, unchanged pre-commit export and byte-exact restoration after undo. It does not stub the planner or geometry API. Results, screenshots, video, source hash and MIT license are retained in `artifacts/studio-test/`.

The first browser run exposed a missing favicon resource. The retained failure report and subsequent passing run are separate. This minor UI correction is not claimed as a learned engineering skill.

The learning video must show genuine saved failures, promotion and reuse. Any prior experimental discovery or fixture-search cost must be disclosed; a video is not a frozen benchmark or independent production qualification.

Current complete Python verification: **156 tests passed** in 97.54 seconds, with deprecation warnings and no failures. The browser build completed. The actual whole-object browser flow passed with zero JavaScript/console errors; a separate recording covers region learning.

Public region-demo fixture discovery used **151 actual deformation calls** while finding suitable failure/repair examples. Some calls try multiple internal candidates; complete internal-attempt totals were not recoverable from every exploratory error log and are not invented. These costs are separate from the earlier 170 + 170 coupon-discovery trials. `artifacts/region-public/DISCOVERY_COST.json` preserves the available counts, timings and limitations.

## Cooperating agents use the same workspace

The MCP server now exposes `import_cad_workspace`, `get_cad_workspace`, `preview_cad_edit`, `apply_cad_preview`, and `undo_cad_edit`. Pass the revision from `get_cad_workspace` as `base_revision` when planning. These bridge to the local HTTP workspace owner on port 2721, so MCP and browser clients share versions and the same preview/commit checks. Start `cadforge.studio_server` first. MCP does not create an independent writer against the session files.

An actual MCP subprocess roundtrip imported the public XYZ cube, used the real language planner to widen it by 1 mm, committed, and restored its exact original bounds with undo. `artifacts/mcp-workspace/edit-roundtrip.json` records the result and the actual 927 model tokens used. This verification did not exercise private benchmark cases.

## Explicit hole-preserving widening

For recognized complete coaxial Z-through-hole profiles, whole-part X/Y widening can now preserve hole positions, radii, stepped/countersunk profiles and thickness coordinates. Ask explicitly to keep the holes unchanged. Unsupported recognition is rejected, and the UI marks protected profiles. Read [the operation, failure history and independent evidence](PROTECTED_EDITS.md). Generic scaling still carries no preservation guarantee.
