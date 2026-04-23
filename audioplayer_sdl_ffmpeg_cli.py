#!/usr/bin/env python3
"""
CLI Audio Player – SDL2 + FFmpeg + Curses TUI
==============================================
Produktionsreife Version mit robustem Thread-Handling, sauberem
Prozess-Management und interaktivem Curses-Interface.

Target : Linux / Arch Linux  (Python >= 3.10)
Deps   : sudo pacman -S ffmpeg python-pysdl2
         # oder:
         pip install pysdl2

Autor  : 2025
Lizenz : MIT
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Stdlib imports – alles was vor dem Dependency-Check laufen muss
# ---------------------------------------------------------------------------
import array
import atexit
import curses
import logging
import os
import queue
import random
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# ESC-Delay VOR dem curses-Import reduzieren (Default 1 Sekunde!)
# ---------------------------------------------------------------------------
os.environ.setdefault("ESCDELAY", "25")

# ---------------------------------------------------------------------------
# Logging (nur bei Umgebungsvariable AUDIOPLAYER_DEBUG aktiv)
# ---------------------------------------------------------------------------
_LOG_FILE = Path(os.environ.get("AUDIOPLAYER_LOG", "/tmp/audioplayer.log"))
if os.environ.get("AUDIOPLAYER_DEBUG"):
    logging.basicConfig(
        filename=str(_LOG_FILE),
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s",
    )
log = logging.getLogger("audioplayer")


# ---------------------------------------------------------------------------
# Dependency Check
# ---------------------------------------------------------------------------
def check_dependencies() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    # Python-Version
    if sys.version_info < (3, 10):
        errors.append(
            f"Python >= 3.10 erforderlich (gefunden: {sys.version.split()[0]})"
        )

    if shutil.which("ffmpeg") is None:
        errors.append("ffmpeg nicht gefunden  ->  sudo pacman -S ffmpeg")
    try:
        import sdl2  # noqa: F401
    except ImportError:
        errors.append(
            "pysdl2 nicht gefunden  ->  sudo pacman -S python-pysdl2"
            "  oder  pip install pysdl2"
        )

    # Python 3.13+ hat kein audioop mehr - Warnung ausgeben
    if sys.version_info >= (3, 13):
        try:
            import audioop_lts  # noqa: F401
        except ImportError:
            warnings.append(
                "audioop-lts nicht installiert - Volume-Skalierung wird langsam sein."
                "\n    Empfohlen: pip install audioop-lts"
            )

    if errors:
        sys.stderr.write("Fehlende Abhaengigkeiten:\n")
        for e in errors:
            sys.stderr.write(f"  x {e}\n")
        sys.exit(1)

    for w in warnings:
        sys.stderr.write(f"  ! {w}\n")


check_dependencies()

import sdl2          # noqa: E402
import sdl2.audio    # noqa: E402

# ---------------------------------------------------------------------------
# Audiokonstanten
# ---------------------------------------------------------------------------
SAMPLE_RATE   = 44100
CHANNELS      = 2
SAMPLE_WIDTH  = 2                             # Bytes per sample (S16)
BYTES_PER_SEC = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH
CHUNK_BYTES   = 8192
SDL_FRAMES    = 2048
FORMAT        = sdl2.AUDIO_S16SYS

QUEUE_MAX_SEC = 2.0                           # max ~2 Sek. Audio gepuffert
QUEUE_MAX     = max(4, int(QUEUE_MAX_SEC * BYTES_PER_SEC / CHUNK_BYTES))

# Ziel-Fuellstand der SDL-Audio-Queue in Bytes.
# Rate-Limiting: Feeder wartet, wenn SDL-Queue ueber diesem Wert liegt.
# Damit wirken Lautstaerke-Aenderungen innerhalb von ~100ms (statt >20s!).
SDL_TARGET_BUFFER_SEC = 0.1
SDL_TARGET_BUFFER     = int(SDL_TARGET_BUFFER_SEC * BYTES_PER_SEC)

AUDIO_EXTS = frozenset({
    ".mp3", ".flac", ".ogg", ".wav", ".aac",
    ".m4a", ".opus", ".wma", ".ape", ".mka",
    ".mp4", ".webm", ".alac", ".oga", ".m4b",
})

# ---------------------------------------------------------------------------
# Globale Subprocess-Registry fuer sauberen Exit
# ---------------------------------------------------------------------------
_procs_lock = threading.Lock()
_active_procs: set[subprocess.Popen] = set()


def _register_proc(proc: subprocess.Popen) -> None:
    with _procs_lock:
        _active_procs.add(proc)


def _unregister_proc(proc: subprocess.Popen) -> None:
    with _procs_lock:
        _active_procs.discard(proc)


@atexit.register
def _kill_all_procs() -> None:
    """Killt alle registrierten FFmpeg-Prozesse bei Programmende."""
    with _procs_lock:
        for proc in list(_active_procs):
            try:
                proc.kill()
            except Exception:
                pass
        _active_procs.clear()


def _setup_signal_handlers() -> None:
    """SIGTERM -> SystemExit (damit atexit/curses.wrapper sauber cleanen)."""
    def _handler(signum: int, _frame: object) -> None:
        log.info("Signal %d empfangen, beende", signum)
        sys.exit(128 + signum)
    signal.signal(signal.SIGTERM, _handler)
    # SIGINT wird von Python automatisch zu KeyboardInterrupt -> bereits behandelt


# ---------------------------------------------------------------------------
# PCM-Lautstaerke-Skalierung
# Optimierungskette (schnellster verfuegbarer Backend gewinnt):
#   1) audioop      – stdlib bis Python 3.12 (C-Code, 230x schneller)
#   2) audioop-lts  – pip-Ersatzpaket fuer Python 3.13+ (gleiche API)
#   3) Pure Python  – array.array + list-comp, ohne Clamping
#      (sicher fuer factor <= 1.0, ~4x schneller als Generator+Clamping)
# ---------------------------------------------------------------------------
_audioop = None
try:
    import audioop as _audioop                                # Python <= 3.12
except ImportError:
    try:
        import audioop_lts as _audioop                        # Python 3.13+ via pip
    except ImportError:
        _audioop = None

if _audioop is not None:
    def scale_volume(data: bytes, factor: float) -> bytes:
        if factor >= 1.0:
            return data
        return _audioop.mul(data, SAMPLE_WIDTH, max(0.0, factor))
    log.debug("Volume-Scaling: audioop/audioop-lts (C)")
else:
    def scale_volume(data: bytes, factor: float) -> bytes:
        if factor >= 1.0:
            return data
        f = max(0.0, factor)
        src = array.array("h", data)
        # factor in [0, 1] garantiert Ergebnis in int16-Range -> kein Clamping
        # List-Comp + int-Cast ist ~4x schneller als Generator mit max/min
        dst = array.array("h", [int(s * f) for s in src])
        return dst.tobytes()
    log.debug("Volume-Scaling: Pure-Python-Fallback")


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Track:
    path:  str
    title: str


# ---------------------------------------------------------------------------
# FFmpeg-Decoder-Thread
# ---------------------------------------------------------------------------
class FFmpegDecoder(threading.Thread):
    """
    Startet ffmpeg als Subprozess und schreibt PCM-Bloecke in eine Queue.

    Robustheits-Eigenschaften:
      * stop() killt den Subprozess sofort -> stdout.read unblockt
      * queue.put mit Timeout + Stop-Check -> kein Deadlock bei voller Queue
      * Subprozess wird in globaler Registry verfolgt (atexit-Cleanup)
    """

    _PUT_TIMEOUT = 0.2   # Sekunden pro put-Versuch

    def __init__(self, path: str, out_q: queue.Queue) -> None:
        super().__init__(daemon=True, name=f"decoder[{os.path.basename(path)}]")
        self.path  = path
        self.out_q = out_q
        self._stop_event = threading.Event()
        self._proc: Optional[subprocess.Popen] = None

    def run(self) -> None:
        cmd = [
            "ffmpeg", "-v", "quiet", "-nostdin",
            "-i", self.path,
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
            "pipe:1",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except (FileNotFoundError, OSError) as e:
            log.error("Popen failed: %s", e)
            self._safe_put(None)
            return

        self._proc = proc
        _register_proc(proc)
        log.debug("Decoder gestartet fuer %s (pid=%d)", self.path, proc.pid)

        try:
            while not self._stop_event.is_set():
                try:
                    data = proc.stdout.read(CHUNK_BYTES)
                except (OSError, ValueError):
                    break                                   # Prozess wurde gekillt
                if not data:
                    break                                   # EOF
                if not self._safe_put(data):
                    break                                   # Stop-Event gesetzt
        finally:
            self._terminate_proc()
            _unregister_proc(proc)
            self._safe_put(b"")                             # EOF-Sentinel
            log.debug("Decoder beendet fuer %s", self.path)

    def _safe_put(self, item: object) -> bool:
        """
        Nichtblockierender put mit Stop-Check.
        Returns True wenn erfolgreich, False wenn Stop-Event gesetzt.
        """
        while not self._stop_event.is_set():
            try:
                self.out_q.put(item, timeout=self._PUT_TIMEOUT)
                return True
            except queue.Full:
                continue
        return False

    def _terminate_proc(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None:                   # noch am Leben
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        except Exception as e:
            log.warning("Subprocess-Terminierung fehlgeschlagen: %s", e)

    def stop(self) -> None:
        """Stoppt Decoder sofort – killt Subprozess, unblockt stdout.read."""
        self._stop_event.set()
        self._terminate_proc()


# ---------------------------------------------------------------------------
# SDL Audio Helper
# ---------------------------------------------------------------------------
def _sdl_queue_audio(dev: int, data: bytes) -> int:
    """Thread-safer Wrapper fuer SDL_QueueAudio (ctypes-sicher)."""
    if not data:
        return 0
    # bytes -> c_void_p via buffer protocol funktioniert, aber explizite
    # Konversion ist robuster ueber pysdl2-Versionen hinweg.
    return sdl2.SDL_QueueAudio(dev, data, len(data))


# ---------------------------------------------------------------------------
# Audio Player
# ---------------------------------------------------------------------------
class AudioPlayer:
    """
    Zentraler Audio-Player mit Thread-sicherer Playlist-Verwaltung.

    Threading-Modell:
      * TUI-Thread ruft oeffentliche Methoden (play/pause/stop/add_track/...)
      * Decoder-Thread schreibt PCM-Bloecke in _buf_q
      * Feeder-Thread liest aus _buf_q und reicht an SDL weiter
      * Ende-Synchronisation ueber Thread.join(timeout)
    """

    _DRAIN_POLL = 0.05
    _JOIN_TIMEOUT = 1.5

    def __init__(self) -> None:
        # Playlist-State (geschuetzt durch _lock fuer Mutationen)
        self.playlist: list[Track] = []
        self._order:   list[int]   = []
        self._shuffle: bool        = False
        self.pos:      int         = 0

        # Wiedergabe-State
        self.volume:  float = 1.0
        self.paused:  bool  = True
        self.playing: bool  = False
        self.last_error: str = ""

        # Threading
        self._lock           = threading.RLock()
        self._buf_q: queue.Queue = queue.Queue(maxsize=QUEUE_MAX)
        self._decoder: Optional[FFmpegDecoder] = None
        self._feeder_thread: Optional[threading.Thread] = None

        # SDL init
        if sdl2.SDL_Init(sdl2.SDL_INIT_AUDIO) < 0:
            err = sdl2.SDL_GetError().decode("utf-8", "replace")
            raise RuntimeError(f"SDL_Init Fehler: {err}")

        self._dev: int = 0
        self._open_device()

    # ── SDL-Device ────────────────────────────────────────────────────────

    def _open_device(self) -> None:
        # pysdl2 >= 0.9.16 verlangt positional args im Konstruktor
        spec = sdl2.audio.SDL_AudioSpec(
            SAMPLE_RATE, FORMAT, CHANNELS, SDL_FRAMES
        )
        dev = sdl2.SDL_OpenAudioDevice(None, 0, spec, None, 0)
        if dev == 0:
            err = sdl2.SDL_GetError().decode("utf-8", "replace")
            raise RuntimeError(f"Audio-Device Fehler: {err}")
        self._dev = dev
        log.debug("SDL-Device geoeffnet: id=%d", dev)

    # ── Interne Wiedergabe-Pipeline ───────────────────────────────────────

    def _push_audio(self, data: bytes) -> None:
        _sdl_queue_audio(self._dev, scale_volume(data, self.volume))

    def _start_decoder(self, path: str) -> None:
        """Muss mit _lock aufgerufen werden."""
        self._buf_q   = queue.Queue(maxsize=QUEUE_MAX)
        self._decoder = FFmpegDecoder(path, self._buf_q)
        self._decoder.start()
        sdl2.SDL_PauseAudioDevice(self._dev, 0)
        self.playing = True
        self.paused  = False
        ft = threading.Thread(target=self._feeder, daemon=True, name="feeder")
        self._feeder_thread = ft
        ft.start()

    def _feeder(self) -> None:
        eof = False
        while self.playing and not eof:
            # ── Rate-Limiting ────────────────────────────────────────────
            # SDL-Queue darf hoechstens SDL_TARGET_BUFFER Bytes halten.
            # Ohne diese Bremse pushed der Feeder das komplette Lied in
            # <1 Sekunde nach SDL. Folge: Lautstaerke-Aenderungen wirken
            # erst viele Sekunden spaeter -> "Volume scheint nicht zu gehen".
            # Auch waehrend Pause: Queue wird nicht verbraucht -> wir warten.
            while (self.playing and
                   sdl2.SDL_GetQueuedAudioSize(self._dev) > SDL_TARGET_BUFFER):
                time.sleep(0.02)

            if not self.playing:
                break

            try:
                block = self._buf_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if block is None:
                self.last_error = "ffmpeg konnte Datei nicht dekodieren"
                break
            if block == b"":
                eof = True
                break
            self._push_audio(block)

        # SDL-Puffer ablaufen lassen (nur bei natuerlichem EOF)
        if eof:
            while self.playing and sdl2.SDL_GetQueuedAudioSize(self._dev) > 0:
                time.sleep(self._DRAIN_POLL)

        # WICHTIG: playing-Status VOR cleanup snapshotten fuer Auto-Advance
        should_advance = eof and self.playing and bool(self.playlist)

        self._cleanup()

        # Auto-Advance nur bei natuerlichem EOF UND wenn noch aktiv
        if should_advance:
            try:
                next_pos = (self.pos + 1) % len(self._order)
                self._play_at(next_pos)
            except Exception as e:
                log.error("Auto-Advance fehlgeschlagen: %s", e)

    def _cleanup(self) -> None:
        """Stoppt Decoder und setzt Wiedergabe-State zurueck."""
        with self._lock:
            if self._decoder is not None:
                self._decoder.stop()
                self._decoder = None
            try:
                sdl2.SDL_ClearQueuedAudio(self._dev)
            except Exception:
                pass
            self.playing = False
            self.paused  = True

    def _stop_sync(self) -> None:
        """
        Stoppt laufende Wiedergabe synchron und wartet auf Feeder-Thread.
        Kein sleep-Hack – verwendet Thread.join mit Timeout.
        """
        with self._lock:
            if self._decoder is not None:
                self._decoder.stop()
            ft = self._feeder_thread
            self.playing = False
            self.paused  = True
            sdl2.SDL_PauseAudioDevice(self._dev, 1)
            sdl2.SDL_ClearQueuedAudio(self._dev)

        # Warten bis Feeder-Thread exitiert (nicht selbst joinen!)
        if ft and ft.is_alive() and ft is not threading.current_thread():
            ft.join(timeout=self._JOIN_TIMEOUT)
            if ft.is_alive():
                log.warning("Feeder-Thread nach %.1fs noch aktiv",
                            self._JOIN_TIMEOUT)

    def _play_at(self, order_pos: int) -> None:
        """Spielt Titel an Position order_pos in _order ab."""
        with self._lock:
            if not self.playlist or not self._order:
                return
            order_pos = order_pos % len(self._order)

            # Wenn wir NICHT aus dem Feeder-Thread kommen, Stop-Sync
            in_feeder = threading.current_thread() is self._feeder_thread

        if not in_feeder:
            self._stop_sync()

        with self._lock:
            if not self.playlist:
                return
            self.pos = order_pos % len(self._order)
            track    = self.playlist[self._order[self.pos]]
            if not os.path.isfile(track.path):
                self.last_error = f"Datei nicht gefunden: {track.title}"
                log.warning("Datei fehlt: %s", track.path)
                return
            self.last_error = ""
            self._start_decoder(track.path)

    # ── Playlist-Verwaltung (thread-safe) ─────────────────────────────────

    def add_track(self, path: str) -> bool:
        if not os.path.isfile(path):
            return False
        with self._lock:
            idx = len(self.playlist)
            self.playlist.append(Track(path=path, title=os.path.basename(path)))
            if self._shuffle and self._order:
                ins = random.randint(self.pos + 1, len(self._order))
                self._order.insert(ins, idx)
            else:
                self._order.append(idx)
        return True

    def add_tracks(self, paths: list[str]) -> int:
        return sum(1 for p in paths if self.add_track(p))

    def remove_track(self, order_pos: int) -> None:
        with self._lock:
            if not (0 <= order_pos < len(self._order)):
                return
            pl_idx     = self._order[order_pos]
            is_current = (order_pos == self.pos)

        if is_current and self.playing:
            self._stop_sync()

        with self._lock:
            # Einmaliger Pass: aus _order entfernen + alle >pl_idx dekrementieren
            self._order = [
                i if i < pl_idx else i - 1
                for i in self._order
                if i != pl_idx
            ]
            self.playlist.pop(pl_idx)

            if not self.playlist:
                self.pos = 0
                return
            if order_pos >= len(self._order):
                self.pos = len(self._order) - 1
            elif is_current:
                self.pos = min(order_pos, len(self._order) - 1)
            elif order_pos < self.pos:
                self.pos = max(0, self.pos - 1)

    def move_track(self, order_pos: int, direction: int) -> int:
        with self._lock:
            new_pos = order_pos + direction
            if not (0 <= new_pos < len(self._order)):
                return order_pos
            self._order[order_pos], self._order[new_pos] = (
                self._order[new_pos], self._order[order_pos]
            )
            if self.pos == order_pos:
                self.pos = new_pos
            elif self.pos == new_pos:
                self.pos = order_pos
            return new_pos

    # ── Oeffentliche API ──────────────────────────────────────────────────

    @property
    def current_track(self) -> Optional[Track]:
        with self._lock:
            if not self.playlist or not self._order:
                return None
            return self.playlist[self._order[self.pos]]

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    def play(self) -> None:
        with self._lock:
            if not self.playlist:
                return
            if self.playing and self.paused:
                sdl2.SDL_PauseAudioDevice(self._dev, 0)
                self.paused = False
                return
            if self.playing:
                return
            pos = self.pos
        self._play_at(pos)

    def toggle_pause(self) -> None:
        with self._lock:
            if not self.playing:
                pos = self.pos
                if self.playlist:
                    self._play_at(pos)
                return
            new_state = 0 if self.paused else 1
            sdl2.SDL_PauseAudioDevice(self._dev, new_state)
            self.paused = not self.paused

    def stop(self) -> None:
        self._stop_sync()
        # Alte Fehlermeldungen beim expliziten Stop verwerfen
        with self._lock:
            self.last_error = ""

    def next_track(self) -> None:
        with self._lock:
            if not self.playlist:
                return
            nxt = (self.pos + 1) % len(self._order)
        self._play_at(nxt)

    def prev_track(self) -> None:
        with self._lock:
            if not self.playlist:
                return
            prv = (self.pos - 1) % len(self._order)
        self._play_at(prv)

    def play_at_order(self, order_pos: int) -> None:
        self._play_at(order_pos)

    def set_volume(self, v: float) -> None:
        self.volume = max(0.0, min(1.0, v))

    def toggle_shuffle(self) -> None:
        with self._lock:
            cur_pl = self._order[self.pos] if self._order else 0
            self._shuffle = not self._shuffle
            if self._shuffle:
                random.shuffle(self._order)
                try:
                    new_pos = self._order.index(cur_pl)
                    self._order[new_pos], self._order[self.pos] = (
                        self._order[self.pos], self._order[new_pos]
                    )
                except ValueError:
                    pass
            else:
                self._order = list(range(len(self.playlist)))
                self.pos    = cur_pl

    def close(self) -> None:
        self._stop_sync()
        sdl2.SDL_CloseAudioDevice(self._dev)
        sdl2.SDL_Quit()
        log.debug("AudioPlayer closed")

    # ── Thread-safer Snapshot fuer TUI-Rendering ─────────────────────────

    def snapshot(self) -> "PlayerSnapshot":
        """
        Erzeugt eine atomare Momentaufnahme des Player-Zustands.
        Garantiert Konsistenz zwischen playlist / _order / pos.
        """
        with self._lock:
            order        = tuple(self._order)
            playlist     = tuple(self.playlist)
            pos          = self.pos
            current      = (playlist[order[pos]]
                            if playlist and order and 0 <= pos < len(order)
                            else None)
            return PlayerSnapshot(
                playlist      = playlist,
                order         = order,
                pos           = pos,
                playing       = self.playing,
                paused        = self.paused,
                volume        = self.volume,
                shuffle       = self._shuffle,
                last_error    = self.last_error,
                current_track = current,
            )

    # ── Playlist-Persistenz (M3U-Format) ─────────────────────────────────

    def save_playlist(self, path: str) -> int:
        """Speichert aktuelle Playlist als einfache M3U-Datei. Gibt Anzahl gespeicherter Titel zurueck."""
        with self._lock:
            tracks = list(self.playlist)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for t in tracks:
                    f.write(f"#EXTINF:-1,{t.title}\n{t.path}\n")
            log.info("Playlist gespeichert: %s (%d Titel)", path, len(tracks))
            return len(tracks)
        except OSError as e:
            log.error("save_playlist(%s) fehlgeschlagen: %s", path, e)
            raise

    def load_playlist(self, path: str) -> int:
        """Laedt M3U-Playlist. Gibt Anzahl erfolgreich geladener Titel zurueck."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError as e:
            log.error("load_playlist(%s) fehlgeschlagen: %s", path, e)
            raise

        added = 0
        playlist_dir = os.path.dirname(os.path.abspath(path))
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Relative Pfade relativ zur M3U-Datei aufloesen
            fp = line if os.path.isabs(line) else os.path.join(playlist_dir, line)
            if self.add_track(fp):
                added += 1
        log.info("Playlist geladen: %s (%d Titel)", path, added)
        return added


# ---------------------------------------------------------------------------
# Atomare Momentaufnahme fuer TUI-Rendering
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    playlist:      tuple
    order:         tuple
    pos:           int
    playing:       bool
    paused:        bool
    volume:        float
    shuffle:       bool
    last_error:    str
    current_track: Optional[Track]

    @property
    def n_tracks(self) -> int:
        return len(self.playlist)

    @property
    def n_order(self) -> int:
        return len(self.order)


# ---------------------------------------------------------------------------
# Curses-Farb-Paare
# ---------------------------------------------------------------------------
C_PLAY, C_PAUSE, C_STOP, C_ACCENT, C_SEL, C_NORM, C_HEADER = range(1, 8)

# Orange gibt es in der 8-Farben-Basis-Palette nicht.
# xterm-256color: Farb-Index 208 = Orange (255, 135, 0).
# Fallback auf Gelb bei nur-8-Farben-Terminals.
COLOR_ORANGE_256 = 208


def setup_colors() -> None:
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK

    # Orange-Theme: erfordert 256-Farben-Terminal (Standard bei Alacritty,
    # Konsole, GNOME Terminal, kitty, wezterm etc.). Fallback: Gelb.
    if curses.COLORS >= 256:
        orange = COLOR_ORANGE_256
    else:
        orange = curses.COLOR_YELLOW

    # Semantische Farben bleiben: Play=Gruen, Pause=Gelb, Stop=Rot
    curses.init_pair(C_PLAY,   curses.COLOR_GREEN,  bg)
    curses.init_pair(C_PAUSE,  curses.COLOR_YELLOW, bg)
    curses.init_pair(C_STOP,   curses.COLOR_RED,    bg)
    # UI-Akzent (Borders, Trennlinien, Volume-Bar, Playlist-Header): Orange
    curses.init_pair(C_ACCENT, orange,              bg)
    # Cursor-Auswahl: Schwarz auf Orange
    curses.init_pair(C_SEL,    curses.COLOR_BLACK,  orange)
    curses.init_pair(C_NORM,   curses.COLOR_WHITE,  bg)
    # Titelleiste: Schwarz auf Orange
    curses.init_pair(C_HEADER, curses.COLOR_BLACK,  orange)


def cp(pair: int, *, bold: bool = False, dim: bool = False) -> int:
    # Sicherheitsnetz: Schwarz-auf-Orange (C_HEADER, C_SEL) darf KEIN bold
    # bekommen. Viele Terminals rendern "bold black" als Hellgrau, was auf
    # orange-Hintergrund praktisch unlesbar wird.
    if pair in (C_HEADER, C_SEL):
        bold = False
    attr = curses.color_pair(pair)
    if bold: attr |= curses.A_BOLD
    if dim:  attr |= curses.A_DIM
    return attr


def safe_addstr(win: "curses._CursesWindow",
                y: int, x: int, text: str, attr: int = 0) -> None:
    """Safer addstr: silently ignores curses.error (e.g. bottom-right cell)."""
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


# ---------------------------------------------------------------------------
# Maus-Button-Konstanten (kompatibel ueber curses-Versionen hinweg)
# ---------------------------------------------------------------------------
# BUTTON5_PRESSED (Scroll-Down) fehlt in aelteren ncurses-Bindings.
# In ncurses ist BUTTON5 = 1 << 21 = 0x200000; Fallback fuer Sicherheit.
BTN_SCROLL_UP   = getattr(curses, "BUTTON4_PRESSED", 0x00080000)
BTN_SCROLL_DOWN = getattr(curses, "BUTTON5_PRESSED", 0x00200000)

SCROLL_STEP = 3   # Zeilen pro Scrollrad-Tick


# ---------------------------------------------------------------------------
# Datei-Browser
# ---------------------------------------------------------------------------
class FileBrowser:
    """
    Curses-Popup zum Durchsuchen des Dateisystems und Auswaehlen von
    Audiodateien. Auswahl persistiert ueber Verzeichniswechsel hinweg.

    Tasten:
      Auf/Ab / k/j   : Cursor bewegen
      PgUp/PgDn      : Seiten-Sprung
      Home/End       : Anfang / Ende
      SPACE          : Datei markieren / entmarkieren
      a              : Alle Audiodateien im Verzeichnis waehlen
      A              : Alle Markierungen loeschen
      ENTER          : Verzeichnis oeffnen / Einzeldatei hinzufuegen
      BACKSPACE      : Uebergeordnetes Verzeichnis
      c              : Auswahl bestaetigen und zurueckkehren
      q / ESC        : Abbrechen

    Maus:
      Linksklick     : Cursor setzen
      Doppelklick    : Verzeichnis oeffnen / Datei direkt hinzufuegen
      Rechtsklick    : Datei markieren / entmarkieren
      Scrollrad      : Liste scrollen
    """

    _HEAD = 3
    _FOOT = 4

    def __init__(self, stdscr: "curses._CursesWindow",
                 start_dir: str = ".") -> None:
        self.stdscr = stdscr
        self.cwd    = os.path.abspath(start_dir)
        self.entries: list[tuple[str, bool]] = []
        self.cursor = 0
        self.offset = 0
        self.selected: set[str] = set()
        self._reload()

    def _reload(self) -> None:
        """Laedt Verzeichnisinhalt via os.scandir (schneller als listdir)."""
        entries: list[tuple[str, bool]] = []
        try:
            with os.scandir(self.cwd) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            entries.append((entry.name, True))
                        elif os.path.splitext(entry.name)[1].lower() in AUDIO_EXTS:
                            entries.append((entry.name, False))
                    except OSError:
                        continue
        except (PermissionError, OSError) as e:
            log.warning("scandir(%s) fehlgeschlagen: %s", self.cwd, e)

        entries.sort(key=lambda e: (not e[1], e[0].lower()))  # Dirs zuerst
        self.entries = [("..", True)] + entries
        self.cursor  = 0
        self.offset  = 0

    def run(self) -> list[str]:
        curses.curs_set(0)
        self.stdscr.timeout(-1)        # blockierender getch (kein Auto-Refresh)
        while True:
            h, w = self.stdscr.getmaxyx()
            self._draw(h, w)
            key = self.stdscr.getch()
            result = self._handle(key, h, w)
            if result is not None:
                return result

    def _handle(self, key: int, h: int, w: int) -> Optional[list[str]]:
        list_h = max(1, h - self._HEAD - self._FOOT)
        n      = len(self.entries)

        # Maus-Events
        if key == curses.KEY_MOUSE:
            return self._handle_mouse(h, w)

        if key in (curses.KEY_UP, ord("k")):
            self.cursor = max(0, self.cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.cursor = min(n - 1, self.cursor + 1)
        elif key == curses.KEY_PPAGE:
            self.cursor = max(0, self.cursor - list_h)
        elif key == curses.KEY_NPAGE:
            self.cursor = min(n - 1, self.cursor + list_h)
        elif key == curses.KEY_HOME:
            self.cursor = 0
        elif key == curses.KEY_END:
            self.cursor = n - 1
        elif key == ord(" "):
            if n > 0:
                name, is_dir = self.entries[self.cursor]
                if not is_dir:
                    full = os.path.join(self.cwd, name)
                    if full in self.selected:
                        self.selected.discard(full)
                    else:
                        self.selected.add(full)
        elif key in (10, 13, curses.KEY_ENTER):
            if n > 0:
                name, is_dir = self.entries[self.cursor]
                if is_dir:
                    target = (
                        os.path.dirname(self.cwd) if name == ".."
                        else os.path.join(self.cwd, name)
                    )
                    self.cwd = os.path.abspath(target)
                    self._reload()
                    # Auswahl BEHALTEN ueber Verzeichniswechsel
                else:
                    full = os.path.join(self.cwd, name)
                    self.selected.add(full)
                    return sorted(self.selected)
        elif key == ord("a"):
            for name, is_dir in self.entries:
                if not is_dir:
                    self.selected.add(os.path.join(self.cwd, name))
        elif key == ord("A"):
            self.selected.clear()
        elif key == ord("c"):
            return sorted(self.selected)
        elif key in (27, ord("q")):
            return []
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self.cwd = os.path.dirname(self.cwd)
            self._reload()

        # Scroll-Sync
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + list_h:
            self.offset = self.cursor - list_h + 1
        self.offset = max(0, self.offset)
        return None

    def _handle_mouse(self, h: int, w: int) -> Optional[list[str]]:
        """Maus-Handler des Datei-Browsers."""
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return None

        list_h = max(1, h - self._HEAD - self._FOOT)
        n      = len(self.entries)

        # Scrollrad
        if bstate & BTN_SCROLL_UP:
            self.cursor = max(0, self.cursor - SCROLL_STEP)
            self._sync_scroll(list_h)
            return None
        if bstate & BTN_SCROLL_DOWN:
            self.cursor = min(n - 1, self.cursor + SCROLL_STEP)
            self._sync_scroll(list_h)
            return None

        is_left  = bool(bstate & curses.BUTTON1_CLICKED)
        is_dbl   = bool(bstate & curses.BUTTON1_DOUBLE_CLICKED)
        is_right = bool(bstate & curses.BUTTON3_CLICKED)

        if not (is_left or is_dbl or is_right):
            return None

        # Region: Liste
        list_top = self._HEAD
        list_bot = h - self._FOOT
        if list_top <= my < list_bot:
            idx = (my - list_top) + self.offset
            if not (0 <= idx < n):
                return None

            self.cursor = idx
            name, is_dir = self.entries[idx]

            # Doppelklick
            if is_dbl:
                if is_dir:
                    target = (os.path.dirname(self.cwd) if name == ".."
                              else os.path.join(self.cwd, name))
                    self.cwd = os.path.abspath(target)
                    self._reload()
                else:
                    full = os.path.join(self.cwd, name)
                    self.selected.add(full)
                    return sorted(self.selected)
                return None

            # Rechtsklick auf Datei: markieren/entmarkieren
            if is_right and not is_dir:
                full = os.path.join(self.cwd, name)
                if full in self.selected:
                    self.selected.discard(full)
                else:
                    self.selected.add(full)
            self._sync_scroll(list_h)
        return None

    def _sync_scroll(self, list_h: int) -> None:
        """Passt offset an, sodass cursor sichtbar bleibt."""
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + list_h:
            self.offset = self.cursor - list_h + 1
        self.offset = max(0, self.offset)

    def _draw(self, h: int, w: int) -> None:
        s      = self.stdscr
        list_h = max(1, h - self._HEAD - self._FOOT)
        s.erase()

        try: s.border()
        except curses.error: pass

        # Titel
        title = " Datei hinzufuegen "
        safe_addstr(s, 0, max(1, (w - len(title)) // 2),
                    title[:w - 2], cp(C_HEADER))

        # Aktueller Pfad
        path_disp = self.cwd
        if len(path_disp) > w - 4:
            path_disp = "..." + path_disp[-(w - 7):]
        safe_addstr(s, 1, 2, f"{path_disp}/"[:w - 3], cp(C_ACCENT))
        safe_addstr(s, 2, 1, "-" * (w - 2), cp(C_ACCENT))

        # Eintraege
        for row in range(list_h):
            idx = self.offset + row
            y   = self._HEAD + row
            if idx >= len(self.entries):
                break
            name, is_dir = self.entries[idx]
            full         = os.path.join(self.cwd, name)
            is_sel       = full in self.selected
            is_cur       = idx == self.cursor

            icon  = "[D]" if is_dir else "[A]"
            check = " [*]" if is_sel else "    "
            label = f" {icon}  {name}{check}"[:w - 3].ljust(w - 2)

            if is_cur:     attr = cp(C_SEL)
            elif is_sel:   attr = cp(C_PLAY, bold=True)
            elif is_dir:   attr = cp(C_ACCENT)
            else:          attr = cp(C_NORM)

            safe_addstr(s, y, 1, label, attr)

        # Footer
        sep_y = h - self._FOOT
        safe_addstr(s, sep_y, 1, "-" * (w - 2), cp(C_ACCENT))
        safe_addstr(s, sep_y + 1, 1,
                    " [Auf/Ab] Navigieren  [SPC] Auswaehlen  [a] Alle  [A] Auswahl loeschen"[:w - 2],
                    cp(C_NORM, dim=True))
        safe_addstr(s, sep_y + 2, 1,
                    " [ENTER] Oeffnen/Hinzufuegen  [c] Bestaetigen  [BKSP] Zurueck  [q/ESC] Abbr."[:w - 2],
                    cp(C_NORM, dim=True))

        sel_label = f" {len(self.selected)} ausgewaehlt "
        safe_addstr(s, h - 1, max(1, (w - len(sel_label)) // 2),
                    sel_label[:w - 2], cp(C_PLAY, bold=True))
        try: s.refresh()
        except curses.error: pass


# ---------------------------------------------------------------------------
# Haupt-TUI
# ---------------------------------------------------------------------------
class TUI:
    """
    Interaktives Curses-Terminal-Interface.

    Layout:
      Zeile 0        : Titelleiste
      Zeile 1        : Now-Playing (Status + Titel + Position)
      Zeile 2        : Lautstaerke-Bar + Shuffle-Indikator
      Zeile 3        : Trennlinie / Playlist-Header
      Zeile 4..h-5   : Playlist (scrollbar)
      Zeile h-4      : Trennlinie
      Zeile h-3..h-2 : Tastenbelegung (2 Zeilen)
      Zeile h-1      : Status / Benachrichtigung
    """

    _HEAD     = 4
    _FOOT     = 4
    _TIMEOUT  = 150            # ms: Refresh-Intervall
    _NOTIFY_S = 2.5            # Sekunden bis Notification verschwindet
    _MOUSE_INTERVAL = 300      # ms: Zeitfenster fuer Doppelklick

    def __init__(self, stdscr: "curses._CursesWindow",
                 player: AudioPlayer) -> None:
        self.stdscr = stdscr
        self.player = player
        self.cursor = 0
        self.offset = 0
        self._notify    = ""
        self._notify_ts = 0.0
        self._running   = True
        self._mouse_enabled = False

        setup_colors()
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.timeout(self._TIMEOUT)
        self._setup_mouse()

    def _setup_mouse(self) -> None:
        """Aktiviert Maus-Events. Terminal muss Maus-Reporting unterstuetzen."""
        try:
            avail, _ = curses.mousemask(curses.ALL_MOUSE_EVENTS)
            if avail:
                curses.mouseinterval(self._MOUSE_INTERVAL)
                # XTerm SGR-Mouse-Mode fuer breite Terminals (> 223 Spalten).
                # Ohne das wird der Maus-Support bei grossen Terminals abgeschnitten.
                try:
                    sys.stdout.write("\033[?1006h")
                    sys.stdout.flush()
                except Exception:
                    pass
                self._mouse_enabled = True
                log.debug("Maus-Support aktiviert")
        except Exception as e:
            log.debug("Maus-Support nicht verfuegbar: %s", e)

    def notify(self, msg: str, duration: Optional[float] = None) -> None:
        self._notify    = msg
        self._notify_ts = time.monotonic() + (duration or self._NOTIFY_S)

    # ── Haupt-Loop ───────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            while self._running:
                self._draw()
                try:
                    key = self.stdscr.getch()
                except KeyboardInterrupt:
                    break
                if key != -1:
                    self._handle_key(key)
        finally:
            # SGR-Mouse-Mode deaktivieren - sonst bleiben Escape-Codes
            # im Terminal, die sich als komische Zeichen aeussern koennen.
            if self._mouse_enabled:
                try:
                    sys.stdout.write("\033[?1006l")
                    sys.stdout.flush()
                except Exception:
                    pass

    # ── Zeichnen ─────────────────────────────────────────────────────────

    def _draw(self) -> None:
        try:
            self._render()
        except curses.error as e:
            log.debug("Render-Fehler (Terminal zu klein?): %s", e)

    def _render(self) -> None:
        s    = self.stdscr
        h, w = s.getmaxyx()
        # Atomare Momentaufnahme -> keine Race-Conditions waehrend des Zeichnens
        snap = self.player.snapshot()
        s.erase()

        if h < 10 or w < 40:
            safe_addstr(s, 0, 0, "Terminal zu klein! Bitte vergroessern.",
                        cp(C_STOP, bold=True))
            s.refresh()
            return

        self._render_header(s, w)
        self._render_now_playing(s, w, snap)
        self._render_volume_shuffle(s, w, snap)
        self._render_playlist_section(s, h, w, snap)
        self._render_footer(s, h, w, snap)

        s.refresh()

    def _render_header(self, s, w: int) -> None:
        title = "  CLI Audio Player  "
        safe_addstr(s, 0, 0, title.center(w - 1)[:w - 1],
                    cp(C_HEADER))

    def _render_now_playing(self, s, w: int, snap: PlayerSnapshot) -> None:
        track = snap.current_track
        if track is None:
            safe_addstr(s, 1, 0, " STOP  ", cp(C_STOP, bold=True))
            safe_addstr(s, 1, 8,
                        " Playlist leer -- [a] Dateien hinzufuegen",
                        cp(C_NORM, dim=True))
            return

        if snap.playing and not snap.paused:
            state_str, state_attr = " PLAY  ", cp(C_PLAY, bold=True)
        elif snap.playing and snap.paused:
            state_str, state_attr = " PAUSE ", cp(C_PAUSE, bold=True)
        else:
            state_str, state_attr = " STOP  ", cp(C_STOP, bold=True)

        order_len = max(1, snap.n_order)
        pos_str   = f" [{snap.pos + 1}/{order_len}] "
        max_title = max(1, w - len(state_str) - len(pos_str) - 2)
        t_disp    = track.title
        if len(t_disp) > max_title:
            t_disp = t_disp[:max_title - 3] + "..."

        safe_addstr(s, 1, 0, state_str, state_attr)
        safe_addstr(s, 1, len(state_str), f" {t_disp}",
                    cp(C_NORM, bold=True))
        safe_addstr(s, 1, w - len(pos_str) - 1, pos_str, cp(C_ACCENT))

    def _render_volume_shuffle(self, s, w: int, snap: PlayerSnapshot) -> None:
        vol_n   = int(snap.volume * 16)
        vol_bar = "=" * vol_n + "-" * (16 - vol_n)
        vol_str = f" Vol |{vol_bar}| {int(snap.volume * 100):3d}%"
        shuf_str = " [SHUFFLE: AN ] " if snap.shuffle else " [SHUFFLE: AUS] "

        safe_addstr(s, 2, 0, vol_str[:w // 2], cp(C_ACCENT))
        attr = cp(C_PLAY, bold=True) if snap.shuffle else cp(C_NORM, dim=True)
        safe_addstr(s, 2, w // 2, shuf_str[:w - w // 2 - 1], attr)

    def _render_playlist_section(self, s, h: int, w: int,
                                 snap: PlayerSnapshot) -> None:
        safe_addstr(s, 3, 0, "-" * (w - 1), cp(C_ACCENT))
        pl_hdr = f" Playlist  {snap.n_tracks} Titel "
        safe_addstr(s, 3, 2, pl_hdr[:w - 4], cp(C_ACCENT, bold=True))

        list_h = max(1, h - self._HEAD - self._FOOT)
        self._sync_cursor(list_h, snap.n_order)

        for row in range(list_h):
            idx = self.offset + row
            y   = self._HEAD + row
            if idx >= snap.n_order:
                safe_addstr(s, y, 0, " " * (w - 1))
                continue

            pl_idx    = snap.order[idx]
            tr        = snap.playlist[pl_idx]
            is_cursor = idx == self.cursor
            is_active = idx == snap.pos and (snap.playing or snap.paused)

            num_str  = f"{idx + 1:>3}."
            play_ind = " >> " if is_active else "    "
            label    = f"{play_ind}{num_str} {tr.title}"[:w - 2].ljust(w - 1)

            if is_cursor and is_active:
                # Cursor auf gerade spielendem Titel: schwarz auf orange,
                # Unterstrich zur Abgrenzung vom normalen Cursor (kein bold
                # -> bold+schwarz wuerde auf vielen Terminals grau werden)
                attr = cp(C_SEL) | curses.A_UNDERLINE
            elif is_cursor:
                attr = cp(C_SEL)
            elif is_active:
                attr = cp(C_PLAY, bold=True)
            else:
                attr = cp(C_NORM)

            safe_addstr(s, y, 0, label, attr)

    def _render_footer(self, s, h: int, w: int, snap: PlayerSnapshot) -> None:
        sep_y = h - self._FOOT
        safe_addstr(s, sep_y, 0, "-" * (w - 1), cp(C_ACCENT))

        keys1 = (" [SPC] Play/Pause  [s] Stop  [n] Naechster  [b] Vorheriger"
                 "  [ENTER] Abspielen")
        keys2 = (" [+/-] Vol  [r] Shuffle  [a] Add  [d/DEL] Entf  [M/m] Move"
                 "  [S/L] Save/Load  [h] Hilfe  [q] Beenden")
        safe_addstr(s, sep_y + 1, 0, keys1[:w - 1], cp(C_NORM, dim=True))
        safe_addstr(s, sep_y + 2, 0, keys2[:w - 1], cp(C_NORM, dim=True))

        status_y = h - 1
        if snap.last_error:
            safe_addstr(s, status_y, 0, f" ! {snap.last_error}"[:w - 1],
                        cp(C_STOP, bold=True))
        elif self._notify and time.monotonic() < self._notify_ts:
            safe_addstr(s, status_y, 0, f" >> {self._notify}"[:w - 1],
                        cp(C_PAUSE, bold=True))

    def _sync_cursor(self, list_h: int, n: int) -> None:
        if n == 0:
            self.cursor = 0
            self.offset = 0
            return
        self.cursor = max(0, min(self.cursor, n - 1))
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + list_h:
            self.offset = self.cursor - list_h + 1
        self.offset = max(0, self.offset)

    # ── Tastatur-Handler ─────────────────────────────────────────────────

    def _handle_key(self, key: int) -> None:
        p = self.player
        n = len(p._order)

        # Terminal-Resize: Screen leeren, damit alte Artefakte verschwinden
        if key == curses.KEY_RESIZE:
            self.stdscr.clear()
            return

        # Maus-Events
        if key == curses.KEY_MOUSE:
            self._handle_mouse()
            return

        # Navigation
        if key in (curses.KEY_UP, ord("k")):
            self.cursor = max(0, self.cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.cursor = min(max(0, n - 1), self.cursor + 1)
        elif key == curses.KEY_PPAGE:
            self.cursor = max(0, self.cursor - 10)
        elif key == curses.KEY_NPAGE:
            self.cursor = min(max(0, n - 1), self.cursor + 10)
        elif key == curses.KEY_HOME:
            self.cursor = 0
        elif key == curses.KEY_END:
            self.cursor = max(0, n - 1)

        # Wiedergabe
        elif key == ord(" "):
            p.toggle_pause()
        elif key in (10, 13, curses.KEY_ENTER):
            if p.playlist and 0 <= self.cursor < n:
                p.play_at_order(self.cursor)
        elif key == ord("s"):
            p.stop()
        elif key == ord("n"):
            p.next_track()
        elif key == ord("b"):
            p.prev_track()

        # Lautstaerke
        elif key in (ord("+"), ord("=")):
            p.set_volume(p.volume + 0.05)
            self.notify(f"Lautstaerke: {int(p.volume * 100)}%")
        elif key == ord("-"):
            p.set_volume(p.volume - 0.05)
            self.notify(f"Lautstaerke: {int(p.volume * 100)}%")

        # Shuffle
        elif key == ord("r"):
            p.toggle_shuffle()
            self.notify("Shuffle: AN" if p.shuffle else "Shuffle: AUS")

        # Playlist
        elif key == ord("a"):
            self._open_file_browser()
        elif key in (ord("d"), curses.KEY_DC):
            if p.playlist and n > 0:
                p.remove_track(self.cursor)
                self.cursor = min(self.cursor, max(0, len(p._order) - 1))
                self.notify("Titel entfernt")
        elif key == ord("M"):
            if p.playlist and n > 0:
                self.cursor = p.move_track(self.cursor, -1)
        elif key == ord("m"):
            if p.playlist and n > 0:
                self.cursor = p.move_track(self.cursor, +1)

        # Save / Load
        elif key == ord("S"):
            self._save_playlist()
        elif key == ord("L"):
            self._load_playlist()

        # Hilfe
        elif key == ord("h"):
            self._show_help()

        # Beenden
        elif key in (ord("q"), 27):
            self._running = False

    # ── Maus-Handler ─────────────────────────────────────────────────────

    def _handle_mouse(self) -> None:
        """Verarbeitet Maus-Events. Klick/Doppelklick/Rechtsklick + Scrollrad."""
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return

        h, w = self.stdscr.getmaxyx()
        p    = self.player
        n    = len(p._order)

        # Scrollrad: Cursor bewegen
        if bstate & BTN_SCROLL_UP:
            self.cursor = max(0, self.cursor - SCROLL_STEP)
            return
        if bstate & BTN_SCROLL_DOWN:
            self.cursor = min(max(0, n - 1), self.cursor + SCROLL_STEP)
            return

        is_left  = bool(bstate & curses.BUTTON1_CLICKED)
        is_dbl   = bool(bstate & curses.BUTTON1_DOUBLE_CLICKED)
        is_right = bool(bstate & curses.BUTTON3_CLICKED)

        if not (is_left or is_dbl or is_right):
            return

        # ── Region: Titelleiste (y=0) -> Hilfe ──────────────────────────
        if my == 0:
            if is_left or is_dbl:
                self._show_help()
            return

        # ── Region: Now Playing (y=1) -> Play/Pause ─────────────────────
        if my == 1:
            if is_left or is_dbl:
                p.toggle_pause()
            return

        # ── Region: Volume + Shuffle (y=2) ──────────────────────────────
        if my == 2:
            # Volume-Bar: " Vol |XXXXXXXXXXXXXXXX|" (16 Zeichen bei x=6..21)
            if 6 <= mx < 22:
                new_vol = (mx - 6) / 15.0  # 0..15 -> 0.0..1.0
                p.set_volume(new_vol)
                self.notify(f"Lautstaerke: {int(p.volume * 100)}%")
                return
            # Shuffle-Label in rechter Haelfte
            if mx >= w // 2:
                p.toggle_shuffle()
                self.notify("Shuffle: AN" if p.shuffle else "Shuffle: AUS")
                return
            return

        # ── Region: Playlist (y in [_HEAD, h-_FOOT)) ────────────────────
        list_top = self._HEAD
        list_bot = h - self._FOOT
        if list_top <= my < list_bot:
            idx = (my - list_top) + self.offset
            if 0 <= idx < n:
                self.cursor = idx
                if is_dbl:
                    p.play_at_order(idx)
                elif is_right:
                    p.remove_track(idx)
                    self.cursor = min(self.cursor, max(0, len(p._order) - 1))
                    self.notify("Titel entfernt")
            return

        # ── Region: Footer-Keybindings -> Hilfe ─────────────────────────
        if h - self._FOOT < my < h - 1 and (is_left or is_dbl):
            self._show_help()
            return

    # ── Datei-Browser ────────────────────────────────────────────────────

    def _open_file_browser(self) -> None:
        start   = os.path.expanduser("~")
        browser = FileBrowser(self.stdscr, start_dir=start)
        try:
            paths = browser.run()
        except Exception as e:
            log.error("FileBrowser-Fehler: %s", e)
            self.notify("Browser-Fehler")
            paths = []

        # Curses-State wiederherstellen
        curses.curs_set(0)
        self.stdscr.timeout(self._TIMEOUT)
        self.stdscr.keypad(True)

        if paths:
            added = self.player.add_tracks(paths)
            self.notify(f"{added} Titel hinzugefuegt"
                        if added else "Keine gueltigen Dateien")

    # ── Playlist-Persistenz (M3U) ────────────────────────────────────────

    _DEFAULT_PLAYLIST = Path(
        os.environ.get("XDG_STATE_HOME",
                       os.path.expanduser("~/.local/state"))
    ) / "audioplayer" / "playlist.m3u"

    def _save_playlist(self) -> None:
        if not self.player.playlist:
            self.notify("Playlist ist leer")
            return
        try:
            self._DEFAULT_PLAYLIST.parent.mkdir(parents=True, exist_ok=True)
            n = self.player.save_playlist(str(self._DEFAULT_PLAYLIST))
            self.notify(f"{n} Titel gespeichert -> {self._DEFAULT_PLAYLIST.name}")
        except OSError as e:
            self.notify(f"Speichern fehlgeschlagen: {e}")

    def _load_playlist(self) -> None:
        if not self._DEFAULT_PLAYLIST.is_file():
            self.notify("Keine gespeicherte Playlist gefunden")
            return
        try:
            n = self.player.load_playlist(str(self._DEFAULT_PLAYLIST))
            self.notify(f"{n} Titel geladen" if n else "Playlist war leer")
        except OSError as e:
            self.notify(f"Laden fehlgeschlagen: {e}")

    # ── Hilfe-Popup ──────────────────────────────────────────────────────

    def _show_help(self) -> None:
        rows: list[tuple[str, str]] = [
            ("WIEDERGABE",    ""),
            ("  SPACE",       "Play / Pause umschalten"),
            ("  ENTER",       "Markierten Titel abspielen"),
            ("  s",           "Stop"),
            ("  n / b",       "Naechster / Vorheriger Titel"),
            ("",              ""),
            ("LAUTSTAERKE",   ""),
            ("  + / =",       "Lauter (+5%)"),
            ("  -",           "Leiser (-5%)"),
            ("",              ""),
            ("PLAYLIST",      ""),
            ("  a",           "Datei-Browser oeffnen"),
            ("  d / DEL",     "Markierten Titel entfernen"),
            ("  M / m",       "Titel nach oben / unten verschieben"),
            ("  r",           "Shuffle ein-/ausschalten"),
            ("  S",           "Playlist speichern (M3U)"),
            ("  L",           "Playlist laden (M3U)"),
            ("",              ""),
            ("NAVIGATION",    ""),
            ("  Auf / Ab",    "(alt.: k / j)"),
            ("  PgUp / PgDn", "10 Zeilen springen"),
            ("  Home / End",  "Anfang / Ende"),
            ("",              ""),
            ("MAUS",          ""),
            ("  Titel",       "Hilfe oeffnen"),
            ("  Now Playing", "Play / Pause"),
            ("  Volume-Bar",  "Lautstaerke direkt setzen"),
            ("  Shuffle-Lbl", "Shuffle umschalten"),
            ("  Playlist LM", "Cursor setzen"),
            ("  Playlist LM2","Titel abspielen (Doppelklick)"),
            ("  Playlist RM", "Titel entfernen"),
            ("  Scrollrad",   "Liste scrollen"),
            ("",              ""),
            ("  h",           "Diese Hilfe"),
            ("  q / ESC",     "Programm beenden"),
        ]

        h, w  = self.stdscr.getmaxyx()
        pop_h = min(len(rows) + 4, h - 2)
        pop_w = min(54, w - 4)
        if pop_h < 6 or pop_w < 30:
            self.notify("Terminal zu klein fuer Hilfe")
            return

        sy, sx = (h - pop_h) // 2, (w - pop_w) // 2
        win = curses.newwin(pop_h, pop_w, sy, sx)
        win.keypad(True)
        win.attron(cp(C_ACCENT))
        try: win.border()
        except curses.error: pass
        win.attroff(cp(C_ACCENT))

        title = " Tastenbelegung "
        safe_addstr(win, 0, max(1, (pop_w - len(title)) // 2),
                    title[:pop_w - 2], cp(C_HEADER))

        content_h = pop_h - 2
        for i, (klabel, desc) in enumerate(rows[:content_h]):
            y = i + 1
            if klabel and not desc:
                safe_addstr(win, y, 1, klabel[:pop_w - 2],
                            cp(C_ACCENT, bold=True))
            elif klabel:
                safe_addstr(win, y, 1, f"{klabel:<14}"[:15],
                            cp(C_PAUSE, bold=True))
                safe_addstr(win, y, 16, desc[:pop_w - 18], cp(C_NORM))

        footer = " [Beliebige Taste] Schliessen "
        safe_addstr(win, pop_h - 1,
                    max(1, (pop_w - len(footer)) // 2),
                    footer[:pop_w - 2], cp(C_SEL))
        win.refresh()
        win.getch()


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------
def _tui_main(stdscr: "curses._CursesWindow", player: AudioPlayer) -> None:
    TUI(stdscr, player).run()


def main() -> int:
    _setup_signal_handlers()

    # SDL VOR curses initialisieren – bei Fehler bleibt Terminal intakt
    try:
        player = AudioPlayer()
    except RuntimeError as e:
        sys.stderr.write(f"x Fehler: {e}\n")
        return 1

    exit_code = 0
    try:
        curses.wrapper(_tui_main, player)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.exception("Unbehandelte Ausnahme im TUI")
        sys.stderr.write(f"x Fehler: {e}\n")
        exit_code = 1
    finally:
        try:
            player.close()
        except Exception as e:
            log.error("player.close fehlgeschlagen: %s", e)

    print("Tschuess!")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
