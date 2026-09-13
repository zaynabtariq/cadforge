# Planner dependency floor

The rigid-translation model introduced `Field(exclude_if=...)`, but the project still allowed Pydantic 2.11. An isolated environment with 2.11.10 reproduced `PydanticSerializationError` during `EditDecision.model_json_schema()`: the unknown field option was treated as schema metadata containing a function. This could prevent typed model planning in an otherwise permitted installation.

`pyproject.toml` now requires Pydantic >=2.12,<3. The [official 2.12 release notes](https://pydantic.dev/articles/pydantic-v2-12-release) identify `exclude_if` as new in that release. The identical isolated probe passed with 2.12.0, including ordinary-command omission and explicit rigid-command preservation. Evidence: `artifacts/dependency-audit/pydantic-2.11.json` and `pydantic-2.12.json`. Reproduce with `scripts/check_planner_dependency.py` and `PYTHONPATH=src` in the chosen environment.

NumPy and SciPy are now direct dependencies because region and surface operations import their APIs directly. Their newly declared minimum versions have not been independently matrix-tested; the current environment passes `uv pip check` across 181 installed packages. This is not a clean-install test of every optional integration or every supported Python/platform combination.

The isolated experiments did not modify the running environment. Frontend verification passed six Node tests and the production build; the existing large-bundle warning remains. No geometry checks, benchmark definitions, learned evidence or hidden inputs changed. No model calls were required for the dependency probe.

Full integration verification completed: `pytest -q` passed **395 tests** in 94.67 seconds, with 15 dependency/deprecation warnings. This includes current CAD editing, learning, engineering and export tests; it is not a rerun or revision of the 100-case hidden evaluation and does not establish production release readiness.
