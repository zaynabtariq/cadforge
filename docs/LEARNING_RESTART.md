# Learning across backend restarts

`record_learning_restart.mjs` exercises the actual browser with public STL imports, mouse section selection, natural-language edits, Apply, Undo and STL export. It first discovers a repair on the public plate, then promotes it through the round object. The test stops the backend process and starts a new process with the same isolated workspace and learning store before the third edit.

The harness verifies different process IDs and byte-identical learning storage immediately across restart. The third edit must report learned reuse in one candidate. It does not reset the production learning store, supply a fake model response or inject the selection. Weave tracing is enabled in both backend processes. Local server logs retain the trace URLs.

This tests process persistence and reuse on a repeated edit after cross-object promotion. It does not prove unfamiliar-object generalization, model-weight training, hardware readiness or an advantage over a strong retrieved-script baseline. The current-validator development comparison remains a tie with retrieval; see `REGION_CONTRACT_TRANSFER.md`.

Reproduce with Vite on 2740 using `CADFORGE_API_URL=http://127.0.0.1:2741`, then `node scripts/record_learning_restart.mjs`. The script owns a test backend on 2741 and creates a fresh isolated run directory. The actual production API on 2721 is separate. Recorded frames show the UI; process shutdown/restart is evidenced by the result and server logs rather than a simulated UI animation.

Verified recording: `artifacts/learning-restart-browser/learning-restart-demo.mp4`. The run changed backend PID 89782→89993, with 10,372 learning-store bytes unchanged across startup. Candidate→promotion→reuse required 2+2+1 geometry trials; all three edits passed. The pre-restart and post-restart round exports are byte-identical. The browser reported no script errors. Three actual model calls used 5,036 tokens; no additional fixture discovery was required beyond the first two edits. Authoring costs are not fully metered. An initial frontend launch used the wrong working directory and failed before any CAD/model work; the corrected launch succeeded.

Raw records: `actual-learning-result.json`; server shutdown/startup and Weave call URLs: `1789274667384/server.log`. No benchmark or production qualification claim follows from this bounded persistence check.

## Current validator rerun

The current rerun is `current-validation/learning-restart-demo.mp4` (48.92 seconds). Its actual browser results are in `current-validation/actual-learning-result.json`. Discovery, cross-object promotion, and post-restart reuse again took **2 + 2 + 1 CAD candidates**, with no browser errors. Three real planner calls used **5,471 total tokens** (5,323 input, 148 output). Backend PID changed 1596 → 1654 while all 10,373 learning-store bytes remained identical. The second and third exported STLs are byte-identical.

This was a fresh isolated development run; the default production store was not reset. Its separate current-context maintenance replay cost another 12 CAD candidates, documented in `LEARNING_REVALIDATION.md`. Authoring and all prior investigation costs remain incompletely metered. These are not equal-budget benchmark results.

The first rerun failed before CAD/model execution because the bundled static UI intercepted the fixture's appended health route. The test service now registers that route before the static mount. Its failure log is retained alongside the successful run. `CADFORGE_LEARNING_VIDEO_DIR` selects a separate output directory so earlier recordings remain intact.
