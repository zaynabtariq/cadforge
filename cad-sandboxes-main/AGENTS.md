# Working on CAD Sandboxes

`click-to-ship/` contains the local quote UI, geometry viewer, browser adapter, and recording script. `cad-preview/` provides the standalone STL preview. Read the README in the relevant directory before changing it.

`fusion-workstation/` contains VM lifecycle, native Autodesk login, the terminal workspace, and an optional adapter to an external modeling CLI. Read its README before running it. Use the documented offline tests for regression checks; real lifecycle and sign-in operations require the user's configured workstation.

Keep credentials in environment variables or an ignored `.env` file. Never commit browser profiles, session URLs, model uploads, recordings, runtime state, logs, or generated artifacts. Use the included test cube for examples.

Run offline checks from `click-to-ship/` with `python3 -m unittest -v test_sessions.py test_recording.py`. The geometry browser test requires the local server and Chrome. Live quoting uploads a model to JLC3DP; use it only when requested. The quoting adapter stops at an estimate.
