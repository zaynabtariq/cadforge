# Rigid selected-section movement

The original selected-region solver could repair failed direct movement by tapering displacement. That is useful only when a transition is acceptable. A request requiring equal movement of every selected point must not silently use that repair.

Translation commands now accept `translation_mode: rigid`. The typed planner carries this constraint for rigid motion, equal selected-point movement and explicit no-deformation/no-taper requests. A deterministic post-planning check restores the constraint if a model drops it. Ordinary existing requests retain the explicitly disclosed transition behavior. Other unsupported preservation constraints continue to request clarification.

The geometry executor restricts rigid requests to direct displacement and checks the entire selected displacement vector. Existing outside-coordinate, face, volume and intersection checks remain active. If the direct edit fails, the original remains unchanged and the preview cannot be committed. Retrieval skips incompatible learned transition priorities; even an injected priority cannot change the executor's allowed strategies. Invalid mode values reject.

Independent tests compare every exported vertex against the expected float32 STL transformation, check unchanged outside coordinates, reproduce the formerly repaired large shear, and inject an incompatible learned priority. Planner tests include a model output that drops rigid mode. The ordinary transition path still repairs the original development failure.

Editing the geometry validator changes its context hash. Existing learning evidence is retained but is not automatically trusted under the new validator; no production store is reset or evidence transplanted. The frozen benchmark remains untouched.

`verify_rigid_intent.py` runs actual model planning and geometry under existing Weave tracing. A first fixture attempted X movement and incorrectly expected rejection; that direction legitimately passed. Its two model calls and geometry outcomes remain in Weave and the first isolated workspace. The corrected experiment uses the known Y shear case. This discovery error is separate from solver correctness; it is not hidden-test feedback.

This protects the selected mesh vertices under the existing numerical tolerance. It does not guarantee continuous CAD features, minimum wall thickness, unchanged mechanical leverage or manufacturing readiness. The current language detector is bounded; unfamiliar wording depends on the typed model or clarification.


Final live verification passed: `artifacts/rigid-intent/93710a8ffb9742c89f4fe7dd970e5cef/result.json` records the rejected 7 mm Y shear and accepted 0.1 mm rigid movement, with the saved workspace byte-identical before/after both previews. The successful run used two model calls, 3,273 tokens and two direct geometry trials. Two earlier harness runs added four model calls and four geometry trials; their traces/workspaces are retained. The second harness error compared normalized workspace STL bytes against uploaded STL bytes, which may differ at import, instead of comparing the same workspace export before/after. This assertion was corrected; no geometry checks changed. Full authoring and first-run token costs are not locally aggregated.

94 focused tests passed, including eight independently authored geometry/priority-bypass cases. The local API was restarted with the new implementation. Weave calls for the successful run:
- https://wandb.ai/zzaynabb-03-radpilot/cadforge-continual/r/call/01a098fa-48fd-71e2-82b2-0e04da92b309
- https://wandb.ai/zzaynabb-03-radpilot/cadforge-continual/r/call/01a098fa-55ce-79ca-92af-14f33903089e
