# Live STL terminal preview

Install the shared viewer dependencies once with `npm ci --prefix click-to-ship`. From the repository root:

```sh
python3 cad-preview/preview.py path/to/model.stl --watch --split right
```

Requires `terminal-browser` (`brew install terminal-browser`) and a compatible terminal. In Ghostty 1.3+ the command opens a split. From a desktop agent without a parent terminal, it opens a separate Ghostty window. Omit `--split` to run in the current terminal. `--no-open` prints the local viewer URL for an ordinary browser.

The server watches one STL, waits for a stable write, and publishes changed bytes. The page polls every 500 ms and replaces geometry while preserving the camera. Failed or incomplete exports keep the last valid mesh visible. Use atomic file replacement for exports when possible. Fit resets the camera; Wireframe toggles mesh edges. STL has no units; displayed dimensions assume millimeters.

Repeated commands reuse the server for the same resolved file. Browser pane reuse is delegated to terminal-browser. To stop the server:

```sh
python3 cad-preview/preview.py path/to/model.stl --stop
```

The viewer uses the pinned Three.js package installed in `click-to-ship/node_modules`. It serves only the viewer, four JavaScript files, and the chosen STL, on a token-scoped loopback URL. Runtime URLs and logs live in the ignored `.runtime/` directory. Export changes to the watched local path to update the model.
