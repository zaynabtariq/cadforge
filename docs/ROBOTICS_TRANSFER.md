# Robot-link transfer with preserved pivot geometry

`cadforge.robotics` adds an editable two-pivot robot link as a different object from the electronics housing and fit coupons. It demonstrates a bounded design edit: increase link width while preserving the pivot axes, their center distance, bore and boss diameters, overall length, and thickness. It does not claim universal object generation or a production-qualified robot arm.

## Executed operation

```python
from cadforge.robotics import RobotLinkSpec, build_link, widen_link

link = build_link(RobotLinkSpec(center_distance=80, width=20))
change = widen_link(link, 28, output_dir="artifacts/robotics")
assert change.accepted
```

The default link has pivots at `(-40, 0)` and `(40, 0)` mm, 4 mm bores, 12 mm bosses, 104 mm overall length and 8 mm total thickness. Increasing its width from 20 to 28 mm preserves those dimensions. The verifier measures cylindrical faces, their axes and diameters, the bounding box and solid validity directly from BRep. It distinguishes inner and outer cylindrical surfaces by the radial surface-normal direction; face orientation labels alone are unreliable after boolean operations.

The edit has an immutable version ID derived from parameters, parent version and backend context. A successful edit returns a new link and exports STEP, STL, JSON and editable Python with a measured operation record. If an interface constraint or independent invariant check fails, the result retains the original link and reports `accepted=False`; the original shape is never mutated. The source model remains available for rollback.

Requests above `interface_max_width` are rejected. Widths below the boss-plus-edge-distance budget are rejected, as are inadequate boss wall material, insufficient end distance, overlapping bosses and nonfinite dimensions. `widen_link()` only accepts an increase; it is not a general shrink operation. These constraints are explicit geometric assumptions, not calibrated manufacturing tolerances.

## Reuse of persistent learned commands

`apply_learned_fit()` applies the existing healthy `supported_fastener` command, including its inherited bore rule, from `ContinualLearning`:

```python
from cadforge.robotics import apply_learned_fit, robot_fit_executor

fitted_spec = apply_learned_fit(
    RobotLinkSpec(), service, context,
    hardware_diameter=3, radial_clearance=0.2, min_wall=1.5,
)
link = build_link(fitted_spec)
change = widen_link(link, 28)
```

This is initial interface sizing. It occurs **before** the pivot design is fixed. Widening thereafter preserves the fitted bores; it does not silently recompute different pivot interfaces.

`robot_fit_executor(template, output_dir=None)` is a real BRep callback compatible with `ContinualLearning.validate_candidate()`. It builds the two-pivot link from candidate bore/boss parameters, checks a requested hardware-plus-clearance swept cylinder at each pivot, checks a full annular material witness at each boss, and measures pivot spacing. It returns `Measurement` with actual overlap/missing-material volumes. With an output directory, it retains CAD, editable parameters and a measured report and returns their SHA256 artifact digests. The orchestrator can use a fresh robot task to monitor an existing promoted rule, preserving the new evidence in SQLite and quarantining the rule if the robot check fails.

```python
active_id = service.latest_id("supported_fastener", context=context)
service.validate_candidate(
    active_id, fresh_robot_cases,
    robot_fit_executor(RobotLinkSpec(), "artifacts/robotics/fit"),
    stage="monitor", context=context,
)
```

The learning context must match the original ideal-CAD context; observed source-range guards still apply during ordinary reuse. A changed material/process/validator context requires a new discovery and validation version. Passing local bore/boss transfer on a robot link is evidence about those interfaces, not arbitrary robotic assemblies or motion planning.

## Validation and remaining scope

The robotics tests execute actual CadQuery geometry, STEP roundtrip measurement, out-of-envelope rollback, an injected geometry translation that the independent pivot checks catch, and positive/negative hardware-clearance probes. A small stub test checks only the adapter contract; it is not counted as learned-skill transfer evidence. Persistent learned transfer should be reported from the orchestrator's actual SQLite and artifact records.

Widening changes mass, inertia, stiffness and possibly joint loading. Preserving pivot geometry does not preserve all dynamic behavior or a load rating. The current module has no multibody dynamics, FEA, fatigue, actuator/fastener selection, physical tolerance calibration or manufactured validation. Its cylindrical-feature selector is scoped to this two-through-bore recipe; arbitrary imported CAD needs explicit feature identification and new invariant contracts. The frozen benchmark is not imported or modified by this module.
