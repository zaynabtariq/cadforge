# Record the quote flow

The UI runs in a normal, visible Chrome window. Playwright records that window while the existing browse worker independently runs JLC3DP in Browserbase. The result is two separate clips for editing; there is no embedded player or terminal browser.

From this directory:

```sh
npm ci
cp .env.example .env
# Set your Browserbase API key in .env before starting the server.
python3 server.py --port 8766 --browserbase --browserbase-env .env
```

Then, in another terminal:

```sh
node record_quote.mjs
```

Only `BROWSERBASE_API_KEY` and optional `BROWSERBASE_PROJECT_ID` are read from that env file. They stay in the server environment. Alternatively set the credentials in the environment and omit `--browserbase-env`.

The script chooses the 20 mm cube, sets quantity two, selects Black Resin, enters quote review, and waits for the matching verified estimate. It records a five-second hold on the completed quote, saves the UI video, releases the provider browser, and downloads Browserbase's MP4. No cart, order, or payment action occurs.

Each run writes `artifacts/quote-recording-TIMESTAMP/`:

- `ui.mp4`: UI video converted with ffmpeg, plus its original `ui.webm`.
- `browserbase-0.mp4`: independently recorded JLC3DP browser. Additional tabs get separate files.
- `timing.json`: UTC times and elapsed time for the scripted UI steps, for alignment during editing.
- `quote.json`, `quote.png`: the verified quote and screenshot.
- `result.json`: Browserbase session ID, dashboard link, and file mapping.

Browserbase's archive also lives under `artifacts/web/SESSION/recording/`. Download assembly can take a few minutes after the browser closes. Errors preserve the UI recording and diagnostic information. Run `python3 -m unittest -v test_sessions.py test_recording.py` for synchronization and recording checks.

Chrome must be installed; ffmpeg is used for MP4 conversion. The script leaves normal Chrome open on the UI recording afterward. Close that window when finished. Browserbase has already been released at that point.

The provider recording uses Browserbase's [Recording Downloads API](https://docs.browserbase.com/platform/browser/observability/recording-downloads): release the session, request MP4 assembly, poll completion, and save the resulting video locally. Signed download URLs are not stored in the recording metadata.
