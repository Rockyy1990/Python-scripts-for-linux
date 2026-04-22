#!/usr/bin/env python3
"""
Terminal Audio Player v3
========================
ffmpeg (decode + filter)  →  pw-cat / pw-play / aplay  (playback)

Änderungen gegenüber v2
-----------------------
  • Native sample rate / channel-count Pass-Through (kein Zwangs-Resampling)
  • 32-bit-Float-Transport zu PipeWire via pw-cat (höchste Qualität)
  • `-re` entfernt  →  volle Buffer-Füllung, kein künstliches Throttling
  • Erweiterte Codec-Unterstützung (> 20 Dateiendungen + ffprobe-Fallback)
  • ffprobe-basierte Metadaten: Titel, Artist, Album, Dauer, Bitrate
  • 4 Normalisierungs-Modi (zyklisch):
        off → replaygain → dynaudnorm → loudnorm → off
  • ReplayGain mit konfigurierbarem Preamp und `replaygain_noclip=1`
  • Automatischer Brickwall-Limiter (alimiter) bei Lautstärke > 100 %
  • Pause / Resume via SIGSTOP / SIGCONT
  • Saubere Prozess-Termination (terminate → wait → kill, Consumer zuerst)
  • Fehler-Diagnose: ffmpeg-stderr wird bei echten Fehlern ausgegeben
  • Thread-safe Pause-Handling während Stop/Skip
  • Lazy Metadata-Probing beim Ordner-Hinzufügen (schnelle UX)
  • `match`/`case`-Dispatcher, `@property`-API, Dataclass für Metadaten
  • `atexit`-Cleanup für saubere Prozess-Beendigung

Abhängigkeiten
--------------
  Pflicht : ffmpeg (≥ 6.0 empfohlen, getestet mit 8.1)
  Optional: ffprobe (für Metadaten & Auto-Format-Detection)
  Ausgabe : pw-cat (bevorzugt) > pw-play > aplay

Python 3.10+
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

# ── Farben ────────────────────────────────────────────────────────────────────
ORANGE = "\033[38;5;214m"
GREEN  = "\033[38;5;82m"
RED    = "\033[38;5;196m"
CYAN   = "\033[38;5;51m"
GRAY   = "\033[38;5;245m"
YELLOW = "\033[38;5;226m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

# ── Konstanten ────────────────────────────────────────────────────────────────

SUPPORTED_EXT: frozenset[str] = frozenset({
    # Lossy
    ".mp3", ".aac", ".m4a", ".m4b", ".opus", ".ogg", ".oga", ".mp2",
    ".wma", ".ac3", ".eac3", ".mka",
    # Lossless
    ".flac", ".wav", ".aiff", ".aif", ".alac", ".ape", ".wv", ".tak", ".tta",
    # DSD (benötigt ffmpeg-Build mit DSD-Support)
    ".dsf", ".dff",
    # Container
    ".caf", ".webm",
})

VOL_MIN, VOL_DEF, VOL_MAX = 0, 100, 200

NORM_MODES: tuple[str, ...] = ("off", "replaygain", "dynaudnorm", "loudnorm")
NORM_LABELS: dict[str, str] = {
    "off":         "AUS",
    "replaygain":  "ReplayGain (Tag-basiert)",
    "dynaudnorm":  "dynaudnorm (adaptiv, für Musik)",
    "loudnorm":    "loudnorm EBU R128 (-16 LUFS, für Podcasts/Broadcast)",
}
NORM_SHORT: dict[str, str] = {
    "replaygain": "RG", "dynaudnorm": "DYN", "loudnorm": "R128",
}


# ── Metadaten-Modell ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class TrackInfo:
    path: Path
    sample_rate: int = 44100
    channels: int = 2
    codec: str = ""
    duration: float = 0.0
    bit_rate: int = 0
    title: str = ""
    artist: str = ""
    album: str = ""
    rg_track_gain: float | None = None  # dB
    rg_track_peak: float | None = None

    @property
    def display_name(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} — {self.title}"
        if self.title:
            return self.title
        return self.path.name

    @property
    def has_replaygain(self) -> bool:
        return self.rg_track_gain is not None


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _parse_rg_value(s: str | None) -> float | None:
    """'‑6.5 dB' → -6.5 ; '' / None / 'invalid' → None"""
    if not s:
        return None
    cleaned = s.strip().lower().replace("db", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def probe_track(path: Path, timeout: float = 10.0) -> TrackInfo | None:
    """Holt Audio-Stream-Info + Tags via ffprobe. Gibt None bei Fehler zurück."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,bit_rate:"
        "stream_tags=title,artist,album,"
        "REPLAYGAIN_TRACK_GAIN,REPLAYGAIN_TRACK_PEAK,"
        "replaygain_track_gain,replaygain_track_peak:"
        "format=duration,bit_rate:"
        "format_tags=title,artist,album,"
        "REPLAYGAIN_TRACK_GAIN,REPLAYGAIN_TRACK_PEAK,"
        "replaygain_track_gain,replaygain_track_peak",
        "-of", "json", str(path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return None

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None

    streams = data.get("streams") or []
    if not streams:
        return None
    s = streams[0]
    fmt = data.get("format") or {}
    s_tags = {k.lower(): v for k, v in (s.get("tags") or {}).items()}
    f_tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}

    def tag(key: str) -> str:
        return s_tags.get(key) or f_tags.get(key) or ""

    try:
        sample_rate = int(s.get("sample_rate") or 44100)
        channels    = int(s.get("channels")    or 2)
    except (TypeError, ValueError):
        return None

    # Sanity
    if not (8000 <= sample_rate <= 384000):
        return None
    if not (1 <= channels <= 8):
        return None

    try:
        duration = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    try:
        bit_rate = int(fmt.get("bit_rate") or s.get("bit_rate") or 0)
    except (TypeError, ValueError):
        bit_rate = 0

    return TrackInfo(
        path=path,
        sample_rate=sample_rate,
        channels=channels,
        codec=s.get("codec_name") or "",
        duration=duration,
        bit_rate=bit_rate,
        title=tag("title"),
        artist=tag("artist"),
        album=tag("album"),
        rg_track_gain=_parse_rg_value(tag("replaygain_track_gain")),
        rg_track_peak=_parse_rg_value(tag("replaygain_track_peak")),
    )


def normalize_path(s: str) -> Path:
    s = s.strip()
    if len(s) >= 2 and s[0] in ('"', "'") and s[0] == s[-1]:
        s = s[1:-1]
    p = Path(s).expanduser()
    with contextlib.suppress(OSError):
        if p.exists():
            p = p.resolve()
    return p


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def input_or_quit(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def fmt_index(i: int, total: int) -> str:
    return f"{i:>{len(str(total))}}"


def truncate(s: str, max_len: int = 60) -> str:
    if len(s) <= max_len:
        return s
    half_l = (max_len - 1) // 2
    half_r = max_len - 1 - half_l
    return s[:half_l] + "…" + s[len(s) - half_r:]


def fmt_duration(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _print_result(ok: bool, msg: str) -> None:
    symbol = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
    print(f"  {symbol}  {ORANGE}{msg}{RESET}")


def _wait_enter() -> None:
    input_or_quit(f"  {GRAY}Enter{RESET}  ")


# ── AudioPlayer ───────────────────────────────────────────────────────────────

class AudioPlayer:
    def __init__(self) -> None:
        # Playlist
        self.playlist:       list[Path]          = []
        self._playlist_set:  set[Path]           = set()
        self._track_info:    dict[Path, TrackInfo] = {}
        self._current_idx:   int                 = 0
        self._current_path:  Path | None         = None

        # Optionen
        self._volume:        int    = VOL_DEF
        self._norm_mode:     str    = "off"
        self._rg_preamp_db:  float  = 0.0
        self._shuffle:       bool   = False
        self._shuffle_order: list[int] = []

        # Prozesse & Sync
        self._proc_lock = threading.Lock()
        self._ff_proc:  subprocess.Popen[bytes] | None = None
        self._con_proc: subprocess.Popen[bytes] | None = None
        self._paused:   bool = False

        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._play_thread: threading.Thread | None = None

        # Backends
        self._pw_cat      = shutil.which("pw-cat")
        self._pw_play     = shutil.which("pw-play")
        self._aplay       = shutil.which("aplay")
        self._has_ffprobe = shutil.which("ffprobe") is not None

        if not (self._pw_cat or self._pw_play or self._aplay):
            print(f"{RED}Warnung: kein Audio-Consumer gefunden "
                  f"(pw-cat / pw-play / aplay).{RESET}")
        if not self._has_ffprobe:
            print(f"{YELLOW}Warnung: ffprobe nicht gefunden. "
                  f"Metadaten/Format-Validierung deaktiviert.{RESET}")

    # ── Öffentliche Properties ───────────────────────────────────────────────

    @property
    def backend_name(self) -> str:
        if self._pw_cat:  return "pw-cat (f32le)"
        if self._aplay:   return "aplay (wav)"
        if self._pw_play: return "pw-play (wav)"
        return "kein Backend"

    @property
    def current_index(self) -> int:
        return self._current_idx

    @property
    def current_track(self) -> TrackInfo | None:
        if self._current_path is None:
            return None
        return self._track_info.get(self._current_path)

    @property
    def volume(self) -> int:           return self._volume
    @property
    def norm_mode(self) -> str:        return self._norm_mode
    @property
    def rg_preamp_db(self) -> float:   return self._rg_preamp_db
    @property
    def shuffle_enabled(self) -> bool: return self._shuffle

    def track_info(self, path: Path) -> TrackInfo | None:
        return self._track_info.get(path)

    # ── Playlist-Verwaltung ──────────────────────────────────────────────────

    def add_file(self, path_str: str, front: bool = False) -> tuple[bool, str]:
        p = normalize_path(path_str)
        if not p.exists():
            return False, f"Nicht gefunden: {p}"
        if not p.is_file():
            return False, "Keine reguläre Datei"
        if p in self._playlist_set:
            return False, "Bereits in Playlist"

        ext_ok = p.suffix.lower() in SUPPORTED_EXT

        # Probe (validiert gleichzeitig das Format)
        info: TrackInfo | None = None
        if self._has_ffprobe:
            info = probe_track(p)
            if info is None and not ext_ok:
                return False, f"Nicht abspielbar ({p.suffix or 'kein Suffix'})"
        elif not ext_ok:
            return False, f"Format nicht unterstützt ({p.suffix})"

        if info is None:
            info = TrackInfo(path=p)

        if front:
            self.playlist.insert(0, p)
            if self.is_playing():
                self._current_idx += 1
        else:
            self.playlist.append(p)
        self._playlist_set.add(p)
        self._track_info[p] = info
        self._shuffle_order = []

        pos_label = "vorne" if front else "hinten"
        return True, f"Hinzugefügt ({pos_label}): {info.display_name}"

    def add_folder(self, path_str: str, recursive: bool = False) -> tuple[bool, str]:
        p = normalize_path(path_str)
        if not p.exists() or not p.is_dir():
            return False, "Kein gültiger Ordner"
        pattern = "**/*" if recursive else "*"
        candidates = sorted(
            f for f in p.glob(pattern)
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
        )
        if not candidates:
            return False, "Keine unterstützten Dateien gefunden"

        added = 0
        for f in candidates:
            if f in self._playlist_set:
                continue
            self.playlist.append(f)
            self._playlist_set.add(f)
            # Lazy probe: erst beim Abspielen (schnelle Ordner-UX)
            added += 1

        self._shuffle_order = []
        return True, f"{added} Datei(en) hinzugefügt aus: {p.name}"

    def remove_track(self, idx: int) -> tuple[bool, str]:
        if not (0 <= idx < len(self.playlist)):
            return False, "Ungültiger Index"
        p = self.playlist[idx]
        name = p.name
        was_current = (idx == self._current_idx) and self.is_playing()

        if was_current:
            self._skip_event.set()
            self._kill_current()

        self.playlist.pop(idx)
        self._playlist_set.discard(p)
        self._track_info.pop(p, None)

        n = len(self.playlist)
        if n == 0:
            self._current_idx = 0
        elif was_current:
            # Damit _next_index den Track, der jetzt an Position `idx` liegt,
            # als nächsten liefert, dekrementieren wir current_idx.
            self._current_idx = max(-1, idx - 1)
        elif idx < self._current_idx:
            self._current_idx -= 1

        if self._current_idx >= n:
            self._current_idx = max(0, n - 1)

        self._shuffle_order = []
        return True, f"Entfernt: {name}"

    def move_track(self, from_idx: int, to_idx: int) -> tuple[bool, str]:
        n = len(self.playlist)
        if not (0 <= from_idx < n and 0 <= to_idx < n):
            return False, "Ungültiger Index"
        track = self.playlist.pop(from_idx)
        self.playlist.insert(to_idx, track)
        # current_idx-Anpassung (einfache Heuristik, ohne Kollisions-Edge-Cases)
        if from_idx == self._current_idx:
            self._current_idx = to_idx
        elif from_idx < self._current_idx <= to_idx:
            self._current_idx -= 1
        elif to_idx <= self._current_idx < from_idx:
            self._current_idx += 1
        self._shuffle_order = []
        return True, f"'{track.name}' → Position {to_idx}"

    def shuffle_playlist(self) -> tuple[bool, str]:
        if len(self.playlist) < 2:
            return False, "Zu wenige Tracks zum Mischen"
        random.shuffle(self.playlist)
        self._shuffle_order = []
        return True, "Playlist gemischt"

    def toggle_shuffle(self) -> str:
        self._shuffle = not self._shuffle
        if self._shuffle:
            self._rebuild_shuffle_order()
        return f"Shuffle: {'AN' if self._shuffle else 'AUS'}"

    def _rebuild_shuffle_order(self) -> None:
        order = list(range(len(self.playlist)))
        random.shuffle(order)
        self._shuffle_order = order

    def clear_playlist(self) -> None:
        self.stop()
        if self._play_thread:
            self._play_thread.join(timeout=2.0)
        self.playlist.clear()
        self._playlist_set.clear()
        self._track_info.clear()
        self._current_idx = 0
        self._current_path = None
        self._shuffle_order = []

    # ── Volume / Normalisierung ──────────────────────────────────────────────

    def set_volume(self, vol: int) -> tuple[bool, str]:
        if not (VOL_MIN <= vol <= VOL_MAX):
            return False, f"Ungültiger Wert (erlaubt: {VOL_MIN}–{VOL_MAX})"
        self._volume = vol
        return True, f"Lautstärke: {vol} %"

    def cycle_normalize(self) -> str:
        idx = NORM_MODES.index(self._norm_mode) if self._norm_mode in NORM_MODES else 0
        self._norm_mode = NORM_MODES[(idx + 1) % len(NORM_MODES)]
        return f"Normalisierung: {NORM_LABELS[self._norm_mode]}"

    def set_rg_preamp(self, db: float) -> tuple[bool, str]:
        if not (-20.0 <= db <= 20.0):
            return False, "Preamp außerhalb des Bereichs (-20..+20 dB)"
        self._rg_preamp_db = db
        return True, f"ReplayGain Preamp: {db:+.1f} dB"

    # ── Status ───────────────────────────────────────────────────────────────

    def is_playing(self) -> bool:
        t = self._play_thread
        return bool(t and t.is_alive())

    def is_paused(self) -> bool:
        return self._paused and self.is_playing()

    def status_line(self) -> str:
        count = len(self.playlist)

        badges = [f"{CYAN}[VOL {self._volume}%]{RESET}"]
        if self._norm_mode != "off":
            badges.append(f"{CYAN}[{NORM_SHORT[self._norm_mode]}]{RESET}")
        if self._shuffle:
            badges.append(f"{CYAN}[SHUFFLE]{RESET}")
        if self.is_paused():
            badges.append(f"{YELLOW}[PAUSE]{RESET}")
        extras = " " + " ".join(badges)

        if self.is_playing() and self._current_path:
            info = self._track_info.get(self._current_path)
            name = truncate(info.display_name if info else self._current_path.name, 40)
            idx  = self._current_idx + 1
            icon = "⏸" if self.is_paused() else "▶"
            color = YELLOW if self.is_paused() else GREEN
            return (f"{color}{icon} {BOLD}{name}{RESET}"
                    f"{GRAY} [{idx}/{count}]{RESET}{extras}")
        return f"{GRAY}⏹  Gestoppt  [{count} Track(s)]{RESET}{extras}"

    # ── ffmpeg/Consumer-Kommandos ────────────────────────────────────────────

    def _build_af_chain(self, info: TrackInfo) -> str | None:
        filters: list[str] = []

        # 1) Normalisierung (vor User-Volume)
        if self._norm_mode == "replaygain" and info.has_replaygain:
            filters.append(
                f"volume=replaygain=track:"
                f"replaygain_preamp={self._rg_preamp_db:.2f}dB:"
                f"replaygain_noclip=1"
            )
        elif self._norm_mode == "dynaudnorm":
            # f=150 Frame-Länge, g=15 Gauss-Fenster, p=0.95 Peak, m=10 max Gain
            filters.append("dynaudnorm=f=150:g=15:p=0.95:m=10")
        elif self._norm_mode == "loudnorm":
            filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

        # 2) User-Volume
        if self._volume != VOL_DEF:
            factor = self._volume / 100.0
            filters.append(f"volume={factor:.4f}:precision=float")
            # 3) Brickwall-Limiter gegen Clipping bei Boost
            if factor > 1.0:
                filters.append(
                    "alimiter=limit=0.98:attack=5:release=50:level=disabled"
                )

        return ",".join(filters) if filters else None

    def _consumer_cmd(self, info: TrackInfo) -> tuple[list[str], str]:
        """Returns (cmd, ffmpeg_output_format). format ∈ {'f32le', 'wav', ''}"""
        if self._pw_cat:
            return (
                [self._pw_cat, "--playback",
                 f"--rate={info.sample_rate}",
                 f"--channels={info.channels}",
                 "--format=f32", "-"],
                "f32le",
            )
        if self._aplay:
            return ([self._aplay, "-q", "-"], "wav")
        if self._pw_play:
            return ([self._pw_play, "--format=wav", "-"], "wav")
        return ([], "")

    def _ffmpeg_cmd(self, info: TrackInfo, out_format: str) -> list[str]:
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "warning", "-nostdin",
            "-i", str(info.path),
        ]
        af = self._build_af_chain(info)
        if af:
            cmd += ["-af", af]

        if out_format == "f32le":
            cmd += [
                "-f", "f32le", "-acodec", "pcm_f32le",
                "-ar", str(info.sample_rate),
                "-ac", str(info.channels),
                "pipe:1",
            ]
        else:  # wav (aplay / pw-play)
            cmd += [
                "-f", "wav", "-acodec", "pcm_s16le",
                "-ar", str(info.sample_rate),
                "-ac", str(info.channels),
                "pipe:1",
            ]
        return cmd

    # ── Prozess-Steuerung ────────────────────────────────────────────────────

    def _kill_current(self) -> None:
        """Beendet ffmpeg + Consumer sauber (Consumer zuerst → ffmpeg EPIPE)."""
        with self._proc_lock:
            ff, con = self._ff_proc, self._con_proc
            self._ff_proc = self._con_proc = None

        # Falls pausiert: aufwecken, sonst greift SIGTERM nicht
        if self._paused:
            for proc in (ff, con):
                if proc and proc.poll() is None:
                    with contextlib.suppress(OSError):
                        os.kill(proc.pid, signal.SIGCONT)
            self._paused = False

        for proc in (con, ff):
            if proc is None or proc.poll() is not None:
                continue
            try:
                proc.terminate()
            except OSError:
                continue
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=0.5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            except OSError:
                pass

    def _run_track(self, info: TrackInfo) -> None:
        consumer_cmd, out_format = self._consumer_cmd(info)
        if not consumer_cmd:
            print(f"{RED}Kein Audio-Backend verfügbar.{RESET}")
            self._stop_event.set()
            return

        ff_cmd = self._ffmpeg_cmd(info, out_format)

        # stderr in Tempfile → kein Deadlock bei vollem Pipe-Puffer,
        # keine zusätzlichen Threads nötig. `with`-Block garantiert Cleanup.
        with tempfile.TemporaryFile(mode="w+b") as err_file:
            try:
                ff = subprocess.Popen(
                    ff_cmd,
                    stdout=subprocess.PIPE,
                    stderr=err_file,
                )
            except FileNotFoundError:
                print(f"{RED}ffmpeg nicht gefunden.{RESET}")
                self._stop_event.set()
                return
            except OSError as e:
                print(f"{RED}ffmpeg-Start fehlgeschlagen: {e}{RESET}")
                return

            consumer: subprocess.Popen[bytes] | None = None
            try:
                consumer = subprocess.Popen(
                    consumer_cmd,
                    stdin=ff.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                # Parent schließt stdout: sonst bekommt ffmpeg kein EPIPE,
                # wenn der Consumer exitiert
                if ff.stdout is not None:
                    ff.stdout.close()
            except OSError as e:
                print(f"{RED}Consumer-Start fehlgeschlagen: {e}{RESET}")
                with contextlib.suppress(OSError):
                    ff.kill()
                return

            with self._proc_lock:
                self._ff_proc  = ff
                self._con_proc = consumer

            # Warten bis Consumer fertig ist oder Stop/Skip
            try:
                while True:
                    if consumer.poll() is not None:
                        break
                    if self._stop_event.wait(0.2):
                        break
                    if self._skip_event.is_set():
                        break
            finally:
                was_interrupted = (
                    self._stop_event.is_set() or self._skip_event.is_set()
                )
                self._kill_current()

                rc = ff.returncode
                if not was_interrupted and rc not in (0, None):
                    try:
                        err_file.seek(0)
                        err = err_file.read().decode(
                            "utf-8", errors="replace"
                        ).strip()
                    except OSError:
                        err = ""
                    if err:
                        lines = err.splitlines()[-3:]
                        msg = "\n    ".join(lines)
                        print(f"\n  {RED}ffmpeg ({rc}):{RESET}\n    {msg}")

    # ── Wiedergabe-Schleife ──────────────────────────────────────────────────

    def _next_index(self, current: int) -> int | None:
        n = len(self.playlist)
        if n == 0:
            return None
        if self._shuffle:
            if not self._shuffle_order or len(self._shuffle_order) != n:
                self._rebuild_shuffle_order()
            try:
                pos = self._shuffle_order.index(current)
            except ValueError:
                return self._shuffle_order[0] if self._shuffle_order else None
            nxt = pos + 1
            return self._shuffle_order[nxt] if nxt < len(self._shuffle_order) else None
        nxt = current + 1
        return nxt if nxt < n else None

    def _playback_loop(self) -> None:
        idx: int | None = self._current_idx
        if self._shuffle and not self._shuffle_order:
            self._rebuild_shuffle_order()

        try:
            while True:
                if self._stop_event.is_set():
                    break
                if idx is None or idx >= len(self.playlist) or idx < 0:
                    # idx < 0 kann nach remove_track am Anfang vorkommen
                    if idx is not None and idx < 0:
                        idx = self._next_index(idx)
                        if idx is None:
                            break
                        continue
                    break

                path = self.playlist[idx]
                self._current_idx  = idx
                self._current_path = path

                if not path.exists():
                    print(f"{RED}Datei nicht mehr vorhanden: {path}{RESET}")
                else:
                    info = self._track_info.get(path)
                    if info is None:
                        info = (probe_track(path) if self._has_ffprobe else None) \
                               or TrackInfo(path=path)
                        self._track_info[path] = info
                    self._run_track(info)

                if self._stop_event.is_set():
                    break
                self._skip_event.clear()
                idx = self._next_index(idx)
        finally:
            self._stop_event.clear()
            self._skip_event.clear()
            self._paused = False
            with self._proc_lock:
                self._ff_proc = None
                self._con_proc = None
            self._current_path = None

    # ── Öffentliche Transport-Steuerung ──────────────────────────────────────

    def play(self, from_idx: int = 0) -> tuple[bool, str]:
        if not self.playlist:
            return False, "Playlist leer"
        from_idx = max(0, min(from_idx, len(self.playlist) - 1))

        if self.is_playing():
            self.stop()
            if self._play_thread:
                self._play_thread.join(timeout=2.0)

        self._current_idx = from_idx
        self._stop_event.clear()
        self._skip_event.clear()
        self._paused = False

        t = threading.Thread(target=self._playback_loop, daemon=True)
        self._play_thread = t
        t.start()

        info = self._track_info.get(self.playlist[from_idx])
        name = info.display_name if info else self.playlist[from_idx].name
        return True, f"Wiedergabe: {truncate(name, 50)}"

    def stop(self) -> tuple[bool, str]:
        if not self.is_playing() and self._ff_proc is None:
            return True, "Keine aktive Wiedergabe"
        self._stop_event.set()
        self._kill_current()
        return True, "Gestoppt"

    def skip(self) -> tuple[bool, str]:
        if not self.is_playing():
            return False, "Keine aktive Wiedergabe"
        self._skip_event.set()
        self._kill_current()
        return True, "Track übersprungen"

    def toggle_pause(self) -> tuple[bool, str]:
        if not self.is_playing():
            return False, "Keine aktive Wiedergabe"
        with self._proc_lock:
            procs = [p for p in (self._ff_proc, self._con_proc)
                     if p is not None and p.poll() is None]
        if not procs:
            return False, "Kein laufender Prozess"

        sig = signal.SIGCONT if self._paused else signal.SIGSTOP
        try:
            for p in procs:
                os.kill(p.pid, sig)
        except OSError as e:
            return False, f"Pause fehlgeschlagen: {e}"

        self._paused = not self._paused
        return True, ("Pausiert" if self._paused else "Fortgesetzt")

    def jump_to(self, idx: int) -> tuple[bool, str]:
        if not (0 <= idx < len(self.playlist)):
            return False, f"Index {idx} ungültig (0–{len(self.playlist) - 1})"
        return self.play(from_idx=idx)


# ── UI / Menü ─────────────────────────────────────────────────────────────────

def print_header(player: AudioPlayer) -> None:
    bar = "─" * 64
    print(f"{ORANGE}{BOLD}{bar}{RESET}")
    print(f"{ORANGE}{BOLD}  Audio Player v3  │  ffmpeg → {player.backend_name}{RESET}")
    print(f"{ORANGE}{BOLD}{bar}{RESET}")
    print(f"  {player.status_line()}")

    info = player.current_track
    if info and player.is_playing():
        details = []
        if info.codec:       details.append(info.codec)
        if info.sample_rate: details.append(f"{info.sample_rate} Hz")
        if info.channels:    details.append(f"{info.channels}ch")
        if info.bit_rate:    details.append(f"{info.bit_rate // 1000} kbps")
        if info.duration:    details.append(fmt_duration(info.duration))
        if info.has_replaygain:
            details.append(f"RG {info.rg_track_gain:+.1f} dB")
        if details:
            print(f"  {GRAY}{' · '.join(details)}{RESET}")
    print(f"{ORANGE}{bar}{RESET}")


def print_menu() -> None:
    entries = [
        ("1", "Playlist anzeigen"),
        ("2", "Datei hinzufügen"),
        ("3", "Ordner hinzufügen"),
        ("4", "Track entfernen"),
        ("5", "Track verschieben"),
        ("",  ""),
        ("p", "▶  Play / ab Index"),
        ("b", "⏸  Pause / Resume"),
        ("s", "⏭  Skip"),
        ("x", "⏹  Stop"),
        ("",  ""),
        ("v", "🔊  Lautstärke  (0–200 %)"),
        ("n", "⚡  Normalisierung  (zyklisch)"),
        ("r", "📊  ReplayGain Preamp"),
        ("",  ""),
        ("z", "🔀  Playlist mischen"),
        ("t", "🔁  Shuffle-Modus"),
        ("c", "🗑   Playlist leeren"),
        ("",  ""),
        ("0", "Beenden"),
    ]
    for key, label in entries:
        if key == "":
            print(f"{GRAY}  {'·' * 50}{RESET}")
        else:
            print(f"  {ORANGE}{BOLD}{key:>2}{RESET}  {label}")
    print(f"{ORANGE}{'─' * 64}{RESET}")


def show_playlist(player: AudioPlayer) -> None:
    clear_screen()
    total = len(player.playlist)
    print(f"{ORANGE}{BOLD}Playlist  ({total} Track(s)){RESET}")
    print(f"{ORANGE}{'─' * 64}{RESET}")
    if not player.playlist:
        print(f"  {GRAY}<leer>{RESET}")
    else:
        for i, p in enumerate(player.playlist):
            marker = (f"{GREEN}▶{RESET}"
                      if player.is_playing() and i == player.current_index
                      else " ")
            num  = fmt_index(i, total)
            info = player.track_info(p)
            name = truncate(info.display_name if info else p.name, 48)
            dur  = fmt_duration(info.duration) if (info and info.duration) else ""
            dur_str = f" {GRAY}{dur}{RESET}" if dur else ""
            print(f"  {marker} {ORANGE}{num}{RESET}  {name}{dur_str}")
    print(f"{ORANGE}{'─' * 64}{RESET}")
    input_or_quit(f"{GRAY}Enter → zurück{RESET}  ")


# ── Menü-Handler ──────────────────────────────────────────────────────────────

def handle_add_file(player: AudioPlayer) -> None:
    clear_screen(); print_header(player)
    print(f"{ORANGE}{BOLD}Datei hinzufügen{RESET}")
    raw = input_or_quit(f"  {ORANGE}Pfad:{RESET} ")
    if not raw.strip():
        return
    pos = input_or_quit(
        f"  Position  {GRAY}[v=vorne / Enter=hinten]{RESET}: "
    ).strip().lower()
    ok, msg = player.add_file(raw, front=(pos == "v"))
    _print_result(ok, msg)
    _wait_enter()


def handle_add_folder(player: AudioPlayer) -> None:
    clear_screen(); print_header(player)
    print(f"{ORANGE}{BOLD}Ordner hinzufügen{RESET}")
    raw = input_or_quit(f"  {ORANGE}Pfad:{RESET} ")
    if not raw.strip():
        return
    rec = input_or_quit(f"  Rekursiv?  {GRAY}[j/N]{RESET}: ").strip().lower()
    ok, msg = player.add_folder(raw, recursive=(rec == "j"))
    _print_result(ok, msg)
    _wait_enter()


def handle_remove(player: AudioPlayer) -> None:
    show_playlist(player)
    if not player.playlist:
        return
    raw = input_or_quit(f"  {ORANGE}Index zum Entfernen:{RESET} ").strip()
    if not raw:
        return
    try:
        ok, msg = player.remove_track(int(raw))
        _print_result(ok, msg)
    except ValueError:
        _print_result(False, "Ungültige Eingabe")
    _wait_enter()


def handle_move(player: AudioPlayer) -> None:
    show_playlist(player)
    if len(player.playlist) < 2:
        return
    try:
        f_raw = input_or_quit(f"  {ORANGE}Von Index:{RESET} ").strip()
        t_raw = input_or_quit(f"  {ORANGE}Nach Index:{RESET} ").strip()
        if not f_raw or not t_raw:
            return
        ok, msg = player.move_track(int(f_raw), int(t_raw))
        _print_result(ok, msg)
    except ValueError:
        _print_result(False, "Ungültige Eingabe")
    _wait_enter()


def handle_play(player: AudioPlayer) -> None:
    raw = input_or_quit(f"  {ORANGE}Ab Index{GRAY} [Enter=0]{RESET}: ").strip()
    try:
        idx = int(raw) if raw else 0
    except ValueError:
        _print_result(False, "Ungültige Eingabe")
        _wait_enter()
        return
    ok, msg = player.play(from_idx=idx)
    _print_result(ok, msg)
    _wait_enter()


def handle_volume(player: AudioPlayer) -> None:
    clear_screen(); print_header(player)
    print(f"{ORANGE}{BOLD}Lautstärke setzen{RESET}")
    print(f"  Aktuell: {CYAN}{player.volume} %{RESET}  "
          f"{GRAY}(0 = stumm, 100 = normal, 200 = doppelt){RESET}")
    print(f"  {GRAY}> 100 % aktiviert automatisch Brickwall-Limiter "
          f"(alimiter).{RESET}")
    raw = input_or_quit(
        f"  {ORANGE}Neuer Wert (0–200){GRAY} [Enter = unverändert]{RESET}: "
    ).strip()
    if raw:
        try:
            ok, msg = player.set_volume(int(raw))
            _print_result(ok, msg)
            if ok:
                print(f"  {GRAY}Hinweis: Änderung ab nächstem Track wirksam.{RESET}")
        except ValueError:
            _print_result(False, "Ungültige Eingabe")
    _wait_enter()


def handle_normalize(player: AudioPlayer) -> None:
    clear_screen(); print_header(player)
    print(f"{ORANGE}{BOLD}Normalisierung (zyklisch){RESET}")
    print(f"  Aktuell: {CYAN}{NORM_LABELS[player.norm_mode]}{RESET}")
    print()
    print(f"  {GRAY}Verfügbare Modi:{RESET}")
    for m in NORM_MODES:
        active = "●" if m == player.norm_mode else "○"
        print(f"    {active} {m:<12} {GRAY}{NORM_LABELS[m]}{RESET}")
    print()
    print(f"  {GRAY}Enter = zum nächsten Modus wechseln · q = abbrechen{RESET}")
    raw = input_or_quit(f"  {ORANGE}Wahl:{RESET} ").strip().lower()
    if raw == "q":
        return
    msg = player.cycle_normalize()
    _print_result(True, msg)

    mode = player.norm_mode
    if mode == "replaygain":
        info = player.current_track
        if info and not info.has_replaygain:
            print(f"  {YELLOW}Achtung: aktueller Track hat keinen "
                  f"ReplayGain-Tag → Normalisierung inaktiv.{RESET}")
        print(f"  {GRAY}Tipp: Tags mit 'rsgain' oder 'r128gain' berechnen.{RESET}")
    elif mode == "dynaudnorm":
        print(f"  {GRAY}Empfohlen für Musik — adaptiv, kein Pumping.{RESET}")
    elif mode == "loudnorm":
        print(f"  {GRAY}EBU R128 Single-Pass (I=-16 LUFS, TP=-1.5 dBTP, "
              f"LRA=11 LU). Gut für Podcasts/Broadcast.{RESET}")
    if mode != "off":
        print(f"  {GRAY}Änderung ab nächstem Track wirksam.{RESET}")
    _wait_enter()


def handle_rg_preamp(player: AudioPlayer) -> None:
    clear_screen(); print_header(player)
    print(f"{ORANGE}{BOLD}ReplayGain Preamp{RESET}")
    print(f"  Aktuell: {CYAN}{player.rg_preamp_db:+.1f} dB{RESET}")
    print(f"  {GRAY}Bereich: -20..+20 dB. +6 dB ist typisch für "
          f"leise gemasterte Alben.{RESET}")
    raw = input_or_quit(
        f"  {ORANGE}Neuer Wert{GRAY} [Enter = unverändert]{RESET}: "
    ).strip()
    if raw:
        try:
            ok, msg = player.set_rg_preamp(float(raw))
            _print_result(ok, msg)
        except ValueError:
            _print_result(False, "Ungültige Eingabe")
    _wait_enter()


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main() -> None:
    if shutil.which("ffmpeg") is None:
        print(f"{RED}{BOLD}ffmpeg nicht gefunden. "
              f"Bitte installieren und erneut starten.{RESET}")
        sys.exit(1)

    player = AudioPlayer()

    # Garantierter Cleanup bei sys.exit / normaler Rückkehr
    def _cleanup() -> None:
        try:
            player.stop()
            if player._play_thread:
                player._play_thread.join(timeout=1.0)
        except Exception:
            pass
    atexit.register(_cleanup)

    while True:
        clear_screen()
        print_header(player)
        print_menu()

        choice = input_or_quit(f"  {ORANGE}Wahl:{RESET} ").strip().lower()

        match choice:
            case "1":
                show_playlist(player)
            case "2":
                handle_add_file(player)
            case "3":
                handle_add_folder(player)
            case "4":
                handle_remove(player)
            case "5":
                handle_move(player)
            case "p":
                handle_play(player)
            case "b":
                ok, msg = player.toggle_pause()
                _print_result(ok, msg)
                _wait_enter()
            case "s":
                ok, msg = player.skip()
                _print_result(ok, msg)
                _wait_enter()
            case "x":
                ok, msg = player.stop()
                _print_result(ok, msg)
                _wait_enter()
            case "v":
                handle_volume(player)
            case "n":
                handle_normalize(player)
            case "r":
                handle_rg_preamp(player)
            case "z":
                ok, msg = player.shuffle_playlist()
                _print_result(ok, msg)
                _wait_enter()
            case "t":
                msg = player.toggle_shuffle()
                print(f"  {ORANGE}{msg}{RESET}")
                _wait_enter()
            case "c":
                confirm = input_or_quit(
                    f"  {ORANGE}Wirklich leeren?{GRAY} [j/N]{RESET}: "
                ).strip().lower()
                if confirm == "j":
                    player.clear_playlist()
                    print(f"  {ORANGE}Playlist geleert{RESET}")
                _wait_enter()
            case "0":
                print(f"  {GRAY}Auf Wiedersehen.{RESET}")
                sys.exit(0)
            case _:
                _print_result(False, f"Ungültige Wahl: '{choice}'")
                _wait_enter()


if __name__ == "__main__":
    main()
