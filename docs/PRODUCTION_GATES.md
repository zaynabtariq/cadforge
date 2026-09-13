# Production engineering gates

`cadforge.engineering` assesses actual delivered BRep solids against an externally supplied `EngineeringContract`. Candidate parameter labels and self-reported measurements do not establish passing geometry. `assess_step` imports the delivered STEP; `assess_geometry` accepts independently identified parts. Anonymous STEP import cannot authenticate semantic part names. These gates extend development work and do not change the frozen v1 benchmark or access hidden cases.

Each gate has `pass`, `fail`, or `blocked` status and records its measurement, threshold and interpretation. `pass` means the specified numerical/geometric check succeeded, `fail` means the delivered artifact contradicts the supplied requirement, and `blocked` means required evidence or a supported method is missing. A count of passing geometry checks is not a percentage of factory readiness. `engineering_ready` remains false; this software does not sign a production release.

## External contract and component provenance

The product owner/evaluator supplies component envelopes in world coordinates, clearances, exact mounting axes, connector insertion corridors, wall witness locations, cable routing, material properties and product limits. Contracts should be versioned and frozen before an optimization loop. Do not derive required limits or component dimensions from the candidate being assessed. Public hardware drawings support bare-board mechanical assumptions; they do not establish a complete assembled electronics envelope, connector insertion force, cable routing or wearable safety.

The official [Raspberry Pi Zero mechanical drawing](https://datasheets.raspberrypi.com/rpizero/raspberry-pi-zero-mechanical-drawing.pdf) and [Zero 2 W mechanical drawing](https://datasheets.raspberrypi.com/rpizero2/raspberry-pi-zero-2-w-mechanical-drawing.pdf) are the starting sources for externally specified board geometry. A production contract must record the actual purchased hardware revision, fitted headers, camera variant, cables, screws and component masses. A placeholder source string is not a supplier certification.

## Checks and their limits

| Check | Measured evidence | What remains unresolved |
|---|---|---|
| Solid geometry | Validity, positive material volume, pairwise material intersections | Numerical validity is not manufacturability |
| Component placement | Intersection of delivered material with a fixed clearance-expanded component box | Envelope accuracy, retention, electrical isolation |
| Mounting holes | Empty cylinder on the specified axis plus a fully occupied bearing annulus | Thread engagement, screw-head clearance, assembly access, pullout and fatigue |
| Port accessibility | Material-free connector insertion box | Actual connector geometry, insertion force and complete cable termination |
| Cable clearance | Swept circular envelope along supplied segments | Ribbon orientation and strain relief |
| Cable bend | Straight routes pass against a sourced radius requirement; sharp polyline corners fail | Curved routes need actual verified arcs; three points do not prove a smooth bend |
| Local print wall | Complete material occupation of an independently specified wall prism | Global thickness, thin corners and process capability |
| Mass and CG | Solid BRep volume times supplied density, plus supplied component masses | Missing BOM items, infill, printing shrinkage, real measured mass |
| Ear reaction | Two-support static reaction from calculated CG and supplied nose/ear positions | Left/right pressure distribution, fit, comfort, motion and skin contact |
| Beam deflection | Complete rectangular material section and externally supplied modulus/load | Anisotropy, creep, joints, stress concentrations and nonlinear behavior |

The linear cantilever screen uses `delta = P L^3 / (3 E I)` and rectangular `I = b h^3 / 12`, with N, mm and MPa units. The formula is documented in NASA's [Mechanical Design Reliability Monograph](https://extapps.ksc.nasa.gov/reliability/Documents/Mechanical-Design-Reliability-Monograph.pdf). The gate requires the entire declared rectangular prism to be present in the actual geometry, a sourced modulus and a prescribed tip load. It also requires deflection below 5% of span as a conservative local modeling condition. That 5% choice is this project's screening assumption, not a certified material limit. This is an analytic screen, not FEA or fatigue analysis.

No default PLA, PETG, PA12 or other mechanical properties are invented. If material/process/lot-specific density or effective printed modulus is absent, the dependent gates remain blocked. A chosen MJF/SLS/FDM process alone supplies neither strength nor a mass model. Global thickness, overhang/support orientation, material qualification, fastener strength, printer tolerance, powered thermal behavior, wear trials and release require further methods or physical evidence. Supplied evidence references are recorded but not automatically authenticated or converted into a release pass.

## Development feedback and self-correction

Stable gate names can drive bounded repairs: reduce interference by increasing an externally permitted clearance, relocate an incorrectly aligned hole, restore missing bearing material, widen a blocked insertion corridor, or increase a deficient beam section. A repair must keep product dimensions and external contracts fixed except for explicitly designated optimization variables. Promote a repair command only after the actual revised BRep passes its target check and independent regressions pass. A fix to one sampled witness must not be called a global manufacturing fix.

The test suite contains deceptive artifacts: a solid box masquerading as a component cavity, a missing hole, an empty hole location with no bearing material, a blocked port, a perforated beam that cannot use the solid-section formula, a sharp cable corner falsely suggesting a bend radius, and invalid STEP content. These tests check rejection behavior as well as successful simple geometry. Test material values are labeled synthetic and do not justify production recommendations.

`contract_from_public_layout` is a convenience adapter for the production layout's documented axes. It independently constructs world-coordinate keepouts and mounts instead of using the candidate's probes. Its input must be an evaluator-approved layout persisted before candidate generation, with `wall_mm` and `clearance_mm` fixed from the external design requirements. Feeding the candidate's own exported layout back into this adapter would defeat independence and is explicitly unsupported as validation evidence. The adapter does not invent absent component masses or material data.
