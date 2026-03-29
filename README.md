# Sony Visualizer

Retro Sony-inspired desktop audio visualizer for Windows, Linux, and macOS (PySide6 + NumPy).

## What It Captures
- Prefers system-output loopback capture.
- Falls back to default microphone input when loopback is unavailable (`CAPTURE_SOURCE="auto"`).
- You can force modes in `visualizer.py`:
  - `CAPTURE_SOURCE = "auto"`
  - `CAPTURE_SOURCE = "loopback"`
  - `CAPTURE_SOURCE = "stereo_mix"` (Windows only)

## Requirements
- Python 3.12
- Windows 10/11, modern Linux desktop, or macOS 12+

## Run From Source
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

## Controls
- `Space`: Start/Stop capture
- `P`: Change visual preset
- `D`: Toggle debug overlay
- `Esc`: Exit

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

## One-Link Distribution (GitHub Releases)
Use one GitHub Release page and upload these 3 files:
- `Sony-Visualizer-vX.Y.Z-windows-x64.exe`
- `Sony-Visualizer-vX.Y.Z-linux-x64.AppImage`
- `Sony-Visualizer-vX.Y.Z-macos.dmg`

Each user downloads only the file for their OS.

## Automated Release (GitHub Actions)
This repo includes workflows under `.github/workflows`:
- `ci.yml`: smoke test on Windows/Linux/macOS
- `release.yml`: build and publish release assets when you push a tag `v*`

Example:
```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow builds all 3 packages and attaches them to the GitHub Release automatically.

## Notes
- `numpy<2` is pinned for `soundcard` compatibility.
- Loopback availability depends on OS/audio setup (especially Linux/macOS).
- On macOS, for system-output capture you may need a virtual loopback device (e.g. BlackHole).
- On first run, macOS may request audio capture permissions.

## Trademark Notice
"Sony" name/logo are trademarks of Sony Group Corporation.
This project is unofficial and not affiliated with or endorsed by Sony.
