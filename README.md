# Sony Visualizer

Retro Sony-inspired desktop audio visualizer for Windows, Linux, and macOS (PySide6 + NumPy).

## Download And Run (End Users)
Download the file that matches your OS from the latest GitHub Release:
- Windows: `Sony-Visualizer-vX.Y.Z-windows-x64.exe`
- Linux: `Sony-Visualizer-vX.Y.Z-linux-x64.AppImage`
- macOS: `Sony-Visualizer-vX.Y.Z-macos.dmg`

### Windows
1. Download `Sony-Visualizer-vX.Y.Z-windows-x64.exe`.
2. Double-click to run.
3. If SmartScreen appears, click `More info` -> `Run anyway`.

### Linux
1. Download `Sony-Visualizer-vX.Y.Z-linux-x64.AppImage`.
2. Open terminal in the download folder and run:
```bash
chmod +x Sony-Visualizer-vX.Y.Z-linux-x64.AppImage
./Sony-Visualizer-vX.Y.Z-linux-x64.AppImage
```
3. If AppImage fails because of FUSE, run:
```bash
./Sony-Visualizer-vX.Y.Z-linux-x64.AppImage --appimage-extract-and-run
```

### macOS
1. Download `Sony-Visualizer-vX.Y.Z-macos.dmg`.
2. Open the DMG and drag `Sony Visualizer.app` to `Applications`.
3. On first launch, if Gatekeeper blocks it: right-click app -> `Open` -> confirm.
4. Allow audio/microphone permission when prompted.

## System Audio Capture Notes (Important)
- Windows: loopback/stereo mix usually works out of the box.
- Linux: system-audio loopback depends on your PulseAudio/PipeWire setup.
- macOS: for true system-output bars, install a virtual loopback device (for example BlackHole) and route output through it.
- `CAPTURE_SOURCE="auto"` already prioritizes loopback sources and falls back to microphone if needed.

## Controls
- `Space`: Start/Stop capture
- `P`: Change visual preset
- `D`: Toggle debug overlay
- `Esc`: Exit

## Capture Modes (visualizer.py)
- `CAPTURE_SOURCE = "auto"` (recommended)
- `CAPTURE_SOURCE = "loopback"`
- `CAPTURE_SOURCE = "stereo_mix"` (Windows only)

## Run From Source (Developers)
```bash
cd /path/to/visualizer
python -m venv .venv
```

Activate venv:
- Windows PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```
- Linux/macOS:
```bash
source .venv/bin/activate
```

Install and run:
```bash
pip install -r requirements.txt
python visualizer.py
```

## Build Packages (Manual)

### Windows (.exe)
```powershell
.\.venv\Scripts\Activate.ps1
.\build-windows.ps1 -Version v1.0.0
```
Output:
- `dist/Sony-Visualizer-v1.0.0-windows-x64.exe`

### Linux (AppImage)
```bash
source .venv/bin/activate
chmod +x build-linux.sh build-linux-appimage.sh
RELEASE_TAG=v1.0.0 bash build-linux-appimage.sh
```
Output:
- `dist/Sony-Visualizer-v1.0.0-linux-x64.AppImage`

### macOS (.dmg)
```bash
source .venv/bin/activate
chmod +x build-macos.sh build-macos-dmg.sh
RELEASE_TAG=v1.0.0 bash build-macos-dmg.sh
```
Output:
- `dist/Sony-Visualizer-v1.0.0-macos.dmg`

## Automated Release (GitHub Actions)
Workflows in `.github/workflows`:
- `ci.yml`: smoke test on Windows/Linux/macOS
- `release.yml`: build and publish release assets when you push a tag `v*`

Example:
```bash
git tag v1.0.0
git push origin v1.0.0
```

## Notes
- `numpy<2` is pinned for `soundcard` compatibility.
- On first run, macOS may request audio capture permission.

## Trademark Notice
"Sony" name/logo are trademarks of Sony Group Corporation.
This project is unofficial and not affiliated with or endorsed by Sony.