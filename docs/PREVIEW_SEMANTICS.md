# Describe executed geometry before Apply

The recovery video exposed a mismatch: the planner said “The selected object will be moved 1 mm,” while the accepted repair moved selected vertices by different amounts, reaching 1 mm only at the interior peak. The smaller learning card disclosed the taper, but the primary preview repeated the incorrect intent.

`studio/src/preview-description.js` now derives section descriptions from the executed preview command and accepted trial. It distinguishes direct selected-vertex translation, tapered peak translation, and the measured selected-vertex span for resize. Rejected previews report unchanged geometry instead of repeating the planner's proposed success. Missing trial provenance does not invent a strategy. Both chat and the Apply banner use this description, including after a learning-store outage.

Six Node tests cover actual recorded trial payloads, rejected output, negative displacement, resizing and absent provenance. Run `node --test studio/tests/preview-description.test.mjs`. Fixture payloads contain public development geometry outcomes; they are independent of ignored artifact paths. No geometry, learning-promotion criteria or frozen benchmark checks change.

The actual browser reproduction script is `scripts/record_learning_preview.mjs`; it checks the visible banner during recovery, promotion and reuse. It uses the same isolated storage-fault server as the recovery test. The test is explicit about this injected storage failure and does not modify the production learning store.

This makes the accepted alternative visible for review. It does not make tapered movement satisfy a request for rigid translation of every selected vertex, nor establish mechanical suitability. Explicit rigid-motion requests now carry a planner/executor contract; see `RIGID_TRANSLATION.md`. Broader or unfamiliar design-intent constraints remain incomplete.

Browser verification passed on all three actual edits: visible taper descriptions, recovery with zero additional CAD executions, promotion, and one-attempt reuse. The two round exports remain byte-identical. Video: `artifacts/learning-preview-browser/learning-preview-demo.mp4`; raw responses and visible summaries: `actual-learning-result.json`. This run used three model requests, 4,848 tokens and five geometry candidates; no extra fixture discovery was needed. Local usage was retained; the isolated server did not enable remote tracing. Authoring costs are not fully metered.
