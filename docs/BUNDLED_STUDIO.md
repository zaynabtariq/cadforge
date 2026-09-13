# Bundled local editor

Build an installable backend plus editor with `scripts/build_studio_wheel.sh`. It installs the frontend lockfile dependencies, builds Vite assets, then packages them under `cadforge/static` in the wheel. A direct wheel build requires an existing `studio/dist`; use the script to avoid stale assets.

Install the wheel with its `studio` extra, then run `cadforge-studio --port 2721` and open `http://127.0.0.1:2721`. The same local process serves the static UI and API. Vite is only needed for frontend development. API routes take precedence, and unknown API paths return 404. The launcher binds loopback and validates its port.

Set `CADFORGE_ARTIFACTS_DIR` to an absolute path to choose storage; otherwise installed copies use persistent user data. If assets are absent during source development, the home page returns an explicit 503 build instruction. The wheel's frontend contains compiled application assets only; it does not include credentials or workspace history. The separate optional marimo Learning lab is not launched automatically.

The packaged browser check uses an unrelated public plate STL, selects its object, requests a 5 mm movement, applies it and exports the result. It runs against the installed wheel with no Vite server. This packaging check may use the offline planner when credentials are absent; it does not demonstrate a model-learning improvement. Existing restart/learning videos cover that separate requirement.

A complete fresh-environment dependency matrix and physical production qualification remain unfinished. This is a local application package, not a public web deployment.

Actual installed-browser verification passed with one model call (1,645 tokens), no browser errors, and no Vite server. Independent export inspection confirms every vertex equals the expected 5 mm X translation after float32 STL serialization, and the mesh is watertight. The wheel contains the HTML, JavaScript, CSS and favicon. Evidence is in `artifacts/studio-wheel/browser-result.json`, `geometry-verification.json` and `bundled-preview.png`. The UI build retains its existing large-bundle warning; authoring costs are not fully metered.
