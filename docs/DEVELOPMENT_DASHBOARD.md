# Evidence in marimo

`notebooks/continual_studio.py` now shows the latest retained tool-pocket comparison alongside separate discovery, validation and comparison costs and the latest product's engineering blockers. The table reports the actual tie with affine retrieval, not an improvement claim inferred from literal-script comparisons.

`development_status` reads only explicit public artifact directories. It checks comparison summaries against retained attempts. A new run with a contract but no completed summary is shown as an error instead of replaced by an older success. Historical missing cost fields are reconstructed from attempt files; missing audit directories or contradictory totals are flagged. Product file-integrity status is displayed separately from its geometric counts. None of these reads execute learning, CAD generation, packaged Python or a hidden benchmark.

The notebook passes `marimo check`; two focused reader tests cover incomplete runs, legacy cost recovery and contradictory totals. A real Chrome session rendered the panel and its retained retrieval tie. The first screenshot exposed stale legacy-summary handling; after fixing the reader and restarting the notebook, browser verification found no legacy cost errors. Evidence: `artifacts/marimo-current-evidence/panel.png`.

Run locally with `marimo run notebooks/continual_studio.py --headless --port 2755 --no-token`. This is the local research view; the general STL editing workspace remains separate. Counts are tracked development executions, not a complete account of all authoring or historical discovery cost.
