#!/usr/bin/env python3
"""
yt-dlp Download Manager (Python-Version)
Audio, Video, Playlist-Downloads und Cookie-Management.

Abhängigkeiten : yt-dlp, ffmpeg
Python-Version : >= 3.10 (wegen match/case)

Verwendung:
    python3 yt-dlp_gui_cli.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

# ── Python-Version prüfen ────────────────────────────────────────────────────

if sys.version_info < (3, 10):
    sys.stderr.write(
        f"Fehler: Python >= 3.10 erforderlich "
        f"(gefunden: {sys.version.split()[0]}).\n"
    )
    sys.exit(1)


# ── Farben (TTY-/NO_COLOR-aware) ─────────────────────────────────────────────

def _colors_enabled() -> bool:
    """Farben aktivieren nur bei TTY, kein NO_COLOR, TERM != dumb."""
    return (
        sys.stdout.isatty()
        and os.environ.get("TERM", "dumb") != "dumb"
        and "NO_COLOR" not in os.environ
    )


_COLOR_ON = _colors_enabled()

# Auf Windows 10+ VT-Verarbeitung aktivieren, damit ANSI-Codes gerendert werden
if _COLOR_ON and os.name == "nt":
    os.system("")


def _c(code: str) -> str:
    return code if _COLOR_ON else ""


class Color:
    """ANSI-Farbcodes. Siehe https://no-color.org/."""

    RESET   = _c("\033[0m")
    BOLD    = _c("\033[1m")
    DIM     = _c("\033[2m")

    RED     = _c("\033[0;31m")
    GREEN   = _c("\033[0;32m")
    YELLOW  = _c("\033[0;33m")
    MAGENTA = _c("\033[0;35m")
    CYAN    = _c("\033[0;36m")

    BRED    = _c("\033[1;31m")
    BGREEN  = _c("\033[1;32m")
    BYELLOW = _c("\033[1;33m")
    BCYAN   = _c("\033[1;36m")
    BWHITE  = _c("\033[1;37m")


# ── Log-Funktionen ───────────────────────────────────────────────────────────

def log_info(msg: str) -> None:
    print(f"{Color.BCYAN}ℹ  {Color.RESET}{msg}")

def log_ok(msg: str) -> None:
    print(f"{Color.BGREEN}✓  {Color.RESET}{Color.GREEN}{msg}{Color.RESET}")

def log_warn(msg: str) -> None:
    print(f"{Color.BYELLOW}⚠  {Color.RESET}{Color.YELLOW}{msg}{Color.RESET}",
          file=sys.stderr)

def log_err(msg: str) -> None:
    print(f"{Color.BRED}✗  {Color.RESET}{Color.RED}{msg}{Color.RESET}",
          file=sys.stderr)

def log_dl(msg: str) -> None:
    print(f"{Color.BCYAN}⬇  {Color.RESET}{Color.CYAN}{msg}{Color.RESET}")

def log_up(msg: str) -> None:
    print(f"{Color.BCYAN}⬆  {Color.RESET}{Color.CYAN}{msg}{Color.RESET}")

def log_hint(msg: str) -> None:
    print(f"   {Color.DIM}{msg}{Color.RESET}")


# ── Konfiguration ────────────────────────────────────────────────────────────

class Config:
    """Zentrale Konfiguration."""

    HOME: Path = Path.home()
    COOKIES_FILE: Path = HOME / ".config" / "yt-dlp" / "cookies.txt"
    DOWNLOAD_DIR: Path = HOME / "Downloads" / "yt-dlp"

    OUTPUT_SINGLE: str = str(DOWNLOAD_DIR / "%(title)s.%(ext)s")
    OUTPUT_PLAYLIST: str = str(
        DOWNLOAD_DIR / "%(playlist)s" / "%(playlist_index)s - %(title)s.%(ext)s"
    )

    # M4A ist der korrekte Container für AAC-Audio
    AUDIO_ARGS: list[str] = [
        "--extract-audio",
        "--audio-format", "m4a",
        "--audio-quality", "0",
    ]

    VIDEO_ARGS: list[str] = [
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
    ]

    PLAYLIST_ARGS: list[str] = ["--yes-playlist"]

    @classmethod
    def initialize(cls) -> None:
        """Verzeichnisse beim Start erstellen."""
        try:
            cls.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            cls.COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log_err(f"Fehler beim Erstellen der Verzeichnisse: {e}")
            sys.exit(1)


class Browser(Enum):
    """Unterstützte Browser für Cookie-Import."""

    FIREFOX  = "firefox"
    VIVALDI  = "vivaldi"
    CHROME   = "chrome"
    CHROMIUM = "chromium"
    BRAVE    = "brave"
    EDGE     = "edge"

    @classmethod
    def get_choices(cls) -> dict[str, "Browser"]:
        return {str(i + 1): browser for i, browser in enumerate(cls)}


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def pause() -> None:
    try:
        input(f"{Color.DIM}Weiter mit Enter ...{Color.RESET}")
    except EOFError:
        print()


# Einfache, robuste URL-Validierung: http(s)://<non-space>
URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)


def is_valid_url(url: str) -> bool:
    return bool(URL_PATTERN.match(url))


def get_url() -> Optional[str]:
    """URL einlesen und validieren. None bei Fehler/leer."""
    try:
        url = input(f"{Color.BWHITE}URL eingeben: {Color.RESET}").strip()
    except EOFError:
        print()
        return None

    if not url:
        log_warn("URL darf nicht leer sein.")
        return None
    if not is_valid_url(url):
        log_warn("Ungültiges URL-Format (erwartet: http:// oder https://).")
        return None
    return url


def get_cookie_args() -> list[str]:
    if Config.COOKIES_FILE.exists():
        return ["--cookies", str(Config.COOKIES_FILE)]
    return []


def check_yt_dlp_installed() -> bool:
    if shutil.which("yt-dlp") is None:
        log_err("'yt-dlp' wurde nicht gefunden.")
        log_hint("Installation: pip install -U yt-dlp")
        return False
    return True


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        log_warn("'ffmpeg' wurde nicht gefunden — Merging/Konvertierung könnte scheitern.")


def run_yt_dlp(args: list[str]) -> bool:
    if not check_yt_dlp_installed():
        return False

    command = ["yt-dlp", *get_cookie_args(), *args]
    try:
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError as e:
        log_err(f"yt-dlp beendet mit Fehlercode {e.returncode}.")
        return False
    except KeyboardInterrupt:
        log_warn("Download abgebrochen (Ctrl+C).")
        return False
    except FileNotFoundError:
        log_err("yt-dlp-Binary nicht ausführbar.")
        return False


def open_directory(path: Path) -> None:
    """Verzeichnis im Dateimanager öffnen (plattformübergreifend)."""
    if not path.exists():
        log_warn(f"Verzeichnis existiert nicht: {path}")
        return

    try:
        match sys.platform:
            case "darwin":
                subprocess.run(["open", str(path)], check=True)
            case "win32":
                # nur auf Windows vorhanden — type-checker via getattr besänftigen
                startfile = getattr(os, "startfile", None)
                if startfile is None:
                    log_err("os.startfile nicht verfügbar.")
                    return
                startfile(str(path))
            case "cygwin":
                subprocess.run(["explorer.exe", str(path)], check=True)
            case _:
                # Linux/BSD: mehrere Dateimanager durchprobieren, bis einer klappt
                file_managers = [
                    "xdg-open", "nautilus", "dolphin", "thunar",
                    "pcmanfm", "nemo", "caja",
                ]
                last_error: Optional[Exception] = None
                for cmd in file_managers:
                    if shutil.which(cmd) is None:
                        continue
                    try:
                        subprocess.run([cmd, str(path)], check=True)
                        return
                    except subprocess.CalledProcessError as e:
                        last_error = e
                        continue
                if last_error is not None:
                    log_warn(f"Konnte Verzeichnis nicht öffnen: {last_error}")
                else:
                    log_warn(
                        "Kein Dateimanager gefunden "
                        f"({', '.join(file_managers)})."
                    )
    except subprocess.CalledProcessError as e:
        log_err(f"Fehler beim Öffnen des Verzeichnisses: {e}")
    except OSError as e:
        log_err(f"OS-Fehler beim Öffnen: {e}")


# ── Download-Funktionen ──────────────────────────────────────────────────────

def _download(
    args: list[str],
    dl_message: str,
    success_message: str,
    needs_ffmpeg: bool = False,
) -> None:
    url = get_url()
    if url is None:
        pause()
        return
    if needs_ffmpeg:
        check_ffmpeg()
    log_dl(dl_message)
    if run_yt_dlp(args + [url]):
        log_ok(success_message)
    pause()


def download_audio() -> None:
    _download(
        Config.AUDIO_ARGS + ["-o", Config.OUTPUT_SINGLE],
        "Lade Audio herunter (M4A/AAC, beste Qualität) …",
        "Download abgeschlossen.",
    )


def download_video() -> None:
    _download(
        Config.VIDEO_ARGS + ["-o", Config.OUTPUT_SINGLE],
        "Lade Video in bester Qualität herunter …",
        "Download abgeschlossen.",
        needs_ffmpeg=True,
    )


def download_audio_and_video() -> None:
    _download(
        Config.VIDEO_ARGS + ["-o", Config.OUTPUT_SINGLE],
        "Lade Audio + Video herunter …",
        "Download abgeschlossen.",
        needs_ffmpeg=True,
    )


def download_playlist_audio() -> None:
    _download(
        Config.PLAYLIST_ARGS + Config.AUDIO_ARGS + ["-o", Config.OUTPUT_PLAYLIST],
        "Lade Playlist (Audio) herunter …",
        "Playlist-Download abgeschlossen.",
    )


def download_playlist_video() -> None:
    _download(
        Config.PLAYLIST_ARGS + Config.VIDEO_ARGS + ["-o", Config.OUTPUT_PLAYLIST],
        "Lade Playlist (Video) herunter …",
        "Playlist-Download abgeschlossen.",
        needs_ffmpeg=True,
    )


# ── Cookie-Management ────────────────────────────────────────────────────────

def import_cookies() -> None:
    if not check_yt_dlp_installed():
        pause()
        return

    print()
    print(f"{Color.BOLD}{Color.BCYAN}Browser auswählen:{Color.RESET}")

    browser_choices = Browser.get_choices()
    for key, browser in browser_choices.items():
        print(f"  {Color.BGREEN}{key}{Color.RESET}) {browser.value.capitalize()}")
    print(f"  {Color.BRED}0{Color.RESET}) {Color.DIM}Abbrechen{Color.RESET}")

    try:
        choice = input(f"{Color.BWHITE}Wahl: {Color.RESET}").strip()
    except EOFError:
        print()
        return

    if choice == "0":
        return

    browser = browser_choices.get(choice)
    if browser is None:
        log_warn("Ungültige Auswahl.")
        pause()
        return

    browser_name = browser.value.capitalize()
    log_dl(f"Importiere Cookies von {browser_name} …")

    cmd = [
        "yt-dlp",
        "--cookies-from-browser", browser.value,
        "--cookies", str(Config.COOKIES_FILE),
        "--skip-download",
        "--quiet",
        "--no-warnings",
        "https://www.youtube.com",
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        log_ok(f"Cookies von {browser_name} erfolgreich importiert.")
        log_info(f"Datei: {Config.COOKIES_FILE}")
    except subprocess.CalledProcessError as e:
        err = (
            e.stderr.decode(errors="replace").strip()
            if e.stderr else "Unbekannter Fehler"
        )
        log_err(f"Fehler beim Importieren der {browser_name}-Cookies: {err}")
        log_hint("Tipp: Browser vollständig schließen und erneut versuchen.")
    pause()


def update_yt_dlp() -> None:
    if not check_yt_dlp_installed():
        pause()
        return

    log_up("Aktualisiere yt-dlp …")
    try:
        subprocess.run(["yt-dlp", "-U"], check=True)
        log_ok("yt-dlp erfolgreich aktualisiert.")
    except subprocess.CalledProcessError as e:
        log_err(f"Fehler beim Update (Fehlercode {e.returncode}).")
        log_hint("Tipp: Bei pip-Installationen: 'pip install -U yt-dlp'")
    pause()


# ── Menü ─────────────────────────────────────────────────────────────────────

class MenuEntry:
    __slots__ = ("key", "label", "hint", "key_color", "action")

    def __init__(
        self,
        key: str,
        label: str,
        hint: str,
        key_color: str,
        action: Optional[Callable[[], None]],
    ) -> None:
        self.key = key
        self.label = label
        self.hint = hint
        self.key_color = key_color
        self.action = action


class Menu:
    """Menü-Definition und -Dispatch."""

    ENTRIES: list[MenuEntry] = [
        MenuEntry("1", "Audio herunterladen",             "(M4A/AAC, beste Qualität)", Color.BGREEN,  download_audio),
        MenuEntry("2", "Video herunterladen",             "(beste Qualität, MP4)",     Color.BGREEN,  download_video),
        MenuEntry("3", "Audio + Video herunterladen",     "(beste Qualität, MP4)",     Color.BGREEN,  download_audio_and_video),
        MenuEntry("4", "Playlist herunterladen",          "(Audio, M4A)",              Color.BGREEN,  download_playlist_audio),
        MenuEntry("5", "Playlist herunterladen",          "(Video, MP4)",              Color.BGREEN,  download_playlist_video),
        MenuEntry("6", "Cookies aus Browser importieren", "",                          Color.BYELLOW, import_cookies),
        MenuEntry("7", "yt-dlp aktualisieren",            "",                          Color.BYELLOW, update_yt_dlp),
        MenuEntry("8", "Download-Verzeichnis öffnen",     "",                          Color.BCYAN,   None),
        MenuEntry("9", "Beenden",                         "",                          Color.BRED,    None),
    ]

    WIDTH = 52

    @staticmethod
    def show() -> None:
        line = "═" * Menu.WIDTH
        print(f"{Color.BCYAN}{line}{Color.RESET}")
        print(f"{Color.BOLD}{Color.BWHITE}"
              f"{'yt-dlp Download Manager'.center(Menu.WIDTH)}"
              f"{Color.RESET}")
        print(f"{Color.BCYAN}{line}{Color.RESET}")

        for e in Menu.ENTRIES:
            label_part = f"{e.label:<32}"
            hint_part = f"{Color.DIM}{e.hint}{Color.RESET}" if e.hint else ""
            print(f"  {e.key_color}{e.key}{Color.RESET})  {label_part} {hint_part}")

        print(f"{Color.BCYAN}{line}{Color.RESET}")

        if Config.COOKIES_FILE.exists():
            cookie_status = f"{Color.GREEN}✓ vorhanden{Color.RESET}"
        else:
            cookie_status = f"{Color.RED}✗ nicht gesetzt{Color.RESET}"

        print(f"  {Color.BOLD}Cookies{Color.RESET} : {cookie_status}")
        print(f"  {Color.BOLD}Ziel{Color.RESET}    : "
              f"{Color.MAGENTA}{Config.DOWNLOAD_DIR}{Color.RESET}")
        print(f"{Color.BCYAN}{line}{Color.RESET}")

    @staticmethod
    def handle_choice(choice: str) -> bool:
        """Gibt False zurück, wenn das Programm beendet werden soll."""
        match choice:
            case "8":
                open_directory(Config.DOWNLOAD_DIR)
                pause()
            case "9":
                print(f"{Color.BGREEN}Auf Wiedersehen! 👋{Color.RESET}")
                return False
            case _:
                for entry in Menu.ENTRIES:
                    if entry.key == choice and entry.action is not None:
                        entry.action()
                        return True
                log_warn("Ungültige Eingabe. Bitte 1–9 wählen.")
                pause()
        return True


# ── Hauptschleife ────────────────────────────────────────────────────────────

def main() -> None:
    Config.initialize()

    while True:
        clear_screen()
        Menu.show()
        try:
            choice = input(
                f"{Color.BWHITE}Option wählen (1–9): {Color.RESET}"
            ).strip()
        except EOFError:
            print()
            break

        if not Menu.handle_choice(choice):
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Color.BYELLOW}Programm abgebrochen.{Color.RESET}")
        sys.exit(130)
    except Exception as e:
        log_err(f"Kritischer Fehler: {e}")
        sys.exit(1)
