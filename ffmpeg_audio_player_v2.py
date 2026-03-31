#!/usr/bin/env python3
"""
Simple Terminal Audio Player
ffmpeg -> PipeWire (pw-play) oder aplay
Unterstützte Formate: mp3, aac, m4a, opus, flac, wav, ogg
Python 3.10+

Features:
  - Lautstärkeregelung  (0–200 %, ffmpeg volume-Filter)
  - Audio-Normalisierung (ffmpeg loudnorm EBU R128, Single-Pass)
  - Shuffle-Modus & Playlist-Mischen
  - Rekursives Ordner-Hinzufügen
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import random
from pathlib import Path

# ── Farben ────────────────────────────────────────────────────────────────────
ORANGE = "\033[38;5;214m"
GREEN  = "\033[38;5;82m"
RED    = "\033[38;5;196m"
CYAN   = "\033[38;5;51m"
GRAY   = "\033[38;5;245m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

SUPPORTED_EXT: frozenset[str] = frozenset(
    {".mp3", ".aac", ".m4a", ".opus", ".flac", ".wav", ".ogg"}
)

VOL_MIN =   0
VOL_MAX = 200
VOL_DEF = 100  # 100 % = keine Änderung


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def normalize_path(s: str) -> Path:
    """Bereinigt Pfad-Eingaben (Anführungszeichen, ~, …)."""
    s = s.strip()
    if len(s) >= 2 and s[0] in ('"', "'") and s[0] == s[-1]:
        s = s[1:-1]
    p = Path(os.path.expanduser(s))
    try:
        if p.exists():
            p = p.resolve()
    except OSError:
        pass
    return p


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def input_or_quit(prompt: str) -> str:
    """Liest Eingabe; beendet das Programm bei Ctrl-C / EOF."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def fmt_index(i: int, total: int) -> str:
    """Rechtsbündige Indexdarstellung mit einheitlicher Breite."""
    return f"{i:>{len(str(total))}}"


def truncate(s: str, max_len: int = 60) -> str:
    """Kürzt einen String mit '…' in der Mitte."""
    if len(s) <= max_len:
        return s
    half_l = (max_len - 1) // 2
    half_r = max_len - 1 - half_l
    return s[:half_l] + "…" + s[len(s) - half_r:]


def _print_result(ok: bool, msg: str) -> None:
    """Gibt ein farbiges ✓/✗ mit Nachricht aus."""
    symbol = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
    print(f"  {symbol}  {ORANGE}{msg}{RESET}")


# ── AudioPlayer ───────────────────────────────────────────────────────────────

class AudioPlayer:
    def __init__(self) -> None:
        self.playlist:        list[Path]             = []
        self._current_idx:    int                    = 0
        self._current_path:   Path | None            = None

        # Wiedergabe-Optionen
        self._volume:         int                    = VOL_DEF
        self._normalize:      bool                   = False
        self._shuffle:        bool                   = False
        self._shuffle_order:  list[int]              = []

        # Prozess-Verwaltung
        self._proc_lock  = threading.Lock()
        self._ff_proc:   subprocess.Popen | None     = None
        self._con_proc:  subprocess.Popen | None     = None

        # Steuer-Events & Thread
        self._stop_event  = threading.Event()
        self._skip_event  = threading.Event()
        self._play_thread: threading.Thread | None   = None

        # Audio-Backend ermitteln
        self._pw_play = shutil.which("pw-play")
        self._aplay   = shutil.which("aplay")
        if not self._pw_play and not self._aplay:
            print(
                f"{ORANGE}Warnung: 'pw-play' und 'aplay' nicht gefunden. "
                f"Kein Audioausgabegerät verfügbar.{RESET}"
            )

    # ── Playlist-Verwaltung ──────────────────────────────────────────────────

    def add_file(self, path_str: str, front: bool = False) -> tuple[bool, str]:
        p = normalize_path(path_str)
        if not p.exists():
            return False, f"Nicht gefunden: {p}"
        if not p.is_file():
            return False, "Keine reguläre Datei"
        if p.suffix.lower() not in SUPPORTED_EXT:
            return False, f"Format nicht unterstützt ({p.suffix})"
        if p in self.playlist:
            return False, "Bereits in Playlist"
        if front:
            self.playlist.insert(0, p)
            if self.is_playing():
                self._current_idx += 1
            return True, f"Hinzugefügt (vorne): {p.name}"
        self.playlist.append(p)
        return True, f"Hinzugefügt (hinten): {p.name}"

    def add_folder(
        self, path_str: str, recursive: bool = False
    ) -> tuple[bool, str]:
        p = normalize_path(path_str)
        if not p.exists() or not p.is_dir():
            return False, "Kein gültiger Ordner"
        pattern = "**/*" if recursive else "*"
        files = sorted(
            f for f in p.glob(pattern)
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
        )
        if not files:
            return False, "Keine unterstützten Dateien gefunden"
        added = 0
        for f in files:
            if f not in self.playlist:
                self.playlist.append(f)
                added += 1
        return True, f"{added} Datei(en) hinzugefügt aus: {p.name}"

    def remove_track(self, idx: int) -> tuple[bool, str]:
        if not (0 <= idx < len(self.playlist)):
            return False, "Ungültiger Index"
        name = self.playlist[idx].name
        if idx == self._current_idx and self.is_playing():
            self._skip_event.set()
            self._kill_current()
        self.playlist.pop(idx)
        if self._current_idx >= len(self.playlist):
            self._current_idx = max(0, len(self.playlist) - 1)
        elif idx < self._current_idx:
            self._current_idx -= 1
        self._shuffle_order = []
        return True, f"Entfernt: {name}"

    def move_track(self, from_idx: int, to_idx: int) -> tuple[bool, str]:
        n = len(self.playlist)
        if not (0 <= from_idx < n and 0 <= to_idx < n):
            return False, "Ungültiger Index"
        track = self.playlist.pop(from_idx)
        self.playlist.insert(to_idx, track)
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
        self._current_idx   = 0
        self._current_path  = None
        self._shuffle_order = []

    def list_playlist(self) -> list[str]:
        return [str(p) for p in self.playlist]

    # ── Lautstärke & Normalisierung ──────────────────────────────────────────

    def set_volume(self, vol: int) -> tuple[bool, str]:
        """Setzt die Lautstärke (0–200 %)."""
        if not (VOL_MIN <= vol <= VOL_MAX):
            return False, f"Ungültiger Wert (erlaubt: {VOL_MIN}–{VOL_MAX})"
        self._volume = vol
        return True, f"Lautstärke: {vol} %"

    def toggle_normalize(self) -> str:
        """Schaltet EBU-R128-Normalisierung (loudnorm) ein/aus."""
        self._normalize = not self._normalize
        return f"Normalisierung: {'AN' if self._normalize else 'AUS'}"

    # ── Status ───────────────────────────────────────────────────────────────

    def is_playing(self) -> bool:
        return bool(self._play_thread and self._play_thread.is_alive())

    def status_line(self) -> str:
        count    = len(self.playlist)
        vol_str  = f" {CYAN}[VOL {self._volume}%]{RESET}"
        norm_str = f" {CYAN}[NORM]{RESET}" if self._normalize else ""
        shuf_str = f" {CYAN}[SHUFFLE]{RESET}" if self._shuffle else ""
        extras   = vol_str + norm_str + shuf_str

        if self.is_playing() and self._current_path:
            name = truncate(self._current_path.name, 40)
            idx  = self._current_idx + 1
            return (
                f"{GREEN}▶ {BOLD}{name}{RESET}"
                f"{GRAY} [{idx}/{count}]{RESET}{extras}"
            )
        return f"{GRAY}⏹  Gestoppt  [{count} Track(s)]{RESET}{extras}"

    # ── ffmpeg-Kommando ──────────────────────────────────────────────────────

    def _build_af_chain(self) -> str | None:
        """
        Baut die ffmpeg -af Filter-Chain.
        Reihenfolge: loudnorm → volume
        """
        filters: list[str] = []
        if self._normalize:
            filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        if self._volume != VOL_DEF:
            factor = self._volume / 100.0
            filters.append(f"volume={factor:.4f}")
        return ",".join(filters) if filters else None

    def _ffmpeg_cmd(self, path: Path) -> list[str]:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-nostdin", "-re",
            "-i", str(path),
        ]
        af = self._build_af_chain()
        if af:
            cmd += ["-af", af]
        cmd += ["-f", "wav", "-ar", "48000", "-ac", "2", "pipe:1"]
        return cmd

    # ── Prozess-Steuerung ────────────────────────────────────────────────────

    def _kill_current(self) -> None:
        """Beendet laufende ffmpeg- und Consumer-Prozesse."""
        with self._proc_lock:
            ff  = self._ff_proc
            con = self._con_proc
            self._ff_proc  = None
            self._con_proc = None
        for proc in (con, ff):
            if proc is None:
                continue
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.kill()
            except OSError:
                pass

    def _run_track(self, path: Path) -> None:
        """Startet ffmpeg + Consumer-Prozess für einen einzelnen Track."""
        try:
            ff = subprocess.Popen(
                self._ffmpeg_cmd(path),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print(f"{ORANGE}ffmpeg nicht gefunden.{RESET}")
            return
        except OSError as e:
            print(f"{ORANGE}ffmpeg Fehler: {e}{RESET}")
            return

        consumer: subprocess.Popen | None = None
        consumer_cmd: list[str] = []

        if self._pw_play:
            consumer_cmd = [self._pw_play, "--format=wav", "-"]
        elif self._aplay:
            consumer_cmd = [self._aplay, "-q", "-"]

        try:
            if consumer_cmd:
                consumer = subprocess.Popen(
                    consumer_cmd,
                    stdin=ff.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if ff.stdout:
                    ff.stdout.close()

            with self._proc_lock:
                self._ff_proc  = ff
                self._con_proc = consumer

            target = consumer if consumer else ff
            while True:
                try:
                    target.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if self._stop_event.is_set() or self._skip_event.is_set():
                    break

        finally:
            self._kill_current()

    # ── Wiedergabe-Schleife ──────────────────────────────────────────────────

    def _next_index(self, current: int) -> int | None:
        n = len(self.playlist)
        if n == 0:
            return None
        if self._shuffle:
            if not self._shuffle_order:
                self._rebuild_shuffle_order()
            try:
                pos = self._shuffle_order.index(current)
            except ValueError:
                return self._shuffle_order[0] if self._shuffle_order else None
            return self._shuffle_order[(pos + 1) % len(self._shuffle_order)]
        nxt = current + 1
        return nxt if nxt < n else None

    def _playback_loop(self) -> None:
        idx: int | None = self._current_idx
        if self._shuffle:
            self._rebuild_shuffle_order()

        while True:
            if self._stop_event.is_set():
                break
            if idx is None or idx >= len(self.playlist):
                break

            path = self.playlist[idx]
            self._current_idx  = idx
            self._current_path = path

            if path.exists():
                self._run_track(path)
            else:
                print(f"{ORANGE}Datei nicht mehr vorhanden: {path}{RESET}")

            if self._stop_event.is_set():
                break

            self._skip_event.clear()
            idx = self._next_index(idx)

        # Aufräumen
        self._stop_event.clear()
        self._skip_event.clear()
        with self._proc_lock:
            self._ff_proc  = None
            self._con_proc = None
        self._current_path = None
        self._play_thread  = None

    # ── Öffentliche Steuerung ────────────────────────────────────────────────

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
        self._play_thread = threading.Thread(
            target=self._playback_loop, daemon=True
        )
        self._play_thread.start()
        return True, f"Wiedergabe: {truncate(self.playlist[from_idx].name, 50)}"

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

    def jump_to(self, idx: int) -> tuple[bool, str]:
        if not (0 <= idx < len(self.playlist)):
            return False, f"Index {idx} ungültig (0–{len(self.playlist) - 1})"
        return self.play(from_idx=idx)


# ── Menü-Helfer ───────────────────────────────────────────────────────────────

def print_header(player: AudioPlayer) -> None:
    bar = "─" * 58
    print(f"{ORANGE}{BOLD}{bar}{RESET}")
    print(f"{ORANGE}{BOLD}  Simple Audio Player  │  ffmpeg → PipeWire / aplay{RESET}")
    print(f"{ORANGE}{BOLD}{bar}{RESET}")
    print(f"  {player.status_line()}")
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
        ("s", "⏭  Skip"),
        ("x", "⏹  Stop"),
        ("",  ""),
        ("v", "🔊  Lautstärke setzen  (0–200 %)"),
        ("n", "⚡  Normalisierung  (loudnorm EBU R128)"),
        ("",  ""),
        ("z", "🔀  Shuffle (Playlist mischen)"),
        ("t", "🔁  Shuffle-Modus umschalten"),
        ("c", "🗑   Playlist leeren"),
        ("",  ""),
        ("0", "Beenden"),
    ]
    for key, label in entries:
        if key == "":
            print(f"{GRAY}  {'·' * 44}{RESET}")
        else:
            print(f"  {ORANGE}{BOLD}{key:>2}{RESET}  {label}")
    print(f"{ORANGE}{'─' * 58}{RESET}")


def show_playlist(player: AudioPlayer) -> None:
    clear_screen()
    total = len(player.playlist)
    print(f"{ORANGE}{BOLD}Playlist  ({total} Track(s)){RESET}")
    print(f"{ORANGE}{'─' * 58}{RESET}")
    if not player.playlist:
        print(f"  {GRAY}<leer>{RESET}")
    else:
        for i, p in enumerate(player.playlist):
            marker = (
                f"{GREEN}▶{RESET}"
                if player.is_playing() and i == player._current_idx
                else " "
            )
            num  = fmt_index(i, total)
            name = truncate(str(p), 50)
            print(f"  {marker} {ORANGE}{num}{RESET}  {name}")
    print(f"{ORANGE}{'─' * 58}{RESET}")
    input_or_quit(f"{GRAY}Enter → zurück{RESET}  ")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main() -> None:
    if shutil.which("ffmpeg") is None:
        print(
            f"{ORANGE}{BOLD}ffmpeg nicht gefunden. "
            f"Bitte installieren und erneut starten.{RESET}"
        )
        sys.exit(1)

    player = AudioPlayer()

    while True:
        clear_screen()
        print_header(player)
        print_menu()

        choice = input_or_quit(f"  {ORANGE}Wahl:{RESET} ").strip().lower()

        # ── Playlist anzeigen ─────────────────────────────────────────────────
        if choice == "1":
            show_playlist(player)

        # ── Datei hinzufügen ──────────────────────────────────────────────────
        elif choice == "2":
            clear_screen()
            print_header(player)
            print(f"{ORANGE}{BOLD}Datei hinzufügen{RESET}")
            raw = input_or_quit(f"  {ORANGE}Pfad:{RESET} ")
            pos = input_or_quit(
                f"  Position  {GRAY}[v=vorne / Enter=hinten]{RESET}: "
            ).strip().lower()
            ok, msg = player.add_file(raw, front=(pos == "v"))
            _print_result(ok, msg)
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Ordner hinzufügen ─────────────────────────────────────────────────
        elif choice == "3":
            clear_screen()
            print_header(player)
            print(f"{ORANGE}{BOLD}Ordner hinzufügen{RESET}")
            raw = input_or_quit(f"  {ORANGE}Pfad:{RESET} ")
            rec = input_or_quit(
                f"  Rekursiv?  {GRAY}[j/N]{RESET}: "
            ).strip().lower()
            ok, msg = player.add_folder(raw, recursive=(rec == "j"))
            _print_result(ok, msg)
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Track entfernen ───────────────────────────────────────────────────
        elif choice == "4":
            show_playlist(player)
            if player.playlist:
                raw = input_or_quit(
                    f"  {ORANGE}Index zum Entfernen:{RESET} "
                ).strip()
                try:
                    ok, msg = player.remove_track(int(raw))
                    _print_result(ok, msg)
                except ValueError:
                    _print_result(False, "Ungültige Eingabe")
                input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Track verschieben ─────────────────────────────────────────────────
        elif choice == "5":
            show_playlist(player)
            if len(player.playlist) >= 2:
                try:
                    f = int(input_or_quit(f"  {ORANGE}Von Index:{RESET} ").strip())
                    t = int(input_or_quit(f"  {ORANGE}Nach Index:{RESET} ").strip())
                    ok, msg = player.move_track(f, t)
                    _print_result(ok, msg)
                except ValueError:
                    _print_result(False, "Ungültige Eingabe")
                input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Play ──────────────────────────────────────────────────────────────
        elif choice == "p":
            raw = input_or_quit(
                f"  {ORANGE}Ab Index{GRAY} [Enter=0]{RESET}: "
            ).strip()
            idx = int(raw) if raw.isdigit() else 0
            ok, msg = player.play(from_idx=idx)
            _print_result(ok, msg)
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Skip ──────────────────────────────────────────────────────────────
        elif choice == "s":
            ok, msg = player.skip()
            _print_result(ok, msg)
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Stop ──────────────────────────────────────────────────────────────
        elif choice == "x":
            ok, msg = player.stop()
            _print_result(ok, msg)
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Lautstärke ────────────────────────────────────────────────────────
        elif choice == "v":
            clear_screen()
            print_header(player)
            print(f"{ORANGE}{BOLD}Lautstärke setzen{RESET}")
            print(
                f"  Aktuell: {CYAN}{player._volume} %{RESET}  "
                f"{GRAY}(0 = stumm, 100 = normal, 200 = doppelt){RESET}"
            )
            raw = input_or_quit(
                f"  {ORANGE}Neuer Wert (0–200){GRAY} [Enter = unverändert]{RESET}: "
            ).strip()
            if raw:
                try:
                    ok, msg = player.set_volume(int(raw))
                    _print_result(ok, msg)
                    if ok:
                        print(
                            f"  {GRAY}Hinweis: Gilt ab dem nächsten Track "
                            f"(oder nach Skip / Play).{RESET}"
                        )
                except ValueError:
                    _print_result(False, "Ungültige Eingabe – bitte eine ganze Zahl eingeben")
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Normalisierung ────────────────────────────────────────────────────
        elif choice == "n":
            msg = player.toggle_normalize()
            print(f"  {ORANGE}{msg}{RESET}")
            if player._normalize:
                print(
                    f"  {GRAY}EBU R128 loudnorm  "
                    f"(I=-16 LUFS, TP=-1.5 dBTP, LRA=11 LU){RESET}"
                )
                print(
                    f"  {GRAY}Hinweis: Single-Pass; gilt ab dem nächsten Track.{RESET}"
                )
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Shuffle mischen ───────────────────────────────────────────────────
        elif choice == "z":
            ok, msg = player.shuffle_playlist()
            _print_result(ok, msg)
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Shuffle-Modus ─────────────────────────────────────────────────────
        elif choice == "t":
            msg = player.toggle_shuffle()
            print(f"  {ORANGE}{msg}{RESET}")
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Playlist leeren ───────────────────────────────────────────────────
        elif choice == "c":
            confirm = input_or_quit(
                f"  {ORANGE}Wirklich leeren?{GRAY} [j/N]{RESET}: "
            ).strip().lower()
            if confirm == "j":
                player.clear_playlist()
                print(f"  {ORANGE}Playlist geleert{RESET}")
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Beenden ───────────────────────────────────────────────────────────
        elif choice == "0":
            player.stop()
            if player._play_thread:
                player._play_thread.join(timeout=2.0)
            print(f"  {GRAY}Auf Wiedersehen.{RESET}")
            sys.exit(0)

        # ── Ungültige Eingabe ─────────────────────────────────────────────────
        else:
            print(f"  {RED}Ungültige Wahl: '{choice}'{RESET}")
            input_or_quit(f"  {GRAY}Enter{RESET}  ")


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
