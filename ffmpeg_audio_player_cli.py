#!/usr/bin/env python3
"""
Simple Terminal Audio Player
ffmpeg -> PipeWire (pw-play) oder aplay
Unterstützte Formate: mp3, aac, m4a, opus, flac, wav, ogg
Python 3.10+
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
import threading
import random
from pathlib import Path
from typing import Optional

# ── Farben ────────────────────────────────────────────────────────────────────
ORANGE  = "\033[38;5;214m"
GREEN   = "\033[38;5;82m"
RED     = "\033[38;5;196m"
CYAN    = "\033[38;5;51m"
GRAY    = "\033[38;5;245m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"

SUPPORTED_EXT = {".mp3", ".aac", ".m4a", ".opus", ".flac", ".wav", ".ogg"}

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def normalize_path(s: str) -> Path:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or \
       (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    p = Path(os.path.expanduser(s))
    try:
        if p.exists():
            p = p.resolve()
    except Exception:
        pass
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
    width = len(str(total))
    return f"{i:>{width}}"


def truncate(s: str, max_len: int = 60) -> str:
    if len(s) <= max_len:
        return s
    half = (max_len - 3) // 2
    return s[:half] + "…" + s[-(max_len - half - 3):]


# ── AudioPlayer ───────────────────────────────────────────────────────────────
class AudioPlayer:
    def __init__(self) -> None:
        self.playlist:       list[Path]               = []
        self._current_idx:   int                      = 0
        self._current_path:  Optional[Path]           = None
        self._shuffle:       bool                     = False
        self._shuffle_order: list[int]                = []

        self._proc_lock  = threading.Lock()
        self._ff_proc:   Optional[subprocess.Popen]  = None
        self._con_proc:  Optional[subprocess.Popen]  = None

        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._play_thread: Optional[threading.Thread] = None

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
            return True, f"Hinzugefügt (vorne): {p.name}"
        else:
            self.playlist.append(p)
            return True, f"Hinzugefügt (hinten): {p.name}"

    def add_folder(self, path_str: str, recursive: bool = False) -> tuple[bool, str]:
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
            self.skip()
        self.playlist.pop(idx)
        if self._current_idx >= len(self.playlist):
            self._current_idx = max(0, len(self.playlist) - 1)
        return True, f"Entfernt: {name}"

    def move_track(self, from_idx: int, to_idx: int) -> tuple[bool, str]:
        n = len(self.playlist)
        if not (0 <= from_idx < n and 0 <= to_idx < n):
            return False, "Ungültiger Index"
        track = self.playlist.pop(from_idx)
        self.playlist.insert(to_idx, track)
        return True, f"'{track.name}' → Position {to_idx}"

    def shuffle_playlist(self) -> tuple[bool, str]:
        if len(self.playlist) < 2:
            return False, "Zu wenige Tracks zum Mischen"
        random.shuffle(self.playlist)
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
        self.playlist.clear()
        self._current_idx  = 0
        self._current_path = None

    def list_playlist(self) -> list[str]:
        return [str(p) for p in self.playlist]

    # ── Status ───────────────────────────────────────────────────────────────

    def is_playing(self) -> bool:
        return bool(self._play_thread and self._play_thread.is_alive())

    def status_line(self) -> str:
        count   = len(self.playlist)
        shuffle = f" {CYAN}[SHUFFLE]{RESET}" if self._shuffle else ""
        if self.is_playing() and self._current_path:
            name = truncate(self._current_path.name, 45)
            idx  = self._current_idx + 1
            return (
                f"{GREEN}▶ {BOLD}{name}{RESET}"
                f"{GRAY} [{idx}/{count}]{RESET}{shuffle}"
            )
        return f"{GRAY}⏹  Gestoppt  [{count} Track(s)]{RESET}{shuffle}"

    # ── ffmpeg / Wiedergabe ──────────────────────────────────────────────────

    def _ffmpeg_cmd(self, path: Path) -> list[str]:
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-nostdin", "-re",
            "-i", str(path),
            "-f", "wav", "-ar", "48000", "-ac", "2",
            "pipe:1",
        ]

    def _kill_current(self) -> None:
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
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass

    def _run_track(self, path: Path) -> None:
        ff_cmd = self._ffmpeg_cmd(path)
        try:
            ff = subprocess.Popen(
                ff_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print(f"{ORANGE}ffmpeg nicht gefunden.{RESET}")
            return
        except Exception as e:
            print(f"{ORANGE}ffmpeg Fehler: {e}{RESET}")
            return

        consumer: Optional[subprocess.Popen] = None
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
                ff.stdout.close()

            with self._proc_lock:
                self._ff_proc  = ff
                self._con_proc = consumer

            if consumer:
                while True:
                    try:
                        consumer.wait(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    if self._stop_event.is_set() or self._skip_event.is_set():
                        break
            else:
                while True:
                    try:
                        ff.wait(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    if self._stop_event.is_set() or self._skip_event.is_set():
                        break

        finally:
            self._kill_current()

    def _next_index(self, current: int) -> Optional[int]:
        n = len(self.playlist)
        if n == 0:
            return None
        if self._shuffle:
            if not self._shuffle_order:
                self._rebuild_shuffle_order()
            try:
                pos      = self._shuffle_order.index(current)
                next_pos = (pos + 1) % len(self._shuffle_order)
                return self._shuffle_order[next_pos]
            except ValueError:
                return self._shuffle_order[0] if self._shuffle_order else None
        return current + 1 if current + 1 < n else None

    def _playback_loop(self) -> None:
        idx = self._current_idx
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
        if not (0 <= from_idx < len(self.playlist)):
            from_idx = 0
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
        name = self.playlist[from_idx].name
        return True, f"Wiedergabe: {truncate(name, 50)}"

    def stop(self) -> tuple[bool, str]:
        if not self.is_playing() and not self._ff_proc:
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
            return False, f"Index {idx} ungültig (0–{len(self.playlist)-1})"
        return self.play(from_idx=idx)


# ── Menü-Helfer ───────────────────────────────────────────────────────────────

def print_header(player: AudioPlayer) -> None:
    print(f"{ORANGE}{BOLD}{'─' * 54}{RESET}")
    print(f"{ORANGE}{BOLD}  Simple Audio Player  │  ffmpeg → PipeWire / aplay{RESET}")
    print(f"{ORANGE}{BOLD}{'─' * 54}{RESET}")
    print(f"  {player.status_line()}")
    print(f"{ORANGE}{'─' * 54}{RESET}")


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
        ("z", "Shuffle (Playlist mischen)"),
        ("t", "Shuffle-Modus umschalten"),
        ("c", "Playlist leeren"),
        ("",  ""),
        ("0", "Beenden"),
    ]
    for key, label in entries:
        if key == "":
            print(f"{GRAY}  {'·' * 40}{RESET}")
        else:
            print(f"  {ORANGE}{BOLD}{key:>2}{RESET}  {label}")
    print(f"{ORANGE}{'─' * 54}{RESET}")


def show_playlist(player: AudioPlayer) -> None:
    clear_screen()
    total = len(player.playlist)
    print(f"{ORANGE}{BOLD}Playlist  ({total} Track(s)){RESET}")
    print(f"{ORANGE}{'─' * 54}{RESET}")
    if not player.playlist:
        print(f"  {GRAY}<leer>{RESET}")
    else:
        for i, p in enumerate(player.playlist):
            marker = f"{GREEN}▶{RESET}" if (
                player.is_playing() and i == player._current_idx
            ) else " "
            num  = fmt_index(i, total)
            name = truncate(str(p), 48)
            print(f"  {marker} {ORANGE}{num}{RESET}  {name}")
    print(f"{ORANGE}{'─' * 54}{RESET}")
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
            print(f"  {'✓' if ok else '✗'}  {ORANGE}{msg}{RESET}")
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
            print(f"  {'✓' if ok else '✗'}  {ORANGE}{msg}{RESET}")
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
                    print(f"  {'✓' if ok else '✗'}  {ORANGE}{msg}{RESET}")
                except ValueError:
                    print(f"  {ORANGE}Ungültige Eingabe{RESET}")
                input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Track verschieben ─────────────────────────────────────────────────
        elif choice == "5":
            show_playlist(player)
            if len(player.playlist) >= 2:
                try:
                    f = int(input_or_quit(f"  {ORANGE}Von Index:{RESET} ").strip())
                    t = int(input_or_quit(f"  {ORANGE}Nach Index:{RESET} ").strip())
                    ok, msg = player.move_track(f, t)
                    print(f"  {'✓' if ok else '✗'}  {ORANGE}{msg}{RESET}")
                except ValueError:
                    print(f"  {ORANGE}Ungültige Eingabe{RESET}")
                input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Play ──────────────────────────────────────────────────────────────
        elif choice == "p":
            raw = input_or_quit(
                f"  {ORANGE}Ab Index{GRAY} [Enter=0]{RESET}: "
            ).strip()
            idx = int(raw) if raw.isdigit() else 0
            ok, msg = player.play(from_idx=idx)
            print(f"  {'✓' if ok else '✗'}  {ORANGE}{msg}{RESET}")
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Skip ──────────────────────────────────────────────────────────────
        elif choice == "s":
            ok, msg = player.skip()
            print(f"  {'✓' if ok else '✗'}  {ORANGE}{msg}{RESET}")
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Stop ──────────────────────────────────────────────────────────────
        elif choice == "x":
            ok, msg = player.stop()
            print(f"  {'✓' if ok else '✗'}  {ORANGE}{msg}{RESET}")
            input_or_quit(f"  {GRAY}Enter{RESET}  ")

        # ── Shuffle mischen ───────────────────────────────────────────────────
        elif choice == "z":
            ok, msg = player.shuffle_playlist()
            print(f"  {'✓' if ok else '✗'}  {ORANGE}{msg}{RESET}")
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
            print(f"  {GRAY}Auf Wiedersehen.{RESET}")
            sys.exit(0)

        # ── Ungültige Eingabe ─────────────────────────────────────────────────
        else:
            print(f"  {ORANGE}Ungültige Wahl{RESET}")
            input_or_quit(f"  {GRAY}Enter{RESET}  ")


if __name__ == "__main__":
    main()
