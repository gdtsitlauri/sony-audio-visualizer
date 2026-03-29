#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

python -m pip install -U pyinstaller

pyinstaller --noconfirm --clean \
  --name "sony-visualizer" \
  --windowed \
  --add-data "sony_logo.svg:." \
  --add-data "sony.ico:." \
  visualizer.py

echo "Build complete: dist/sony-visualizer"