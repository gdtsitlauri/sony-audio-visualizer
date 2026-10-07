# Sony Visualizer

A retro, Sony-inspired desktop audio visualizer for Windows, Linux and macOS, written in Python with
PySide6 and NumPy. It captures the sound the computer is playing (or the microphone), splits it with an
FFT into 64 logarithmically spaced bands between 28 Hz and 18 kHz, and draws them as animated bars.

| part | what it does |
| --- | --- |
| capture | system-audio loopback where available, otherwise the microphone (`soundcard`, 48 kHz, blocks of 2,048 samples) |
| analysis | windowed FFT, 64 bands, smoothing and peak markers |
| presets | `accurate` (fixed decibel scale) and `balanced` (adaptive level), switched with `P` |
| packaging | PyInstaller builds for Windows (.exe), Linux (AppImage) and macOS (.dmg), published by GitHub Actions |

## Download and run

The [latest release](https://github.com/gdtsitlauri/sony-audio-visualizer/releases/latest) has a file for
each system:

- **Windows:** `Sony-Visualizer-vX.Y.Z-windows-x64.exe`. Double-click it; if SmartScreen appears, choose
  *More info* → *Run anyway*.
- **Linux:** `Sony-Visualizer-vX.Y.Z-linux-x64.AppImage`.

  ```bash
  chmod +x Sony-Visualizer-vX.Y.Z-linux-x64.AppImage
  ./Sony-Visualizer-vX.Y.Z-linux-x64.AppImage
  ./Sony-Visualizer-vX.Y.Z-linux-x64.AppImage --appimage-extract-and-run   # if FUSE is missing
  ```

- **macOS:** `Sony-Visualizer-vX.Y.Z-macos.dmg`. Drag *Sony Visualizer.app* to *Applications*; if Gatekeeper
  blocks the first launch, right-click the app → *Open*, and allow audio access when asked.

## Controls

| key | action |
| --- | --- |
| `Space` | start or stop capture |
| `P` | next visual preset |
| `D` | debug overlay |
| `Esc` | exit |

The capture source is set by `CAPTURE_SOURCE` at the top of `visualizer.py`: `auto` (default: loopback
first, microphone as fallback), `loopback`, or `stereo_mix` (Windows only).

## Limitations (reported as such)

- System-audio capture depends on the platform. On Windows loopback usually works out of the box; on
  Linux it depends on the PulseAudio/PipeWire setup; macOS has no system loopback, so a virtual device such
  as BlackHole is needed, with the output routed through it.
- `numpy<2` is pinned (1.26.4) for compatibility with `soundcard`.

## Folder map

```
sony-audio-visualizer/
  visualizer.py                     the application
  requirements.txt                  numpy, PySide6, soundcard
  sony.ico, sony_logo.svg           icons
  Sony Visualizer.spec              PyInstaller specification
  build-windows.ps1                 Windows .exe
  build-linux.sh, build-linux-appimage.sh
  build-macos.sh, build-macos-dmg.sh
  RELEASE_TEMPLATE.md               release checklist
  .github/workflows/                ci.yml (smoke test on all three systems), release.yml (builds on tags v*)
```

## Running from source

Python 3.12 is used by the builds.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python visualizer.py
```

## Building packages

```text
.\build-windows.ps1 -Version v1.0.0                     # Windows, PowerShell: dist/Sony-Visualizer-v1.0.0-windows-x64.exe
RELEASE_TAG=v1.0.0 bash build-linux-appimage.sh         # Linux: dist/Sony-Visualizer-v1.0.0-linux-x64.AppImage
RELEASE_TAG=v1.0.0 bash build-macos-dmg.sh              # macOS: dist/Sony-Visualizer-v1.0.0-macos.dmg
```

Pushing a tag such as `v1.0.6` makes `release.yml` build all three and publish them as a GitHub release.

## Author and license

George David Tsitlauri. MIT license ([LICENSE](LICENSE)).

"Sony" and the Sony logo are trademarks of Sony Group Corporation. This project is unofficial and is not
affiliated with or endorsed by Sony.
