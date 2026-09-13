# Clean installation verification

The bundled wheel was installed with `[studio,agents,observability]` into a new Python 3.11 virtual environment. The dependency resolver installed 163 packages, and `uv pip check` reports compatible installed requirements. `artifacts/clean-install/resolved-packages.txt` records the exact resolved environment. This snapshot is specific to the tested macOS/Python environment, not a cross-platform lockfile.

Verification scripts run from `/tmp` with checkout `PYTHONPATH` removed. They assert the imported CADForge module is under the new environment, then exercise workspace HTTP commit/export/project reopen, typed planning, MCP registration and native production CAD. The typed planning check uses Pydantic AI's TestModel to deliberately drop a rigid constraint and verifies that the planner restores it. This is an integration test double, not remote inference evidence. Weave is imported; these checks do not test remote trace delivery. Existing actual browser/restart runs retain separate remote-model and Weave evidence.

The CAD check builds the reference glasses, evaluates the independent engineering contract and exports editable Python/JSON plus STEP/STL/SVG. Passing geometric gates does not resolve the physical blocked gates. Output and subprocess logs are retained under `artifacts/clean-install/`.

Reproduce installation with `uv venv --python 3.11 <new-env>` and `uv pip install --python <new-env>/bin/python 'path/to/cadforge-0.1.0-py3-none-any.whl[studio,agents,observability]'`. Run `check_installed_workspace.py` and `check_clean_install.py <evidence-dir>` using that interpreter outside the checkout, with an explicit absolute `CADFORGE_ARTIFACTS_DIR`.

The marimo and FEA extras, operating-system matrix, physical prototype and production release remain outside this check. No hidden benchmark was executed or changed. No paid inference was used; engineering authoring costs are not fully metered.

Results: both subprocesses completed successfully. Workspace reopen preserved identical exported STL bytes. The clean MCP server registered 10 tools; typed rigid-intent planning passed. Native glasses CAD exported successfully with **43 pass, 0 fail, 11 blocked** engineering gates. The blocked gates remain unchanged and prevent production qualification. Exact records: `workspace.txt`, `integrations.txt` and `evidence/result.json`.
