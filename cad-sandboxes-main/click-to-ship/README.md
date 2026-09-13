# CAD → JLC3DP quote

To record a scripted quote in regular Chrome and download the separate Browserbase video for editing, see [RECORDING.md](RECORDING.md).

For the interactive web UI, run `python3 click-to-ship/server.py --port 8766` from the repository root and open **http://127.0.0.1:8766**. See [WEB.md](WEB.md) for the async session protocol and synchronization tests.

`quote.py` uploads one CAD model to JLC3DP through the **browse CLI** and returns a JSON estimate. It uses browser interactions and rendered page data, with no private API calls. It stops at the quote screen; it never adds to cart, submits an order, or pays.

## Run

Requires Python 3 and `browse` on PATH, plus local Chrome/Chromium. No Python packages, JLC3DP account, or Browserbase API key are needed for the tested flow.

From the repository root:

```sh
python3 click-to-ship/quote.py click-to-ship/fixtures/cube-20mm.stl \
  --technology SLA \
  --material '9600 Resin' \
  --color White \
  --quantity 1 \
  --category blocks \
  --description '20 mm resin test cube'
```

Replace the fixture with the sandbox's exported model. The CLI accepts STL, STEP/STP, OBJ, and 3MF. STL coordinates must be exported in millimeters; inspect `dimensions_mm` against the CAD model before relying on its quote. Only the included STL has been tested so far.

JSON goes to stdout; progress goes to stderr. Exit status is zero for an estimate and one for a workflow error. Each run writes `quote.json`, `page-state.json`, and `snapshot.txt` in a unique folder under `artifacts/`. Errors write `error.json` and diagnostic page state instead. These files can contain model filenames and descriptions; keep them out of source control.

Add `--keep-browser` to leave the quoted part open for inspection. The returned `browser_session` can be used with `browse snapshot --session SESSION`. Close it with `browse stop --session SESSION`. Otherwise the adapter closes its own session automatically.

## Workflow

1. Open a fresh named browser session and wait for the empty upload page. Confirm the site region is United States / USD.
2. Upload the model through `input[type=file]` using `browse upload`.
3. Wait for the actual filename, a single selected part, a positive price, and matching part/subtotal amounts. The site's built-in sample is never accepted as the uploaded model.
4. Open **Edit Specifications**. Select the process and material by current accessibility refs; set optional color and quantity.
5. Select the product category, then **others**, and enter the accurate description. The description is required to save changed specifications.
6. Wait for stable pricing and check for manufacturing rejection messages. Save, then wait until the part price and summary total agree.
7. Reopen specifications to verify the process, material, quantity, description, and optional color persisted. Close the dialog.
8. Wait for the regional shipping estimate, extract the result, and save the rendered-page evidence.

Snapshot refs change across sessions and page updates. The adapter resolves them afresh by exact role/name and waits for controls to appear. All shell invocations use argument arrays to preserve filenames and descriptions literally.

## Inputs and returned estimate

`--technology` accepts SLA, FDM, MJF, SLS, SLM, WJP, or BJ. Material/color names must exactly match the buttons displayed for that process. SLA / 9600 Resin is the default. Other process/material combinations need validation with suitable geometry; choosing a supported process does not establish that a part is manufacturable.

`--category` is mandatory: `blocks`, `connectors`, `irregular`, `office`, or `toys`. Choose the category appropriate to the part and provide a truthful `--description` of at most 30 characters. The `others` branch and custom description have been exercised for `blocks`; other category menus may differ and will fail explicitly if the expected control is missing.

Finish, threading, packaging, and build speed retain JLC3DP's defaults. Their visible selections and material notes are returned in `configuration`; selected build time is returned in `build_time`. For the resin cube, defaults were white, general sanding, no threads, branded packaging, and standard build time.

The integration should display these fields:

| Field | Meaning |
|---|---|
| `manufacturing_subtotal` | Price for the requested quantity; excludes shipping |
| `average_unit_price` | Manufacturing subtotal divided by quantity |
| `build_time` | Selected manufacturing time, separate from transit |
| `shipping.amount` / `shipping.details` | Country-level estimate and carrier/transit text, or null if unavailable |
| `estimated_manufacturing_plus_shipping` | Sum of those estimates, or null if shipping is unavailable |
| `checkout_total` | Always null at this stage |
| `file_sha256`, `quoted_at` | Identify the exact model bytes and observation time |

Money is encoded as decimal strings in USD. The adapter currently requires the US site region and does not enter an address. Taxes, duties, and other checkout adjustments are unverified. Manufacturing prices remain subject to JLC3DP review; material notes are not a full manufacturability assessment.

## Integration boundary

Have the CAD sandbox export a local file and invoke the Python command with subprocess arguments. Parse its stdout JSON and return the estimate to the user. If `status` is `error`, expose the reason and keep the artifacts for inspection; never present a partial, stale, or sample-model price as a successful quote.

The current implementation handles one part per run. It fails on missing controls, incompatible geometry warnings, unexpected region/currency, or mismatched saved settings. It does not retry uploads or any order action.
