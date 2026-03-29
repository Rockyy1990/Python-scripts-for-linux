#!/usr/bin/env python3
"""
Arch Linux System Manager
TUI · pacman · yay · Python 3.12+
"""

import curses
import subprocess
import sys
import os
from dataclasses import dataclass
from typing import Callable


# ─────────────────────────────────────────────────────────
#  Farb-Konstanten  (Arch Linux Blau-Schema)
# ─────────────────────────────────────────────────────────
COLOR_ACCENT   = 1   # Arch-Blau  (#1793D1)
COLOR_SELECTED = 2   # Ausgewählter Eintrag (invertiert)
COLOR_HEADER   = 3   # Titelzeile
COLOR_FOOTER   = 4   # Fußzeile / Info-Text
COLOR_ERROR    = 5   # Fehlermeldungen / Warnungen
COLOR_INPUT    = 6   # Eingabefeld-Hintergrund
COLOR_BORDER   = 7   # Rahmen & Trennlinien


# ─────────────────────────────────────────────────────────
#  Datenstruktur Menüeintrag
# ─────────────────────────────────────────────────────────
@dataclass
class MenuItem:
    label:     str
    desc:      str
    action:    Callable | None         = None
    submenu:   list["MenuItem"] | None = None
    separator: bool                    = False


# ─────────────────────────────────────────────────────────
#  Farben initialisieren – Arch Linux Blau (#1793D1)
# ─────────────────────────────────────────────────────────
def init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()

    if curses.can_change_color() and curses.COLORS >= 256:
        # #1793D1 = RGB(23, 147, 209) → curses 0–1000-Skala: (90, 576, 820)
        curses.init_color(9,   90,  576,  820)   # Arch-Blau
        curses.init_color(10,  50,  300,  560)   # Dunkel-Blau
        ARCH_BLUE = 9
        DARK_BLUE = 10
    else:
        ARCH_BLUE = curses.COLOR_CYAN
        DARK_BLUE = curses.COLOR_BLUE

    BG = -1  # transparenter Terminal-Hintergrund

    curses.init_pair(COLOR_ACCENT,   ARCH_BLUE,           BG)
    curses.init_pair(COLOR_SELECTED, curses.COLOR_BLACK,  ARCH_BLUE)
    curses.init_pair(COLOR_HEADER,   ARCH_BLUE,           BG)
    curses.init_pair(COLOR_FOOTER,   DARK_BLUE,           BG)
    curses.init_pair(COLOR_ERROR,    curses.COLOR_RED,    BG)
    curses.init_pair(COLOR_INPUT,    curses.COLOR_BLACK,  ARCH_BLUE)
    curses.init_pair(COLOR_BORDER,   DARK_BLUE,           BG)


# ─────────────────────────────────────────────────────────
#  Hilfs-Funktion: Text sicher in Fenster schreiben
# ─────────────────────────────────────────────────────────
def _safe_addstr(
    win: curses.window, y: int, x: int, text: str, max_width: int
) -> None:
    """Schreibt text ab (y, x), abgeschnitten auf max_width Zeichen.
    Ignoriert curses.error am Fensterrand (z. B. rechte untere Ecke)."""
    try:
        win.addstr(y, x, text[:max(0, max_width)])
    except curses.error:
        pass


# ─────────────────────────────────────────────────────────
#  Befehl ausführen  (verlässt curses temporär)
# ─────────────────────────────────────────────────────────
def run_command(stdscr: curses.window, cmd: list[str], title: str) -> int:
    curses.endwin()

    sep = "═" * 60
    print(f"\n{sep}")
    print(f"  ▶  {title}")
    print(f"  CMD: {' '.join(cmd)}")
    print(f"{sep}\n")

    result = subprocess.run(cmd)

    print(f"\n{sep}")
    if result.returncode == 0:
        print("  [✓] Erfolgreich abgeschlossen.")
    else:
        print(f"  [✗] Fehler – Exit-Code: {result.returncode}")
    print(sep)
    input("\n  [Enter] drücken, um zurückzukehren … ")

    stdscr.refresh()
    return result.returncode


# ─────────────────────────────────────────────────────────
#  Nachrichten-Dialog  (reine Info, nur Enter/Leertaste)
# ─────────────────────────────────────────────────────────
def message_dialog(stdscr: curses.window, title: str, message: str) -> None:
    height, width = stdscr.getmaxyx()
    dh, dw = 7, min(62, width - 4)
    sy = (height - dh) // 2
    sx = (width  - dw) // 2

    win = curses.newwin(dh, dw, sy, sx)
    win.bkgd(" ", curses.color_pair(COLOR_ACCENT))
    win.border()

    win.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
    _safe_addstr(win, 1, 2, f"  {title}", dw - 4)
    win.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)

    win.attron(curses.color_pair(COLOR_ACCENT))
    _safe_addstr(win, 3, 2, f"  {message}", dw - 4)
    win.attroff(curses.color_pair(COLOR_ACCENT))

    win.attron(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
    _safe_addstr(win, 5, 2, "  [Enter] OK  ", dw - 4)
    win.attroff(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
    win.refresh()

    while True:
        key = win.getch()
        if key in (10, curses.KEY_ENTER, ord(" "), 27):
            break

    del win
    stdscr.touchwin()
    stdscr.refresh()


# ─────────────────────────────────────────────────────────
#  Eingabe-Dialog
# ─────────────────────────────────────────────────────────
def input_dialog(stdscr: curses.window, prompt: str) -> str:
    height, width = stdscr.getmaxyx()
    dh, dw = 7, min(62, width - 4)
    sy = (height - dh) // 2
    sx = (width  - dw) // 2

    win = curses.newwin(dh, dw, sy, sx)
    win.bkgd(" ", curses.color_pair(COLOR_ACCENT))
    win.border()

    win.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
    _safe_addstr(win, 1, 2, f"  {prompt}", dw - 4)
    win.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)

    _safe_addstr(win, 3, 2, "  ▶ ", dw - 4)
    win.attron(curses.color_pair(COLOR_INPUT))
    _safe_addstr(win, 3, 6, " " * (dw - 8), dw - 8)
    win.attroff(curses.color_pair(COLOR_INPUT))
    win.refresh()

    curses.echo()
    curses.curs_set(1)
    raw = win.getstr(3, 6, dw - 8)
    curses.noecho()
    curses.curs_set(0)

    del win
    stdscr.touchwin()
    stdscr.refresh()
    return raw.decode("utf-8").strip()


# ─────────────────────────────────────────────────────────
#  Bestätigungs-Dialog
# ─────────────────────────────────────────────────────────
def confirm_dialog(stdscr: curses.window, message: str) -> bool:
    height, width = stdscr.getmaxyx()
    dh, dw = 7, min(58, width - 4)
    sy = (height - dh) // 2
    sx = (width  - dw) // 2

    win = curses.newwin(dh, dw, sy, sx)
    win.bkgd(" ", curses.color_pair(COLOR_ACCENT))
    win.border()

    win.attron(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
    _safe_addstr(win, 1, 2, "  !! Bestätigung erforderlich", dw - 4)
    win.attroff(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)

    win.attron(curses.color_pair(COLOR_ACCENT))
    _safe_addstr(win, 3, 2, f"  {message}", dw - 4)
    win.attroff(curses.color_pair(COLOR_ACCENT))

    win.attron(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
    _safe_addstr(win, 5, 2, "  [J/Y] Ja        [N/Q] Nein  ", dw - 4)
    win.attroff(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
    win.refresh()

    while True:
        key = win.getch()
        ch  = chr(key).lower() if 0 < key < 256 else ""
        if ch in ("j", "y"):
            del win; stdscr.touchwin(); stdscr.refresh()
            return True
        if ch in ("n", "q") or key == 27:
            del win; stdscr.touchwin(); stdscr.refresh()
            return False


# ─────────────────────────────────────────────────────────
#  Menü zeichnen
# ─────────────────────────────────────────────────────────
def draw_menu(
    stdscr:     curses.window,
    items:      list[MenuItem],
    selected:   int,
    title:      str,
    breadcrumb: str = "",
    offset:     int = 0,
) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    inner_w = width - 4   # nutzbare Breite ohne Rahmen-Zeichen

    # ── Rahmen ───────────────────────────────────────────
    stdscr.attron(curses.color_pair(COLOR_BORDER))
    stdscr.border()
    stdscr.attroff(curses.color_pair(COLOR_BORDER))

    # ── Header ───────────────────────────────────────────
    stdscr.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
    _safe_addstr(stdscr, 1, 2, "   Arch Linux System Manager", inner_w)
    _safe_addstr(stdscr, 2, 2, "─" * inner_w, inner_w)
    heading = f"   ▸ {breadcrumb}" if breadcrumb else f"   {title}"
    _safe_addstr(stdscr, 3, 2, heading, inner_w)
    stdscr.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)

    # ── Einträge ─────────────────────────────────────────
    menu_start = 5
    max_rows   = height - menu_start - 4
    visible    = items[offset: offset + max_rows]

    for idx, item in enumerate(visible):
        y       = menu_start + idx
        abs_idx = idx + offset    # absoluter Index in items[]

        if item.separator:
            stdscr.attron(curses.color_pair(COLOR_BORDER))
            _safe_addstr(stdscr, y, 4, "─" * (inner_w - 2), inner_w - 2)
            stdscr.attroff(curses.color_pair(COLOR_BORDER))
            continue

        is_sel = abs_idx == selected
        prefix = "  ▶ " if is_sel else "    "
        label  = f"{prefix}{item.label}"

        if is_sel:
            stdscr.attron(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
            _safe_addstr(stdscr, y, 2, label, inner_w)
            pad = inner_w - len(label)
            if pad > 0:
                _safe_addstr(stdscr, y, 2 + len(label), " " * pad, pad)
            stdscr.attroff(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
        else:
            stdscr.attron(curses.color_pair(COLOR_ACCENT))
            _safe_addstr(stdscr, y, 2, label, inner_w)
            stdscr.attroff(curses.color_pair(COLOR_ACCENT))

    # ── Scroll-Indikatoren ───────────────────────────────
    mid = width // 2
    if offset > 0:
        stdscr.attron(curses.color_pair(COLOR_BORDER) | curses.A_BOLD)
        _safe_addstr(stdscr, menu_start - 1, mid - 1, " ▲ ", 3)
        stdscr.attroff(curses.color_pair(COLOR_BORDER) | curses.A_BOLD)
    if offset + max_rows < len(items):
        stdscr.attron(curses.color_pair(COLOR_BORDER) | curses.A_BOLD)
        _safe_addstr(stdscr, menu_start + max_rows, mid - 1, " ▼ ", 3)
        stdscr.attroff(curses.color_pair(COLOR_BORDER) | curses.A_BOLD)

    # ── Beschreibungs-Zeile ──────────────────────────────
    if 0 <= selected < len(items) and not items[selected].separator:
        desc_y = height - 4
        stdscr.attron(curses.color_pair(COLOR_BORDER))
        _safe_addstr(stdscr, desc_y - 1, 2, "─" * inner_w, inner_w)
        stdscr.attroff(curses.color_pair(COLOR_BORDER))
        stdscr.attron(curses.color_pair(COLOR_FOOTER))
        _safe_addstr(stdscr, desc_y, 2, f"  ℹ  {items[selected].desc}", inner_w)
        stdscr.attroff(curses.color_pair(COLOR_FOOTER))

    # ── Footer ───────────────────────────────────────────
    footer = "  [↑↓] Navigieren   [Enter] Auswählen   [1–9] Schnellwahl   [Q] Zurück"
    stdscr.attron(curses.color_pair(COLOR_FOOTER) | curses.A_DIM)
    _safe_addstr(stdscr, height - 2, 2, footer, inner_w)
    stdscr.attroff(curses.color_pair(COLOR_FOOTER) | curses.A_DIM)

    stdscr.refresh()


# ─────────────────────────────────────────────────────────
#  Generische Menü-Schleife  (Scroll + Schnellwahl)
# ─────────────────────────────────────────────────────────
def _build_quick_map(items: list[MenuItem], selectable: list[int]) -> dict[int, int]:
    """Bildet Zifferntasten '1'–'9' und 'Q' auf selectable-Indizes ab."""
    qmap: dict[int, int] = {}
    for si, abs_i in enumerate(selectable):
        lbl = items[abs_i].label.strip()
        if len(lbl) >= 3 and lbl[0] == "[" and lbl[2] == "]":
            ch = lbl[1].lower()
            qmap[ord(ch)] = si
            if ch.isalpha():
                qmap[ord(ch.upper())] = si
    return qmap


def run_menu(
    stdscr:     curses.window,
    items:      list[MenuItem],
    title:      str,
    breadcrumb: str = "",
) -> None:
    selectable = [i for i, m in enumerate(items) if not m.separator]
    if not selectable:
        return

    quick_map = _build_quick_map(items, selectable)
    pos       = 0    # Index in selectable[]
    offset    = 0    # Scroll-Offset in items[]

    def _visible_rows() -> int:
        h, _ = stdscr.getmaxyx()
        return max(1, h - 5 - 4)   # menu_start=5, Fußbereich=4

    while True:
        selected = selectable[pos]

        # Scroll-Offset nachführen (selected immer sichtbar halten)
        vr = _visible_rows()
        if selected < offset:
            offset = selected
        elif selected >= offset + vr:
            offset = selected - vr + 1

        draw_menu(stdscr, items, selected, title, breadcrumb, offset)
        key = stdscr.getch()

        match key:
            case curses.KEY_UP:
                pos = max(0, pos - 1)
            case curses.KEY_DOWN:
                pos = min(len(selectable) - 1, pos + 1)
            case curses.KEY_HOME:
                pos = 0
            case curses.KEY_END:
                pos = len(selectable) - 1
            case curses.KEY_PPAGE:                          # Bild ↑
                pos = max(0, pos - max(1, vr // 2))
            case curses.KEY_NPAGE:                          # Bild ↓
                pos = min(len(selectable) - 1, pos + max(1, vr // 2))
            case 10 | curses.KEY_ENTER:
                item = items[selected]
                if item.submenu:
                    bc = (
                        f"{breadcrumb} > {item.label}"
                        if breadcrumb
                        else f"{title} > {item.label}"
                    )
                    run_menu(stdscr, item.submenu, item.label, bc)
                elif item.action:
                    item.action()
            case _ if key in quick_map:
                pos = quick_map[key]
            case _ if key in (ord("q"), ord("Q"), 27):
                return


# ─────────────────────────────────────────────────────────
#  Alle Aktionen  (Closures über stdscr)
# ─────────────────────────────────────────────────────────
def make_actions(stdscr: curses.window) -> dict[str, Callable]:

    # ── Update / Upgrade ────────────────────────────────
    def system_sync():
        run_command(stdscr, ["sudo", "pacman", "-Sy"],
                    "Paketdatenbank synchronisieren")

    def system_upgrade_pacman():
        run_command(stdscr, ["sudo", "pacman", "-Syu", "--noconfirm"],
                    "System-Upgrade mit pacman")

    def system_upgrade_yay():
        run_command(stdscr, ["yay", "-Syu", "--noconfirm"],
                    "System-Upgrade mit yay (pacman + AUR)")

    # ── Pakete installieren ──────────────────────────────
    def install_pacman():
        pkg = input_dialog(stdscr, "Paketname eingeben (pacman):")
        if pkg:
            run_command(stdscr, ["sudo", "pacman", "-S", "--noconfirm", pkg],
                        f"Installiere via pacman: {pkg}")

    def install_yay():
        pkg = input_dialog(stdscr, "Paketname eingeben (yay / AUR):")
        if pkg:
            run_command(stdscr, ["yay", "-S", "--noconfirm", pkg],
                        f"Installiere via yay: {pkg}")

    # ── Pakete entfernen ────────────────────────────────
    def remove_pacman():
        pkg = input_dialog(stdscr, "Paketname eingeben (pacman entfernen):")
        if pkg:
            run_command(stdscr, ["sudo", "pacman", "-Rns", "--noconfirm", pkg],
                        f"Entferne via pacman: {pkg}")

    def remove_yay():
        pkg = input_dialog(stdscr, "Paketname eingeben (yay entfernen):")
        if pkg:
            run_command(stdscr, ["yay", "-Rns", "--noconfirm", pkg],
                        f"Entferne via yay: {pkg}")

    # ── Suche ───────────────────────────────────────────
    def search_pkg():
        pkg = input_dialog(stdscr, "Suchbegriff eingeben:")
        if pkg:
            run_command(stdscr, ["yay", "-Ss", pkg],
                        f"Suche nach: {pkg}")

    def list_installed():
        run_command(stdscr, ["pacman", "-Q"],
                    "Alle installierten Pakete auflisten")

    # ── Keyring & Datenbank ─────────────────────────────
    def update_keyring():
        run_command(stdscr,
                    ["sudo", "pacman", "-Sy", "--needed", "archlinux-keyring"],
                    "Arch Linux Keyring aktualisieren")

    def refresh_db():
        run_command(stdscr, ["sudo", "pacman", "-Syy"],
                    "Paketdatenbank erzwungen erneuern")

    def refresh_keys():
        run_command(stdscr, ["sudo", "pacman-key", "--refresh-keys"],
                    "GPG-Schlüssel aktualisieren")

    def populate_keys():
        run_command(stdscr,
                    ["sudo", "pacman-key", "--populate", "archlinux"],
                    "Schlüssel befüllen")

    def init_keyring():
        run_command(stdscr, ["sudo", "pacman-key", "--init"],
                    "Schlüssel initialisieren")

    # ── Cache & Wartung ─────────────────────────────────
    def clean_cache():
        run_command(stdscr, ["sudo", "pacman", "-Sc", "--noconfirm"],
                    "Paket-Cache bereinigen")

    def clean_cache_all():
        if confirm_dialog(stdscr, "Gesamten Cache löschen? (pacman -Scc)"):
            run_command(stdscr, ["sudo", "pacman", "-Scc", "--noconfirm"],
                        "Gesamten Cache löschen")

    def list_orphans():
        run_command(stdscr, ["pacman", "-Qdt"],
                    "Verwaiste Pakete anzeigen")

    def remove_orphans():
        if not confirm_dialog(stdscr, "Alle verwaisten Pakete entfernen?"):
            return
        orphans = subprocess.run(
            ["pacman", "-Qdtq"],
            capture_output=True, text=True
        ).stdout.split()
        if orphans:
            run_command(stdscr,
                        ["sudo", "pacman", "-Rns", "--noconfirm"] + orphans,
                        "Verwaiste Pakete entfernen")
        else:
            message_dialog(stdscr, "Wartung", "Keine verwaisten Pakete gefunden.")

    # ── System ──────────────────────────────────────────
    def system_reboot():
        if confirm_dialog(stdscr, "System jetzt neu starten?"):
            run_command(stdscr, ["sudo", "reboot"],
                        "System wird neu gestartet")

    def system_shutdown():
        if confirm_dialog(stdscr, "System jetzt herunterfahren?"):
            run_command(stdscr, ["sudo", "shutdown", "-h", "now"],
                        "System wird heruntergefahren")

    return {
        "sync":            system_sync,
        "upgrade_pacman":  system_upgrade_pacman,
        "upgrade_yay":     system_upgrade_yay,
        "install_pacman":  install_pacman,
        "install_yay":     install_yay,
        "remove_pacman":   remove_pacman,
        "remove_yay":      remove_yay,
        "search":          search_pkg,
        "list_installed":  list_installed,
        "update_keyring":  update_keyring,
        "refresh_db":      refresh_db,
        "refresh_keys":    refresh_keys,
        "populate_keys":   populate_keys,
        "init_keyring":    init_keyring,
        "clean_cache":     clean_cache,
        "clean_cache_all": clean_cache_all,
        "list_orphans":    list_orphans,
        "remove_orphans":  remove_orphans,
        "reboot":          system_reboot,
        "shutdown":        system_shutdown,
    }


# ─────────────────────────────────────────────────────────
#  Menüstruktur
# ─────────────────────────────────────────────────────────
def build_menu(a: dict[str, Callable]) -> list[MenuItem]:
    return [
        MenuItem(
            label="[1] Update & Upgrade",
            desc="Datenbank synchronisieren und System aktualisieren",
            submenu=[
                MenuItem("[1] Datenbank synchronisieren",
                         "sudo pacman -Sy",
                         action=a["sync"]),
                MenuItem("[2] System-Upgrade (pacman)",
                         "sudo pacman -Syu --noconfirm",
                         action=a["upgrade_pacman"]),
                MenuItem("[3] System-Upgrade (yay)",
                         "yay -Syu --noconfirm  (pacman + AUR)",
                         action=a["upgrade_yay"]),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[2] Pakete installieren",
            desc="Pakete über pacman oder yay installieren",
            submenu=[
                MenuItem("[1] Installieren via pacman",
                         "sudo pacman -S <paket>",
                         action=a["install_pacman"]),
                MenuItem("[2] Installieren via yay (AUR)",
                         "yay -S <paket>",
                         action=a["install_yay"]),
                MenuItem("", "", separator=True),
                MenuItem("[3] Paket suchen",
                         "yay -Ss <suchbegriff>",
                         action=a["search"]),
                MenuItem("[4] Installierte Pakete auflisten",
                         "pacman -Q",
                         action=a["list_installed"]),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[3] Pakete entfernen",
            desc="Pakete über pacman oder yay entfernen",
            submenu=[
                MenuItem("[1] Entfernen via pacman",
                         "sudo pacman -Rns <paket>",
                         action=a["remove_pacman"]),
                MenuItem("[2] Entfernen via yay",
                         "yay -Rns <paket>",
                         action=a["remove_yay"]),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[4] Keyring & Datenbank",
            desc="Schlüssel und Paketdatenbank verwalten",
            submenu=[
                MenuItem("[1] Arch Keyring aktualisieren",
                         "pacman -Sy --needed archlinux-keyring",
                         action=a["update_keyring"]),
                MenuItem("[2] Datenbank erzwungen erneuern",
                         "pacman -Syy",
                         action=a["refresh_db"]),
                MenuItem("", "", separator=True),
                MenuItem("[3] GPG-Schlüssel aktualisieren",
                         "pacman-key --refresh-keys",
                         action=a["refresh_keys"]),
                MenuItem("[4] Schlüssel befüllen",
                         "pacman-key --populate archlinux",
                         action=a["populate_keys"]),
                MenuItem("[5] Schlüssel initialisieren",
                         "pacman-key --init",
                         action=a["init_keyring"]),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[5] Cache & Wartung",
            desc="Cache bereinigen und Orphans verwalten",
            submenu=[
                MenuItem("[1] Cache bereinigen",
                         "pacman -Sc",
                         action=a["clean_cache"]),
                MenuItem("[2] Gesamten Cache löschen",
                         "pacman -Scc",
                         action=a["clean_cache_all"]),
                MenuItem("", "", separator=True),
                MenuItem("[3] Verwaiste Pakete anzeigen",
                         "pacman -Qdt",
                         action=a["list_orphans"]),
                MenuItem("[4] Verwaiste Pakete entfernen",
                         "pacman -Rns $(pacman -Qdtq)",
                         action=a["remove_orphans"]),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[6] System",
            desc="Neustart oder Herunterfahren",
            submenu=[
                MenuItem("[1] Neustart",
                         "sudo reboot",
                         action=a["reboot"]),
                MenuItem("[2] Herunterfahren",
                         "sudo shutdown -h now",
                         action=a["shutdown"]),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[Q] Beenden",
            desc="Programm beenden",
        ),
    ]


# ─────────────────────────────────────────────────────────
#  Hauptfunktion
# ─────────────────────────────────────────────────────────
def main(stdscr: curses.window) -> None:
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)

    init_colors()
    stdscr.bkgd(" ", curses.color_pair(COLOR_ACCENT))

    actions = make_actions(stdscr)
    menu    = build_menu(actions)

    selectable  = [i for i, m in enumerate(menu) if not m.separator]
    quick_map   = _build_quick_map(menu, selectable)
    pos         = 0
    offset      = 0

    def _visible_rows() -> int:
        h, _ = stdscr.getmaxyx()
        return max(1, h - 5 - 4)

    while True:
        selected = selectable[pos]

        vr = _visible_rows()
        if selected < offset:
            offset = selected
        elif selected >= offset + vr:
            offset = selected - vr + 1

        draw_menu(stdscr, menu, selected, "Hauptmenü", offset=offset)
        key = stdscr.getch()

        match key:
            case curses.KEY_UP:
                pos = max(0, pos - 1)
            case curses.KEY_DOWN:
                pos = min(len(selectable) - 1, pos + 1)
            case curses.KEY_HOME:
                pos = 0
            case curses.KEY_END:
                pos = len(selectable) - 1
            case curses.KEY_PPAGE:
                pos = max(0, pos - max(1, vr // 2))
            case curses.KEY_NPAGE:
                pos = min(len(selectable) - 1, pos + max(1, vr // 2))
            case 10 | curses.KEY_ENTER:
                item = menu[selected]
                if item.label.startswith("[Q]"):
                    if confirm_dialog(stdscr, "Programm wirklich beenden?"):
                        return
                elif item.submenu:
                    run_menu(
                        stdscr,
                        item.submenu,
                        item.label,
                        breadcrumb=f"Hauptmenü > {item.label}",
                    )
                elif item.action:
                    item.action()
            case _ if key in quick_map:
                new_pos = quick_map[key]
                item    = menu[selectable[new_pos]]
                if item.label.startswith("[Q]"):
                    if confirm_dialog(stdscr, "Programm wirklich beenden?"):
                        return
                elif item.submenu:
                    run_menu(
                        stdscr,
                        item.submenu,
                        item.label,
                        breadcrumb=f"Hauptmenü > {item.label}",
                    )
                elif item.action:
                    item.action()
                else:
                    pos = new_pos
            case _ if key in (ord("q"), ord("Q"), 27):
                if confirm_dialog(stdscr, "Programm wirklich beenden?"):
                    return


# ─────────────────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    if os.geteuid() == 0:
        print("Bitte NICHT als root starten – sudo wird intern verwendet.")
        sys.exit(1)

    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass

    print("Auf Wiedersehen!\n")
