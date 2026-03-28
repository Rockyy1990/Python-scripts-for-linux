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
from pathlib import Path
from typing import List, Optional

# ── ANSI-Farben ──────────────────────────────────────────────────────────────
ORANGE = "\033[38;5;214m"
GREEN  = "\033[38;5;82m"
GRAY   = "\033[38;5;240m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Konstanten ────────────────────────────────────────────────────────────────
SUPPORTED_EXT: frozenset[str] = frozenset(
    {".mp3", ".aac", ".m4a", ".opus", ".flac", ".wav", ".ogg"}
)

FFMPEG_FLAGS = [
    "ffmpeg", "-hide_banner", "-loglevel", "error",
    "-nostdin", "-re",
]

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def normalize_path(s: str) -> Path:
    """Bereinigt Pfad-Strings (Anführungszeichen, ~, relative Pfade)."""
    s = s.strip().strip("\"'")
    return Path(os.path.expanduser(s)).resolve()


def fmt_name(p: Path) -> str:
    return p.name


def _terminate(proc: Optional[subprocess.Popen]) -> None:
    """Beendet einen Prozess sauber (terminate → kill)."""
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=0.5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ── AudioPlayer ───────────────────────────────────────────────────────────────

class AudioPlayer:
    def __init__(self) -> None:
        self.playlist: List[Path] = []

        self._lock = threading.Lock()
        self._ff:       Optional[subprocess.Popen] = None
        self._consumer: Optional[subprocess.Popen] = None

        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._play_thread: Optional[threading.Thread] = None

        self._current_idx:  int           = -1
        self._current_path: Optional[Path] = None

        self._player_bin: Optional[str] = shutil.which("pw-play") or shutil.which("aplay")
        if self._player_bin is None:
            _warn("'pw-play' oder 'aplay' nicht gefunden – kein Audioausgang verfügbar.")

    # ── Status ────────────────────────────────────────────────────────────

    def is_playing(self) -> bool:
        return self._play_thread is not None and self._play_thread.is_alive()

    def status_line(self) -> str:
        if not self.is_playing() or self._current_path is None:
            return f"{GRAY}● Gestoppt{RESET}"
        idx   = self._current_idx
        total = len(self.playlist)
        name  = fmt_name(self._current_path)
        return f"{GREEN}{BOLD}▶ [{idx + 1}/{total}]{RESET}{GREEN} {name}{RESET}"

    # ── Playlist-Verwaltung ───────────────────────────────────────────────

    def add_file(self, path_str: str, *, front: bool = False) -> tuple[bool, str]:
        p = normalize_path(path_str)
        if not p.exists():
            return False, f"Nicht gefunden: {p}"
        if not p.is_file():
            return False, "Kein reguläres Datei"
        if p.suffix.lower() not in SUPPORTED_EXT:
            return False, f"Format nicht unterstützt: {p.suffix}"
        if front:
            self.playlist.insert(0, p)
            if self.is_playing():
                self._current_idx += 1          # Index nach hinten verschieben
            return True, f"Vorne hinzugefügt: {fmt_name(p)}"
        else:
            self.playlist.append(p)
            return True, f"Hinzugefügt: {fmt_name(p)}"

    def add_folder(self, path_str: str) -> tuple[bool, str]:
        p = normalize_path(path_str)
        if not p.is_dir():
            return False, f"Kein Verzeichnis: {p}"
        files = sorted(
            f for f in p.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
        )
        if not files:
            return False, "Keine unterstützten Dateien gefunden"
        self.playlist.extend(files)
        return True, f"{len(files)} Datei(en) aus »{p.name}« hinzugefügt"

    def remove_track(self, idx: int) -> tuple[bool, str]:
        if not (0 <= idx < len(self.playlist)):
            return False, "Ungültiger Index"
        removed = self.playlist.pop(idx)
        if idx == self._current_idx:
            self.skip()
        elif idx < self._current_idx:
            self._current_idx -= 1
        return True, f"Entfernt: {fmt_name(removed)}"

    def clear_playlist(self) -> None:
        self.stop()
        self.playlist.clear()

    # ── Wiedergabe ────────────────────────────────────────────────────────

    def _kill_procs(self) -> None:
        with self._lock:
            ff, consumer = self._ff, self._consumer
            self._ff = self._consumer = None
        # Consumer zuerst beenden, dann ffmpeg
        _terminate(consumer)
        _terminate(ff)

    def _run_track(self, path: Path) -> None:
        cmd = [*FFMPEG_FLAGS, "-i", str(path), "-f", "wav", "-ar", "48000", "-ac", "2", "pipe:1"]
        try:
            ff = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            _warn("ffmpeg nicht gefunden. Bitte installieren.")
            return
        except Exception as exc:
            _warn(f"ffmpeg-Fehler: {exc}")
            return

        consumer: Optional[subprocess.Popen] = None
        if self._player_bin:
            try:
                consumer = subprocess.Popen(
                    [self._player_bin, "-"],
                    stdin=ff.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                ff.stdout.close()   # Pipe-Eigentümerschaft an Consumer übergeben
            except Exception as exc:
                _warn(f"Player-Fehler: {exc}")
                ff.terminate()
                return
        else:
            ff.stdout.close()

        with self._lock:
            self._ff       = ff
            self._consumer = consumer

        target = consumer if consumer else ff
        while target.poll() is None:
            if self._stop_event.is_set() or self._skip_event.is_set():
                break
            try:
                target.wait(timeout=0.15)
            except Exception:
                break

        self._kill_procs()

    def _playback_loop(self) -> None:
        while 0 <= self._current_idx < len(self.playlist):
            if self._stop_event.is_set():
                break
            self._skip_event.clear()
            path = self.playlist[self._current_idx]
            self._current_path = path
            if path.exists():
                self._run_track(path)
            if self._stop_event.is_set():
                break
            self._current_idx += 1

        # Aufräumen
        self._stop_event.clear()
        self._skip_event.clear()
        self._current_path = None
        self._current_idx  = -1
        self._play_thread  = None

    def play(self, start_idx: int = 0) -> tuple[bool, str]:
        if not self.playlist:
            return False, "Playlist leer"
        if not (0 <= start_idx < len(self.playlist)):
            return False, "Ungültiger Index"
        self.stop()
        self._current_idx = start_idx
        self._stop_event.clear()
        self._skip_event.clear()
        self._play_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._play_thread.start()
        return True, f"Wiedergabe ab #{start_idx + 1}: {fmt_name(self.playlist[start_idx])}"

    def skip(self) -> tuple[bool, str]:
        if not self.is_playing():
            return False, "Keine aktive Wiedergabe"
        self._skip_event.set()
        return True, "Übersprungen"

    def stop(self) -> tuple[bool, str]:
        self._stop_event.set()
        self._kill_procs()
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=1.5)
        self._current_path = None
        self._current_idx  = -1
        return True, "Gestoppt"


# ── UI-Hilfsfunktionen ────────────────────────────────────────────────────────

def _warn(msg: str) -> None:
    print(f"{ORANGE}⚠  {msg}{RESET}")


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def show_playlist(player: AudioPlayer) -> None:
    clear_screen()
    print(f"{ORANGE}{BOLD}Playlist{RESET}  {player.status_line()}\n")
    if not player.playlist:
        print(f"{GRAY}  <leer>{RESET}")
    else:
        cur = player._current_idx
        for i, p in enumerate(player.playlist):
            marker = f"{GREEN}▶{RESET}" if i == cur else f"{GRAY} {RESET}"
            print(f"  {marker} {ORANGE}{i + 1:>3}.{RESET} {p.name}")
    print()


# ── Hauptmenü ─────────────────────────────────────────────────────────────────

MENU = f"""
  {ORANGE}1{RESET}  Playlist anzeigen
  {ORANGE}2{RESET}  Datei hinzufügen (Ende)
  {ORANGE}3{RESET}  Datei hinzufügen (Anfang)
  {ORANGE}4{RESET}  Ordner hinzufügen
  {ORANGE}5{RESET}  Track entfernen (Index)
  {ORANGE}6{RESET}  Abspielen (ab Anfang)
  {ORANGE}7{RESET}  Abspielen ab Index
  {ORANGE}8{RESET}  Nächster Track (Skip)
  {ORANGE}9{RESET}  Stop
  {ORANGE}c{RESET}  Playlist leeren
  {ORANGE}0{RESET}  Beenden
"""


def main() -> None:
    if shutil.which("ffmpeg") is None:
        print(f"{ORANGE}{BOLD}ffmpeg nicht gefunden. Bitte installieren und erneut starten.{RESET}")
        sys.exit(1)

    player = AudioPlayer()

    while True:
        clear_screen()
        print(f"{ORANGE}{BOLD}  ♪ Simple Audio Player{RESET}  {player.status_line()}")
        print(MENU)
        choice = ask(f"{ORANGE}›{RESET} ").strip().lower()

        match choice:
            case "1":
                show_playlist(player)
                ask(f"{GRAY}Enter zum Zurück{RESET}")

            case "2":
                path = ask(f"{ORANGE}Pfad zur Datei:{RESET} ")
                ok, msg = player.add_file(path)
                print(f"{ORANGE}{msg}{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "3":
                path = ask(f"{ORANGE}Pfad zur Datei:{RESET} ")
                ok, msg = player.add_file(path, front=True)
                print(f"{ORANGE}{msg}{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "4":
                path = ask(f"{ORANGE}Ordnerpfad:{RESET} ")
                ok, msg = player.add_folder(path)
                print(f"{ORANGE}{msg}{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "5":
                show_playlist(player)
                raw = ask(f"{ORANGE}Index (1-basiert) zum Entfernen:{RESET} ").strip()
                try:
                    idx = int(raw) - 1
                    ok, msg = player.remove_track(idx)
                    print(f"{ORANGE}{msg}{RESET}")
                except ValueError:
                    print(f"{ORANGE}Ungültige Eingabe{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "6":
                _, msg = player.play(start_idx=0)
                print(f"{ORANGE}{msg}{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "7":
                show_playlist(player)
                raw = ask(f"{ORANGE}Ab Index (1-basiert) abspielen:{RESET} ").strip()
                try:
                    idx = int(raw) - 1
                    _, msg = player.play(start_idx=idx)
                    print(f"{ORANGE}{msg}{RESET}")
                except ValueError:
                    print(f"{ORANGE}Ungültige Eingabe{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "8":
                _, msg = player.skip()
                print(f"{ORANGE}{msg}{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "9":
                _, msg = player.stop()
                print(f"{ORANGE}{msg}{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "c":
                player.clear_playlist()
                print(f"{ORANGE}Playlist geleert{RESET}")
                ask(f"{GRAY}Enter{RESET}")

            case "0":
                player.stop()
                sys.exit(0)

            case _:
                print(f"{ORANGE}Ungültige Wahl{RESET}")
                ask(f"{GRAY}Enter{RESET}")


if __name__ == "__main__":
    main()
