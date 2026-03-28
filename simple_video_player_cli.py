#!/usr/bin/env python3
"""
simple_video_player_cli.py
Terminal-Menü-Videoplayer für Linux.
Unterstützt: mp4, mkv, webm, avi, mov, flv, ts, m4v
Wiedergabe via ffplay (ffmpeg); PipeWire empfohlen für Audio-Routing.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── ANSI-Farben ───────────────────────────────────────────────────────────────
ORANGE = "\033[38;5;208m"
DIM    = "\033[2m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ── Konstanten ────────────────────────────────────────────────────────────────
SUPPORTED_EXT: frozenset[str] = frozenset(
    {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts", ".m4v"}
)
HEADER = f"{ORANGE}{BOLD}▶  Simple Video Player  (ffplay + PipeWire){RESET}"
CONTROLS = (
    f"  {ORANGE}<Nr>{RESET}  Datei abspielen   "
    f"{ORANGE}p{RESET}  Pfad wählen   "
    f"{ORANGE}s{RESET}  Stream-URL\n"
    f"  {ORANGE}r{RESET}   Liste aktualisieren   "
    f"{ORANGE}q{RESET}  Beenden"
)

# ── Tab-Completion für Pfadeingaben (optional, nur wenn readline verfügbar) ───
try:
    import readline

    def _path_completer(text: str, state: int) -> str | None:
        p = Path(text).expanduser()
        base, prefix = (p.parent, p.name) if not text.endswith("/") else (p, "")
        try:
            matches = [
                str(child) + ("/" if child.is_dir() else "")
                for child in base.iterdir()
                if child.name.startswith(prefix)
            ]
        except PermissionError:
            matches = []
        return matches[state] if state < len(matches) else None

    readline.set_completer(_path_completer)
    readline.set_completer_delims(" \t\n;")
    readline.parse_and_bind("tab: complete")
except ImportError:
    pass  # readline ist optional (z. B. auf Windows nicht verfügbar)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def clear_screen() -> None:
    """Bildschirm löschen via ANSI-Escape (schneller als os.system)."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def pause(msg: str = "Enter drücken …") -> None:
    input(f"{DIM}{msg}{RESET} ")


def fmt_size(path: Path) -> str:
    """Dateigröße als lesbaren String (KB / MB / GB)."""
    try:
        b = path.stat().st_size
    except OSError:
        return "?"
    for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if b >= threshold:
            return f"{b / threshold:.1f} {unit}"
    return f"{b} B"


def check_ffplay() -> str:
    """Prüft beim Start einmalig, ob ffplay verfügbar ist."""
    path = shutil.which("ffplay")
    if path is None:
        sys.exit(
            "Fehler: ffplay nicht gefunden. "
            "Bitte ffmpeg installieren (enthält ffplay)."
        )
    return path


# ── Kernfunktionen ────────────────────────────────────────────────────────────
def find_videos(directory: Path) -> list[Path]:
    """
    Scannt das Verzeichnis mit os.scandir() (schneller als Path.iterdir()
    bei großen Verzeichnissen) und gibt sortierte Video-Pfade zurück.
    """
    if not directory.is_dir():
        return []
    videos: list[Path] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if (
                    entry.is_file(follow_symlinks=True)
                    and Path(entry.name).suffix.lower() in SUPPORTED_EXT
                ):
                    videos.append(Path(entry.path))
    except PermissionError:
        pass
    videos.sort()
    return videos


def print_menu(videos: list[Path], cwd: Path) -> None:
    clear_screen()
    print(HEADER)
    print(f"\n{DIM}Verzeichnis:{RESET} {cwd}\n")

    if not videos:
        print(f"{DIM}Keine unterstützten Videodateien gefunden.{RESET}")
    else:
        col_w = len(str(len(videos)))  # Breite der Nummernspalte
        for i, v in enumerate(videos, start=1):
            size = fmt_size(v)
            print(
                f"  {ORANGE}{i:{col_w}d}{RESET}. "
                f"{v.name}  {DIM}({size}){RESET}"
            )

    print(f"\n{CONTROLS}\n")


def run_ffplay(ffplay_bin: str, target: str) -> None:
    """Startet ffplay und wartet bis zur Beendigung."""
    subprocess.run(
        [ffplay_bin, "-autoexit", "-loglevel", "warning", target],
        check=False,
    )


def resolve_path(raw: str) -> tuple[Path | None, str | None]:
    """
    Löst eine Benutzereingabe zu einem gültigen Pfad auf.
    Gibt (Path, 'dir'|'file') oder (None, None) zurück.
    """
    if not raw:
        return None, None
    p = Path(raw).expanduser().resolve()
    if not p.exists():
        print(f"Pfad nicht gefunden: {p}")
        pause()
        return None, None
    if p.is_dir():
        return p, "dir"
    if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
        return p, "file"
    print(f"Nicht unterstütztes Dateiformat: {p.suffix!r}")
    pause()
    return None, None


# ── Hauptschleife ─────────────────────────────────────────────────────────────
def main() -> None:
    ffplay_bin = check_ffplay()
    cwd = Path.cwd()
    videos = find_videos(cwd)

    while True:
        print_menu(videos, cwd)
        raw = input(f"{ORANGE}Auswahl:{RESET} ").strip()

        match raw.lower():
            case "":
                continue

            case "q":
                print("Tschüss!")
                sys.exit(0)

            case "r":
                videos = find_videos(cwd)

            case "s":
                url = input("Stream-URL: ").strip()
                if url:
                    run_ffplay(ffplay_bin, url)

            case "p":
                raw_path = input("Pfad (Datei oder Verzeichnis): ").strip()
                path, kind = resolve_path(raw_path)
                if path is None:
                    continue
                if kind == "dir":
                    cwd = path
                    videos = find_videos(cwd)
                else:
                    run_ffplay(ffplay_bin, str(path))

            case _ if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(videos):
                    run_ffplay(ffplay_bin, str(videos[idx]))
                else:
                    print(f"Ungültige Auswahl (1–{len(videos)}).")
                    pause()

            case _:
                # Freitext als Pfad interpretieren
                path, kind = resolve_path(raw)
                if path is None:
                    print("Unbekannte Eingabe.")
                    pause()
                elif kind == "dir":
                    cwd = path
                    videos = find_videos(cwd)
                else:
                    run_ffplay(ffplay_bin, str(path))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
