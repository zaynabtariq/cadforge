# Learning-store outage behavior

A region edit previously called strategy retrieval before running geometry. A corrupt or inaccessible history store therefore aborted the geometric operation even when the normal checked repair could succeed.

The workspace now falls back to the ordinary checked strategy sequence when retrieval fails. It records the retrieval error, validator context, actual repair trials and final learning-write status in the local preview. Geometry executes once. Corrupt history is never erased or replaced with an empty store, and an unsuccessful learning write is explicitly labeled `audit_failed`, not a promotion or successful reuse.

An isolated fault-injection run used a deliberately corrupt test store, a real sphere STL and a 7 mm selected-region request. The sharp candidate failed, the interior transition passed, and both trials survived in the preview while the corrupt store remained unchanged. No production learning data was modified. See `artifacts/learning-outage/result.json` and its referenced preview. Tests also inject a permission failure and verify unchanged saved geometry before Apply and no duplicate geometry execution. All 16 focused outage/learning/workspace tests passed.

This improves evidence retention during a storage failure; it does not repair the corrupt store, automatically reconcile retained previews, or claim the missing outcomes were learned. Those recovery actions remain separate work. The existing local repair still has peak-displacement semantics and all geometric checks remain active. The fault-injection run made zero model calls; authoring costs are not fully metered.

## Recovering retained outcomes

New previews also retain their immutable source version, source STL hash and validator context. **Retry saving learning** can persist those actual outcomes once storage is healthy. It rejects changed source meshes, changed validators and projects without locally executed preview evidence. It does not rerun CAD, fabricate trials, or repair/reset a corrupt store. Old previews missing recovery metadata are not silently promoted.

The learning store saves a receipt with each event. A repeated request for the same session/preview and identical measured data returns that receipt without adding evidence, skills or quarantines; conflicting data rejects. This also handles a write that completed before an error reached the caller. The retry button and `/api/sessions/{session_id}/previews/{preview_id}/learning/retry` route expose this operation. Recovery is explicitly requested, not a background scan.

An isolated real-geometry experiment retained sphere and capsule repair outcomes during a deliberately corrupt test store. After preserving the corrupt file and restoring test-store availability, retries produced a candidate then promotion with zero geometry calls. A third mesh used the recovered strategy in one attempt. Overall: three geometry executions, five candidate attempts (2+2+1), zero model calls. Evidence is in `artifacts/learning-recovery/result.json`. The production store was untouched, and these are bounded development transfers, not hidden benchmark results.

All 21 focused recovery/outage/learning/workspace tests passed, including an ambiguous completed-write failure, no-CAD-rerun assertion, source/context changes and archive rejection. The actual HTTP route was also checked through FastAPI TestClient on the isolated workspace. The retry button subsequently passed the recorded browser fault-injection test below. Engineering authoring costs remain unmetered.


## Recorded browser recovery and reuse

`artifacts/learning-recovery-browser/learning-recovery-demo.mp4` records actual public STL upload, mouse marquee selection, plain-language requests, retry, Apply and STL export. An isolated fixture deliberately starts with corrupt learning storage; a test-only control endpoint preserves that file and restores storage availability. The actual UI retry then saves the retained candidate with **zero additional geometry executions**. A second public mesh promotes the repair, and Undo followed by the same request reuses it in one attempt instead of two. The two round-model exports are byte-identical. This final step is repeat-task reuse after cross-mesh promotion, not an unseen third-object evaluation.

The successful recording uses three actual model calls (4,849 tokens) and five candidate trials (2+2+1). A preserved harness failure before recovery adds one model call (1,615 tokens) and two trials; total discovery plus recording is four calls, 6,464 tokens and seven trials. No production learning store was reset. The isolated server did not enable remote Weave tracing; local model usage and all responses are retained. Authoring costs are not fully metered.

Reproduce by starting `scripts/serve_learning_recovery_test.py`, running Vite on port 2740 with `CADFORGE_API_URL=http://127.0.0.1:2741`, then `node scripts/record_learning_recovery.mjs`. Each fixture server launch creates a fresh isolated directory. The fixture endpoints exist only in this test script. The production history endpoint now reads its configured workspace store, preventing cross-workspace history mixing. Eleven focused recovery/outage/learning tests and the frontend build pass. See `verification.json`, `actual-learning-result.json` and `discovery-1/` for evidence. These remain development tests, with all existing geometric checks active and no change to the frozen benchmark.
