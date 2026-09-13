# Reference glasses mass and numerical contract integrity

The production audit reproduced an invalid acceptance: an infinite ear-support coordinate produced a zero reaction and passed both static-support and ear-load gates. NaN/Infinity material or component inputs could also yield nonfinite reports. Dataclass construction had not validated those inputs.

`engineering.assess_geometry` now checks finite contract data and valid support axes before any geometry measurement. It also checks intermediate material mass, CG, support span, reactions, deflection and emitted numerical gate fields, so finite inputs that overflow cannot become a false pass. The independent finite-input regression includes a sentinel proving invalid contracts fail before touching geometry and an unchanged valid 1 g reference load case. Before/after evidence is retained in `artifacts/production/mass-audit/`.

Run `.venv/bin/python scripts/screen_reference_mass.py` to rebuild the existing reference from editable parameters against its pre-build hardware layout and save the nominal inventory. The mass contract is written before CAD generation. It uses the existing explicitly labeled HP legacy PA12 profile (1.01 g/cm³), not a newly invented or current-qualified density.

| Known item | Nominal mass |
| --- | ---: |
| Modeled printed parts | 24.385710 g |
| Pi Zero 2 W catalog entry | 12 g |
| Camera Module 3 catalog entry | 4 g |
| Known-inventory sum | 40.385710 g |

The report includes per-part BRep volumes and masses, source/qualification metadata, hashes of input contracts, independent engineering gates and unknown inventory entries. The subtotal is not a measured assembly weight or a certified lower bound. Cable, fastener, microSD and lens masses remain absent. The CG uses only known items and approximates electronics at their envelope centers; it does not establish actual load distribution or comfort. No maximum wearable mass requirement, wearer support geometry, physical fit, material qualification or production-release pass is inferred.

This is an agent-authored validator repair and a reproducible deterministic calculation. It does not demonstrate model-weight training. The archived benchmark and private cases were untouched. No LLM requests were required for the CAD/mass calculation; engineering authoring and verification costs are not fully metered.
