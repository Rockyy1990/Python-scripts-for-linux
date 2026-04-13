#!/usr/bin/env python3
"""
yt-dlp Download Manager
Unterstützt Audio, Video, Playlist-Downloads und Cookie-Management.
Erfordert: yt-dlp, ffmpeg

Verwendung:
    python3 yt-dlp-manager.py
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

# ── Logging-Konfiguration ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Konfiguration ────────────────────────────────────────────────────────────

class Config:
    """Zentrale Konfiguration."""

    HOME: Path = Path.home()
    COOKIES_FILE: Path = HOME / ".config" / "yt-dlp" / "cookies.txt"
    DOWNLOAD_DIR: Path = HOME / "Downloads" / "yt-dlp"

    # Ausgabe-Templates
    OUTPUT_SINGLE: str = str(DOWNLOAD_DIR / "%(title)s.%(ext)s")
    OUTPUT_PLAYLIST: str = str(DOWNLOAD_DIR / "%(playlist)s" / "%(playlist_index)s - %(title)s.%(ext)s")

    # yt-dlp Argumente
    AUDIO_ARGS: list[str] = [
        "--extract-audio",
        "--audio-format", "aac",
        "--audio-quality", "0",
    ]

    VIDEO_ARGS: list[str] = [
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
    ]

    @classmethod
    def initialize(cls) -> None:
        """Verzeichnisse beim Start erstellen."""
        try:
            cls.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            cls.COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Verzeichnisse initialisiert: {cls.DOWNLOAD_DIR}")
        except OSError as e:
            logger.error(f"Fehler beim Erstellen der Verzeichnisse: {e}")
            sys.exit(1)


class Browser(Enum):
    """Unterstützte Browser für Cookie-Import."""

    FIREFOX = "firefox"
    VIVALDI = "vivaldi"
    CHROME = "chrome"
    CHROMIUM = "chromium"
    BRAVE = "brave"
    EDGE = "edge"

    @classmethod
    def get_choices(cls) -> dict[str, Browser]:
        """Gibt ein Dict mit Menü-Nummern und Browser-Enums zurück."""
        return {str(i + 1): browser for i, browser in enumerate(cls)}


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def clear_screen() -> None:
    """Bildschirm plattformunabhängig leeren."""
    os.system("cls" if os.name == "nt" else "clear")


def pause() -> None:
    """Auf Enter-Taste warten."""
    input("Weiter mit Enter ...")


def get_url() -> Optional[str]:
    """URL vom Benutzer einlesen und validieren."""
    url = input("URL eingeben: ").strip()

    if not url:
        logger.warning("URL darf nicht leer sein.")
        return None

    if not is_valid_url(url):
        logger.warning("Ungültiges URL-Format.")
        return None

    return url


def is_valid_url(url: str) -> bool:
    """Validiert, ob die URL ein gültiges Format hat."""
    # Akzeptiert http:// und https:// URLs
    pattern = r"^https?://[^\s/$.?#].[^\s]*$"
    return bool(re.match(pattern, url, re.IGNORECASE))


def get_cookie_args() -> list[str]:
    """Cookie-Argumente zurückgeben, falls die Datei existiert."""
    if Config.COOKIES_FILE.exists():
        return ["--cookies", str(Config.COOKIES_FILE)]
    return []


def check_yt_dlp_installed() -> bool:
    """Prüft, ob yt-dlp installiert ist."""
    if shutil.which("yt-dlp") is None:
        logger.error("'yt-dlp' wurde nicht gefunden. Bitte installieren: pip install -U yt-dlp")
        return False
    return True


def run_yt_dlp(args: list[str]) -> bool:
    """
    yt-dlp mit den angegebenen Argumenten ausführen.

    Args:
        args: Liste der yt-dlp Argumente

    Returns:
        True bei Erfolg, False bei Fehler
    """
    if not check_yt_dlp_installed():
        return False

    command = ["yt-dlp"] + get_cookie_args() + args

    try:
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"yt-dlp beendet mit Fehlercode {e.returncode}.")
        return False
    except KeyboardInterrupt:
        logger.warning("Download abgebrochen (Ctrl+C).")
        return False


def open_directory(path: Path) -> None:
    """Download-Verzeichnis im Dateimanager öffnen."""
    if not path.exists():
        logger.error(f"Verzeichnis existiert nicht: {path}")
        return

    try:
        match sys.platform:
            case "darwin":
                # macOS
                subprocess.run(["open", str(path)], check=True)
            case "win32":
                # Windows
                os.startfile(str(path))  # type: ignore[attr-defined]
            case "cygwin":
                # WSL/Cygwin
                subprocess.run(["explorer.exe", str(path)], check=True)
            case _:
                # Linux - mehrere Dateimanager versuchen
                opened = False
                for cmd in ["xdg-open", "nautilus", "dolphin", "thunar", "pcmanfm"]:
                    if shutil.which(cmd):
                        subprocess.run([cmd, str(path)], check=True)
                        opened = True
                        break

                if not opened:
                    logger.error("Kein Dateimanager gefunden (xdg-open, nautilus, dolphin, thunar, pcmanfm).")
    except subprocess.CalledProcessError as e:
        logger.error(f"Fehler beim Öffnen des Verzeichnisses: {e}")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler: {e}")


# ── Download-Funktionen ──────────────────────────────────────────────────────

def download_audio() -> None:
    """Einzelne URL als High-Quality AAC-Audio herunterladen."""
    url = get_url()
    if not url:
        pause()
        return

    logger.info("Lade Audio herunter …")
    if run_yt_dlp(Config.AUDIO_ARGS + ["-o", Config.OUTPUT_SINGLE, url]):
        logger.info("✓ Download abgeschlossen.")
    pause()


def download_video() -> None:
    """Einzelne URL als Video in bester Qualität herunterladen."""
    url = get_url()
    if not url:
        pause()
        return

    logger.info("Lade Video in bester Qualität herunter …")
    if run_yt_dlp(Config.VIDEO_ARGS + ["-o", Config.OUTPUT_SINGLE, url]):
        logger.info("✓ Download abgeschlossen.")
    pause()


def download_audio_and_video() -> None:
    """Audio und Video gemeinsam in bester Qualität herunterladen."""
    url = get_url()
    if not url:
        pause()
        return

    logger.info("Lade Audio + Video herunter …")
    if run_yt_dlp(Config.VIDEO_ARGS + ["-o", Config.OUTPUT_SINGLE, url]):
        logger.info("✓ Download abgeschlossen.")
    pause()


def download_playlist_audio() -> None:
    """Playlist als AAC-Audio herunterladen."""
    url = get_url()
    if not url:
        pause()
        return

    logger.info("Lade Playlist (Audio) herunter …")
    if run_yt_dlp(Config.AUDIO_ARGS + ["-o", Config.OUTPUT_PLAYLIST, url]):
        logger.info("✓ Playlist-Download abgeschlossen.")
    pause()


def download_playlist_video() -> None:
    """Playlist als Video in bester Qualität herunterladen."""
    url = get_url()
    if not url:
        pause()
        return

    logger.info("Lade Playlist (Video) herunter …")
    if run_yt_dlp(Config.VIDEO_ARGS + ["-o", Config.OUTPUT_PLAYLIST, url]):
        logger.info("✓ Playlist-Download abgeschlossen.")
    pause()


# ── Cookie-Management ────────────────────────────────────────────────────────

def import_cookies() -> None:
    """Cookies aus einem unterstützten Browser importieren."""
    if not check_yt_dlp_installed():
        pause()
        return

    print("Browser auswählen:")
    browser_choices = Browser.get_choices()

    for key, browser in browser_choices.items():
        print(f"  {key}) {browser.value.capitalize()}")
    print(f"  {len(browser_choices) + 1}) Abbrechen")

    choice = input("Wahl: ").strip()

    if choice == str(len(browser_choices) + 1):
        return

    browser = browser_choices.get(choice)
    if not browser:
        logger.warning("Ungültige Auswahl.")
        pause()
        return

    logger.info(f"Importiere Cookies von {browser.value.capitalize()} …")
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", browser.value,
        "--cookies", str(Config.COOKIES_FILE),
        "https://www.youtube.com",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"✓ Cookies von {browser.value.capitalize()} erfolgreich importiert.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Fehler beim Importieren der {browser.value.capitalize()}-Cookies: {e.stderr.decode() if e.stderr else 'Unbekannter Fehler'}")
    pause()


def update_yt_dlp() -> None:
    """yt-dlp auf die neueste Version aktualisieren."""
    if not check_yt_dlp_installed():
        pause()
        return

    logger.info("Aktualisiere yt-dlp …")
    try:
        subprocess.run(["yt-dlp", "-U"], check=True)
        logger.info("✓ yt-dlp erfolgreich aktualisiert.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Fehler beim Update: Fehlercode {e.returncode}")
    pause()


# ── Menü ─────────────────────────────────────────────────────────────────────

class Menu:
    """Menü-Management."""

    ENTRIES: list[tuple[str, str, Optional[Callable[[], None]]]] = [
        ("1", "Audio herunterladen          (AAC, beste Qualität)", download_audio),
        ("2", "Video herunterladen          (beste Qualität, MP4)", download_video),
        ("3", "Audio + Video herunterladen  (beste Qualität, MP4)", download_audio_and_video),
        ("4", "Playlist herunterladen       (Audio, AAC)", download_playlist_audio),
        ("5", "Playlist herunterladen       (Video, MP4)", download_playlist_video),
        ("6", "Cookies aus Browser importieren", import_cookies),
        ("7", "yt-dlp aktualisieren", update_yt_dlp),
        ("8", "Download-Verzeichnis öffnen", None),
        ("9", "Beenden", None),
    ]

    @staticmethod
    def show() -> None:
        """Hauptmenü ausgeben."""
        width = 56
        separator = "═" * width

        print(f"{separator}")
        print("yt-dlp Download Manager".center(width))
        print(separator)

        for key, label, _ in Menu.ENTRIES:
            print(f"  {key})  {label}")

        print(separator)

        cookie_status = "✓ vorhanden" if Config.COOKIES_FILE.exists() else "✗ nicht gesetzt"
        print(f"  Cookies : {cookie_status}")
        print(f"  Ziel    : {Config.DOWNLOAD_DIR}")
        print(separator)

    @staticmethod
    def handle_choice(choice: str) -> bool:
        """
        Menü-Auswahl verarbeiten.

        Args:
            choice: Benutzer-Eingabe

        Returns:
            False wenn Programm beendet werden soll, sonst True
        """
        match choice:
            case "8":
                open_directory(Config.DOWNLOAD_DIR)
                pause()
            case "9":
                print("Auf Wiedersehen! 👋")
                return False
            case _:
                # Suche nach passender Aktion
                for key, _, action in Menu.ENTRIES:
                    if key == choice and action:
                        action()
                        return True

                logger.warning("Ungültige Eingabe. Bitte 1–9 wählen.")
                pause()

        return True


# ── Hauptschleife ─────────────────────────────────────────────────────────────

def main() -> None:
    """Programmschleife starten."""
    Config.initialize()

    while True:
        clear_screen()
        Menu.show()
        choice = input("Option wählen (1–9): ").strip()

        if not Menu.handle_choice(choice):
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Programm abgebrochen.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Kritischer Fehler: {e}", exc_info=True)
        sys.exit(1)
