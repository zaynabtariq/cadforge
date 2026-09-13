# CAD Sandboxes

An interactive CAD preview and manufacturing quote prototype. Upload a model, inspect its geometry, choose material and quantity, and watch the price update as a browser checks the selections with JLC3DP.

## Run locally

Requires Python 3.10+, Node.js 22+, npm, and Google Chrome.

```sh
npm install -g browse@0.9.6
cd cad-sandboxes-main/click-to-ship
npm ci
python3 server.py --port 8766
```

Open **http://127.0.0.1:8766** and choose the included 20 mm test cube or your own STL, STEP, OBJ, or 3MF file. Selecting a file starts an upload to JLC3DP. The default browser runs locally and does not require a Browserbase account.

The model preview opens immediately while a background worker uploads and analyzes the part. Material and quantity changes are queued, saved, and verified before a quote is marked current. Shipping is a US country-level estimate; the flow ends at quote review.

## Project layout

| Directory | Purpose |
| --- | --- |
| `click-to-ship/` | Quote UI, geometry viewer, browser automation, and recording script |
| `cad-preview/` | Standalone STL viewer with live file updates |
| `fusion-workstation/` | Configurable VM lifecycle, native Autodesk login, and terminal workspace UI |

See [the UI protocol](click-to-ship/WEB.md), [recording instructions](click-to-ship/RECORDING.md), [the visual theme](click-to-ship/THEME.md), and [the STL preview](cad-preview/README.md).

The [Fusion workstation guide](fusion-workstation/README.md) covers AWS configuration, native sign-in, the terminal workspace, and the optional adapter to an external modeling CLI. Supply your own deployment configuration and credentials; generated state and private keys are excluded.

For a local STL beside your terminal conversation:

```sh
python3 cad-preview/preview.py click-to-ship/fixtures/cube-20mm.stl --watch --split right
```

This opens the live viewer using `terminal-browser`. Add `--no-open` to obtain a URL for a regular browser, or use `--stop` to close the preview server for that file.

## Record a demo

Optional Browserbase mode records the provider browser independently of the regular Chrome UI. Supply your own Browserbase credentials in an ignored local `.env` file using [the example](click-to-ship/.env.example), then follow [RECORDING.md](click-to-ship/RECORDING.md). The script saves separate UI and provider clips for editing.

## Test

From `click-to-ship/`:

```sh
python3 -m unittest -v test_sessions.py test_recording.py
```

With the local server running, `python3 test_preview_browser.py` checks model parsing, dimensions, and viewer controls without creating a provider session. Browser automation depends on the provider's current interface; live prices and material availability are not test fixtures.

This prototype binds to loopback and stores sessions in one process. Restarting the server requires a new quote session. Authentication and durable ownership would be needed before hosting the UI for other users.
