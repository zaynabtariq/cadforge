# Retaining unresolved counterexamples

A development run exposed a failure in persistent strategy learning. On an imported sphere, a 7 mm selected-section edit required a checked repair. A 5 mm edit on a capsule supplied topology transfer and promoted that repair. A 100 mm sphere edit then failed and quarantined it. Repeating the easy 7 mm edit immediately promoted the same strategy with a new evidence-derived ID. The earlier failure had effectively been forgotten.

Quarantine now covers the strategy, axis and validator context, including historical aliases in existing stores. Later successful executions are still recorded and may be applied when all geometry checks pass, but they cannot automatically restore the quarantined priority. The user-facing result explains that the current edit passed while an earlier counterexample remains unresolved. Other strategies and validator contexts retain their own evidence boundaries.

The regression test executes all four real geometry previews and checks candidate → promotion → quarantine → successful execution without re-promotion. It also constructs a historical alias to verify migration-compatible recommendation behavior. The learning, recovery, outage and composition suites pass 20 tests. An initial test command referenced a nonexistent pluralized outage filename and ran no tests; the corrected command is:

```sh
.venv/bin/pytest -q tests/test_edit_learning.py tests/test_learning_recovery.py tests/test_learning_outage.py tests/test_composition.py
```

This conservative policy does not learn a safe displacement range from the failure. Automatic rehabilitation would require a refined support contract and rechecking the retained counterexample, which are not implemented. Existing geometry validation remains mandatory, and these development cases are separate from the frozen benchmark.

## Sequence rollback and pre-promotion failures

Independent review reproduced an equivalent gap before first promotion: sphere 7 mm repair, sphere 100 mm failure, then capsule 5 mm repair still promoted the failed strategy. Failed transition trials now exclude the corresponding axis/strategy/context family even when no skill ID existed yet. Explicit rigid requests stay outside transition support.

Composed edits now persist executed failures of priorities that already exist in the real store. They record the exact trials without another geometry execution and retain the receipt in the step outcome, which the UI displays. Successful scratch learning cannot be promoted through this negative-evidence path. Shared-invariant failures are assessed afterward and do not incorrectly blame a locally passing strategy. Store write failures remain visible as audit failures; automatic retry for these composed counterexamples is not implemented.

The expanded learning, recovery, outage, composition, invariant and sequence suites pass 49 tests. This policy is deliberately broad within an axis and validator context: refining support by displacement and topology, then independently rehabilitating a strategy, remains future work. No archived benchmark score has been rerun or changed.
