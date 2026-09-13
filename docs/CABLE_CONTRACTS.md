# Cable route validation across scales

Three invalid engineering results were reproduced before this repair:

- A small 45-degree polyline corner passed the straight/bend gate because the squared raw cross product was compared against an absolute tolerance. Scaling the same corner changed its classification.
- A duplicate-point two-point route failed clearance but incorrectly passed the separate bend gate.
- A negative supplier minimum bend radius passed a straight-route gate.

The evaluator now checks positive finite cable radius and supplied bend limits, three-dimensional finite coordinates, and positive finite segment lengths before CAD measurements. Missing bend specifications still remain blocked. Straightness uses unit segment directions, a dimensionless sine-angle tolerance of 1e-12 and a positive dot product. The same resolved corner now fails regardless of coordinate scale; reversals remain invalid. The angular tolerance is numerical policy, not a physical bend-radius guarantee.

The repair is reusable across objects and materials. `tests/test_cable_contract.py` independently covers scaled 45/90-degree corners, repeated points, malformed limits, straight controls, absent specifications and reversals. Before/after probe outputs are retained in `artifacts/cable-contract/`. No supplier properties were invented, and none of these test-only assumptions are promoted into a qualified material/cable specification.

The production glasses still require a real cable selection, endpoint/connector placement, routed geometry, supplier bending limits and strain-relief assessment. Polyline corners have zero radius. Smooth physical bends need verified arc geometry; these checks do not qualify an unspecified camera ribbon cable or powered assembly. Frozen benchmark files and hidden cases were untouched.

Verification: the combined engineering/finite-input/production-geometry suite passed 85 tests. Six additional malformed-coordinate/radius checks were then added to verify rejection before touching CAD, bringing the cable-specific suite to 25 tests. These development checks use real BRep intersections and no model calls; authoring costs are not fully metered. This is an agent-authored deterministic validator improvement with retained counterexamples, not autonomous model-weight learning or new production qualification.
