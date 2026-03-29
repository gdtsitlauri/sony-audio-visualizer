#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

python -m pip install -U pyinstaller

ICONSET_DIR="$ROOT_DIR/build/SonyVisualizer.iconset"
ICON_ICNS="$ROOT_DIR/build/sony.icns"

rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

python - "$ROOT_DIR/sony_logo.svg" "$ICONSET_DIR" <<'PY'
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

svg_path = Path(sys.argv[1])
iconset_dir = Path(sys.argv[2])
renderer = QSvgRenderer(str(svg_path))
if not renderer.isValid():
    raise SystemExit(f"Invalid SVG icon: {svg_path}")

# Required iconset sizes for iconutil -> .icns.
slots = [
    (16, 1), (16, 2),
    (32, 1), (32, 2),
    (128, 1), (128, 2),
    (256, 1), (256, 2),
    (512, 1), (512, 2),
]

for base, scale in slots:
    px = base * scale
    image = QImage(px, px, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()

    suffix = "@2x" if scale == 2 else ""
    out_name = f"icon_{base}x{base}{suffix}.png"
    out_path = iconset_dir / out_name
    if not image.save(str(out_path)):
        raise SystemExit(f"Failed to write {out_path}")
PY

iconutil -c icns "$ICONSET_DIR" -o "$ICON_ICNS"

pyinstaller --noconfirm --clean \
  --name "Sony Visualizer" \
  --windowed \
  --osx-bundle-identifier "com.tom.sonyvisualizer" \
  --icon "$ICON_ICNS" \
  --add-data "sony_logo.svg:." \
  --add-data "sony.ico:." \
  --collect-data soundcard \
  visualizer.py

APP_PATH="$ROOT_DIR/dist/Sony Visualizer.app"
if [ ! -d "$APP_PATH" ]; then
  echo "Build failed: app bundle not found at $APP_PATH"
  exit 1
fi

PLIST_PATH="$APP_PATH/Contents/Info.plist"
if [ -f "$PLIST_PATH" ]; then
  /usr/libexec/PlistBuddy -c "Add :NSMicrophoneUsageDescription string Sony Visualizer needs audio input access for real-time visualization." "$PLIST_PATH" \
    || /usr/libexec/PlistBuddy -c "Set :NSMicrophoneUsageDescription Sony Visualizer needs audio input access for real-time visualization." "$PLIST_PATH"
fi

echo "Build complete: dist/Sony Visualizer.app"
