# MJF PA12 manufacturing assumptions

The selected process is MJF PA12 and the selected power architecture uses an external USB supply. These decisions permit a nominal prototype package; they do not establish printer calibration, assembly fit or production release.

## Material profile and retrieval limits

HP's current [official materials portfolio](https://www.hp.com/us-en/printers/3d-printers/materials.html) links its HP Jet Fusion 5200 PA12 data to [document 4AA8-5028ENW](https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA8-5028ENW). During this run that document host returned service/DNS errors, so its current numerical contents were not verified. Do not label the implemented profile as a verified 2026 material specification.

For transparent preliminary screening, `materials.py` records HP-authored document **4AA6-4895ENE, November 2017**, read from a [distributor-hosted copy of the original HP datasheet](https://www.3dmeclab.com/download/MJF/MJF-PA12.pdf). Its values are specific to the stated legacy process context:

| Property | Nominal value | Datasheet method |
|---|---:|---|
| Printed-part density | 1.01 g/cm³ | ASTM D792 |
| XY tensile modulus | 1700 MPa | ASTM D638 |
| Z tensile modulus | 1800 MPa | ASTM D638 |

The datasheet identifies balanced print mode with FW BD5 and treats these as typical values rather than specification limits. Code uses 1700 MPa for a preliminary stiffness screen because it is the lower listed directional value; that choice is not a statistical material lower bound. No allowable stress is supplied. These values cannot establish lot-specific strength, fatigue, creep, skin-contact suitability, dye/coating compatibility or current-machine performance. HP's primary [white paper 4AA7-2326ENW](https://h20195.www2.hp.com/v2/getpdf.aspx/4AA7-2326ENW.pdf) separately identifies 1700–1800 MPa modulus in its legacy PA12 context. It does not resolve the unavailable current datasheet.

## Hardware mass and representative eyewear sizing

The official Raspberry Pi [Zero family article](https://www.raspberrypi.com/news/what-can-you-build-with-raspberry-pi-zero/) lists **12 g for Zero 2 W**. The official [camera hardware comparison](https://www.raspberrypi.com/documentation/accessories/camera.html) lists **4 g for Camera Module 3**. These are nominal component values, not weighed installed assemblies. The known electronics subtotal is 16 g. Cables, fasteners, microSD, lenses and any additional components remain separately unknown; an estimate using only that subtotal must be labeled incomplete.

Ray-Ban's [official RX7074 product page](https://india.ray-ban.com/eyeglasses/male/rx7074.html) supports a representative marketed **52–18–145 mm** reference: lens width, bridge and temple length, respectively. It also lists a **42.4 mm lens height**. The detailed lens width is 52.1 mm, while its marketed size is 52 mm; the CAD uses nominal 52 mm. This is one commercial size, not an anthropometric standard, individual wearer measurement or permission to reproduce the product's styling. Electronics weight and rigid housing placement alter the fit problem substantially.

## Prototype handoff requirements

The production exporter now writes separate named-part STEP/STL files under `parts/` and a portable `manufacturing-manifest.json`. It records millimeter units, the parameter specification, provisional process, BRep volumes, bounds, solid counts, byte counts and SHA-256 file identities. `cadforge.handoff.verify_handoff` detects missing or modified inventoried files without executing the editable Python source. Integrity metadata does not authenticate a reviewer or qualify a manufacturing process.

The reference package in `artifacts/production/named-handoff/` contains six part pairs and 18 inventoried files. All file identities pass; independent reopening checks the part STEP volumes and STL watertight positive volumes. The engineering assessment remains 43 pass / 0 fail / 11 blocked. Ten handoff/product tests pass, including an actual STEP roundtrip and detection of altered source and missing STL files. The handoff does not supply a complete purchased BOM, physical fit measurements or release approval.

Export separate named-part STEP/STL files and editable source, with a manifest recording units, file hashes, BRep volume, bounds, provisional material/process and revision. Include a BOM identifying purchased board/camera variants, camera cable compatibility, USB cable routing, all screws/nuts/washers, lenses and unresolved masses. The assembly drawing must show actual fastener engagement, driver/nut access and cable termination.

A print supplier must review orientation, powder removal, minimum features, long thin temples, shrinkage, hole compensation and finishing. Fit coupons can test manufacturing capability before committing to a complete frame. A numerically learned allowance from virtual cylinders is not printer calibration; retain both the intended finished dimension and the selected manufacturing compensation in the record. Physical coupons, powered thermal testing, assembled mass/CG, wear fit, retention and independent release approval remain open evidence gates.

Straight tool approach corridors now have an independent geometric gate; see [tool access](TOOL_ACCESS.md). A provisional reference screen clears 16 assumed approaches against printed parts, while the default product assessment leaves tool access blocked until an explicit contract is supplied. Earlier 11-blocker reports predate this additional gate.

## Inventory validation and assembly-mesh limitation

The handoff verifier previously passed `{"files": {}}`. It now rejects incomplete and malformed manifests before hashing: missing source, missing STEP/STL references, duplicate names/JSON keys, invalid dimensions, unsupported units/version, invalid hashes, and unsafe paths. Escaping symlinks fail as well. The writer applies the same structural checks before publishing a manifest. Four tests cover the real export round trip and these adversarial inventory cases. This is completeness and byte identity, not an independent geometric or manufacturing certificate; arbitrary matching bytes can still satisfy integrity metadata.

A read-only audit of `artifacts/production/named-handoff` found all 18 inventoried files intact and six valid individual STEP solids and closed individual STL meshes. However, combined `design.stl` has 39 edges incident to four faces at assembly contacts and is not watertight. **Use the named part STEP/STL pairs for fabrication review; the combined mesh is only an assembly visualization.** The combined STEP has six valid solids. New manifests explicitly state this distinction.

Remaining handoff work includes packaging versioned regeneration dependencies, including engineering contracts/reports in the inventory, and independent validation of each claimed geometric property. The existing editable Python specification agrees with the JSON specifications but depends on an installed `cadforge` implementation. Physical production qualification remains open.

## Independent named-part geometry screen

Production export now reopens each named STEP/STL and writes `geometry-screen.json`. Its fixed numerical policy checks valid positive STEP solids, closed consistently wound positive STL components, matching component counts, bounds, and volume. Hash verification must pass first. No packaged source is executed. These measurements do not prove surface equivalence, self-intersection absence, minimum walls, or physical suitability.

The first real run failed the camera lid's STEP/manifest bounds check: **0.001865 mm** difference exceeded the fixed **0.001 mm** gate. Export had populated a cached triangulation, which influenced default CAD bounding boxes. The reusable `exact_bounds` measurement now explicitly disables triangulation and shape-tolerance expansion. The checker limit was unchanged. A rotated cylindrical regression verifies that coarse tessellation cannot change this measurement.

The original failing report remains `artifacts/production/handoff-geometry-current.json`. A fresh regeneration at `artifacts/production/exact-bounds-handoff/geometry-screen.json` passes all six named parts; maximum STEP/manifest bounds discrepancy is about **1.13e-12 mm**. Eight focused tests pass, including hash-consistent open and wrong-size meshes that correctly fail geometric screening. This is a deterministic measurement repair and reusable export check, not learned-model training or production approval.

## Completed review-evidence inventory

The production boundary now attaches four explicit report roles to the final manifest: prebuild layout, prebuild engineering contract, engineering assessment, and exported-geometry screen. Every report is hashed alongside CAD/source files. Missing roles or references reject publication; a changed report fails integrity verification. Publication uses a temporary file and atomic replacement. This protects accidental replacement relative to the manifest, not malicious replacement of both the package and its manifest; it is not a signature or independent approval.

The geometry screen runs before final evidence inventory and records the geometry-stage inventory it actually checked. The final manifest then hashes that completed report. Reports do not hash the final manifest, avoiding circular evidence. The final inventory check is an external receipt, not part of its own inventory.

Actual fresh package: `artifacts/production/review-evidence-handoff/`. Its final inventory verifies **22 files** and the named-part geometry screen passes. The engineering assessment remains **43 pass, zero fail, 12 blocked**. Those blockers include missing explicit tool/cable/material/load contracts and physical process, fastener, tolerance, thermal, wearer and release qualification. They were not converted to passes by attaching reports. Nineteen focused handoff, geometry-screen and product tests pass.

## Explicit prebuild review inputs

The Python product boundary accepts `run_production(spec, directory, review_inputs=...)`. Allowed additions are typed tool-access, cable and beam contracts; sourced density; and a mass limit. Density/source must be supplied together, numeric limits must be positive and finite, and named contracts must be unique. Supplements cannot replace components, ports, mounts, wall witnesses or required parts. The combined contract is serialized and hashed before candidate construction. The Python API and typed MCP JSON endpoint support these inputs; an editor form is not implemented.

A prebuild regression exposed that the previous production contract had an empty required-part list. The recipe now independently requires chassis, Pi lid, camera lid and three cable-guide segments. The unrelated-box regression must fail this gate as well as bearing-material gates. These expected names are fixed before generation, never copied from candidate outputs.

Fresh `artifacts/production/explicit-review-handoff/` uses the earlier declared provisional straight-tool envelopes (6 mm diameter, 20 mm approach). All 16 printed-part tool-clearance checks pass; the assessment is 59 pass, zero fail, 11 blocked, with 22 inventoried files intact. This replaces an unspecified-tool block with a bounded check of explicit assumptions. It does not qualify purchased tools, screw engagement, real assembly order or physical access. Tool assumptions and remaining physical blockers are retained in the package. Seventeen focused product/review tests pass.


## Agent review contract interface

The MCP `create_camera_glasses` tool now accepts optional `review_inputs`. Its generated schema describes tool-access, cable and beam records, sourced density, and mass limits. Nested unknown fields, boolean/string dimensions, nonfinite coordinates and empty source labels are rejected. Dataclass contracts are constructed only after validation, and the same supplement boundary prevents replacement of fixed hardware requirements. Existing calls without review inputs retain their behavior.

Example review input, expressing an assumption rather than purchased-tool qualification:

```json
{"tool_access":[{"name":"driver","origin":[0,0,20],"axis":[0,0,1],"radius_mm":3,"length_mm":20,"source":"Declared prototype tool envelope"}]}
```

A real MCP dispatch with the earlier 16 provisional approach envelopes produced the package under `artifacts/mcp-review-check/production/`. Direct inspection confirmed all 16 inputs in the prebuild contract, 22 inventoried files intact, and 59 passing / zero failing / 11 blocked engineering gates. The first result-printing harness used the wrong SDK property (`isError` instead of `is_error`) after successful construction; no CAD rerun was needed to inspect the saved result. The corrected MCP and product suites pass 16 tests. An older fallback assertion that could hide SDK errors was also corrected.

## Current installed-package acceptance

The current source passes 525 development Python tests (88 seconds, 13 dependency warnings), excluding the archived benchmark test file. Six frontend tests pass. The frontend and wheel rebuilt successfully; Vite retains a roughly 921 kB JavaScript chunk warning.

The rebuilt wheel was installed into the separate 163-package environment with no dependency conflicts. From `/tmp`, the installed editor passed save/reopen, two-step edits, exact Undo and bundled static UI checks with zero model calls. `scripts/check_installed_review.py` then exercised the installed MCP JSON review boundary through actual glasses export: all four review roles persisted, 22 files passed integrity checks, and six named parts passed the geometry screen. Its tool witness is explicitly synthetic installation evidence, not assembly qualification.

Evidence is under `artifacts/clean-install/current-validation/`, including wheel SHA256 in `acceptance.json` and the installed module path/report in `installed-review-result.json`. Full test output is `artifacts/current-suite.log`; build output is `artifacts/current-wheel-build.log`. An initial harness-file write used `/tmp` as its relative directory and failed before running; the corrected absolute file write and subsequent installed execution succeeded. No archived benchmark result was changed and no production-release claim follows from this software acceptance.

## Packaged regeneration source

New handoffs include a restricted production-recipe source snapshot under `regeneration/src/cadforge`, exact installed dependency versions in `regeneration/requirements.txt`, and Python/platform metadata. All snapshot files are inventoried. The requirements resolve transitive dependencies for the current platform; binary hashes, OS libraries and package wheels are not included. This is source/version provenance, not a fully reproducible machine image. `packaging` is now an explicit project dependency and the lockfile was updated offline.

`check_packaged_regeneration.py` builds a known package, edits a copy of its literal lens-width parameter from 52 to 53 mm, and runs that source in a separate process from `/tmp`. It asserts CADForge imports come from the packaged snapshot, not the checkout or installed CADForge. The first run found a missing function-local camera-interconnect import. That failure log is retained; the snapshot now includes the module, and a static import-closure regression catches relative imports anywhere in the recipe source.

The corrected run regenerated all six parts with the requested 53 mm width. Named-part geometry screening and the 30-file regenerated inventory pass. Evidence: `artifacts/production/packaged-regeneration/regeneration-result.json`; original failure: `initial-failure.log`. Eight handoff tests pass, including source-change detection and import closure. The wider handoff/product suites passed 19 tests before the missing-module repair; no broad-suite claim is made for subsequent changes.

Regeneration reuses installed Python dependencies and does not prove a clean dependency installation. It produces geometry and its screen, **not a new independent engineering assessment**; the original prebuild contracts and product report cannot qualify changed dimensions. Physical qualification remains open. No credentials, runtime learning stores, benchmark instances or user files are copied into this restricted snapshot.

## Fresh dependency-environment regeneration

The packaged requirements were installed into a newly created environment at `artifacts/regeneration-clean/venv`. All 49 pinned distributions matched their recorded versions, and `uv pip check` found no dependency conflicts. CADForge itself was not installed. A copied recipe was edited from 52 to 54 mm lens width and executed from `/tmp` with only the packaged source on `PYTHONPATH`.

The run verified the imported CADForge path points into the package, regenerated the requested 54 mm specification, passed all named-part geometry screens, and passed its 30-file inventory. Evidence: `artifacts/regeneration-clean/result.json`, `dependency-verification.json`, and `install.log`. The geometry process remained CPU-active during its longer initial execution; it was observed to completion rather than restarted or counted as failed due to an observation timeout.

This closes the previous clean Python-dependency installation gap for the recorded macOS/Python environment. It still does not establish cross-platform binary reproducibility, a new engineering review of the modified dimensions, physical fit, or production release. The source snapshot and package hashes identify the artifacts; they are not authentication signatures.

## Fresh review after a parameter edit

`cadforge.handoff_review.review_handoff` accepts an explicit complete expected specification and optional review inputs. It requires package integrity and exact specification agreement, constructs and records the independent sourced-recipe contract, then reopens named STEP parts for engineering assessment. Packaged Python is never executed. Results are written to a separate new directory, preserving the original package. The equivalent MCP tool is `review_camera_glasses_handoff`.

The clean-environment 54 mm regeneration was assessed against the original approved recipe inputs with the lens width explicitly changed to 54 mm. Its new assessment records **43 pass, zero fail, 12 blocked**, with no source execution. Evidence: `artifacts/regeneration-clean/fresh-engineering-review/review-result.json` and its contract. No old engineering report was reused to qualify the changed design. The review does not include the earlier provisional tool assumptions unless explicitly supplied; consequently the unspecified-tool gate remains blocked.

Tests reject a mismatched expected specification and an unrelated valid box, retain source nonexecution, and verify MCP dispatch of explicit review inputs. Physical qualification remains open even when all available geometric gates pass. The contract derives from the sourced glasses recipe; this reviewer does not yet review arbitrary product families.

## Combined review of STEP, STL and engineering gates

Fresh review now retains both the independent export-geometry screen and the engineering assessment. `export_consistent` requires the bounded geometry screen to pass and the package inventory to remain unchanged through review. It does not mean physical readiness or exact surface equivalence. The component checks remain explicitly scoped to volume, bounds, topology and closure. A final inventory reread detects ordinary concurrent file/manifest changes; it is not protection against a hostile actor changing and restoring files between reads.

Nine review/screen tests pass. New regressions show that a rehashed wrong-size STL cannot hide behind its valid STEP file, and that changing a source file during review invalidates the receipt. The real 54 mm package passes the combined export screen with an unchanged inventory; independent engineering counts remain 43 pass, zero fail, 12 blocked. Evidence: `artifacts/regeneration-clean/combined-review/review-result.json`. No original report or checker limit was weakened, and no production readiness is claimed.

## Surface-location counterexample and added check

A real development counterexample exposed a false pass in the earlier export screen: moving a through-hole from X=-3 to X=+3 mm preserved stock bounds, topology and volume closely enough for all checks to pass. Its integrity hashes were intentionally updated to isolate the geometric checker limitation. `artifacts/handoff-surface-counterexample/before.json` retains that pass.

The screen now measures every mesh vertex and triangle center against the STEP's boundary shells, with a fixed 0.1 mm distance limit and 50,000-point cap. Measuring shells is essential: distance to a solid can treat an interior point as zero distance, hiding a misplaced hole wall. The shifted-hole fixture now fails with a 2 mm discrepancy; `after.json` retains the corrected result. No previous threshold was relaxed.

All six parts of the actual 54 mm package pass the new screen. The largest measured discrepancy is 0.001661 mm on the camera lid. Evidence: `artifacts/regeneration-clean/surface-screen.json`. Ten geometry/review tests pass, including the shifted-hole regression whose volume and bounds checks still pass while its new surface-location check fails.

This checks discrete mesh vertices and triangle centers in one direction. It is not continuous or bidirectional surface-equivalence proof; errors between those locations or smaller than the numerical limit can remain undetected. Oversized inputs fail the bounded screen rather than silently sampling fewer points. Existing packaged source snapshots retain their original checker versions; regenerating a new handoff is required to include this updated source.
