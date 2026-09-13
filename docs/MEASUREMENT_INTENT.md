# Preserving dimensional intent

A development audit found the offline numeric guard could overwrite a correct model response with a truncated quantity. Actual before/after responses are retained under `artifacts/measurement-intent/`.

| Request | Before | Repaired |
| --- | --- | --- |
| Move this .5 cm right | 50 mm | 5 mm |
| Move this 1/2 inch right | 1 mm | 12.7 mm |
| Make this 0.04 m wide | 0.04 mm | 40 mm |
| Move this 1e1 mm right | 1 mm | 10 mm |
| Move this 2 cm right and 3 cm up | Dropped the upward move | Requests one movement first |

The shared planner now consumes complete decimal, fraction, mixed-fraction and scientific quantities. It converts mm, cm, meters, inches, feet and yards. Ambiguous decimal commas, invalid fractions, conflicting dimensions and unsupported units require clarification. The current command schema represents one resize or movement axis; it cannot silently discard a second requested axis. Explicit minimum-wall quantities work before or after the words “minimum wall”, including “at least”. Contradictory radius/diameter specifications are rejected. A model clarification is retained rather than replaced with an offline command.

Independent regression tests cover these failures, ordinary unitless millimeters, box syntax, adversarial model outputs, and conflicting wall/extent constraints. The focused planner/workspace run passed 80 tests. This is a bounded grammar guard, not a proof that arbitrary language is understood; geometric validation still applies independently.

`scripts/test_measurement_studio_browser.mjs` imports the unrelated public plate STL through the real file input, selects it with a real canvas click, submits “Move this .5 cm right”, applies, exports and undoes it. Exported STL bounds independently confirm a 5 mm X translation, unchanged dimensions, watertightness, unchanged export before Apply, and byte-exact Undo. No API or model was mocked. Artifacts and the raw recording are under `artifacts/measurement-studio-test/`.

This repair was authored by the engineering agents after inspecting actual failures. It persists in the shared planner and project instructions; it is not model-weight training or an automatically discovered runtime strategy. The earlier learning-loop recording demonstrates that separate runtime mechanism. No archived benchmark code, instances or scores were changed. Offline probes have zero model calls; live browser usage is recorded in each result and aggregated in `artifacts/measurement-intent/costs.json`. Agent-authoring costs are not fully metered and must not be reported as zero.
