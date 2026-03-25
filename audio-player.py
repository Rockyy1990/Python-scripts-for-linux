#!/usr/bin/env python3
"""
Audio Player mit Playlist-Unterstützung
Unterstützt: MP3, AAC, OPUS, FLAC
Audio Server: PipeWire
Codec-Engine: FFmpeg
"""

import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict


@dataclass
class AudioFile:
    """Datenklasse für Audio-Dateien"""
    path: str
    title: str
    duration: int = 0


class Playlist:
    """Verwaltung von Playlisten"""

    def __init__(self, name: str = "default"):
        self.name = name
        self.files: List[AudioFile] = []
        self.current_index = 0

    def add_file(self, file_path: str) -> bool:
        """Datei zur Playlist hinzufügen"""
        if not os.path.isfile(file_path):
            return False
        title = os.path.basename(file_path)
        self.files.append(AudioFile(path=file_path, title=title))
        return True

    def remove_file(self, index: int) -> bool:
        """Datei aus Playlist entfernen"""
        if 0 <= index < len(self.files):
            self.files.pop(index)
            if self.current_index >= len(self.files) and self.current_index > 0:
                self.current_index -= 1
            return True
        return False

    def get_current_file(self) -> Optional[AudioFile]:
        """Aktuelle Datei abrufen"""
        if 0 <= self.current_index < len(self.files):
            return self.files[self.current_index]
        return None

    def next_file(self) -> Optional[AudioFile]:
        """Zur nächsten Datei wechseln"""
        if self.current_index < len(self.files) - 1:
            self.current_index += 1
            return self.get_current_file()
        return None

    def previous_file(self) -> Optional[AudioFile]:
        """Zur vorherigen Datei wechseln"""
        if self.current_index > 0:
            self.current_index -= 1
            return self.get_current_file()
        return None

    def save(self, file_path: str) -> bool:
        """Playlist in JSON speichern"""
        try:
            data = {
                'name': self.name,
                'files': [asdict(f) for f in self.files]
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Fehler beim Speichern: {e}")
            return False

    def load(self, file_path: str) -> bool:
        """Playlist aus JSON laden"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.name = data.get('name', 'default')
            self.files = [AudioFile(**f) for f in data.get('files', [])]
            self.current_index = 0
            return True
        except Exception as e:
            print(f"Fehler beim Laden: {e}")
            return False


class AudioPlayer:
    """Audio Player mit PipeWire und FFmpeg"""

    SUPPORTED_FORMATS = {'.mp3', '.aac','.m4a', '.opus', '.flac'}

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.is_playing = False
        self.is_paused = False
        self.playlist = Playlist()
        self.playback_thread: Optional[threading.Thread] = None
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        """Überprüfe erforderliche Abhängigkeiten"""
        try:
            subprocess.run(['ffplay', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("\n⚠️  ffplay nicht gefunden. Installiere FFmpeg:")
            print("   Ubuntu/Debian: sudo apt install ffmpeg")
            print("   Fedora: sudo dnf install ffmpeg")
            print("   Arch: sudo pacman -S ffmpeg")
            sys.exit(1)

    def play_file(self, file_path: str) -> bool:
        """Einzelne Datei abspielen"""
        if not os.path.isfile(file_path):
            return False

        if self.is_playing:
            self.stop()

        self.is_playing = True
        self.is_paused = False

        try:
            # ffplay mit PipeWire Audio-Server
            self.process = subprocess.Popen(
                ['ffplay', '-nodisp', '-autoexit', '-hide_banner', '-loglevel', 'error', file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.playback_thread = threading.Thread(target=self._wait_playback_end, daemon=True)
            self.playback_thread.start()
            return True
        except Exception as e:
            print(f"Fehler beim Abspielen: {e}")
            self.is_playing = False
            return False

    def _wait_playback_end(self) -> None:
        """Warte auf Ende der Wiedergabe"""
        if self.process:
            self.process.wait()
        self.is_playing = False

    def play_playlist(self) -> None:
        """Gesamte Playlist abspielen"""
        if not self.playlist.files:
            print("Playlist ist leer!")
            return
        self.playlist.current_index = 0
        self._play_current()

    def _play_current(self) -> None:
        """Aktuelle Datei in Playlist abspielen"""
        current = self.playlist.get_current_file()
        if current:
            print(f"\n▶️  Spiele ab: {current.title}")
            self.play_file(current.path)

    def stop(self) -> None:
        """Wiedergabe stoppen"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.is_playing = False
        self.is_paused = False

    def pause(self) -> None:
        """Wiedergabe pausieren"""
        if self.is_playing and not self.is_paused:
            if self.process:
                self.process.send_signal(subprocess.signal.SIGSTOP)
                self.is_paused = True

    def resume(self) -> None:
        """Wiedergabe fortsetzen"""
        if self.is_paused and self.process:
            self.process.send_signal(subprocess.signal.SIGCONT)
            self.is_paused = False

    def next(self) -> None:
        """Zur nächsten Datei in Playlist wechseln"""
        if self.playlist.next_file():
            self._play_current()

    def previous(self) -> None:
        """Zur vorherigen Datei in Playlist wechseln"""
        if self.playlist.previous_file():
            self._play_current()

    def add_file_to_playlist(self, file_path: str) -> bool:
        """Datei zur Playlist hinzufügen"""
        return self.playlist.add_file(file_path)

    def add_directory_to_playlist(self, dir_path: str) -> int:
        """Alle Audio-Dateien aus Verzeichnis hinzufügen"""
        count = 0
        if os.path.isdir(dir_path):
            for file in sorted(os.listdir(dir_path)):
                file_path = os.path.join(dir_path, file)
                if os.path.isfile(file_path):
                    ext = os.path.splitext(file)[1].lower()
                    if ext in self.SUPPORTED_FORMATS:
                        if self.add_file_to_playlist(file_path):
                            count += 1
        return count


class ColorTerminal:
    """Terminal-Farben für die Menü-Ausgabe"""

    ORANGE = '\033[38;5;208m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'

    @staticmethod
    def orange(text: str) -> str:
        """Text in Orange"""
        return f"{ColorTerminal.ORANGE}{text}{ColorTerminal.RESET}"

    @staticmethod
    def colored(text: str, color: str) -> str:
        """Text mit Farbe"""
        return f"{color}{text}{ColorTerminal.RESET}"


class Menu:
    """Interaktives Menü-System"""

    def __init__(self, player: AudioPlayer):
        self.player = player
        self.running = True

    def clear_screen(self) -> None:
        """Bildschirm löschen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def display_header(self) -> None:
        """Kopfzeile anzeigen"""
        self.clear_screen()
        print(ColorTerminal.orange("╔════════════════════════════════════════╗"))
        print(ColorTerminal.orange("║          AUDIO PLAYER v1.0             ║"))
        print(ColorTerminal.orange("╚════════════════════════════════════════╝"))
        print()

    def display_status(self) -> None:
        """Status anzeigen"""
        if self.player.is_playing:
            status = "▶️  Läuft"
        elif self.player.is_paused:
            status = "⏸️  Pausiert"
        else:
            status = "⏹️  Gestoppt"

        print(ColorTerminal.orange("─" * 42))
        print(f"Status: {ColorTerminal.colored(status, ColorTerminal.CYAN)}")

        current = self.player.playlist.get_current_file()
        if current:
            print(f"Aktuell: {ColorTerminal.colored(current.title, ColorTerminal.GREEN)}")
        print(f"Playlist: {len(self.player.playlist.files)} Dateien")
        print(ColorTerminal.orange("─" * 42))
        print()

    def display_main_menu(self) -> None:
        """Hauptmenü anzeigen"""
        self.display_header()
        self.display_status()

        print(ColorTerminal.orange("HAUPTMENÜ:"))
        print(ColorTerminal.orange("1") + " - Datei abspielen")
        print(ColorTerminal.orange("2") + " - Verzeichnis zur Playlist hinzufügen")
        print(ColorTerminal.orange("3") + " - Playlist anzeigen")
        print(ColorTerminal.orange("4") + " - Playlist abspielen")
        print(ColorTerminal.orange("5") + " - Wiedergabe steuern")
        print(ColorTerminal.orange("6") + " - Playlist verwalten")
        print(ColorTerminal.orange("7") + " - Playlist speichern/laden")
        print(ColorTerminal.orange("0") + " - Beenden")
        print()

    def display_playback_menu(self) -> None:
        """Wiedergabe-Steuerungsmenü"""
        self.display_header()
        self.display_status()

        print(ColorTerminal.orange("WIEDERGABE-STEUERUNG:"))
        print(ColorTerminal.orange("1") + " - Pause/Fortsetzen")
        print(ColorTerminal.orange("2") + " - Stopp")
        print(ColorTerminal.orange("3") + " - Nächste Datei")
        print(ColorTerminal.orange("4") + " - Vorherige Datei")
        print(ColorTerminal.orange("0") + " - Zurück")
        print()

    def display_playlist(self) -> None:
        """Playlist anzeigen"""
        self.display_header()

        if not self.player.playlist.files:
            print(ColorTerminal.colored("Playlist ist leer!", ColorTerminal.RED))
            input("\nEnter zum Fortfahren...")
            return

        print(ColorTerminal.orange("PLAYLIST:"))
        print()

        for i, file in enumerate(self.player.playlist.files):
            marker = "▶️ " if i == self.player.playlist.current_index else "  "
            print(f"{marker}{ColorTerminal.orange(f'{i+1:2d}.')} {file.title}")

        print()
        input("Enter zum Fortfahren...")

    def select_file(self) -> Optional[str]:
        """Datei auswählen"""
        self.display_header()

        file_path = input(ColorTerminal.orange("Pfad zur Audio-Datei eingeben: ")).strip()

        if os.path.isfile(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in AudioPlayer.SUPPORTED_FORMATS:
                return file_path
            else:
                print(
                    ColorTerminal.colored(
                        f"Format nicht unterstützt! Unterstützt: {', '.join(AudioPlayer.SUPPORTED_FORMATS)}",
                        ColorTerminal.RED,
                    )
                )
        else:
            print(ColorTerminal.colored("Datei nicht gefunden!", ColorTerminal.RED))

        input("\nEnter zum Fortfahren...")
        return None

    def select_directory(self) -> Optional[str]:
        """Verzeichnis auswählen"""
        self.display_header()

        dir_path = input(ColorTerminal.orange("Pfad zum Verzeichnis eingeben: ")).strip()

        if os.path.isdir(dir_path):
            return dir_path
        else:
            print(ColorTerminal.colored("Verzeichnis nicht gefunden!", ColorTerminal.RED))

        input("\nEnter zum Fortfahren...")
        return None

    def manage_playlist(self) -> None:
        """Playlist-Verwaltungsmenü"""
        while True:
            self.display_header()
            self.display_status()

            if not self.player.playlist.files:
                print(ColorTerminal.colored("Playlist ist leer!", ColorTerminal.RED))
                print()
                input("Enter zum Fortfahren...")
                break

            print(ColorTerminal.orange("PLAYLIST VERWALTEN:"))
            print(ColorTerminal.orange("1") + " - Datei entfernen")
            print(ColorTerminal.orange("2") + " - Playlist leeren")
            print(ColorTerminal.orange("0") + " - Zurück")
            print()

            choice = input(ColorTerminal.orange("Wahl: ")).strip()

            if choice == "1":
                self.display_playlist()
                try:
                    index = int(input(ColorTerminal.orange("Nummer eingeben: ")).strip()) - 1
                    if self.player.playlist.remove_file(index):
                        print(ColorTerminal.colored("Datei entfernt!", ColorTerminal.GREEN))
                    else:
                        print(ColorTerminal.colored("Ungültige Nummer!", ColorTerminal.RED))
                except ValueError:
                    print(ColorTerminal.colored("Ungültige Eingabe!", ColorTerminal.RED))
                input("\nEnter zum Fortfahren...")

            elif choice == "2":
                confirm = input(ColorTerminal.orange("Playlist wirklich leeren? (j/n): ")).strip().lower()
                if confirm == 'j':
                    self.player.playlist.files.clear()
                    self.player.playlist.current_index = 0
                    print(ColorTerminal.colored("Playlist geleert!", ColorTerminal.GREEN))
                input("\nEnter zum Fortfahren...")

            elif choice == "0":
                break

    def save_load_playlist(self) -> None:
        """Playlist speichern/laden"""
        while True:
            self.display_header()

            print(ColorTerminal.orange("PLAYLIST SPEICHERN/LADEN:"))
            print(ColorTerminal.orange("1") + " - Playlist speichern")
            print(ColorTerminal.orange("2") + " - Playlist laden")
            print(ColorTerminal.orange("0") + " - Zurück")
            print()

            choice = input(ColorTerminal.orange("Wahl: ")).strip()

            if choice == "1":
                filename = input(ColorTerminal.orange("Dateipfad zum Speichern eingeben: ")).strip()
                if self.player.playlist.save(filename):
                    print(ColorTerminal.colored("Playlist gespeichert!", ColorTerminal.GREEN))
                else:
                    print(ColorTerminal.colored("Fehler beim Speichern!", ColorTerminal.RED))
                input("\nEnter zum Fortfahren...")

            elif choice == "2":
                filename = input(ColorTerminal.orange("Dateipfad zum Laden eingeben: ")).strip()
                if self.player.playlist.load(filename):
                    print(ColorTerminal.colored("Playlist geladen!", ColorTerminal.GREEN))
                else:
                    print(ColorTerminal.colored("Fehler beim Laden!", ColorTerminal.RED))
                input("\nEnter zum Fortfahren...")

            elif choice == "0":
                break

    def main_loop(self) -> None:
        """Hauptschleife des Menüs"""
        while self.running:
            self.display_header()
            self.display_main_menu()
            choice = input(ColorTerminal.orange("Wahl: ")).strip()

            if choice == "1":
                file_path = self.select_file()
                if file_path:
                    self.player.play_file(file_path)
                    input("Enter zum Fortfahren...")

            elif choice == "2":
                dir_path = self.select_directory()
                if dir_path:
                    count = self.player.add_directory_to_playlist(dir_path)
                    print(f"{count} Dateien hinzugefügt.")
                    input("Enter zum Fortfahren...")

            elif choice == "3":
                self.display_playlist()

            elif choice == "4":
                self.player.play_playlist()
                input("Enter zum Fortfahren...")

            elif choice == "5":
                self._playback_control()

            elif choice == "6":
                self.manage_playlist()

            elif choice == "7":
                self.save_load_playlist()

            elif choice == "0":
                self.running = False
                self.player.stop()
                print("Beenden...")
            else:
                print("Ungültige Wahl!")
                input("Enter zum Fortfahren...")

    def _playback_control(self) -> None:
        """Steuerung der Wiedergabe"""
        while True:
            self.display_header()
            self.display_status()
            self.display_playback_menu()
            choice = input(ColorTerminal.orange("Wahl: ")).strip()

            if choice == "1":
                if self.player.is_paused:
                    self.player.resume()
                elif self.player.is_playing:
                    self.player.pause()
                else:
                    print("Keine Wiedergabe aktiv.")
                time.sleep(1)

            elif choice == "2":
                self.player.stop()
                break

            elif choice == "3":
                self.player.next()
                time.sleep(1)

            elif choice == "4":
                self.player.previous()
                time.sleep(1)

            elif choice == "0":
                break

            else:
                print("Ungültige Wahl!")
                time.sleep(1)


if __name__ == "__main__":
    player = AudioPlayer()
    menu = Menu(player)
    try:
        menu.main_loop()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        player.stop()
        sys.exit()
