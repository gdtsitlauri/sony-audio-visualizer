#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

python -m pip install -U pyinstaller

# Build the app binary first.
pyinstaller --noconfirm --clean --onefile \
  --name "sony-visualizer" \
  --windowed \
  --add-data "sony_logo.svg:." \
  --add-data "sony.ico:." \
  visualizer.py

APPDIR="$ROOT_DIR/dist/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp "$ROOT_DIR/dist/sony-visualizer" "$APPDIR/usr/bin/sony-visualizer"
chmod +x "$APPDIR/usr/bin/sony-visualizer"
cp "$ROOT_DIR/sony_logo.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/sony-visualizer.svg"

cat > "$APPDIR/sony-visualizer.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Sony Visualizer
Exec=sony-visualizer
Icon=sony-visualizer
Categories=AudioVideo;Audio;
Terminal=false
EOF

cp "$APPDIR/sony-visualizer.desktop" "$APPDIR/usr/share/applications/sony-visualizer.desktop"
cp "$ROOT_DIR/sony_logo.svg" "$APPDIR/.DirIcon"

TOOLS_DIR="$ROOT_DIR/.tools"
mkdir -p "$TOOLS_DIR"
APPIMAGETOOL="$TOOLS_DIR/appimagetool-x86_64.AppImage"

if [ ! -x "$APPIMAGETOOL" ]; then
  curl -L "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -o "$APPIMAGETOOL"
  chmod +x "$APPIMAGETOOL"
fi

OUTPUT="$ROOT_DIR/dist/Sony-Visualizer-x86_64.AppImage"
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT"

FINAL_OUTPUT="$OUTPUT"
if [ -n "${RELEASE_TAG:-}" ]; then
  FINAL_OUTPUT="$ROOT_DIR/dist/Sony-Visualizer-${RELEASE_TAG}-linux-x64.AppImage"
  mv "$OUTPUT" "$FINAL_OUTPUT"
fi

echo "Build complete: $FINAL_OUTPUT"
