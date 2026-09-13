# Local FEA evidence

A real local CalculiX 2.23 solver and Gmsh 4.15.2 mesher now run on this Apple Silicon machine. `cadforge.fea.solve_cantilever` exports the supplied CadQuery BRep to STEP, imports that STEP into Gmsh, generates quadratic C3D10 tetrahedra, writes the complete CalculiX input deck and runs the external executable. It preserves STEP, mesh, input, solver logs, displacement/stress FRD, DAT and structured result files. This is not an analytic-only result or simulated solver response.

## Reproduce

Install Python dependencies with `uv sync --extra fea --extra dev`. On macOS arm64, install the solver into the ignored project-local tool directory:

```sh
mkdir -p .tools/fea
curl -Ls https://micro.mamba.pm/api/micromamba/osx-arm64/latest | tar -xj -C .tools/fea bin/micromamba
.tools/fea/bin/micromamba create -y -p "$PWD/.tools/fea/env" --override-channels -c conda-forge calculix=2.23
.venv/bin/python scripts/fea_study.py
.venv/bin/python -m pytest tests/test_fea.py -q
```

On another platform, install its CalculiX binary and set `CADFORGE_CCX` to the executable's absolute path. The backend also searches PATH. The exact locally installed conda package URLs are preserved in `artifacts/fea/conda-explicit-osx-arm64.txt`. `uv.lock` records the Python mesher dependency. No executable or environment is committed.

The initial local environment creation emitted a warning that it could not register its prefix in the user's `.conda/environments.txt`; the project-local environment nevertheless installed successfully and the executable was tested. Reproduction uses `--override-channels` explicitly to limit resolution to conda-forge.

## Verification before robot comparison

The verification fixture is a 100 × 10 × 5 mm rectangular cantilever. Its xmin face is fully fixed, and an explicit synthetic total −10 N Z force is equally divided among xmax face nodes. E = 210000 MPa and ν = 0.3 describe a textbook homogeneous isotropic elastic fixture, not an approved product material. Euler–Bernoulli predicts 0.15238095 mm tip displacement. A 5% displacement agreement criterion was set before running the robot-link study.

| Mesh size | Elements | Mean displacement magnitude | Analytic error |
|---|---:|---:|---:|
| 4 mm | 652 | 0.15125585 mm | 0.73835% |
| 2.5 mm | 2024 | 0.15142855 mm | 0.62501% |

Both meshes passed. Their reaction imbalance was below 0.000003 N. This verifies the exercised meshing, element ordering, unit system, boundary/load construction and solver-output path for this fixture; it is not exhaustive solver validation. The slight difference includes 3D end constraints versus ideal beam assumptions.

## Actual robot-link comparison

The existing two-pivot BRep was solved at widths 20 and 28 mm, with all other `RobotLinkSpec` defaults retained. Both models use exactly the same **synthetic end-clamp comparison**, not a simulated pin or actual robot assembly: xmin fixed XYZ, total −10 N on xmax, isotropic E = 210000 MPa and ν = 0.3.

| Link width | 4 mm mesh displacement | 2.5 mm mesh displacement |
|---|---:|---:|
| 20 mm | 0.04678512 mm | 0.04701664 mm |
| 28 mm | 0.03360360 mm | 0.03375265 mm |

The wider link deflected approximately 28.21% less on the finer mesh in this nominal comparison. Coarse-to-fine changes are approximately 0.49% and 0.44%, respectively. Two mesh levels are useful evidence, not a complete convergence proof. The authoritative node/element counts, loads, force balance and measured timings are in `artifacts/fea/summary.json`.

No load rating, factor of safety, fatigue life, joint stiffness or production release is established. Pivot contact, bolts, realistic supports, actuator loads, impact, creep, material anisotropy and print defects are absent. Stress fields are exported but clamp-local peak stress is not interpreted as an admissible strength metric. This study must not clear the wearable or robot production-readiness gates.

## Primary references

- [CalculiX author's manual, version 2.22](https://www.dhondt.de/ccx_2.22.pdf): model/step structure, static analysis, elastic material cards and displacement/stress output. The runtime used here is 2.23; the version is captured by calling its executable.
- [Official CalculiX source repository](https://github.com/Dhondtguido/CalculiX): solver implementation and distribution provenance.
- [Official Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html): OpenCASCADE STEP import, mesh generation, higher-order elements and input-deck export.
- [Conda-forge CalculiX feedstock](https://github.com/conda-forge/calculix-feedstock): platform package build recipe.
