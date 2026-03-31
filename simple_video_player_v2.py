#!/usr/bin/env python3
# video_player.py
# Interaktiver Terminal-Video-Player für Linux
# Erfordert: ffplay (ffmpeg), PipeWire/PulseAudio
# Unterstützt alle gängigen ffmpeg-Videoformate

import os
import re
import shlex
import subprocess
from pathlib import Path
from urllib.parse import unquote

# ── Farben ────────────────────────────────────────────────────────────────────
ORANGE = "\033[38;5;208m"
CYAN   = "\033[38;5;51m"
GREEN  = "\033[38;5;82m"
YELLOW = "\033[38;5;226m"
RED    = "\033[38;5;196m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Unterstützte Datei-Endungen (für Verzeichnis-Browser) ─────────────────────
SUPPORTED_EXT: frozenset[str] = frozenset({
    ".mp4", ".mkv", ".webm", ".avi",  ".mov",  ".flv",  ".wmv",
    ".m4v", ".ts",  ".mts",  ".m2ts", ".ogv",  ".ogg",  ".3gp",
    ".3g2", ".divx",".xvid", ".vob",  ".mpg",  ".mpeg", ".m2v",
    ".f4v", ".rmvb",".rm",   ".asf",  ".mxf",  ".dv",   ".qt",
    ".hevc",".h264",".h265", ".av1",  ".ivf",  ".nut",  ".mka",
})

# ── Alle von ffplay unterstützten URL-Schemata ────────────────────────────────
URL_SCHEMES: tuple[str, ...] = (
    "http://", "https://",
    "rtmp://", "rtmps://",
    "rtsp://", "rtsps://",
    "ftp://",  "ftps://",
    "udp://",  "rtp://",
    "srt://",  "srtp://",
    "mms://",  "mmsh://",  "mmst://",
    "pipe:",   "fd:",
    "data:",
)

# ── Globaler Zustand ──────────────────────────────────────────────────────────
state: dict = {
    "volume":    100,   # 0–200
    "normalize": False,
}

# ── Eingabe-Bereinigung ───────────────────────────────────────────────────────
def sanitize_input(raw: str) -> str:
    """
    Bereinigt Benutzereingaben für Pfade und URLs.

    Behandelt:
      - führende/nachfolgende Leerzeichen
      - umgebende Anführungszeichen  ("..." oder '...')
      - spitze Klammern              (<...>, Markdown/Discord-Stil)
      - file:// URI                  → normaler Pfad
      - URL-Encoding                 (%20 → Leerzeichen)
      - Tilde-Expansion              (~ → Home-Verzeichnis)
    """
    s = raw.strip()

    # Äußere Anführungszeichen entfernen (einfach oder doppelt)
    if len(s) >= 2 and (
        (s[0] == '"'  and s[-1] == '"') or
        (s[0] == "'"  and s[-1] == "'")
    ):
        s = s[1:-1]

    # Spitze Klammern entfernen <url>
    if len(s) >= 2 and s[0] == "<" and s[-1] == ">":
        s = s[1:-1]

    # file:// URI → lokaler Pfad
    if s.lower().startswith("file://"):
        s = unquote(s[7:])              # file:///home/user/… → /home/user/…
        s = re.sub(r"^//", "/", s)      # sicherstellen: führender Slash

    # URL-kodierte Zeichen dekodieren (nur für lokale Pfade)
    if not is_url(s) and "%" in s:
        s = unquote(s)

    # Tilde expandieren
    if s.startswith("~"):
        s = str(Path(s).expanduser())

    return s


def is_url(s: str) -> bool:
    """True wenn s ein ffplay-kompatibles URL-Schema hat."""
    return s.lower().startswith(URL_SCHEMES)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def clear() -> None:
    os.system("clear" if os.name == "posix" else "cls")


def pause(msg: str = "Weiter mit Enter …") -> None:
    input(f"\n{DIM}{msg}{RESET}")


def vol_bar(vol: int, width: int = 20) -> str:
    """ASCII-Balken für Lautstärke-Anzeige."""
    filled = round(vol / 200 * width)
    bar    = "█" * filled + "░" * (width - filled)
    color  = GREEN if vol <= 100 else YELLOW if vol <= 150 else RED
    return f"{color}[{bar}]{RESET} {vol}%"


def norm_tag() -> str:
    return f"{GREEN}EIN{RESET}" if state["normalize"] else f"{RED}AUS{RESET}"


def find_videos(directory: Path) -> list[Path]:
    """Videodateien im Verzeichnis suchen (nicht rekursiv, sortiert)."""
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
    )


# ── ffplay ────────────────────────────────────────────────────────────────────
def build_ffplay_args(target: str) -> list[str]:
    """
    Baut die ffplay-Argumentliste.

    Lautstärke-Strategie:
      - Normalize AUS, vol ≤ 100  →  natives -volume  (kein Filter-Overhead)
      - Normalize AUS, vol > 100  →  -af volume=X.XXX (Verstärkung)
      - Normalize EIN             →  alles in -af Kette: loudnorm[,volume=X.XXX]
    """
    args: list[str] = ["ffplay", "-autoexit", "-loglevel", "warning"]
    audio_filters: list[str] = []
    vol = state["volume"]

    if state["normalize"]:
        # EBU R128 – Normalisierung zuerst, dann Lautstärke anpassen
        audio_filters.append("loudnorm=I=-23:LRA=7:TP=-2")
        if vol != 100:
            audio_filters.append(f"volume={vol / 100.0:.3f}")
    else:
        if vol < 100:
            # Natives ffplay-Volume (0–100), kein Filter-Overhead
            args += ["-volume", str(vol)]
        elif vol > 100:
            # Verstärkung über Audio-Filter
            audio_filters.append(f"volume={vol / 100.0:.3f}")
        # vol == 100 → keine zusätzlichen Argumente nötig

    if audio_filters:
        args += ["-af", ",".join(audio_filters)]

    args.append(target)
    return args


def run_ffplay(target: str) -> None:
    """Startet ffplay mit den aktuellen Einstellungen."""
    args = build_ffplay_args(target)
    print(f"\n{DIM}$ {shlex.join(args)}{RESET}\n")
    try:
        subprocess.run(args, check=False)
    except FileNotFoundError:
        print(f"\n{RED}✗ ffplay nicht gefunden.{RESET} ffmpeg installieren:")
        print("    sudo apt install ffmpeg    # Debian / Ubuntu / Mint")
        print("    sudo pacman -S ffmpeg      # Arch / Manjaro")
        print("    sudo dnf install ffmpeg    # Fedora")
        pause()
    except PermissionError:
        print(f"\n{RED}✗ Keine Berechtigung, ffplay auszuführen.{RESET}")
        pause()
    except Exception as exc:
        print(f"\n{RED}✗ Unerwarteter Fehler: {exc}{RESET}")
        pause()


# ── Untermenü: Datei öffnen ───────────────────────────────────────────────────
def menu_open_file() -> None:
    clear()
    print(f"{ORANGE}{BOLD}── Datei öffnen ──────────────────────────────────────{RESET}\n")
    print(f"{DIM}Pfad mit oder ohne Anführungszeichen / spitze Klammern eingeben.{RESET}\n")

    raw = input("Dateipfad: ").strip()
    if not raw:
        return

    clean = sanitize_input(raw)
    p = Path(clean).resolve()

    if not p.exists():
        print(f"\n{RED}✗ Pfad existiert nicht:{RESET} {p}")
        pause()
        return
    if not p.is_file():
        print(f"\n{RED}✗ Keine reguläre Datei:{RESET} {p}")
        pause()
        return
    if p.suffix.lower() not in SUPPORTED_EXT:
        print(f"\n{YELLOW}⚠ Erweiterung '{p.suffix}' nicht in der bekannten Liste.{RESET}")
        ans = input("Trotzdem versuchen? [j/N] ").strip().lower()
        if ans not in ("j", "ja", "y", "yes"):
            return

    run_ffplay(str(p))


# ── Untermenü: Verzeichnis-Browser ────────────────────────────────────────────
def menu_open_directory() -> None:
    cwd = Path(os.getcwd())

    while True:
        videos = find_videos(cwd)
        clear()
        print(f"{ORANGE}{BOLD}── Verzeichnis-Browser ──────────────────────────────{RESET}\n")
        print(f"  {DIM}Pfad:{RESET} {CYAN}{cwd}{RESET}\n")

        if not videos:
            print(f"  {DIM}(Keine unterstützten Videodateien gefunden){RESET}\n")
        else:
            col_w = 52
            print(f"  {DIM}{'Nr':>3}  {'Dateiname':<{col_w}}  Größe{RESET}")
            print(f"  {DIM}{'─' * 3}  {'─' * col_w}  {'─' * 8}{RESET}")
            for i, v in enumerate(videos, 1):
                size_mb = v.stat().st_size / 1_048_576
                name    = v.name if len(v.name) <= col_w else v.name[:col_w - 1] + "…"
                print(f"  {ORANGE}{i:>3}{RESET}  {name:<{col_w}}  {DIM}{size_mb:>6.1f} MB{RESET}")
            print()

        print(f"  {ORANGE}..{RESET}   Übergeordnetes Verzeichnis")
        print(f"  {ORANGE}cd{RESET}   Verzeichnis wechseln (Pfad eingeben)")
        print(f"  {ORANGE}q {RESET}   Zurück zum Hauptmenü")
        print()

        raw = input(f"{ORANGE}Nr / Aktion: {RESET}").strip()
        if not raw or raw.lower() == "q":
            break

        if raw == "..":
            cwd = cwd.parent
            continue

        if raw.lower() == "cd":
            r = input("Verzeichnis: ").strip()
            if r:
                d = Path(sanitize_input(r)).resolve()
                if d.is_dir():
                    cwd = d
                else:
                    print(f"\n{RED}✗ Kein gültiges Verzeichnis:{RESET} {d}")
                    pause()
            continue

        # Nummer eingegeben?
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(videos):
                run_ffplay(str(videos[idx]))
            else:
                print(f"\n{RED}✗ Ungültige Auswahl (1–{max(len(videos), 1)}).{RESET}")
                pause()
            continue

        # Direkte Pfad- oder Verzeichnis-Eingabe
        clean = sanitize_input(raw)
        candidate = Path(clean).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / clean
        candidate = candidate.resolve()

        if candidate.is_dir():
            cwd = candidate
        elif candidate.is_file():
            if candidate.suffix.lower() not in SUPPORTED_EXT:
                print(f"\n{YELLOW}⚠ Unbekannte Erweiterung '{candidate.suffix}'.{RESET}")
                if input("Trotzdem versuchen? [j/N] ").strip().lower() not in ("j", "ja", "y", "yes"):
                    continue
            run_ffplay(str(candidate))
        else:
            print(f"\n{RED}✗ Nicht gefunden:{RESET} {candidate}")
            pause()


# ── Untermenü: Stream / URL ───────────────────────────────────────────────────
def menu_stream() -> None:
    clear()
    print(f"{ORANGE}{BOLD}── Stream / URL abspielen ─────────────────────────────{RESET}\n")

    # Schemata übersichtlich darstellen
    names = [s.rstrip(":/") for s in URL_SCHEMES]
    line  = "  "
    for name in names:
        candidate = line + f"{CYAN}{name}{RESET}  "
        # Länge ohne ANSI-Codes prüfen
        if len(line) + len(name) + 2 > 62:
            print(line)
            line = f"  {CYAN}{name}{RESET}  "
        else:
            line += f"{CYAN}{name}{RESET}  "
    if line.strip():
        print(line)

    print(f"\n{DIM}Anführungszeichen, spitze Klammern und URL-Encoding werden")
    print(f"automatisch bereinigt.{RESET}\n")

    raw = input("URL eingeben: ").strip()
    if not raw:
        return

    url = sanitize_input(raw)

    if not is_url(url):
        print(f"\n{YELLOW}⚠ Kein bekanntes URL-Schema erkannt.{RESET}")
        ans = input("Trotzdem mit ffplay versuchen? [j/N] ").strip().lower()
        if ans not in ("j", "ja", "y", "yes"):
            return

    run_ffplay(url)


# ── Untermenü: Lautstärke ─────────────────────────────────────────────────────
def menu_volume() -> None:
    while True:
        clear()
        print(f"{ORANGE}{BOLD}── Lautstärke ─────────────────────────────────────────{RESET}\n")
        print(f"  Aktuell : {vol_bar(state['volume'])}")
        print(f"\n  Bereich : {ORANGE}0–100%{RESET} Normal  │  {ORANGE}101–200%{RESET} Verstärkt\n")
        print(f"  {ORANGE}+{RESET}    +5%        {ORANGE}-{RESET}    -5%")
        print(f"  {ORANGE}++{RESET}   +20%       {ORANGE}--{RESET}   -20%")
        print(f"  {ORANGE}r{RESET}    Reset auf 100%")
        print(f"  {ORANGE}q{RESET}    Zurück\n")
        print(f"  Oder direkt einen Wert eingeben {DIM}(0–200){RESET}:")
        print()

        raw = input(f"{ORANGE}Eingabe: {RESET}").strip()
        c   = raw.lower()

        if c in ("q", ""):
            break
        elif c == "r":
            state["volume"] = 100
        elif c == "+":
            state["volume"] = min(200, state["volume"] + 5)
        elif c == "-":
            state["volume"] = max(0,   state["volume"] - 5)
        elif c == "++":
            state["volume"] = min(200, state["volume"] + 20)
        elif c == "--":
            state["volume"] = max(0,   state["volume"] - 20)
        elif raw.isdigit():
            v = int(raw)
            if 0 <= v <= 200:
                state["volume"] = v
            else:
                print(f"\n{RED}✗ Wert muss zwischen 0 und 200 liegen.{RESET}")
                pause()
        else:
            print(f"\n{RED}✗ Unbekannte Eingabe.{RESET}")
            pause()


# ── Untermenü: Formate ────────────────────────────────────────────────────────
def menu_formats() -> None:
    clear()
    print(f"{ORANGE}{BOLD}── Unterstützte Datei-Endungen ────────────────────────{RESET}\n")
    exts  = sorted(SUPPORTED_EXT)
    cols  = 5
    col_w = 10
    for i, ext in enumerate(exts):
        print(f"  {CYAN}{ext:<{col_w}}{RESET}", end="\n" if (i + 1) % cols == 0 else "")
    if len(exts) % cols != 0:
        print()  # Zeilenumbruch wenn letzte Zeile nicht voll
    print(f"\n  {DIM}Hinweis: ffplay spielt alle von ffmpeg unterstützten Formate ab –")
    print(f"  auch Endungen, die hier nicht aufgelistet sind.{RESET}\n")
    pause()


# ── Hauptmenü ─────────────────────────────────────────────────────────────────
def print_main_menu() -> None:
    clear()
    print(f"{ORANGE}{BOLD}  ╔══════════════════════════════════════════════╗")
    print(  "  ║         Simple Video Player  v2.1            ║")
    print(  "  ║      ffplay  +  PipeWire / PulseAudio        ║")
    print(f"  ╚══════════════════════════════════════════════╝{RESET}")
    print()
    print(f"  {ORANGE}1{RESET}  Datei öffnen              {DIM}(direkter Pfad){RESET}")
    print(f"  {ORANGE}2{RESET}  Verzeichnis durchsuchen   {DIM}(Datei auswählen){RESET}")
    print(f"  {ORANGE}3{RESET}  Stream / URL abspielen    {DIM}(alle Schemata){RESET}")
    print()
    print(f"  {ORANGE}v{RESET}  Lautstärke     {vol_bar(state['volume'], width=15)}")
    print(f"  {ORANGE}n{RESET}  Auto-Normalize {norm_tag()}")
    print()
    print(f"  {ORANGE}f{RESET}  Unterstützte Formate")
    print(f"  {ORANGE}q{RESET}  Beenden")
    print()
    print(f"  {DIM}ffplay → Leertaste: Pause · ←/→: ±10s · ↑/↓: ±1min · m: Mute · q: Stopp{RESET}")
    print()


def main() -> None:
    while True:
        print_main_menu()
        # raw NICHT mit .lower() umwandeln – Pfade sind case-sensitiv
        raw = input(f"{ORANGE}  Auswahl: {RESET}").strip()

        if not raw:
            continue

        c = raw.lower()  # nur für Menü-Tasten verwenden

        if c == "q":
            print(f"\n{DIM}Auf Wiedersehen.{RESET}\n")
            break
        elif c == "1":
            menu_open_file()
        elif c == "2":
            menu_open_directory()
        elif c == "3":
            menu_stream()
        elif c == "v":
            menu_volume()
        elif c == "n":
            state["normalize"] = not state["normalize"]
        elif c == "f":
            menu_formats()
        else:
            # Direkteingabe: sanitizen und als URL oder Pfad versuchen
            clean = sanitize_input(raw)

            if is_url(clean):
                run_ffplay(clean)
                continue

            p = Path(clean).resolve()
            if p.is_file():
                run_ffplay(str(p))
            elif p.is_dir():
                os.chdir(p)
                menu_open_directory()
            else:
                print(f"\n{RED}  ✗ Unbekannte Option oder Pfad nicht gefunden: '{raw}'{RESET}")
                pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{DIM}Abgebrochen.{RESET}\n")
