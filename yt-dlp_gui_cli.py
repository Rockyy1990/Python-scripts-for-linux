#!/usr/bin/env python3
"""
yt-dlp Download Manager
Unterstützt Audio, Video, Playlist-Downloads und Cookie-Management.
Erfordert: yt-dlp, ffmpeg
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# ── Konfiguration ────────────────────────────────────────────────────────────

HOME         = Path.home()
COOKIES_FILE = HOME / ".config" / "yt-dlp" / "cookies.txt"
DOWNLOAD_DIR = HOME / "Downloads" / "yt-dlp"

# Verzeichnisse beim Start sicherstellen
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def clear_screen() -> None:
    """Bildschirm plattformunabhängig leeren."""
    os.system("cls" if os.name == "nt" else "clear")


def pause() -> None:
    """Auf Enter-Taste warten."""
    input("Weiter mit Enter ...")


def get_url() -> str | None:
    """URL vom Benutzer einlesen und validieren."""
    url = input("URL eingeben: ").strip()
    if not url:
        print("⚠  Fehler: URL darf nicht leer sein.")
        return None
    return url


def cookie_args() -> list[str]:
    """Cookie-Argumente zurückgeben, falls die Datei existiert."""
    return ["--cookies", str(COOKIES_FILE)] if COOKIES_FILE.exists() else []


def run_yt_dlp(args: list[str]) -> bool:
    """
    yt-dlp mit den angegebenen Argumenten ausführen.
    Gibt True bei Erfolg, False bei Fehler zurück.
    """
    command = ["yt-dlp"] + cookie_args() + args
    try:
        subprocess.run(command, check=True)
        return True
    except FileNotFoundError:
        print("✗  Fehler: 'yt-dlp' wurde nicht gefunden. Bitte installieren.")
    except subprocess.CalledProcessError as exc:
        print(f"✗  yt-dlp beendet mit Fehlercode {exc.returncode}.")
    return False


def open_directory(path: Path) -> None:
    """Download-Verzeichnis im Dateimanager öffnen."""
    try:
        match sys.platform:
            case "darwin":
                subprocess.run(["open", str(path)], check=True)
            case "win32" | "cygwin":
                os.startfile(str(path))          # type: ignore[attr-defined]
            case _:
                subprocess.run(["xdg-open", str(path)], check=True)
    except Exception as exc:
        print(f"⚠  Verzeichnis konnte nicht geöffnet werden: {exc}")
        print(f"   Pfad: {path}")

# ── Download-Funktionen ──────────────────────────────────────────────────────

OUTPUT_SINGLE   = str(DOWNLOAD_DIR / "%(title)s.%(ext)s")
OUTPUT_PLAYLIST = str(DOWNLOAD_DIR / "%(playlist)s" / "%(playlist_index)s - %(title)s.%(ext)s")

AUDIO_ARGS = [
    "--extract-audio",
    "--audio-format", "aac",
    "--audio-quality", "0",
]

VIDEO_ARGS = [
    "-f", "bestvideo+bestaudio/best",
    "--merge-output-format", "mp4",
]


def download_audio() -> None:
    """Einzelne URL als High-Quality AAC-Audio herunterladen."""
    if not (url := get_url()):
        return
    print("⬇  Lade Audio herunter …")
    if run_yt_dlp(AUDIO_ARGS + ["-o", OUTPUT_SINGLE, url]):
        print("✓  Download abgeschlossen.")
    pause()


def download_video() -> None:
    """Einzelne URL als Video in bester Qualität herunterladen."""
    if not (url := get_url()):
        return
    print("⬇  Lade Video in bester Qualität herunter …")
    if run_yt_dlp(VIDEO_ARGS + ["-o", OUTPUT_SINGLE, url]):
        print("✓  Download abgeschlossen.")
    pause()


def download_audio_and_video() -> None:
    """Audio und Video gemeinsam in bester Qualität herunterladen."""
    if not (url := get_url()):
        return
    print("⬇  Lade Audio + Video herunter …")
    if run_yt_dlp(VIDEO_ARGS + ["-o", OUTPUT_SINGLE, url]):
        print("✓  Download abgeschlossen.")
    pause()


def download_playlist_audio() -> None:
    """Playlist als AAC-Audio herunterladen."""
    if not (url := get_url()):
        return
    print("⬇  Lade Playlist (Audio) herunter …")
    if run_yt_dlp(AUDIO_ARGS + ["-o", OUTPUT_PLAYLIST, url]):
        print("✓  Playlist-Download abgeschlossen.")
    pause()


def download_playlist_video() -> None:
    """Playlist als Video in bester Qualität herunterladen."""
    if not (url := get_url()):
        return
    print("⬇  Lade Playlist (Video) herunter …")
    if run_yt_dlp(VIDEO_ARGS + ["-o", OUTPUT_PLAYLIST, url]):
        print("✓  Playlist-Download abgeschlossen.")
    pause()

# ── Cookie-Management ────────────────────────────────────────────────────────

SUPPORTED_BROWSERS: dict[str, str] = {
    "1": "firefox",
    "2": "vivaldi",
    "3": "chrome",
    "4": "chromium",
    "5": "brave",
    "6": "edge",
}


def import_cookies() -> None:
    """Cookies aus einem unterstützten Browser importieren."""
    print("Browser auswählen:")
    for key, name in SUPPORTED_BROWSERS.items():
        print(f"  {key}) {name.capitalize()}")
    print(f"  {len(SUPPORTED_BROWSERS) + 1}) Abbrechen")

    choice = input("Wahl: ").strip()

    if choice == str(len(SUPPORTED_BROWSERS) + 1):
        return

    browser = SUPPORTED_BROWSERS.get(choice)
    if not browser:
        print("⚠  Ungültige Auswahl.")
        pause()
        return

    print(f"⬇  Importiere Cookies von {browser.capitalize()} …")
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", browser,
        "--cookies", str(COOKIES_FILE),
        "https://www.youtube.com",
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"✓  Cookies von {browser.capitalize()} erfolgreich importiert.")
    except FileNotFoundError:
        print("✗  Fehler: 'yt-dlp' wurde nicht gefunden.")
    except subprocess.CalledProcessError:
        print(f"✗  Fehler beim Importieren der {browser.capitalize()}-Cookies.")
    pause()

# ── Menü ─────────────────────────────────────────────────────────────────────

MENU_ENTRIES: list[tuple[str, str]] = [
    ("1", "Audio herunterladen          (AAC, beste Qualität)"),
    ("2", "Video herunterladen          (beste Qualität, MP4)"),
    ("3", "Audio + Video herunterladen  (beste Qualität, MP4)"),
    ("4", "Playlist herunterladen       (Audio, AAC)"),
    ("5", "Playlist herunterladen       (Video, MP4)"),
    ("6", "Cookies aus Browser importieren"),
    ("7", "Download-Verzeichnis öffnen"),
    ("8", "Beenden"),
]


def show_menu() -> None:
    """Hauptmenü ausgeben."""
    width = 52
    print("" + "═" * width)
    print("  yt-dlp Download Manager".center(width))
    print("═" * width)
    for key, label in MENU_ENTRIES:
        print(f"  {key})  {label}")
    print("═" * width)
    cookie_status = "✓ vorhanden" if COOKIES_FILE.exists() else "✗ nicht gesetzt"
    print(f"  Cookies : {cookie_status}")
    print(f"  Ziel    : {DOWNLOAD_DIR}")
    print("═" * width)

# ── Hauptschleife ─────────────────────────────────────────────────────────────

ACTION_MAP: dict[str, object] = {
    "1": download_audio,
    "2": download_video,
    "3": download_audio_and_video,
    "4": download_playlist_audio,
    "5": download_playlist_video,
    "6": import_cookies,
}


def main() -> None:
    """Programmschleife starten."""
    while True:
        clear_screen()
        show_menu()
        choice = input("Option wählen (1–8): ").strip()

        match choice:
            case "7":
                open_directory(DOWNLOAD_DIR)
                pause()
            case "8":
                print("Auf Wiedersehen! 👋")
                break
            case _ if choice in ACTION_MAP:
                ACTION_MAP[choice]()          # type: ignore[operator]
            case _:
                print("⚠  Ungültige Eingabe. Bitte 1–8 wählen.")
                pause()


if __name__ == "__main__":
    main()
