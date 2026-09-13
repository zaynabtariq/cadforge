# Widen an imported part without changing its holes

The editor now accepts requests such as “Make this 2 cm wider without moving or resizing the holes.” Select the whole part. The planner chooses `resize_preserving_holes` rather than ordinary scaling. X/Y widening is supported; shrinking, Z resizing, blind or tilted holes, ambiguous channels, and broader mechanical invariants remain unsupported.

The operation recognizes complete circular coaxial through-hole profiles aligned with Z, including stepped, countersunk and rounded entrances supported by the recognizer. It verifies the full thickness span and accounts for the mesh genus. All recognized wall and shoulder vertices stay fixed. The outer material expands beyond a protected band containing the hole profiles and an explicitly assumed support margin. This margin is a geometric policy, not a verified strength or minimum-wall certification.

The UI draws the recognized profile rings and shows the measured result before Apply. No unsupported preservation request silently falls back to generic scaling. Large rail stretches, insufficient material outside the protected band, invalid geometry or incomplete recognition reject the preview.

## Failure and correction

An independent test fixed the required hole coordinates and dimensions before the operation was implemented. Ordinary scaling failed that preservation contract. The first attempted protected vertex mapping also failed: triangles spanning the deformation boundary flipped.

The correction subdivides those triangles at the protected-band planes before applying the piecewise affine widening. It retains original protected vertices while allowing new triangle topology outside the protected surfaces. The retained failing candidate and successful result are in `artifacts/protected-learning/repair-evidence.json`.

A separate numerical audit caught an attempted validation-coordinate scaling that would have changed physical area/volume floors. The final implementation keeps physical area, volume and orientation checks in millimeters. Only triangle-intersection checks use explicit coordinate normalization, with a separately documented numerical policy. Independent crossing/non-crossing tests at three scales exercise that policy. Neither this policy nor the underlying floating-point predicates are an exact geometric proof. The existing region-edit validator and frozen benchmark files were not changed.

This is an engineering-agent-authored reusable operation developed from failures. It is distinct from the runtime learner that promotes region-repair priorities or fits fastener relations; it is not presented as model-weight learning.

## Real browser verification

The unchanged public `plate_holes.STL` from the trimesh repository was uploaded through the native file input. The browser clicked its canvas, submitted the actual plain-language request, reviewed the candidate, applied it, exported it and undid it. No planner/API/selection mocks were used.

- Width increased from approximately 203.2 to 223.2 mm.
- Five internal hole contours were independently compared at nine sampled heights: 45 contour comparisons remained unchanged.
- Y/Z extents, positive volume and watertightness were checked.
- Export before Apply stayed unchanged; Undo restored exact original STL bytes.
- Browser JavaScript and console error counts were zero.

`scripts/test_protected_studio_browser.mjs` performs this acceptance test. Results, screenshots, raw video and exported STL files are in `artifacts/protected-studio-test/`. The existing learning-loop video remains separate and demonstrates runtime strategy promotion/reuse.

## Concurrent agents

A preview can carry an expected source revision. If another agent commits while language planning runs, the stale plan is rejected before geometry execution. The browser sends its source revision; the server also rechecks its planning snapshot atomically in the workspace preview boundary. Commit independently rejects stale preview versions. A regression test verifies that an older plan cannot overwrite newer geometry.

## Verification record

The full Python suite passed 189 tests before the final concurrency regression was added. The subsequent focused workspace/planner/protected suite passed all 48 tests, including that new regression. The frontend build and real browser flow passed. These checks support the described geometric operation, not manufacturing, load rating, fatigue, thermal behavior, arbitrary hole orientation or general CAD-history recovery.

Four explicitly recorded live smoke-test model calls consumed 4,173 tokens in total (two browser runs, one standalone protected planner run, one MCP roundtrip). `artifacts/protected-studio-test/recorded-costs.json` itemizes them. Engineering-agent authoring and exploratory CAD execution costs are not fully metered and are not represented as zero. A subsequent stale MCP request was rejected before model planning, recorded separately.

## Coordinate-aligned imported orientations

`axial_protected_edit.resize_preserving_axial_holes` now recognizes complete through profiles along world X, Y or Z before executing protected widening. It uses cyclic coordinate permutations with positive determinant, preserving original numbers exactly. The established Z-profile kernel performs all inherited checks in that local frame; its failure is never retried under another orientation. Original protected world coordinates are checked again after mapping back. Widening along the bore direction and oblique/ambiguous hole directions remain unsupported.

The workspace uses this adapter for protected X/Y widening. Feature records include the local-to-world axis order when needed, and the browser maps orange hole rings through that order. This is deterministic composition of a checked operation and a coordinate transform, not a new learned parameter rule. The earlier low-level Z-only kernel and its rejection tests are unchanged. Multi-step global hole invariants still have their separate Z-oriented limitations.

Twenty axial/protected/workspace tests pass. A real Chrome flow imported a rotated copy of the public `plate_holes.STL` and requested “Make this 1 cm wider keeping holes fixed.” Preview, Apply, export and Undo succeeded without browser errors. The width increased 10 mm; all 384 recognized protected vertices across five profiles remained exact. Undo bytes matched the canonical imported workspace version. The first verification mistakenly required pre-import STL index order to survive import; the corrected comparison uses the retained imported baseline, not an approximate geometry comparison.

Evidence: `artifacts/axial-browser/browser-result.json`, `verification.json`, `preview.png`, and exported STLs. One actual planner request used 1,742 input and 73 output tokens. This test extends orientation coverage for coordinate-aligned profiles, not arbitrary assemblies, oblique axes or mechanical-strength qualification.

## Rotated sequence invariants

The composition invariant now uses the same unambiguous axial recognizer to identify protected vertices, then hashes their **world-coordinate** values and canonically oriented world triangles. It does not compare normalized or rotated approximations. Thus original hole surfaces remain exact after every speculative step for supported X/Y/Z-aligned profiles. Oblique and ambiguous recognition still fails. This supersedes the earlier note about Z-only multi-step invariants.

Thirty-one composition-invariant, axial-edit and sequence-planner tests pass. New cases cover two protected widenings of a rotated plate, and rejection of a subsequent hole-moving step with no commit. A real Chrome run on a rotated copy of the public plate requested two 1 cm widenings while keeping holes fixed throughout. Both step invariants passed; the exported width grew exactly 20 mm; all 384 protected vertices from five profiles remained exact; one Undo restored the imported bytes.

Evidence: `artifacts/axial-sequence-browser/browser-result.json`, `verification.json`, `preview.png`, and exported STLs. Two real planner requests used 3,478 input plus 151 output tokens. Reproduce with `scripts/test_axial_sequence_browser.mjs` against the isolated server on 2757, then `scripts/verify_axial_sequence.py`. This extends checked command composition; it does not constitute new learned-rule promotion, strength qualification, or a frozen benchmark result.

### Height changes perpendicular to the bore

The workspace now accepts protected X, Y or Z expansion. Natural-language height/taller requests retain explicit units and use the same axial recognition and inherited geometry checks. Expansion along the recognized bore axis remains rejected; shrinking and oblique frames remain unsupported.

Actual browser evidence is retained in `artifacts/axial-height-browser/`: the public plate rotated to a Y-axis bore accepted “Make this 1 cm taller keeping holes fixed”. Export verification checks a 10 mm Z increase, exact original protected world vertices, watertightness, Euler characteristic and byte-exact Undo against the canonical imported baseline. This used one model request, 1,753 input and 81 output tokens. This is an engineering capability extension, not evidence of an automatically promoted learned skill.

Validation: 94 targeted Python tests passed across axial editing, planning, quantity intent and composition invariants; six frontend description tests passed and the production UI build succeeded (existing bundle-size warning remains).
