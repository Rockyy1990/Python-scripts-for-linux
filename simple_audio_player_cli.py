#!/usr/bin/env python3
"""
Simple Terminal Audio Player
ffmpeg -> PipeWire (pw-play) oder aplay
Unterstützte Formate: mp3, aac, m4a, opus, flac
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

ORANGE = "\033[38;5;214m"
BOLD = "\033[1m"
RESET = "\033[0m"

SUPPORTED_EXT = {".mp3", ".aac", ".m4a", ".opus", ".flac"}


def normalize_path(s: str) -> Path:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    p = Path(os.path.expanduser(s))
    try:
        if p.exists():
            p = p.resolve()
    except Exception:
        pass
    return p


class AudioPlayer:
    def __init__(self) -> None:
        self.playlist: List[Path] = []
        self._proc_lock = threading.Lock()
        self._current_proc: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._play_thread: Optional[threading.Thread] = None

        self._pw_play = shutil.which("pw-play")
        self._aplay = shutil.which("aplay")
        if not self._pw_play and not self._aplay:
            print(f"{ORANGE}Warnung: 'pw-play' oder 'aplay' nicht gefunden. Kein Audioausgabegerät verfügbar.{RESET}")

    def add_file_front(self, path_str: str) -> tuple[bool, str]:
        p = normalize_path(path_str)
        if not p.exists():
            return False, "Datei nicht gefunden"
        if not p.is_file():
            return False, "Keine reguläre Datei"
        if p.suffix.lower() not in SUPPORTED_EXT:
            return False, "Format nicht unterstützt"
        self.playlist.insert(0, p)
        return True, "Hinzugefügt (vorne)"

    def list_playlist(self) -> List[str]:
        return [str(p) for p in self.playlist]

    def clear_playlist(self) -> None:
        self.stop()
        self.playlist.clear()

    def _ffmpeg_cmd(self, path: Path) -> List[str]:
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-re",
            "-i",
            str(path),
            "-f",
            "wav",
            "-ar",
            "48000",
            "-ac",
            "2",
            "pipe:1",
        ]

    def _run_track(self, path: Path) -> None:
        ff_cmd = self._ffmpeg_cmd(path)
        try:
            ff = subprocess.Popen(ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            print(f"{ORANGE}ffmpeg nicht gefunden. Bitte installieren.{RESET}")
            return
        except Exception as e:
            print(f"{ORANGE}Fehler beim Starten von ffmpeg: {e}{RESET}")
            return

        with self._proc_lock:
            self._current_proc = ff

        consumer_proc: Optional[subprocess.Popen] = None
        try:
            if self._pw_play:
                # pw-play accepts "-" as stdin in many implementations
                consumer_proc = subprocess.Popen([self._pw_play, "-"], stdin=ff.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                ff.stdout.close()
                consumer_proc.wait()
            elif self._aplay:
                # aplay reads WAV from stdin with "-"
                consumer_proc = subprocess.Popen([self._aplay, "-"], stdin=ff.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                ff.stdout.close()
                consumer_proc.wait()
            else:
                # No consumer: just wait ffmpeg to finish
                ff.wait()
        except Exception:
            pass
        finally:
            with self._proc_lock:
                if self._current_proc is ff:
                    self._current_proc = None
            try:
                if consumer_proc and consumer_proc.poll() is None:
                    consumer_proc.terminate()
            except Exception:
                pass
            try:
                if ff and ff.poll() is None:
                    ff.terminate()
            except Exception:
                pass

    def _playback_loop(self) -> None:
        # sequential playback from start to end of playlist
        idx = 0
        while idx < len(self.playlist):
            if self._stop_event.is_set():
                break
            path = self.playlist[idx]
            if not path.exists():
                idx += 1
                continue
            self._run_track(path)
            if self._stop_event.is_set():
                break
            idx += 1
        self._stop_event.clear()
        with self._proc_lock:
            self._current_proc = None
        self._play_thread = None

    def play_playlist(self) -> tuple[bool, str]:
        if not self.playlist:
            return False, "Playlist leer"
        if self._play_thread and self._play_thread.is_alive():
            return False, "Bereits Wiedergabe aktiv"
        self._stop_event.clear()
        self._play_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._play_thread.start()
        return True, "Wiedergabe gestartet (ab Anfang der Playlist)"

    def stop(self) -> tuple[bool, str]:
        self._stop_event.set()
        with self._proc_lock:
            proc = self._current_proc
            self._current_proc = None
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass
            return True, "Stop ausgeführt"
        return True, "Stop: keine aktive Wiedergabe"


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def input_or_quit(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def main() -> None:
    if shutil.which("ffmpeg") is None:
        print(f"{ORANGE}{BOLD}ffmpeg nicht gefunden. Bitte installieren und erneut starten.{RESET}")
        sys.exit(1)

    player = AudioPlayer()

    while True:
        clear_screen()
        print(f"{ORANGE}{BOLD}Simple Audio Player (ffmpeg -> PipeWire / aplay){RESET}")
        print(f"{ORANGE}1){RESET} Playlist anzeigen")
        print(f"{ORANGE}2){RESET} Datei zur Playlist hinzufügen (am Anfang)")
        print(f"{ORANGE}3){RESET} Playlist abspielen (immer ab Anfang)")
        print(f"{ORANGE}4){RESET} Stop")
        print(f"{ORANGE}5){RESET} Playlist leeren")
        print(f"{ORANGE}0){RESET} Beenden")
        choice = input_or_quit(f"{ORANGE}Wahl:{RESET} ").strip()

        if choice == "1":
            clear_screen()
            print(f"{ORANGE}{BOLD}Playlist:{RESET}")
            if not player.playlist:
                print(f"{ORANGE}<leer>{RESET}")
            else:
                for i, p in enumerate(player.playlist):
                    print(f"{ORANGE}{i}{RESET}: {p}")
            input_or_quit(f"{ORANGE}Enter zum Zurück{RESET}")

        elif choice == "2":
            path = input_or_quit(f"{ORANGE}Pfad zur Datei:{RESET} ").strip()
            ok, msg = player.add_file_front(path)
            print(f"{ORANGE}{msg}{RESET}")
            input_or_quit(f"{ORANGE}Enter{RESET}")

        elif choice == "3":
            player.stop()
            ok, msg = player.play_playlist()
            print(f"{ORANGE}{msg}{RESET}")
            input_or_quit(f"{ORANGE}Enter{RESET}")

        elif choice == "4":
            ok, msg = player.stop()
            print(f"{ORANGE}{msg}{RESET}")
            input_or_quit(f"{ORANGE}Enter{RESET}")

        elif choice == "5":
            player.clear_playlist()
            print(f"{ORANGE}Playlist geleert{RESET}")
            input_or_quit(f"{ORANGE}Enter{RESET}")

        elif choice == "0":
            player.stop()
            sys.exit(0)

        else:
            print(f"{ORANGE}Ungültige Wahl{RESET}")
            input_or_quit(f"{ORANGE}Enter{RESET}")


if __name__ == "__main__":
    main()
