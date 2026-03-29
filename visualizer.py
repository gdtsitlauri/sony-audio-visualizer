
def resource_path(filename):
    import sys
    import os
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(__file__), filename)

import sys
import re
import threading
import time
from pathlib import Path 

import numpy as np 

from PySide6.QtCore import Qt, QThread, QTimer, QRectF, Signal, QSize, QPoint
from PySide6.QtGui import (
    QColor,
    QBrush,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget


SAMPLERATE = 48000
BLOCKSIZE = 2048
BARS = 64
WINDOW_W = 520
WINDOW_H_COLLAPSED = 180
CASSETTE_SECTION_H = 126
WINDOW_H_EXPANDED = WINDOW_H_COLLAPSED + CASSETTE_SECTION_H
MIN_FREQ_HZ = 28.0
MAX_FREQ_HZ = 18000.0
VISUAL_PRESET = "accurate"  # accurate | balanced
CAPTURE_SOURCE = "auto"  # auto | loopback | stereo_mix

VIRTUAL_LOOPBACK_TERMS = (
    "blackhole",
    "loopback",
    "soundflower",
    "vb-cable",
    "background music",
    "monitor of",
)

def _is_virtual_loopback_name(name):
    lname = str(name).lower()
    return any(term in lname for term in VIRTUAL_LOOPBACK_TERMS)

VISUAL_PRESETS = {
    "accurate": {
        "mode": "accurate",
        "db_floor": -84.0,
        "db_ceiling": -6.0,
        "worker_attack": 0.90,
        "worker_release": 0.72,
        "spatial_kernel": [1],
        "post_power": 1.0,
        "ui_rise_speed": 0.72,
        "ui_fall_speed": 0.46,
        "ui_kernel": [1, 2, 1],
        "peak_fall": 0.030,
    },
    "balanced": {
        "mode": "adaptive",
        "ref_percentile": 96.0,
        "ref_floor": 0.08,
        "ref_rise": 0.40,
        "ref_decay": 0.990,
        "ref_fall_mix": 0.12,
        "loudness_floor_db": -52.0,
        "loudness_ceil_db": -6.0,
        "energy_base": 0.46,
        "energy_span": 1.12,
        "volume_min_gain": 0.78,
        "volume_max_gain": 1.22,
        "peak_percentile": 98.0,
        "peak_limit": 0.98,
        "clip_limit": 1.35,
        "tanh_drive": 1.55,
        "worker_attack": 0.58,
        "worker_release": 0.34,
        "spatial_kernel": [1, 2, 3, 2, 1],
        "post_power": 0.88,
        "ui_rise_speed": 0.50,
        "ui_fall_speed": 0.28,
        "ui_kernel": [1, 2, 1],
        "peak_fall": 0.024,
    },
}


def get_sc():
    import soundcard as sc
    import warnings

    # MediaFoundation can occasionally report dropped chunks; keep console clean.
    warn_cls = getattr(sc, "SoundcardRuntimeWarning", RuntimeWarning)
    warnings.filterwarnings(
        "ignore",
        message="data discontinuity in recording",
        category=warn_cls,
    )
    return sc


def ensure_sony_logo():
    base = Path(__file__).resolve().parent
    logo_path = base / "sony_logo.svg"

    if logo_path.exists():
        return logo_path

    # Avoid network calls during UI startup; use local asset only.
    return None


def _pick_stereo_mix_mic(sc, default_speaker):
    stereo_terms = ("stereo mix", "wave out", "what u hear", "monitor")
    mics = sc.all_microphones(include_loopback=True)
    candidates = [m for m in mics if any(t in m.name.lower() for t in stereo_terms)]
    if not candidates:
        return None

    speaker_tokens = [
        t for t in re.split(r"[^a-z0-9]+", default_speaker.name.lower()) if len(t) >= 4
    ]
    for mic in candidates:
        lname = mic.name.lower()
        if any(tok in lname for tok in speaker_tokens):
            return mic

    return candidates[0]



def _pick_virtual_loopback_mic(sc, default_speaker=None):
    try:
        mics = sc.all_microphones(include_loopback=True)
    except Exception:
        return None

    candidates = [m for m in mics if _is_virtual_loopback_name(getattr(m, "name", ""))]
    if not candidates:
        return None

    if default_speaker is not None:
        speaker_tokens = [
            t for t in re.split(r"[^a-z0-9]+", default_speaker.name.lower()) if len(t) >= 4
        ]
        for mic in candidates:
            lname = str(getattr(mic, "name", "")).lower()
            if any(tok in lname for tok in speaker_tokens):
                return mic

    return candidates[0]

def _pick_default_input_mic(sc):
    try:
        mic = sc.default_microphone()
        if mic is not None:
            return mic
    except Exception:
        pass

    try:
        mics = sc.all_microphones(include_loopback=False)
    except Exception:
        mics = []

    if mics:
        return mics[0]
    return None


def find_capture_mic():
    sc = get_sc()

    source_mode = str(CAPTURE_SOURCE).strip().lower()
    if source_mode not in {"auto", "loopback", "stereo_mix"}:
        source_mode = "auto"

    try:
        default_speaker = sc.default_speaker()
    except Exception:
        default_speaker = None

    # Windows-specific Stereo Mix path.
    if source_mode in {"auto", "stereo_mix"} and default_speaker is not None:
        try:
            stereo_mix_mic = _pick_stereo_mix_mic(sc, default_speaker)
        except Exception:
            stereo_mix_mic = None

        if stereo_mix_mic is not None:
            return stereo_mix_mic

        if source_mode == "stereo_mix":
            raise RuntimeError("Stereo Mix/What U Hear device was not found.")

    # Try default speaker loopback first.
    if source_mode in {"auto", "loopback"} and default_speaker is not None:
        try:
            mic = sc.get_microphone(default_speaker.name, include_loopback=True)
            if mic is not None:
                return mic
        except Exception:
            pass

    # Generic loopback scan.
    try:
        loopbacks = [
            m for m in sc.all_microphones(include_loopback=True)
            if getattr(m, "isloopback", False)
        ]
    except Exception:
        loopbacks = []

    if loopbacks:
        if default_speaker is not None:
            speaker_name = default_speaker.name.lower()
            for mic in loopbacks:
                if speaker_name in mic.name.lower():
                    return mic
        return loopbacks[0]

    # Virtual loopback devices (especially common on macOS).
    virtual_loopback_mic = _pick_virtual_loopback_mic(sc, default_speaker)
    if virtual_loopback_mic is not None:
        return virtual_loopback_mic

    # Cross-platform fallback for systems without loopback support.
    if source_mode == "auto":
        mic = _pick_default_input_mic(sc)
        if mic is not None:
            return mic

    if source_mode == "loopback":
        if sys.platform.startswith("darwin"):
            raise RuntimeError(
                "No loopback capture device found. Install a virtual loopback device (e.g. BlackHole), then route output to it, or switch CAPTURE_SOURCE to 'auto' for microphone fallback."
            )
        raise RuntimeError(
            "No loopback capture device found. Switch CAPTURE_SOURCE to 'auto' for microphone fallback."
        )

    mic = _pick_default_input_mic(sc)
    if mic is not None:
        return mic

    raise RuntimeError("No usable audio input device found.")
class AudioWorker(QThread):
    levels_ready = Signal(object)
    error_ready = Signal(str)
    stats_ready = Signal(object)

    def __init__(self, preset):
        super().__init__()
        self.running = False
        self.preset = dict(preset)
        self._recorder = None
        self._recorder_lock = threading.Lock()

    def stop(self, timeout_ms=3000):
        self.running = False
        self.requestInterruption()

        with self._recorder_lock:
            recorder = self._recorder

        if recorder is not None:
            close_fn = getattr(recorder, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass

        return self.wait(timeout_ms)

    def run(self):
        self.running = True

        try:
            mic = find_capture_mic()
            p = self.preset
            mode = p.get("mode", "adaptive")
            capture_name = str(getattr(mic, "name", "unknown"))
            capture_name_l = capture_name.lower()
            if any(t in capture_name_l for t in ("stereo mix", "wave out", "what u hear")):
                capture_kind = "stereo-mix"
            elif bool(getattr(mic, "isloopback", False)):
                capture_kind = "loopback"
            elif _is_virtual_loopback_name(capture_name_l):
                capture_kind = "virtual-loopback"
            else:
                capture_kind = "input"

            window = np.hanning(BLOCKSIZE).astype(np.float32)
            fft_amp_scale = 2.0 / max(float(np.sum(window)), 1e-12)
            freqs = np.fft.rfftfreq(BLOCKSIZE, d=1.0 / SAMPLERATE)
            nyquist = SAMPLERATE * 0.5
            min_freq = MIN_FREQ_HZ
            max_freq = min(MAX_FREQ_HZ, nyquist * 0.98)
            if max_freq <= min_freq:
                max_freq = nyquist * 0.9
            edges = np.geomspace(min_freq, max_freq, BARS + 1)
            band_centers = np.sqrt(edges[:-1] * edges[1:])
            spectral_tilt = np.power(np.maximum(band_centers, 1.0) / 1000.0, 0.12)
            spectral_tilt = np.clip(spectral_tilt, 0.90, 1.20).astype(np.float32)
            band_bins = [
                np.nonzero((freqs >= edges[i]) & (freqs < edges[i + 1]))[0]
                for i in range(BARS)
            ]

            smoothed = np.zeros(BARS, dtype=np.float32)
            ref_level = 0.22

            spatial_kernel = np.asarray(
                p.get("spatial_kernel", [1, 2, 3, 2, 1]),
                dtype=np.float32,
            )
            if spatial_kernel.ndim != 1 or spatial_kernel.size == 0:
                spatial_kernel = np.array([1, 2, 3, 2, 1], dtype=np.float32)
            spatial_kernel /= spatial_kernel.sum()
            post_power = float(p.get("post_power", 0.88))

            db_floor = float(p.get("db_floor", -78.0))
            db_ceiling = float(p.get("db_ceiling", -6.0))
            db_span = max(db_ceiling - db_floor, 1.0)
            expected_block_sec = BLOCKSIZE / float(SAMPLERATE)

            stats_blocks_total = 0
            stats_blocks_since_emit = 0
            stats_empty_total = 0
            stats_gaps_total = 0
            stats_channels = 0
            stats_last_emit = time.perf_counter()
            last_block_time = None

            with mic.recorder(samplerate=SAMPLERATE, blocksize=BLOCKSIZE) as recorder:
                with self._recorder_lock:
                    self._recorder = recorder

                try:
                    while self.running and not self.isInterruptionRequested():
                        data = recorder.record(numframes=BLOCKSIZE)

                        if data is None or len(data) == 0:
                            stats_empty_total += 1

                            now = time.perf_counter()
                            if now - stats_last_emit >= 0.5:
                                interval = max(now - stats_last_emit, 1e-6)
                                self.stats_ready.emit(
                                    {
                                        "blocks_per_sec": stats_blocks_since_emit / interval,
                                        "dropouts": stats_empty_total,
                                        "gaps": stats_gaps_total,
                                        "blocks_total": stats_blocks_total,
                                        "channels": stats_channels,
                                        "capture_name": capture_name,
                                        "capture_kind": capture_kind,
                                    }
                                )
                                stats_blocks_since_emit = 0
                                stats_last_emit = now
                            continue

                        block = np.asarray(data, dtype=np.float32)
                        if block.ndim == 1:
                            block = block[:, np.newaxis]
                        elif block.ndim != 2:
                            continue
                        stats_channels = int(block.shape[1])

                        rms = float(np.sqrt(np.mean(np.square(block)) + 1e-12))
                        peak = float(np.max(np.abs(block)))

                        if peak < 1e-6:
                            smoothed *= 0.95
                            self.levels_ready.emit(smoothed.copy())
                            continue

                        # Keep stereo information without phase cancellation between channels.
                        windowed = block * window[:, np.newaxis]
                        spectrum = np.mean(np.abs(np.fft.rfft(windowed, axis=0)), axis=1)
                        if mode == "accurate":
                            spectrum *= fft_amp_scale
                        bands = np.zeros(BARS, dtype=np.float32)

                        for i, idx in enumerate(band_bins):
                            if idx.size:
                                chunk = spectrum[idx]
                                rms_band = float(np.sqrt(np.mean(np.square(chunk)) + 1e-12))
                                if mode == "accurate":
                                    bands[i] = rms_band
                                else:
                                    max_band = float(np.max(chunk))
                                    bands[i] = 0.58 * rms_band + 0.42 * max_band

                        if mode == "accurate":
                            bands_db = 20.0 * np.log10(np.maximum(bands, 1e-12))
                            bands = (bands_db - db_floor) / db_span
                            bands = np.clip(bands, 0.0, 1.0)
                        else:
                            bands = np.log1p(bands * 20.0)

                            local_ref = max(
                                float(np.percentile(bands, p["ref_percentile"])),
                                p["ref_floor"],
                            )
                            if local_ref > ref_level:
                                ref_level = (
                                    (1.0 - p["ref_rise"]) * ref_level
                                    + p["ref_rise"] * local_ref
                                )
                            else:
                                ref_level = max(
                                    p["ref_decay"] * ref_level,
                                    (1.0 - p["ref_fall_mix"]) * ref_level
                                    + p["ref_fall_mix"] * local_ref,
                                )

                            bands = bands / max(ref_level, 1e-6)

                            if (
                                "loudness_floor_db" in p
                                and "loudness_ceil_db" in p
                            ):
                                rms_db = 20.0 * np.log10(max(rms, 1e-12))
                                loud_db_span = max(
                                    float(p["loudness_ceil_db"]) - float(p["loudness_floor_db"]),
                                    1e-6,
                                )
                                loudness = np.clip(
                                    (rms_db - float(p["loudness_floor_db"])) / loud_db_span,
                                    0.0,
                                    1.0,
                                )
                            else:
                                loudness = np.clip(
                                    rms * float(p.get("loudness_scale", 11.0)),
                                    0.0,
                                    1.0,
                                )

                            energy_gain = p["energy_base"] + p["energy_span"] * loudness
                            bands *= energy_gain

                            bands *= spectral_tilt
                            tone_shape = np.linspace(0.98, 1.02, BARS, dtype=np.float32)
                            bands *= tone_shape

                            frame_peak = max(
                                float(np.percentile(bands, p["peak_percentile"])),
                                1e-6,
                            )
                            if frame_peak > p["peak_limit"]:
                                bands *= p["peak_limit"] / frame_peak

                            bands = np.clip(bands, 0.0, p["clip_limit"])
                            bands = np.tanh(bands * p["tanh_drive"])
                            if (
                                "volume_min_gain" in p
                                and "volume_max_gain" in p
                            ):
                                vol_min = float(p["volume_min_gain"])
                                vol_max = float(p["volume_max_gain"])
                                bands *= vol_min + (vol_max - vol_min) * loudness

                        bands = np.convolve(bands, spatial_kernel, mode="same")
                        if abs(post_power - 1.0) > 1e-6:
                            bands = np.power(bands, post_power)

                        attack = p["worker_attack"]
                        release = p["worker_release"]
                        smoothed = np.where(
                            bands > smoothed,
                            smoothed + attack * (bands - smoothed),
                            smoothed + release * (bands - smoothed),
                        )

                        smoothed = np.clip(smoothed, 0.0, 1.0)
                        self.levels_ready.emit(smoothed.copy())

                        now = time.perf_counter()
                        stats_blocks_total += 1
                        stats_blocks_since_emit += 1
                        if (
                            last_block_time is not None
                            and (now - last_block_time) > expected_block_sec * 2.5
                        ):
                            stats_gaps_total += 1
                        last_block_time = now

                        if now - stats_last_emit >= 0.5:
                            interval = max(now - stats_last_emit, 1e-6)
                            self.stats_ready.emit(
                                {
                                    "blocks_per_sec": stats_blocks_since_emit / interval,
                                    "dropouts": stats_empty_total,
                                    "gaps": stats_gaps_total,
                                    "blocks_total": stats_blocks_total,
                                    "channels": stats_channels,
                                    "capture_name": capture_name,
                                    "capture_kind": capture_kind,
                                }
                            )
                            stats_blocks_since_emit = 0
                            stats_last_emit = now
                finally:
                    with self._recorder_lock:
                        self._recorder = None

                    now = time.perf_counter()
                    interval = max(now - stats_last_emit, 1e-6)
                    self.stats_ready.emit(
                        {
                            "blocks_per_sec": stats_blocks_since_emit / interval,
                            "dropouts": stats_empty_total,
                            "gaps": stats_gaps_total,
                            "blocks_total": stats_blocks_total,
                            "channels": stats_channels,
                            "capture_name": capture_name,
                            "capture_kind": capture_kind,
                        }
                    )

        except Exception as e:
            self.error_ready.emit(str(e))


class SonyVisualizer(QWidget):
    def __init__(self):
        super().__init__()

        self.preset_order = list(VISUAL_PRESETS.keys())
        self.visual_preset = (
            VISUAL_PRESET if VISUAL_PRESET in VISUAL_PRESETS else "balanced"
        )
        self.visual_cfg = {}
        self.ui_rise_speed = 0.32
        self.ui_fall_speed = 0.14
        self.ui_kernel = np.array([1, 2, 2, 2, 1], dtype=np.float32)
        self.peak_fall_step = 0.016
        self.apply_visual_preset(self.visual_preset, update_title=False)

        self.setWindowTitle(f"Sony Visualizer ({self.visual_preset})")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        self.target_levels = np.zeros(BARS, dtype=np.float32)
        self.display_levels = np.zeros(BARS, dtype=np.float32)
        self.peak_levels = np.zeros(BARS, dtype=np.float32)
        self.error_text = None

        self.debug_overlay_enabled = False
        self.debug_ui_fps = 0.0
        self.debug_worker_bps = 0.0
        self.debug_dropouts = 0
        self.debug_gaps = 0
        self.debug_blocks_total = 0
        self.debug_channels = 0
        self.debug_capture_name = "-"
        self.debug_capture_kind = "-"
        self._debug_ui_frames = 0
        self._debug_last_fps_update = time.perf_counter()

        self.worker = None
        self.is_visualizing = False

        self.collapsed_size = QSize(WINDOW_W, WINDOW_H_COLLAPSED)
        self.expanded_size = QSize(WINDOW_W, WINDOW_H_EXPANDED)
        self.cassette_expanded = False
        self.resize(self.collapsed_size)
        self.setMinimumSize(WINDOW_W, WINDOW_H_COLLAPSED)
        self.setMaximumSize(WINDOW_W, WINDOW_H_EXPANDED)

        self.logo_renderer = None
        logo_path = ensure_sony_logo()
        if logo_path is not None:
            try:
                renderer = QSvgRenderer(str(logo_path))
                if renderer.isValid():
                    self.logo_renderer = renderer
            except Exception:
                self.logo_renderer = None

        self.static_cache = None
        self.cached_size = QSize()
        self.display_rect = QRectF()
        self.content_rect = QRectF()
        self.header_h = 0.0

        self.close_button_rect = QRectF()
        self.pin_button_rect = QRectF()
        self.expand_button_rect = QRectF()
        self.transport_button_rect = QRectF()
        self.cassette_panel_rect = QRectF()
        self.cassette_window_rect = QRectF()

        self.close_pressed = False
        self.pin_pressed = False
        self.expand_pressed = False
        self.transport_pressed = False
        self.is_corner_pinned = False
        self.drag_offset = None

        self.cassette_elapsed_sec = 0.0
        self.cassette_phase_left = 0.0
        self.cassette_phase_right = 0.0
        self._last_anim_ts = time.perf_counter()
        self._anim_target_hz = 60.0
        self._anim_frame_period = 1.0 / self._anim_target_hz
        self._anim_next_tick = None
        self._anim_screen_name = ""

        self.anim_timer = QTimer(self)
        self.anim_timer.setSingleShot(True)
        self.anim_timer.setTimerType(Qt.PreciseTimer)
        self.anim_timer.timeout.connect(self.on_anim_timer)
        self.refresh_animation_timing(force=True)
        self.schedule_next_frame()

        # Do not start in play mode; user must press space to start
        # QTimer.singleShot(180, self.start_capture)

    def start_capture(self):
        if self.is_visualizing:
            return

        if not self.stop_capture(clear_levels=False):
            self.update()
            return
        self.error_text = None

        self.worker = AudioWorker(self.visual_cfg)
        self.worker.levels_ready.connect(self.on_levels)
        self.worker.error_ready.connect(self.on_error)
        self.worker.stats_ready.connect(self.on_worker_stats)
        self.worker.start()
        self.is_visualizing = True

        self.debug_worker_bps = 0.0
        self.debug_dropouts = 0
        self.debug_gaps = 0
        self.debug_blocks_total = 0
        self.debug_channels = 0
        self.debug_capture_name = "-"
        self.debug_capture_kind = "-"
        self.update()

    def stop_capture(self, clear_levels=True):
        stopped = True
        if self.worker is not None:
            stopped = self.worker.stop()
            if stopped:
                self.worker = None
            else:
                self.error_text = "Audio worker ÃŽÂ´ÃŽÂµÃŽÂ½ Ãâ€žÃŽÂµÃÂÃŽÂ¼ÃŽÂ±Ãâ€žÃŽÂ¹ÃÆ’Ãâ€žÃŽÂ·ÃŽÂºÃŽÂµ ÃŽÂºÃŽÂ±ÃŽÂ¸ÃŽÂ±ÃÂÃŽÂ±."
        self.is_visualizing = False
        if clear_levels:
            self.target_levels[:] = 0.0
        self.update()
        return stopped

    def toggle_capture(self):
        if self.is_visualizing:
            self.stop_capture(clear_levels=False)
        else:
            self.start_capture()

    def on_levels(self, levels):
        if self.is_visualizing:
            self.target_levels = np.asarray(levels, dtype=np.float32)
        self.error_text = None

    def on_error(self, message):
        self.error_text = str(message)
        self.stop_capture(clear_levels=False)
        self.update()

    def on_worker_stats(self, stats):
        self.debug_worker_bps = float(stats.get("blocks_per_sec", 0.0))
        self.debug_dropouts = int(stats.get("dropouts", 0))
        self.debug_gaps = int(stats.get("gaps", 0))
        self.debug_blocks_total = int(stats.get("blocks_total", 0))
        self.debug_channels = int(stats.get("channels", self.debug_channels))
        if "capture_name" in stats:
            self.debug_capture_name = str(stats.get("capture_name", "-"))
        if "capture_kind" in stats:
            self.debug_capture_kind = str(stats.get("capture_kind", "-"))
        if self.debug_overlay_enabled:
            self.update()

    def invalidate_cache(self):
        self.static_cache = None
        self.cached_size = QSize()

    def resizeEvent(self, event):
        self.invalidate_cache()
        super().resizeEvent(event)

    def get_display_refresh_hz(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return 60.0, ""

        try:
            hz = float(screen.refreshRate())
        except Exception:
            hz = 0.0

        if not np.isfinite(hz) or hz < 30.0 or hz > 360.0:
            hz = 60.0

        return hz, str(screen.name())

    def refresh_animation_timing(self, force=False):
        hz, screen_name = self.get_display_refresh_hz()
        if (
            not force
            and abs(hz - self._anim_target_hz) < 0.4
            and screen_name == self._anim_screen_name
        ):
            return

        self._anim_target_hz = hz
        self._anim_screen_name = screen_name
        self._anim_frame_period = 1.0 / max(hz, 1.0)
        self._anim_next_tick = time.perf_counter() + self._anim_frame_period

    def schedule_next_frame(self):
        if self._anim_next_tick is None:
            self._anim_next_tick = time.perf_counter() + self._anim_frame_period

        now = time.perf_counter()
        delay_sec = max(0.0, self._anim_next_tick - now)
        delay_ms = max(0, int(round(delay_sec * 1000.0)))
        self.anim_timer.start(delay_ms)

    def on_anim_timer(self):
        self.refresh_animation_timing()
        self.animate_frame()

        now = time.perf_counter()
        if self._anim_next_tick is None:
            self._anim_next_tick = now

        self._anim_next_tick += self._anim_frame_period
        if self._anim_next_tick < now - (self._anim_frame_period * 2.0):
            self._anim_next_tick = now
        while self._anim_next_tick <= now:
            self._anim_next_tick += self._anim_frame_period

        self.schedule_next_frame()

    def animate_frame(self):
        now = time.perf_counter()
        dt = min(max(now - self._last_anim_ts, 0.0), 0.1)
        self._last_anim_ts = now

        target = self.target_levels if self.is_visualizing else np.zeros_like(self.target_levels)

        rising = target > self.display_levels
        self.display_levels[rising] += self.ui_rise_speed * (
            target[rising] - self.display_levels[rising]
        )
        self.display_levels[~rising] += self.ui_fall_speed * (
            target[~rising] - self.display_levels[~rising]
        )

        self.display_levels = np.convolve(self.display_levels, self.ui_kernel, mode="same")
        self.display_levels = np.clip(self.display_levels, 0.0, 1.0)

        self.peak_levels = np.maximum(
            self.peak_levels - self.peak_fall_step,
            self.display_levels,
        )
        self.advance_cassette_animation(dt)

        self._debug_ui_frames += 1
        elapsed = now - self._debug_last_fps_update
        if elapsed >= 0.5:
            self.debug_ui_fps = self._debug_ui_frames / max(elapsed, 1e-6)
            self._debug_ui_frames = 0
            self._debug_last_fps_update = now

        self.update()

    def closeEvent(self, event):
        if self.anim_timer.isActive():
            self.anim_timer.stop()
        self.stop_capture(clear_levels=False)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key_Space:
            self.toggle_capture()
            return
        if event.key() == Qt.Key_P:
            self.cycle_visual_preset()
            return
        if event.key() == Qt.Key_D:
            self.debug_overlay_enabled = not self.debug_overlay_enabled
            self.update()
            return
        super().keyPressEvent(event)

    def apply_visual_preset(self, preset_name, update_title=True):
        cfg = VISUAL_PRESETS.get(preset_name, VISUAL_PRESETS["balanced"])
        self.visual_preset = preset_name if preset_name in VISUAL_PRESETS else "balanced"
        self.visual_cfg = dict(cfg)

        self.ui_rise_speed = float(cfg["ui_rise_speed"])
        self.ui_fall_speed = float(cfg["ui_fall_speed"])
        self.peak_fall_step = float(cfg["peak_fall"])

        self.ui_kernel = np.asarray(cfg["ui_kernel"], dtype=np.float32)
        self.ui_kernel /= max(float(self.ui_kernel.sum()), 1e-6)

        if update_title:
            self.setWindowTitle(f"Sony Visualizer ({self.visual_preset})")
            self.update()

    def cycle_visual_preset(self):
        current_index = self.preset_order.index(self.visual_preset)
        next_index = (current_index + 1) % len(self.preset_order)
        next_preset = self.preset_order[next_index]

        was_running = self.is_visualizing
        self.apply_visual_preset(next_preset)

        if was_running:
            self.stop_capture(clear_levels=False)
            self.start_capture()

    def move_to_bottom_right(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        area = screen.availableGeometry()
        margin = 12
        x = area.x() + area.width() - self.width() - margin
        y = area.y() + area.height() - self.height() - margin
        self.move(int(x), int(y))

    def toggle_corner_pin(self):
        self.is_corner_pinned = not self.is_corner_pinned
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.is_corner_pinned)
        self.show()

        if self.is_corner_pinned:
            self.move_to_bottom_right()

        self.update()

    def toggle_cassette_section(self):
        self.cassette_expanded = not self.cassette_expanded
        target = self.expanded_size if self.cassette_expanded else self.collapsed_size
        self.resize(target)
        self.invalidate_cache()

        if self.is_corner_pinned:
            self.move_to_bottom_right()

        self.update()

    def cassette_reel_radii(self):
        # Approximate cassette tape transfer with constant linear speed.
        hub_r = 11.0
        full_r = 27.0
        side_minutes = 45.0
        side_duration = max(side_minutes * 60.0, 1.0)
        progress = (self.cassette_elapsed_sec % side_duration) / side_duration
        area_span = full_r * full_r - hub_r * hub_r
        left_r = np.sqrt(hub_r * hub_r + (1.0 - progress) * area_span)
        right_r = np.sqrt(hub_r * hub_r + progress * area_span)
        return float(left_r), float(right_r)

    def advance_cassette_animation(self, dt):
        if dt <= 0:
            return

        if self.is_visualizing:
            self.cassette_elapsed_sec += dt
            left_r, right_r = self.cassette_reel_radii()
            tape_speed = 17.5  # visual units / sec
            self.cassette_phase_left -= (tape_speed / max(left_r, 1e-6)) * dt
            self.cassette_phase_right += (tape_speed / max(right_r, 1e-6)) * dt

        tau = 2.0 * np.pi
        self.cassette_phase_left %= tau
        self.cassette_phase_right %= tau

    def mousePressEvent(self, event):
        pos = event.position()

        if event.button() == Qt.LeftButton:
            if self.close_button_rect.contains(pos):
                self.close_pressed = True
                self.update()
                return

            if self.pin_button_rect.contains(pos):
                self.pin_pressed = True
                self.update()
                return

            if self.expand_button_rect.contains(pos):
                self.expand_pressed = True
                self.update()
                return

            if self.transport_button_rect.contains(pos):
                self.transport_pressed = True
                self.update()
                return

            header_drag_zone = QRectF(0, 0, self.width(), max(38, self.header_h + 8))
            if header_drag_zone.contains(pos):
                if self.is_corner_pinned:
                    return
                self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        pos = event.position()

        if event.button() == Qt.LeftButton:
            if self.close_pressed:
                self.close_pressed = False
                if self.close_button_rect.contains(pos):
                    self.close()
                    return
                self.update()

            if self.pin_pressed:
                self.pin_pressed = False
                if self.pin_button_rect.contains(pos):
                    self.toggle_corner_pin()
                    return
                self.update()

            if self.expand_pressed:
                self.expand_pressed = False
                if self.expand_button_rect.contains(pos):
                    self.toggle_cassette_section()
                    return
                self.update()

            if self.transport_pressed:
                self.transport_pressed = False
                if self.transport_button_rect.contains(pos):
                    self.toggle_capture()
                    return
                self.update()

            self.drag_offset = None

        super().mouseReleaseEvent(event)

    def ensure_static_cache(self):
        if self.static_cache is not None and self.cached_size == self.size():
            return

        if self.width() <= 0 or self.height() <= 0:
            return

        self.cached_size = self.size()
        self.static_cache = QPixmap(self.size())
        self.static_cache.fill(Qt.transparent)

        painter = QPainter(self.static_cache)
        painter.setRenderHint(QPainter.Antialiasing)

        full = QRectF(self.rect())
        top_full = QRectF(full.left(), full.top(), full.width(), min(full.height(), WINDOW_H_COLLAPSED))
        self.draw_full_panel(painter, top_full)

        inner = top_full.adjusted(10, 10, -10, -10)
        self.header_h = max(30, min(42, inner.height() * 0.18))

        self.draw_logo(painter, inner, self.header_h)
        self.layout_controls(inner, self.header_h)
        self.draw_controls(painter)

        self.display_rect = QRectF(
            inner.left() + 8,
            inner.top() + self.header_h + 2,
            inner.width() - 16,
            inner.height() - self.header_h - 10,
        )
        self.content_rect = self.display_rect.adjusted(12, 12, -12, -12)

        self.draw_display_background(painter, self.display_rect)
        self.draw_frequency_engraving(painter, self.display_rect, self.content_rect)

        self.cassette_panel_rect = QRectF()
        self.cassette_window_rect = QRectF()
        if self.cassette_expanded and full.height() > WINDOW_H_COLLAPSED + 10:
            cassette_top = WINDOW_H_COLLAPSED - 3.0
            cassette_h = full.height() - cassette_top - 6.0
            self.cassette_panel_rect = QRectF(8.0, cassette_top, full.width() - 16.0, cassette_h)
            self.draw_cassette_section_base(painter, self.cassette_panel_rect)
            self.cassette_window_rect = self.cassette_panel_rect.adjusted(48, 10, -48, -18)

        painter.end()

    def layout_controls(self, inner, header_h):
        btn_h = max(22.0, header_h - 6.0)
        close_w = 30.0
        pin_w = 34.0
        expand_w = 34.0
        transport_w = 74.0
        gap = 8.0

        # Move buttons 3px higher than center
        y = inner.top() + (header_h - btn_h) / 2 - 3
        close_x = inner.right() - close_w - 4
        pin_x = close_x - gap - pin_w
        expand_x = pin_x - gap - expand_w
        transport_x = expand_x - gap - transport_w

        self.close_button_rect = QRectF(close_x, y, close_w, btn_h)
        self.pin_button_rect = QRectF(pin_x, y, pin_w, btn_h)
        self.expand_button_rect = QRectF(expand_x, y, expand_w, btn_h)
        self.transport_button_rect = QRectF(transport_x, y, transport_w, btn_h)

    def paintEvent(self, event):
        self.ensure_static_cache()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.static_cache is not None:
            painter.drawPixmap(0, 0, self.static_cache)

        self.draw_controls(painter)
        self.draw_bars(painter, self.display_rect, self.content_rect)
        self.draw_debug_overlay(painter)
        self.draw_cassette_live(painter)

        if self.error_text:
            painter.setPen(QColor(220, 40, 40))
            font = QFont("Arial", 10, QFont.Bold)
            painter.setFont(font)
            painter.drawText(
                self.display_rect.adjusted(12, 12, -12, -12),
                Qt.AlignCenter | Qt.TextWordWrap,
                f"ÃŽÂ£Ãâ€ ÃŽÂ¬ÃŽÂ»ÃŽÂ¼ÃŽÂ±:\n{self.error_text}",
            )

    def draw_debug_overlay(self, painter):
        if not self.debug_overlay_enabled or self.display_rect.isNull():
            return

        box = QRectF(
            self.display_rect.left() + 8,
            self.display_rect.top() + 6,
            min(255.0, self.display_rect.width() - 16.0),
            70.0,
        )
        if box.width() <= 0 or box.height() <= 0:
            return

        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.setBrush(QColor(8, 12, 18, 185))
        painter.drawRoundedRect(box, 4, 4)

        painter.setPen(QColor(192, 212, 232))
        font = QFont("Consolas", 8)
        painter.setFont(font)
        ch_text = f"ch:{self.debug_channels}" if self.debug_channels > 0 else "ch:?"
        capture_line = f"{self.debug_capture_kind} {ch_text}: {self.debug_capture_name}"
        line1 = f"mode: {self.visual_preset}"
        line3 = f"ui fps: {self.debug_ui_fps:5.1f} | audio bps: {self.debug_worker_bps:5.1f}"
        line4 = f"dropouts: {self.debug_dropouts} | gaps: {self.debug_gaps} | blocks: {self.debug_blocks_total}"

        text_rect = box.adjusted(6, 4, -6, -4)
        fm = painter.fontMetrics()
        line_h = fm.height()
        line_gap = 1.0
        line_step = line_h + line_gap

        line1_rect = QRectF(text_rect.left(), text_rect.top(), text_rect.width(), line_h)
        line2_rect = QRectF(text_rect.left(), text_rect.top() + line_step, text_rect.width(), line_h)
        line3_rect = QRectF(text_rect.left(), text_rect.top() + 2 * line_step, text_rect.width(), line_h)
        line4_rect = QRectF(text_rect.left(), text_rect.top() + 3 * line_step, text_rect.width(), line_h)

        painter.drawText(line1_rect, Qt.AlignLeft | Qt.AlignTop, line1)
        painter.drawText(line3_rect, Qt.AlignLeft | Qt.AlignTop, line3)
        painter.drawText(line4_rect, Qt.AlignLeft | Qt.AlignTop, line4)

        # Marquee: when capture text is longer than the row, scroll it left in a loop.
        text_w = float(fm.horizontalAdvance(capture_line))
        visible_w = max(1.0, line2_rect.width())
        if text_w <= visible_w:
            painter.drawText(line2_rect, Qt.AlignLeft | Qt.AlignTop, capture_line)
            return

        gap_w = float(max(24, fm.horizontalAdvance("   ")))
        period = text_w + gap_w
        speed_px_per_sec = 24.0
        offset = (time.perf_counter() * speed_px_per_sec) % period
        start_x = line2_rect.left() - offset
        baseline_y = line2_rect.top() + fm.ascent()

        painter.save()
        painter.setClipRect(line2_rect)
        painter.drawText(int(start_x), int(baseline_y), capture_line)
        painter.drawText(int(start_x + period), int(baseline_y), capture_line)
        painter.restore()

    def draw_full_panel(self, painter, rect):
        panel_grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        panel_grad.setColorAt(0.00, QColor(214, 216, 219))
        panel_grad.setColorAt(0.12, QColor(201, 203, 206))
        panel_grad.setColorAt(0.50, QColor(181, 184, 188))
        panel_grad.setColorAt(0.82, QColor(160, 163, 167))
        panel_grad.setColorAt(1.00, QColor(148, 151, 155))

        painter.setPen(QPen(QColor(74, 76, 80), 1.2))
        painter.setBrush(QBrush(panel_grad))
        painter.drawRoundedRect(rect, 12, 12)

        top_reflect = QRectF(rect.left() + 2, rect.top() + 2, rect.width() - 4, 24)
        reflect_grad = QLinearGradient(
            top_reflect.left(),
            top_reflect.top(),
            top_reflect.left(),
            top_reflect.bottom(),
        )
        reflect_grad.setColorAt(0.0, QColor(255, 255, 255, 95))
        reflect_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(reflect_grad))
        painter.drawRoundedRect(top_reflect, 10, 10)

        for y in range(int(rect.top()) + 6, int(rect.bottom()) - 6, 2):
            tone = 180 + int(10 * np.sin(y * 0.06))
            tone = max(120, min(220, tone))
            painter.setPen(QColor(tone, tone, tone, 18))
            painter.drawLine(int(rect.left()) + 5, y, int(rect.right()) - 5, y)

        bottom_shadow = QRectF(rect.left() + 4, rect.bottom() - 12, rect.width() - 8, 8)
        shadow_grad = QLinearGradient(
            bottom_shadow.left(),
            bottom_shadow.top(),
            bottom_shadow.left(),
            bottom_shadow.bottom(),
        )
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 45))
        painter.setBrush(QBrush(shadow_grad))
        painter.drawRoundedRect(bottom_shadow, 6, 6)

    def draw_logo(self, painter, inner, header_h):
        logo_h = header_h * 0.70

        if self.logo_renderer is not None:
            default_size = self.logo_renderer.defaultSize()
            if default_size.width() > 0 and default_size.height() > 0:
                aspect = default_size.width() / default_size.height()
            else:
                aspect = 1280 / 225
        else:
            aspect = 1280 / 225

        logo_w = logo_h * aspect
        max_w = min(inner.width() * 0.24, 145)
        if logo_w > max_w:
            logo_w = max_w
            logo_h = logo_w / aspect

        x = inner.left() + 10
        y = inner.top() + (header_h - logo_h) / 2 - 1

        logo_rect = QRectF(x, y, logo_w, logo_h)

        if self.logo_renderer is not None:
            self.logo_renderer.render(painter, logo_rect)
        else:
            painter.setPen(QColor(18, 18, 18))
            font = QFont("Times New Roman")
            font.setBold(True)
            font.setPixelSize(max(16, int(logo_h * 0.78)))
            painter.setFont(font)
            painter.drawText(logo_rect, Qt.AlignLeft | Qt.AlignVCenter, "SONY")

    def draw_button_base(self, painter, rect, pressed=False):
        grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        if pressed:
            grad.setColorAt(0.0, QColor(120, 122, 126))
            grad.setColorAt(0.3, QColor(195, 197, 201))
            grad.setColorAt(1.0, QColor(150, 153, 158))
        else:
            grad.setColorAt(0.0, QColor(236, 237, 239))
            grad.setColorAt(0.25, QColor(198, 200, 203))
            grad.setColorAt(0.7, QColor(174, 177, 182))
            grad.setColorAt(1.0, QColor(224, 226, 229))

        painter.setPen(QPen(QColor(55, 57, 60), 1.0))
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(rect, 3.5, 3.5)

        inner = rect.adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor(255, 255, 255, 55), 0.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(inner, 3.0, 3.0)
        # Removed bottom slot highlight for a cleaner look

    def draw_controls(self, painter):
        if (
            self.transport_button_rect.isNull()
            or self.expand_button_rect.isNull()
            or self.pin_button_rect.isNull()
            or self.close_button_rect.isNull()
        ):
            return

        self.draw_button_base(painter, self.transport_button_rect, self.transport_pressed)
        self.draw_button_base(painter, self.expand_button_rect, self.expand_pressed)
        self.draw_button_base(painter, self.pin_button_rect, self.pin_pressed)
        self.draw_button_base(painter, self.close_button_rect, self.close_pressed)

        painter.setPen(Qt.NoPen)

        if self.is_visualizing:
            # Draw pause bars (orange) when playing
            painter.setBrush(QColor(232, 146, 18))
            bar_w = 3.0
            gap = 3.0
            total_w = bar_w * 2 + gap
            x = self.transport_button_rect.center().x() - total_w / 2
            y = self.transport_button_rect.top() + 5
            h = self.transport_button_rect.height() - 10
            painter.drawRect(QRectF(x, y, bar_w, h))
            painter.drawRect(QRectF(x + bar_w + gap, y, bar_w, h))
        else:
            # Draw play icon (black triangle) when paused
            painter.setBrush(QColor(0, 0, 0))
            cx = self.transport_button_rect.center().x()
            cy = self.transport_button_rect.center().y()
            w = 13
            h = 16
            path = QPainterPath()
            path.moveTo(cx - w / 2, cy - h / 2)
            path.lineTo(cx - w / 2, cy + h / 2)
            path.lineTo(cx + w / 2, cy)
            path.closeSubpath()
            painter.drawPath(path)

        exp_color = QColor(232, 146, 18) if self.cassette_expanded else QColor(30, 32, 34)
        painter.setPen(QPen(exp_color, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cx = self.expand_button_rect.center().x()
        cy = self.expand_button_rect.center().y()
        dx = 5.0
        dy = 3.2
        if self.cassette_expanded:
            painter.drawLine(
                QPoint(int(cx - dx), int(cy + dy / 2)),
                QPoint(int(cx), int(cy - dy)),
            )
            painter.drawLine(
                QPoint(int(cx), int(cy - dy)),
                QPoint(int(cx + dx), int(cy + dy / 2)),
            )
        else:
            painter.drawLine(
                QPoint(int(cx - dx), int(cy - dy / 2)),
                QPoint(int(cx), int(cy + dy)),
            )
            painter.drawLine(
                QPoint(int(cx), int(cy + dy)),
                QPoint(int(cx + dx), int(cy - dy / 2)),
            )

        icon_color = QColor(232, 146, 18) if self.is_corner_pinned else QColor(30, 32, 34)
        painter.setPen(QPen(icon_color, 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        icon = self.pin_button_rect.adjusted(8, 6, -8, -6)
        left = int(icon.left())
        top = int(icon.top())
        right = int(icon.right())
        bottom = int(icon.bottom())
        body = QRectF(left + 1, top + 1, max(6.0, icon.width() * 0.46), max(4.0, icon.height() * 0.42))
        painter.drawRoundedRect(body, 1.2, 1.2)
        painter.drawLine(QPoint(left, bottom), QPoint(right, bottom))
        painter.drawLine(QPoint(right, top), QPoint(right, bottom))
        painter.drawLine(QPoint(right - 4, bottom), QPoint(right, bottom))
        painter.drawLine(QPoint(right, bottom - 4), QPoint(right, bottom))

        if self.is_corner_pinned:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(232, 146, 18))
            painter.drawEllipse(QRectF(right - 3.0, bottom - 3.0, 2.6, 2.6))

        if self.is_visualizing:
            painter.setBrush(QColor(210, 18, 18))
            pen_color = QColor(190, 10, 10)
        else:
            painter.setBrush(QColor(0, 0, 0))
            pen_color = QColor(0, 0, 0)
        x_rect = self.close_button_rect.adjusted(0, 0, 0, 0)
        cx = x_rect.center().x()
        cy = x_rect.center().y()
        painter.setPen(QPen(pen_color, 2.2, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPoint(int(cx - 4), int(cy - 4)), QPoint(int(cx + 4), int(cy + 4)))
        painter.drawLine(QPoint(int(cx + 4), int(cy - 4)), QPoint(int(cx - 4), int(cy + 4)))

    def draw_cassette_section_base(self, painter, rect):
        if rect.isNull():
            return

        panel_grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        panel_grad.setColorAt(0.0, QColor(206, 209, 214))
        panel_grad.setColorAt(0.5, QColor(179, 183, 189))
        panel_grad.setColorAt(1.0, QColor(148, 153, 160))

        painter.setPen(QPen(QColor(92, 96, 102), 1.1))
        painter.setBrush(QBrush(panel_grad))
        painter.drawRoundedRect(rect, 8, 8)

    def draw_cassette_reel(self, painter, cx, cy, outer_r, tape_r, phase):
        rim_rect = QRectF(cx - outer_r, cy - outer_r, outer_r * 2.0, outer_r * 2.0)
        rim_grad = QLinearGradient(rim_rect.left(), rim_rect.top(), rim_rect.left(), rim_rect.bottom())
        rim_grad.setColorAt(0.0, QColor(222, 224, 227))
        rim_grad.setColorAt(0.55, QColor(165, 169, 174))
        rim_grad.setColorAt(1.0, QColor(102, 106, 112))
        painter.setPen(QPen(QColor(96, 100, 106), 1.0))
        painter.setBrush(QBrush(rim_grad))
        painter.drawEllipse(rim_rect)

        groove_r = max(outer_r - 3.2, 4.0)
        groove_rect = QRectF(cx - groove_r, cy - groove_r, groove_r * 2.0, groove_r * 2.0)
        painter.setPen(QPen(QColor(112, 116, 122, 160), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(groove_rect)

        tape_rect = QRectF(cx - tape_r, cy - tape_r, tape_r * 2.0, tape_r * 2.0)
        tape_grad = QLinearGradient(tape_rect.left(), tape_rect.top(), tape_rect.left(), tape_rect.bottom())
        tape_grad.setColorAt(0.0, QColor(70, 72, 76))
        tape_grad.setColorAt(1.0, QColor(36, 38, 42))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(tape_grad))
        painter.drawEllipse(tape_rect)

        hub_r = max(4.5, outer_r * 0.21)
        hub_rect = QRectF(cx - hub_r, cy - hub_r, hub_r * 2.0, hub_r * 2.0)
        hub_grad = QLinearGradient(hub_rect.left(), hub_rect.top(), hub_rect.left(), hub_rect.bottom())
        hub_grad.setColorAt(0.0, QColor(230, 232, 236))
        hub_grad.setColorAt(1.0, QColor(100, 104, 110))
        painter.setBrush(QBrush(hub_grad))
        painter.setPen(QPen(QColor(84, 88, 94), 1))
        painter.drawEllipse(hub_rect)

        core_r = max(1.8, hub_r * 0.34)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(14, 15, 17))
        painter.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2.0, core_r * 2.0))

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(float(np.degrees(phase)))
        spoke_inner = hub_r + 0.8
        spoke_outer = max(spoke_inner + 2.0, tape_r - 2.0)
        painter.setPen(QPen(QColor(184, 188, 194, 175), 1.3, Qt.SolidLine, Qt.RoundCap))
        for _ in range(6):
            painter.drawLine(QPoint(int(spoke_inner), 0), QPoint(int(spoke_outer), 0))
            painter.rotate(60.0)
        painter.restore()

        dot_dist = max(hub_r + 3.0, tape_r - 1.8)
        dot_x = cx + dot_dist * np.cos(phase)
        dot_y = cy + dot_dist * np.sin(phase)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(214, 50, 38, 210))
        painter.drawEllipse(QRectF(dot_x - 1.2, dot_y - 1.2, 2.4, 2.4))

    def draw_cassette_live(self, painter):
        if not self.cassette_expanded or self.cassette_window_rect.isNull():
            return

        window_rect = self.cassette_window_rect
        if window_rect.width() <= 0 or window_rect.height() <= 0:
            return

        frame_rect = QRectF(window_rect)
        frame_grad = QLinearGradient(frame_rect.left(), frame_rect.top(), frame_rect.left(), frame_rect.bottom())
        frame_grad.setColorAt(0.0, QColor(205, 208, 212))
        frame_grad.setColorAt(0.45, QColor(172, 176, 181))
        frame_grad.setColorAt(1.0, QColor(194, 198, 203))
        painter.setPen(QPen(QColor(96, 100, 106), 1.1))
        painter.setBrush(QBrush(frame_grad))
        painter.drawRoundedRect(frame_rect, 8, 8)

        body_rect = frame_rect.adjusted(3.0, 3.0, -3.0, -3.0)
        body_grad = QLinearGradient(body_rect.left(), body_rect.top(), body_rect.left(), body_rect.bottom())
        body_grad.setColorAt(0.0, QColor(246, 246, 248))
        body_grad.setColorAt(0.48, QColor(224, 225, 229))
        body_grad.setColorAt(1.0, QColor(176, 178, 184))
        painter.setPen(QPen(QColor(92, 95, 101), 1.0))
        painter.setBrush(QBrush(body_grad))
        painter.drawRoundedRect(body_rect, 6.5, 6.5)

        painter.setPen(QPen(QColor(255, 255, 255, 58), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(body_rect.adjusted(1, 1, -1, -1), 5.5, 5.5)

        center_window = QRectF(
            body_rect.center().x() - body_rect.width() * 0.15,
            body_rect.top() + body_rect.height() * 0.30,
            body_rect.width() * 0.30,
            body_rect.height() * 0.35,
        )
        slot_grad = QLinearGradient(center_window.left(), center_window.top(), center_window.left(), center_window.bottom())
        slot_grad.setColorAt(0.0, QColor(86, 70, 60))
        slot_grad.setColorAt(0.5, QColor(62, 48, 40))
        slot_grad.setColorAt(1.0, QColor(42, 32, 28))
        painter.setPen(QPen(QColor(74, 64, 58), 1))
        painter.setBrush(QBrush(slot_grad))
        painter.drawRoundedRect(center_window, 2, 2)

        flow = (self.cassette_phase_right / (2.0 * np.pi))
        stripe_x = center_window.left() + (flow % 1.0) * center_window.width()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(214, 184, 160, 78))
        painter.drawRect(QRectF(stripe_x - 2.5, center_window.top() + 1, 5.0, center_window.height() - 2))

        tape_y = center_window.center().y()
        painter.setPen(QPen(QColor(54, 44, 39), 1.0))
        painter.drawLine(
            int(body_rect.left() + body_rect.width() * 0.27),
            int(tape_y),
            int(body_rect.right() - body_rect.width() * 0.27),
            int(tape_y),
        )

        cx_l = body_rect.left() + body_rect.width() * 0.28
        cx_r = body_rect.right() - body_rect.width() * 0.28
        cy = body_rect.top() + body_rect.height() * 0.58
        outer_r = min(26.0, body_rect.height() * 0.33)
        left_pack, right_pack = self.cassette_reel_radii()
        scale = outer_r / 27.0
        left_pack *= scale
        right_pack *= scale

        self.draw_cassette_reel(painter, cx_l, cy, outer_r, left_pack, self.cassette_phase_left)
        self.draw_cassette_reel(painter, cx_r, cy, outer_r, right_pack, self.cassette_phase_right)

        ruler_y = body_rect.top() + body_rect.height() * 0.26
        left_edge = body_rect.left() + body_rect.width() * 0.36
        right_edge = body_rect.right() - body_rect.width() * 0.36
        painter.setPen(QPen(QColor(104, 108, 114, 170), 1))
        painter.drawLine(int(left_edge), int(ruler_y), int(right_edge), int(ruler_y))
        for i in range(11):
            x = left_edge + i * (right_edge - left_edge) / 10.0
            h = 6 if i % 5 == 0 else 3
            painter.drawLine(int(x), int(ruler_y), int(x), int(ruler_y - h))

        painter.setPen(QColor(84, 88, 94, 200))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        num_w = 22.0
        painter.drawText(QRectF(left_edge - num_w / 2, ruler_y - 17.0, num_w, 12.0), Qt.AlignHCenter | Qt.AlignVCenter, "0")
        painter.drawText(QRectF((left_edge + right_edge) * 0.5 - num_w / 2, ruler_y - 17.0, num_w, 12.0), Qt.AlignHCenter | Qt.AlignVCenter, "5")
        painter.drawText(QRectF(right_edge - num_w / 2, ruler_y - 17.0, num_w, 12.0), Qt.AlignHCenter | Qt.AlignVCenter, "10")

    def draw_display_background(self, painter, rect):
        frame = rect.adjusted(-5, -5, 5, 5)
        frame_grad = QLinearGradient(frame.left(), frame.top(), frame.left(), frame.bottom())
        frame_grad.setColorAt(0.0, QColor(70, 72, 76))
        frame_grad.setColorAt(0.45, QColor(35, 36, 39))
        frame_grad.setColorAt(1.0, QColor(76, 78, 82))

        painter.setPen(QPen(QColor(54, 54, 56), 1.2))
        painter.setBrush(QBrush(frame_grad))
        painter.drawRoundedRect(frame, 8, 8)

        bg_grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        bg_grad.setColorAt(0.0, QColor(8, 8, 9))
        bg_grad.setColorAt(0.52, QColor(12, 12, 13))
        bg_grad.setColorAt(1.0, QColor(4, 4, 4))
        painter.setPen(QPen(QColor(16, 16, 16), 1))
        painter.setBrush(QBrush(bg_grad))
        painter.drawRoundedRect(rect, 6, 6)

        reflection = QRectF(rect.left() + 8, rect.top() + 5, rect.width() - 16, rect.height() * 0.18)
        reflection_path = QPainterPath()
        reflection_path.addRoundedRect(reflection, 6, 6)
        refl_grad = QLinearGradient(
            reflection.left(),
            reflection.top(),
            reflection.left(),
            reflection.bottom(),
        )
        refl_grad.setColorAt(0.0, QColor(255, 255, 255, 25))
        refl_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setClipPath(reflection_path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(refl_grad))
        painter.drawRect(reflection)
        painter.setClipping(False)

        base_glow = QRectF(rect.left() + 10, rect.bottom() - 32, rect.width() - 20, 24)
        glow_grad = QLinearGradient(
            base_glow.left(),
            base_glow.top(),
            base_glow.left(),
            base_glow.bottom(),
        )
        glow_grad.setColorAt(0.0, QColor(160, 0, 0, 0))
        glow_grad.setColorAt(1.0, QColor(150, 0, 0, 55))
        painter.setBrush(QBrush(glow_grad))
        painter.drawRoundedRect(base_glow, 4, 4)

        painter.setPen(QPen(QColor(255, 255, 255, 8), 1))
        for i in range(1, 5):
            y = rect.top() + i * rect.height() / 5
            painter.drawLine(int(rect.left() + 10), int(y), int(rect.right() - 10), int(y))

        inner_line = QRectF(rect.left() + 1, rect.top() + 1, rect.width() - 2, rect.height() - 2)
        painter.setPen(QPen(QColor(255, 255, 255, 16), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(inner_line, 6, 6)

    def draw_frequency_engraving(self, painter, display_rect, content_rect):
        if display_rect.isNull() or content_rect.isNull():
            return

        max_freq = min(MAX_FREQ_HZ, SAMPLERATE * 0.5 * 0.98)
        if max_freq <= MIN_FREQ_HZ:
            return

        marks_hz = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
        labels = ["31", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"]

        # Scale marks on the gray panel under the display, aligned to the log-frequency bars.
        tick_top = display_rect.bottom() + 2.0
        tick_bottom = display_rect.bottom() + 6.0
        text_top = display_rect.bottom() + 6.0

        if tick_bottom >= self.height() - 1:
            return

        log_min = np.log(MIN_FREQ_HZ)
        log_span = np.log(max_freq) - log_min
        if log_span <= 1e-9:
            return

        baseline_y = tick_top - 1.0
        painter.setPen(QPen(QColor(84, 86, 90, 110), 1))
        painter.drawLine(
            int(content_rect.left()),
            int(baseline_y),
            int(content_rect.right()),
            int(baseline_y),
        )

        font = QFont("Arial")
        font.setPixelSize(8)
        font.setBold(True)
        painter.setFont(font)

        for hz, label in zip(marks_hz, labels):
            if hz < MIN_FREQ_HZ or hz > max_freq:
                continue

            t = (np.log(hz) - log_min) / log_span
            x = content_rect.left() + t * content_rect.width()
            tx = x - 14.0
            text_rect = QRectF(tx, text_top, 28.0, 10.0)

            # Engraved tick effect (highlight + shadow).
            painter.setPen(QPen(QColor(242, 243, 245, 65), 1))
            painter.drawLine(int(x), int(tick_top), int(x), int(tick_bottom - 1))
            painter.setPen(QPen(QColor(44, 46, 49, 130), 1))
            painter.drawLine(int(x + 1), int(tick_top + 1), int(x + 1), int(tick_bottom))

            # Engraved text effect.
            painter.setPen(QColor(244, 245, 247, 70))
            painter.drawText(
                text_rect.adjusted(0, -1, 0, -1),
                Qt.AlignHCenter | Qt.AlignTop,
                label,
            )
            painter.setPen(QColor(42, 44, 47, 145))
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)

    def draw_bars(self, painter, rect, content):
        if rect.isNull() or content.isNull():
            return

        baseline = content.bottom()
        max_height = content.height() - 4

        spacing = 1.6
        total_spacing = spacing * (BARS - 1)
        bar_width = max(2.2, (content.width() - total_spacing) / BARS)
        radius = min(2.0, bar_width / 2.0)

        painter.setRenderHint(QPainter.Antialiasing, True)

        for i, value in enumerate(self.display_levels):
            x = content.left() + i * (bar_width + spacing)
            height = float(value) * max_height
            if height >= 0.25:
                bar_rect = QRectF(x, baseline - height, bar_width, height)

                shadow_rect = bar_rect.adjusted(-0.4, 0, 0.5, 0.5)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 78))
                painter.drawRoundedRect(shadow_rect, radius, radius)

                metal_grad = QLinearGradient(
                    bar_rect.left(),
                    bar_rect.top(),
                    bar_rect.left(),
                    bar_rect.bottom(),
                )
                metal_grad.setColorAt(0.0, QColor(248, 248, 249))
                metal_grad.setColorAt(0.18, QColor(228, 229, 231))
                metal_grad.setColorAt(0.48, QColor(184, 186, 190))
                metal_grad.setColorAt(0.82, QColor(132, 135, 140))
                metal_grad.setColorAt(1.0, QColor(195, 197, 201))

                painter.setPen(QPen(QColor(255, 255, 255, 20), 0.8))
                painter.setBrush(QBrush(metal_grad))
                painter.drawRoundedRect(bar_rect, radius, radius)

                shine = QRectF(
                    bar_rect.left() + 0.45,
                    bar_rect.top() + 0.45,
                    max(0.7, bar_rect.width() * 0.22),
                    max(0.0, bar_rect.height() - 0.9),
                )
                if shine.height() > 2:
                    shine_grad = QLinearGradient(
                        shine.left(),
                        shine.top(),
                        shine.left(),
                        shine.bottom(),
                    )
                    shine_grad.setColorAt(0.0, QColor(255, 255, 255, 85))
                    shine_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(shine_grad))
                    painter.drawRoundedRect(shine, radius, radius)

            peak_height = float(self.peak_levels[i]) * max_height
            if peak_height >= 0.9:
                peak_y = baseline - peak_height
                cap_rect = QRectF(x, peak_y - 2.0, bar_width, 1.8)
                painter.setBrush(QColor(225, 20, 20, 225))
                painter.drawRoundedRect(cap_rect, 0.9, 0.9)


if __name__ == "__main__":
    from PySide6.QtGui import QIcon

    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "sony.visualizer.app.1"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Sony Visualizer")

    if sys.platform.startswith("linux"):
        app.setApplicationName("sony-visualizer")
        set_desktop_file_name = getattr(app, "setDesktopFileName", None)
        if callable(set_desktop_file_name):
            set_desktop_file_name("sony-visualizer")

    if sys.platform.startswith("win"):
        icon_candidates = ["sony.ico", "sony_logo.svg"]
    else:
        icon_candidates = ["sony_logo.svg", "sony.ico"]

    icon = QIcon()
    for icon_name in icon_candidates:
        candidate_path = Path(resource_path(icon_name))
        if not candidate_path.exists():
            continue
        candidate_icon = QIcon(str(candidate_path))
        if not candidate_icon.isNull():
            icon = candidate_icon
            break

    window = SonyVisualizer()
    if not icon.isNull():
        app.setWindowIcon(icon)
        window.setWindowIcon(icon)
    window.show()

    sys.exit(app.exec())
