#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Build .app first.
bash "$ROOT_DIR/build-macos.sh"

APP_PATH="$ROOT_DIR/dist/Sony Visualizer.app"
DMG_PATH="$ROOT_DIR/dist/Sony-Visualizer.dmg"

if [ ! -d "$APP_PATH" ]; then
  echo "Error: app bundle not found at $APP_PATH"
  exit 1
fi

rm -f "$DMG_PATH"
hdiutil create -volname "Sony Visualizer" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"

FINAL_DMG="$DMG_PATH"
if [ -n "${RELEASE_TAG:-}" ]; then
  FINAL_DMG="$ROOT_DIR/dist/Sony-Visualizer-${RELEASE_TAG}-macos.dmg"
  mv "$DMG_PATH" "$FINAL_DMG"
fi

echo "Build complete: $FINAL_DMG"
