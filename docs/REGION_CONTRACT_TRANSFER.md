# Learning after rigid-contract enforcement

The geometry-validator change invalidated older strategy contexts. A fresh public development run checks that learning still reduces repeated work under the stronger contract and does not bypass rigid intent. It does not replace or revise the frozen v1 benchmark.

`evaluate_region_contract_transfer.py` writes a four-case contract and SHA-256 before discovery or evaluation. Two actual discovery geometries establish a candidate and promote the repair under the current validator. Evaluation uses two differently dimensioned capsules and small/large rigid requests. These are known procedural families, not hidden or broad novel-object cases. Evaluation never records outcomes into the learning store; its bytes are checked unchanged afterward.

Every arm has the same maximum of three candidate trials per case and the same unchanged geometry checks. The arms differ only in strategy priority: default sharp-first, a manually supplied retrieved transition, or priority read from the learned store. This is a deterministic strategy ablation, not an equal-token multi-agent benchmark. The retrieved strategy's authoring/discovery cost is not measured.

| Arm | Accepted edits | Rejected edits | Candidate trials |
|---|---:|---:|---:|
| No learned priority | 3 | 1 | 6 |
| Retrieved transition script | 3 | 1 | 4 |
| Learned priority | 3 | 1 | 4 |

The large rigid shear is rejected by every arm. An incompatible supplied transition cannot alter the rigid executor's allowed strategies. No rejection is relabeled as successful CAD generation. Learning saves two candidate trials relative to default ordering, but ties the retrieved script; this run establishes no learning advantage over retrieval or broad generalization.

Discovery costs two geometry executions and four candidates. Evaluation costs twelve executions and fourteen candidates, for fourteen executions and eighteen candidates overall. There are zero model calls in this run. Learning and script authoring costs are not fully metered. All raw checks, discovery previews, source meshes and accepted STL exports are retained in `artifacts/region-contract-transfer/4a62438ff4a848dd81bdbb144432d440`. The contract hash is `21128cdf7acef1df7dcbe1a456a57ce271425dccb757ebf874b9419808871e20`.

A regression additionally verifies that an incompatible rigid rejection does not quarantine a valid transition strategy: later transition-permitted use still succeeds in one candidate. The learning store records the rigid failure with no used skill, preserving both evidence and scope separation.

Independent artifact verification (`independent-verification.json`) confirms byte-identical accepted STL exports across all arms, unchanged outside coordinates, full accepted-trial gates, and exact serialized rigid displacement. The store contains only the two discovery events and one promoted skill. The script asserts before/after store bytes are identical; separate temporal hash snapshots were not retained. Discovery costs four candidates and this evaluation saves only two, so this run does not yet amortize discovery cost.
