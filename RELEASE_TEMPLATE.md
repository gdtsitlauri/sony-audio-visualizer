# Release Template

## Version
- Tag: `vX.Y.Z`
- Title: `Sony Visualizer vX.Y.Z`

## Build/Publish Options

### Option A (Recommended): Automatic via GitHub Actions
1. Push tag:
   - `git tag vX.Y.Z`
   - `git push origin vX.Y.Z`
2. Workflow `release.yml` builds and publishes assets automatically.

### Option B: Manual Local Build
Upload these files to the Release:
- `Sony-Visualizer-vX.Y.Z-windows-x64.exe`
- `Sony-Visualizer-vX.Y.Z-linux-x64.AppImage`
- `Sony-Visualizer-vX.Y.Z-macos.dmg`

## Release Notes Template
```md
## Sony Visualizer vX.Y.Z

### Downloads
- Windows (x64): `Sony-Visualizer-vX.Y.Z-windows-x64.exe`
- Linux (x64): `Sony-Visualizer-vX.Y.Z-linux-x64.AppImage`
- macOS: `Sony-Visualizer-vX.Y.Z-macos.dmg`

### Changes
- [bullet 1]
- [bullet 2]

### Notes
- Capture mode defaults to `auto` (loopback first, microphone fallback if needed).
- Linux/macOS loopback availability depends on system audio setup.
```

## Pre-Release Checklist
- Confirm `visualizer.py` compiles (`python -m py_compile visualizer.py`)
- Confirm package names use `vX.Y.Z`
- Confirm all three assets uploaded to one Release
