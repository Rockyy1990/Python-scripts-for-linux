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
#  Farb-Konstanten
# ─────────────────────────────────────────────────────────
COLOR_ORANGE   = 1
COLOR_SELECTED = 2
COLOR_HEADER   = 3
COLOR_FOOTER   = 4
COLOR_ERROR    = 6
COLOR_INPUT    = 7
COLOR_BORDER   = 8


# ─────────────────────────────────────────────────────────
#  Datenstruktur Menüeintrag
# ─────────────────────────────────────────────────────────
@dataclass
class MenuItem:
    label:     str
    desc:      str
    action:    Callable | None       = None
    submenu:   list["MenuItem"] | None = None
    separator: bool                  = False


# ─────────────────────────────────────────────────────────
#  Farben initialisieren
# ─────────────────────────────────────────────────────────
def init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()

    if curses.can_change_color() and curses.COLORS >= 256:
        curses.init_color(9,  1000, 650, 0)   # Orange
        curses.init_color(10,  800, 400, 0)   # Dunkel-Orange
        ORANGE      = 9
        DARK_ORANGE = 10
    else:
        ORANGE      = curses.COLOR_YELLOW
        DARK_ORANGE = curses.COLOR_YELLOW

    BG = -1

    curses.init_pair(COLOR_ORANGE,   ORANGE,             BG)
    curses.init_pair(COLOR_SELECTED, curses.COLOR_BLACK, ORANGE)
    curses.init_pair(COLOR_HEADER,   ORANGE,             BG)
    curses.init_pair(COLOR_FOOTER,   DARK_ORANGE,        BG)
    curses.init_pair(COLOR_ERROR,    curses.COLOR_RED,   BG)
    curses.init_pair(COLOR_INPUT,    curses.COLOR_BLACK, ORANGE)
    curses.init_pair(COLOR_BORDER,   DARK_ORANGE,        BG)


# ─────────────────────────────────────────────────────────
#  Befehl ausführen (verlässt curses temporär)
# ─────────────────────────────────────────────────────────
def run_command(stdscr: curses.window, cmd: list[str], title: str) -> int:
    curses.endwin()

    line = "=" * 60
    print()
    print(line)
    print(f"  >> {title}")
    print(f"  CMD: {' '.join(cmd)}")
    print(line)
    print()

    result = subprocess.run(cmd)

    print()
    print(line)
    if result.returncode == 0:
        print("  [OK] Erfolgreich abgeschlossen.")
    else:
        print(f"  [!!] Fehler - Exit-Code: {result.returncode}")
    print(line)
    input("[Enter] druecken um zurueckzukehren ...")

    stdscr.refresh()
    return result.returncode


# ─────────────────────────────────────────────────────────
#  Eingabe-Dialog
# ─────────────────────────────────────────────────────────
def input_dialog(stdscr: curses.window, prompt: str) -> str:
    height, width = stdscr.getmaxyx()
    dh = 7
    dw = min(60, width - 4)
    sy = (height - dh) // 2
    sx = (width  - dw) // 2

    win = curses.newwin(dh, dw, sy, sx)
    win.bkgd(" ", curses.color_pair(COLOR_ORANGE))
    win.border()

    win.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
    win.addstr(1, 2, prompt[: dw - 4])
    win.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)

    win.addstr(3, 2, "> ")
    win.attron(curses.color_pair(COLOR_INPUT))
    win.addstr(3, 4, " " * (dw - 6))
    win.attroff(curses.color_pair(COLOR_INPUT))
    win.refresh()

    curses.echo()
    curses.curs_set(1)
    raw = win.getstr(3, 4, dw - 6)
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
    dh = 7
    dw = min(56, width - 4)
    sy = (height - dh) // 2
    sx = (width  - dw) // 2

    win = curses.newwin(dh, dw, sy, sx)
    win.bkgd(" ", curses.color_pair(COLOR_ORANGE))
    win.border()

    win.attron(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
    win.addstr(1, 2, "!! Bestaetigung erforderlich")
    win.attroff(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)

    win.attron(curses.color_pair(COLOR_ORANGE))
    win.addstr(3, 2, message[: dw - 4])
    win.attroff(curses.color_pair(COLOR_ORANGE))

    win.attron(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
    win.addstr(5, 2, "  [J] Ja        [N] Nein  ")
    win.attroff(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
    win.refresh()

    while True:
        key = win.getch()
        ch  = chr(key).lower() if 0 < key < 256 else ""
        if ch in ("j", "y"):
            del win
            stdscr.touchwin()
            stdscr.refresh()
            return True
        if ch in ("n", "q"):
            del win
            stdscr.touchwin()
            stdscr.refresh()
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
) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    # Rahmen
    stdscr.attron(curses.color_pair(COLOR_BORDER))
    stdscr.border()
    stdscr.attroff(curses.color_pair(COLOR_BORDER))

    # Header
    stdscr.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
    stdscr.addstr(1, 2, "  Arch Linux System Manager"[: width - 4])
    stdscr.addstr(2, 2, ("-" * (width - 4))[: width - 4])

    if breadcrumb:
        stdscr.addstr(3, 2, f"  > {breadcrumb}"[: width - 4])
    else:
        stdscr.addstr(3, 2, f"  {title}"[: width - 4])

    stdscr.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)

    menu_start = 5

    # Einträge
    visible = items[: height - menu_start - 4]
    for idx, item in enumerate(visible):
        y = menu_start + idx

        if item.separator:
            stdscr.attron(curses.color_pair(COLOR_BORDER))
            stdscr.addstr(y, 4, ("-" * (width - 8))[: width - 8])
            stdscr.attroff(curses.color_pair(COLOR_BORDER))
            continue

        prefix = "  >> " if idx == selected else "     "
        label  = f"{prefix}{item.label}"

        if idx == selected:
            stdscr.attron(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
            stdscr.addstr(y, 2, label[: width - 4])
            pad = width - 4 - len(label)
            if pad > 0:
                stdscr.addstr(y, 2 + len(label), " " * pad)
            stdscr.attroff(curses.color_pair(COLOR_SELECTED) | curses.A_BOLD)
        else:
            stdscr.attron(curses.color_pair(COLOR_ORANGE))
            stdscr.addstr(y, 2, label[: width - 4])
            stdscr.attroff(curses.color_pair(COLOR_ORANGE))

    # Beschreibung
    if 0 <= selected < len(items) and not items[selected].separator:
        desc_y = height - 4
        stdscr.attron(curses.color_pair(COLOR_BORDER))
        stdscr.addstr(desc_y - 1, 2, ("-" * (width - 4))[: width - 4])
        stdscr.attroff(curses.color_pair(COLOR_BORDER))
        stdscr.attron(curses.color_pair(COLOR_FOOTER))
        stdscr.addstr(desc_y, 2, f"  Info: {items[selected].desc}"[: width - 4])
        stdscr.attroff(curses.color_pair(COLOR_FOOTER))

    # Footer
    footer = "  [Auf/Ab] Navigieren   [Enter] Auswaehlen   [Q] Zurueck/Beenden"
    stdscr.attron(curses.color_pair(COLOR_FOOTER) | curses.A_DIM)
    stdscr.addstr(height - 2, 2, footer[: width - 4])
    stdscr.attroff(curses.color_pair(COLOR_FOOTER) | curses.A_DIM)

    stdscr.refresh()


# ─────────────────────────────────────────────────────────
#  Generische Menü-Schleife
# ─────────────────────────────────────────────────────────
def run_menu(
    stdscr:     curses.window,
    items:      list[MenuItem],
    title:      str,
    breadcrumb: str = "",
) -> None:
    selectable = [i for i, m in enumerate(items) if not m.separator]
    pos = 0

    while True:
        selected = selectable[pos]
        draw_menu(stdscr, items, selected, title, breadcrumb)
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
            case 10 | curses.KEY_ENTER:
                item = items[selected]
                if item.submenu:
                    bc = f"{breadcrumb} > {item.label}" if breadcrumb else f"{title} > {item.label}"
                    run_menu(stdscr, item.submenu, item.label, bc)
                elif item.action:
                    item.action()
            case _ if key in (ord("q"), ord("Q"), 27):
                return


# ─────────────────────────────────────────────────────────
#  Alle Aktionen (Closures über stdscr)
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
                    "GPG-Schluessel aktualisieren")

    def populate_keys():
        run_command(stdscr,
                    ["sudo", "pacman-key", "--populate", "archlinux"],
                    "Schluessel befuellen")

    def init_keyring():
        run_command(stdscr, ["sudo", "pacman-key", "--init"],
                    "Schluessel initialisieren")

    # ── Cache & Wartung ─────────────────────────────────
    def clean_cache():
        run_command(stdscr, ["sudo", "pacman", "-Sc", "--noconfirm"],
                    "Paket-Cache bereinigen")

    def clean_cache_all():
        if confirm_dialog(stdscr, "Gesamten Cache loeschen? (pacman -Scc)"):
            run_command(stdscr, ["sudo", "pacman", "-Scc", "--noconfirm"],
                        "Gesamten Cache loeschen")

    def list_orphans():
        run_command(stdscr, ["pacman", "-Qdt"],
                    "Verwaiste Pakete anzeigen")

    def remove_orphans():
        if confirm_dialog(stdscr, "Alle verwaisten Pakete entfernen?"):
            orphans = subprocess.run(
                ["pacman", "-Qdtq"],
                capture_output=True, text=True
            ).stdout.split()
            if orphans:
                run_command(stdscr,
                            ["sudo", "pacman", "-Rns", "--noconfirm"] + orphans,
                            "Verwaiste Pakete entfernen")
            else:
                confirm_dialog(stdscr, "Keine verwaisten Pakete gefunden.")

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
                MenuItem(
                    "[1] Datenbank synchronisieren",
                    "sudo pacman -Sy",
                    action=a["sync"],
                ),
                MenuItem(
                    "[2] System-Upgrade (pacman)",
                    "sudo pacman -Syu --noconfirm",
                    action=a["upgrade_pacman"],
                ),
                MenuItem(
                    "[3] System-Upgrade (yay)",
                    "yay -Syu --noconfirm  (pacman + AUR)",
                    action=a["upgrade_yay"],
                ),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[2] Pakete installieren",
            desc="Pakete ueber pacman oder yay installieren",
            submenu=[
                MenuItem(
                    "[1] Installieren via pacman",
                    "sudo pacman -S <paket>",
                    action=a["install_pacman"],
                ),
                MenuItem(
                    "[2] Installieren via yay (AUR)",
                    "yay -S <paket>",
                    action=a["install_yay"],
                ),
                MenuItem("", "", separator=True),
                MenuItem(
                    "[3] Paket suchen",
                    "yay -Ss <suchbegriff>",
                    action=a["search"],
                ),
                MenuItem(
                    "[4] Installierte Pakete auflisten",
                    "pacman -Q",
                    action=a["list_installed"],
                ),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[3] Pakete entfernen",
            desc="Pakete ueber pacman oder yay entfernen",
            submenu=[
                MenuItem(
                    "[1] Entfernen via pacman",
                    "sudo pacman -Rns <paket>",
                    action=a["remove_pacman"],
                ),
                MenuItem(
                    "[2] Entfernen via yay",
                    "yay -Rns <paket>",
                    action=a["remove_yay"],
                ),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[4] Keyring & Datenbank",
            desc="Schluessel und Paketdatenbank verwalten",
            submenu=[
                MenuItem(
                    "[1] Arch Keyring aktualisieren",
                    "pacman -Sy --needed archlinux-keyring",
                    action=a["update_keyring"],
                ),
                MenuItem(
                    "[2] Datenbank erzwungen erneuern",
                    "pacman -Syy",
                    action=a["refresh_db"],
                ),
                MenuItem("", "", separator=True),
                MenuItem(
                    "[3] GPG-Schluessel aktualisieren",
                    "pacman-key --refresh-keys",
                    action=a["refresh_keys"],
                ),
                MenuItem(
                    "[4] Schluessel befuellen",
                    "pacman-key --populate archlinux",
                    action=a["populate_keys"],
                ),
                MenuItem(
                    "[5] Schluessel initialisieren",
                    "pacman-key --init",
                    action=a["init_keyring"],
                ),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[5] Cache & Wartung",
            desc="Cache bereinigen und Orphans verwalten",
            submenu=[
                MenuItem(
                    "[1] Cache bereinigen",
                    "pacman -Sc",
                    action=a["clean_cache"],
                ),
                MenuItem(
                    "[2] Gesamten Cache loeschen",
                    "pacman -Scc",
                    action=a["clean_cache_all"],
                ),
                MenuItem("", "", separator=True),
                MenuItem(
                    "[3] Verwaiste Pakete anzeigen",
                    "pacman -Qdt",
                    action=a["list_orphans"],
                ),
                MenuItem(
                    "[4] Verwaiste Pakete entfernen",
                    "pacman -Rns $(pacman -Qdtq)",
                    action=a["remove_orphans"],
                ),
            ],
        ),
        MenuItem("", "", separator=True),
        MenuItem(
            label="[6] System",
            desc="Neustart oder Herunterfahren",
            submenu=[
                MenuItem(
                    "[1] Neustart",
                    "sudo reboot",
                    action=a["reboot"],
                ),
                MenuItem(
                    "[2] Herunterfahren",
                    "sudo shutdown -h now",
                    action=a["shutdown"],
                ),
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
    stdscr.bkgd(" ", curses.color_pair(COLOR_ORANGE))

    actions = make_actions(stdscr)
    menu    = build_menu(actions)

    selectable = [i for i, m in enumerate(menu) if not m.separator]
    pos = 0

    while True:
        selected = selectable[pos]
        draw_menu(stdscr, menu, selected, "Hauptmenue")
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
            case 10 | curses.KEY_ENTER:
                item = menu[selected]
                if item.label == "[Q] Beenden":
                    if confirm_dialog(stdscr, "Programm wirklich beenden?"):
                        return
                elif item.submenu:
                    run_menu(
                        stdscr,
                        item.submenu,
                        item.label,
                        breadcrumb=f"Hauptmenue > {item.label}",
                    )
                elif item.action:
                    item.action()
            case _ if key in (ord("q"), ord("Q"), 27):
                if confirm_dialog(stdscr, "Programm wirklich beenden?"):
                    return


# ─────────────────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    if os.geteuid() == 0:
        print("Bitte NICHT als root starten. sudo wird intern verwendet.")
        sys.exit(1)

    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass

    print("Auf Wiedersehen!\n")
