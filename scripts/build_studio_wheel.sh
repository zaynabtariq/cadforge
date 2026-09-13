#!/bin/sh
# Build frontend before packaging so wheel assets match source.
set -eu
cd "$(dirname "$0")/.."
npm --prefix studio ci
npm --prefix studio run build
uv build --wheel --out-dir artifacts/studio-wheel
