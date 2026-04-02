#!/usr/bin/env python3
"""
yt-dlp Download Manager
Unterstützt Audio, Video, Playlist-Downloads und Cookie-Management.
Erfordert: yt-dlp, ffmpeg
"""

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
    input("\nWeiter mit Enter ...")


def get_url() -> str | None:
    """URL vom Benutzer einlesen und validieren."""
    url = input("  URL eingeben: ").strip()
    if not url:
        print("  ⚠  Fehler: URL darf nicht leer sein.")
        return None
    if not url.startswith(("http://", "https://")):
        print("  ⚠  Warnung: URL beginnt nicht mit http:// oder https://")
        confirm = input("  Trotzdem fortfahren? (j/N): ").strip().lower()
        if confirm != "j":
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
        print("  ✗  Fehler: 'yt-dlp' nicht gefunden. Bitte installieren.")
    except subprocess.CalledProcessError as exc:
        print(f"  ✗  yt-dlp beendet mit Fehlercode {exc.returncode}.")
    return False


def get_yt_dlp_version() -> str:
    """Installierte yt-dlp-Version zurückgeben."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "nicht gefunden"


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
        print(f"  ✓  Verzeichnis geöffnet: {path}")
    except Exception as exc:
        print(f"  ⚠  Verzeichnis konnte nicht geöffnet werden: {exc}")
        print(f"     Pfad: {path}")

# ── Download-Funktionen ──────────────────────────────────────────────────────

OUTPUT_SINGLE   = str(DOWNLOAD_DIR / "%(title)s.%(ext)s")
OUTPUT_PLAYLIST = str(DOWNLOAD_DIR / "%(playlist)s" / "%(playlist_index)s - %(title)s.%(ext)s")

# Nur Audio extrahieren
AUDIO_ARGS = [
    "--extract-audio",
    "--audio-format", "aac",
    "--audio-quality", "0",
]

# Nur Video (kein separater Audiotrack)
VIDEO_ONLY_ARGS = [
    "-f", "bestvideo/best",
    "--merge-output-format", "mp4",
]

# Video mit bestem Audiotrack kombiniert
VIDEO_AUDIO_ARGS = [
    "-f", "bestvideo+bestaudio/best",
    "--merge-output-format", "mp4",
]

# Kein versehentlicher Playlist-Download bei Einzelvideos
NO_PLAYLIST = ["--no-playlist"]


def download_audio() -> None:
    """Einzelne URL als High-Quality AAC-Audio herunterladen."""
    if not (url := get_url()):
        return
    print("\n  ⬇  Lade Audio herunter …")
    if run_yt_dlp(AUDIO_ARGS + NO_PLAYLIST + ["-o", OUTPUT_SINGLE, url]):
        print("  ✓  Download abgeschlossen.")
    pause()


def download_video() -> None:
    """Einzelne URL als reines Video (ohne separaten Audiotrack) herunterladen."""
    if not (url := get_url()):
        return
    print("\n  ⬇  Lade Video (nur Bild) herunter …")
    if run_yt_dlp(VIDEO_ONLY_ARGS + NO_PLAYLIST + ["-o", OUTPUT_SINGLE, url]):
        print("  ✓  Download abgeschlossen.")
    pause()


def download_audio_and_video() -> None:
    """Einzelne URL als Video mit bestem Audiotrack herunterladen."""
    if not (url := get_url()):
        return
    print("\n  ⬇  Lade Video + Audio (beste Qualität) herunter …")
    if run_yt_dlp(VIDEO_AUDIO_ARGS + NO_PLAYLIST + ["-o", OUTPUT_SINGLE, url]):
        print("  ✓  Download abgeschlossen.")
    pause()


def download_playlist_audio() -> None:
    """Playlist als AAC-Audio herunterladen."""
    if not (url := get_url()):
        return
    print("\n  ⬇  Lade Playlist (Audio) herunter …")
    if run_yt_dlp(AUDIO_ARGS + ["-o", OUTPUT_PLAYLIST, url]):
        print("  ✓  Playlist-Download abgeschlossen.")
    pause()


def download_playlist_video() -> None:
    """Playlist als Video + Audio in bester Qualität herunterladen."""
    if not (url := get_url()):
        return
    print("\n  ⬇  Lade Playlist (Video + Audio) herunter …")
    if run_yt_dlp(VIDEO_AUDIO_ARGS + ["-o", OUTPUT_PLAYLIST, url]):
        print("  ✓  Playlist-Download abgeschlossen.")
    pause()

# ── yt-dlp Upgrade ───────────────────────────────────────────────────────────

def upgrade_yt_dlp() -> None:
    """yt-dlp auf die neueste Version aktualisieren."""
    print("\n  🔄  Suche nach Updates für yt-dlp …\n")
    try:
        subprocess.run(["yt-dlp", "-U"], check=True)
        print(f"\n  ✓  yt-dlp ist jetzt auf Version: {get_yt_dlp_version()}")
    except FileNotFoundError:
        print("  ✗  Fehler: 'yt-dlp' nicht gefunden. Bitte installieren.")
    except subprocess.CalledProcessError as exc:
        print(f"  ✗  Update fehlgeschlagen (Code {exc.returncode}).")
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
    width = 40
    print("\n  " + "─" * width)
    print("  Browser auswählen:")
    for key, name in SUPPORTED_BROWSERS.items():
        print(f"    {key})  {name.capitalize()}")
    print(f"    {len(SUPPORTED_BROWSERS) + 1})  Abbrechen")
    print("  " + "─" * width)

    choice = input("  Wahl: ").strip()

    if choice == str(len(SUPPORTED_BROWSERS) + 1):
        return

    browser = SUPPORTED_BROWSERS.get(choice)
    if not browser:
        print("  ⚠  Ungültige Auswahl.")
        pause()
        return

    print(f"\n  ⬇  Importiere Cookies von {browser.capitalize()} …")
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
        print(f"  ✓  Cookies von {browser.capitalize()} erfolgreich importiert.")
    except FileNotFoundError:
        print("  ✗  Fehler: 'yt-dlp' nicht gefunden.")
    except subprocess.CalledProcessError:
        print(f"  ✗  Fehler beim Importieren der {browser.capitalize()}-Cookies.")
    pause()

# ── Menü ─────────────────────────────────────────────────────────────────────

MENU_ENTRIES: list[tuple[str, str]] = [
    ("1", "Audio herunterladen          (AAC, beste Qualität)"),
    ("2", "Video herunterladen          (nur Bild, MP4)"),
    ("3", "Video + Audio herunterladen  (beste Qualität, MP4)"),
    ("4", "Playlist herunterladen       (Audio, AAC)"),
    ("5", "Playlist herunterladen       (Video + Audio, MP4)"),
    ("─", ""),   # Trennlinie
    ("6", "Cookies aus Browser importieren"),
    ("7", "Download-Verzeichnis öffnen"),
    ("8", "yt-dlp aktualisieren         (yt-dlp -U)"),
    ("─", ""),   # Trennlinie
    ("9", "Beenden"),
]

WIDTH = 56


def show_menu() -> None:
    """Hauptmenü ausgeben."""
    version = get_yt_dlp_version()
    cookie_status = "✓ vorhanden" if COOKIES_FILE.exists() else "✗ nicht gesetzt"

    print("╔" + "═" * WIDTH + "╗")
    print("║" + "  yt-dlp Download Manager".center(WIDTH) + "║")
    print("╠" + "═" * WIDTH + "╣")

    for key, label in MENU_ENTRIES:
        if key == "─":
            print("║" + "  " + "┄" * (WIDTH - 2) + "║")
        else:
            line = f"  {key})  {label}"
            print("║" + line.ljust(WIDTH) + "║")

    print("╠" + "═" * WIDTH + "╣")
    print("║" + f"  Version : {version}".ljust(WIDTH) + "║")
    print("║" + f"  Cookies : {cookie_status}".ljust(WIDTH) + "║")
    print("║" + f"  Ziel    : {DOWNLOAD_DIR}".ljust(WIDTH) + "║")
    print("╚" + "═" * WIDTH + "╝")

# ── Hauptschleife ─────────────────────────────────────────────────────────────

ACTION_MAP: dict[str, object] = {
    "1": download_audio,
    "2": download_video,
    "3": download_audio_and_video,
    "4": download_playlist_audio,
    "5": download_playlist_video,
    "6": import_cookies,
    "8": upgrade_yt_dlp,
}


def main() -> None:
    """Programmschleife starten."""
    while True:
        clear_screen()
        show_menu()
        choice = input("\n  Option wählen (1–9): ").strip()

        match choice:
            case "7":
                open_directory(DOWNLOAD_DIR)
                pause()
            case "9":
                print("\n  Auf Wiedersehen! 👋\n")
                break
            case _ if choice in ACTION_MAP:
                clear_screen()
                label = MENU_ENTRIES[[k for k, _ in MENU_ENTRIES].index(choice)][1]
                print(f"\n  ── Aktion: {label} ──\n")
                ACTION_MAP[choice]()          # type: ignore[operator]
            case _:
                print("  ⚠  Ungültige Eingabe. Bitte 1–9 wählen.")
                pause()


if __name__ == "__main__":
    main()
