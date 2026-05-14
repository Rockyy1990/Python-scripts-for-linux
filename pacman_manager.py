#!/usr/bin/env python3
"""
pacman_manager.py — Interactive Arch Linux package manager CLI
Requires: Python 3.12+, pacman, optional yay (AUR helper)
"""

# /// script
# requires-python = ">=3.12"
# ///

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import IntEnum, auto
from typing import Final

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# ANSI colour helpers
# ──────────────────────────────────────────────────────────────────────────────
RESET:  Final[str] = "\033[0m"
BOLD:   Final[str] = "\033[1m"
RED:    Final[str] = "\033[91m"
GREEN:  Final[str] = "\033[92m"
YELLOW: Final[str] = "\033[93m"
CYAN:   Final[str] = "\033[96m"
BLUE:   Final[str] = "\033[94m"
DIM:    Final[str] = "\033[2m"


def c(text: str, colour: str) -> str:
    """Wrap *text* in an ANSI colour escape sequence."""
    return f"{colour}{text}{RESET}"


# ──────────────────────────────────────────────────────────────────────────────
# Comfort-level notification helpers  (Windows-11-style advisory banners)
# ──────────────────────────────────────────────────────────────────────────────
def _banner(label: str, colour: str, message: str) -> None:
    width: int = 70
    print(f"\n{colour}{BOLD}{'─' * width}{RESET}")
    print(f"{colour}{BOLD}  {label}{RESET}  {message}")
    print(f"{colour}{BOLD}{'─' * width}{RESET}\n")


def info(message: str) -> None:
    """Informational advisory banner."""
    _banner("ℹ  HINWEIS", CYAN, message)


def warn(message: str) -> None:
    """Warning banner – action may have side-effects."""
    _banner("⚠  WARNUNG", YELLOW, message)


def danger(message: str) -> None:
    """Danger banner – destructive / irreversible action."""
    _banner("✖  ACHTUNG", RED, message)


def success(message: str) -> None:
    """Success confirmation banner."""
    _banner("✔  ERFOLG", GREEN, message)


# ──────────────────────────────────────────────────────────────────────────────
# Menu item definition
# ──────────────────────────────────────────────────────────────────────────────
class Choice(IntEnum):
    INSTALL         = auto()
    REMOVE          = auto()
    SEARCH          = auto()
    UPGRADE         = auto()
    YAY_UPGRADE     = auto()
    CLEAN_CACHE     = auto()
    RENEW_KEYRING   = auto()
    RENEW_KEYS      = auto()
    EDIT_PACMAN_CONF = auto()
    EDIT_MIRRORS    = auto()
    REBOOT          = auto()
    SHUTDOWN        = auto()
    QUIT            = auto()


@dataclass(frozen=True, slots=True)
class MenuItem:
    choice: Choice
    label: str
    icon: str


MENU_ITEMS: Final[tuple[MenuItem, ...]] = (
    MenuItem(Choice.INSTALL,          "Paket installieren",                    "📦"),
    MenuItem(Choice.REMOVE,           "Paket entfernen",                       "🗑 "),
    MenuItem(Choice.SEARCH,           "Paket suchen",                          "🔍"),
    MenuItem(Choice.UPGRADE,          "System-Upgrade  (pacman -Syu)",         "🔄"),
    MenuItem(Choice.YAY_UPGRADE,      "AUR-Upgrade     (yay)",                 "⭐"),
    MenuItem(Choice.CLEAN_CACHE,      "Cache leeren    (pacman -Scc)",         "🧹"),
    MenuItem(Choice.RENEW_KEYRING,    "archlinux-keyring erneuern",            "🔑"),
    MenuItem(Choice.RENEW_KEYS,       "Alle Schlüssel erneuern",               "🗝 "),
    MenuItem(Choice.EDIT_PACMAN_CONF, "pacman.conf bearbeiten",                "📝"),
    MenuItem(Choice.EDIT_MIRRORS,     "Mirrorliste bearbeiten",                "🌐"),
    MenuItem(Choice.REBOOT,           "System neu starten",                    "🔁"),
    MenuItem(Choice.SHUTDOWN,         "System herunterfahren",                 "⏻ "),
    MenuItem(Choice.QUIT,             "Beenden",                               "🚪"),
)

# ──────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────────────────────────────────────
def _require_root_capable() -> None:
    """Ensure sudo is available (not necessarily root yet)."""
    if shutil.which("sudo") is None:
        danger("sudo nicht gefunden – bitte als root ausführen.")
        sys.exit(1)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute *cmd*, stream output to the terminal, return CompletedProcess."""
    log.debug("Executing: %s", " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if check and result.returncode != 0:
        warn(f"Befehl beendet mit Exit-Code {result.returncode}: {' '.join(cmd)}")
    return result


def confirm(prompt: str, *, default: bool = False) -> bool:
    """Ask a yes/no question; return True for yes."""
    hint: str = "[J/n]" if default else "[j/N]"
    try:
        raw: str = input(f"{BOLD}{prompt} {hint}: {RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if raw == "":
        return default
    return raw in {"j", "ja", "y", "yes"}


def prompt_package_name(action: str) -> str | None:
    """Prompt for a package name; return None if empty."""
    try:
        name: str = input(
            f"{BOLD}Paketname für '{action}'{RESET} (leer = abbrechen): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return name or None


# ──────────────────────────────────────────────────────────────────────────────
# Action handlers
# ──────────────────────────────────────────────────────────────────────────────
def handle_install() -> None:
    info("Pakete werden mit pacman -S installiert.")
    name = prompt_package_name("installieren")
    if not name:
        return
    run(["sudo", "pacman", "-S", "--needed", name])


def handle_remove() -> None:
    warn("Abhängigkeiten werden mit -Rs ebenfalls entfernt!")
    name = prompt_package_name("entfernen")
    if not name:
        return
    if confirm(f"Paket '{name}' wirklich entfernen?"):
        run(["sudo", "pacman", "-Rs", name])


def handle_search() -> None:
    name = prompt_package_name("suchen")
    if not name:
        return
    run(["pacman", "-Ss", name], check=False)


def handle_upgrade() -> None:
    info("Führt ein vollständiges System-Upgrade durch (pacman -Syu).")
    if confirm("Jetzt upgraden?", default=True):
        run(["sudo", "pacman", "-Syu"])
        success("System-Upgrade abgeschlossen.")


def handle_yay_upgrade() -> None:
    if shutil.which("yay") is None:
        warn("yay nicht gefunden. Installation: pacman -S yay oder aus dem AUR.")
        return
    info("Führt ein vollständiges AUR + Repo-Upgrade durch (yay).")
    if confirm("Jetzt upgraden?", default=True):
        run(["yay", "-Syu"])
        success("yay-Upgrade abgeschlossen.")


def handle_clean_cache() -> None:
    danger(
        "pacman -Scc löscht ALLE gecachten Pakete – kein Rollback mehr möglich!\n"
        "  Empfehlung: Nur ausführen wenn Speicherplatz knapp ist."
    )
    if confirm("Wirklich gesamten Cache leeren?"):
        run(["sudo", "pacman", "-Scc", "--noconfirm"])
        success("Package-Cache geleert.")


def handle_renew_keyring() -> None:
    info("archlinux-keyring wird aktualisiert – behebt Signaturfehler.")
    run(["sudo", "pacman", "-Sy", "--noconfirm", "archlinux-keyring"])
    success("archlinux-keyring erfolgreich erneuert.")


def handle_renew_keys() -> None:
    info(
        "Alle Schlüssel werden neu initialisiert und populiert.\n"
        "  Dies kann einige Minuten dauern."
    )
    if confirm("Schlüssel jetzt erneuern?", default=True):
        run(["sudo", "pacman-key", "--init"])
        run(["sudo", "pacman-key", "--populate", "archlinux"])
        run(["sudo", "pacman-key", "--refresh-keys"])
        success("Schlüsselbund erfolgreich erneuert.")


def handle_edit_pacman_conf() -> None:
    conf_path: str = "/etc/pacman.conf"
    info(f"Öffnet {conf_path} in nano (sudo).")
    run(["sudo", "nano", conf_path], check=False)


def handle_edit_mirrors() -> None:
    mirror_path: str = "/etc/pacman.d/mirrorlist"
    info(
        f"Öffnet {mirror_path} in nano (sudo).\n"
        "  Tipp: reflector --country Germany --latest 10 --sort rate "
        "--save /etc/pacman.d/mirrorlist"
    )
    run(["sudo", "nano", mirror_path], check=False)


def handle_reboot() -> None:
    danger("Das System wird jetzt neu gestartet!")
    if confirm("Wirklich neu starten?"):
        run(["sudo", "systemctl", "reboot"])


def handle_shutdown() -> None:
    danger("Das System wird jetzt heruntergefahren!")
    if confirm("Wirklich herunterfahren?"):
        run(["sudo", "systemctl", "poweroff"])


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch table
# ──────────────────────────────────────────────────────────────────────────────
HANDLERS: Final[dict[Choice, object]] = {
    Choice.INSTALL:          handle_install,
    Choice.REMOVE:           handle_remove,
    Choice.SEARCH:           handle_search,
    Choice.UPGRADE:          handle_upgrade,
    Choice.YAY_UPGRADE:      handle_yay_upgrade,
    Choice.CLEAN_CACHE:      handle_clean_cache,
    Choice.RENEW_KEYRING:    handle_renew_keyring,
    Choice.RENEW_KEYS:       handle_renew_keys,
    Choice.EDIT_PACMAN_CONF: handle_edit_pacman_conf,
    Choice.EDIT_MIRRORS:     handle_edit_mirrors,
    Choice.REBOOT:           handle_reboot,
    Choice.SHUTDOWN:         handle_shutdown,
}

# ──────────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────────
def _clear() -> None:
    os.system("clear")


def _print_header() -> None:
    """Print a styled application header."""
    yay_status: str = (
        c("yay ✔", GREEN) if shutil.which("yay") else c("yay ✘", DIM)
    )
    print(
        f"\n{BOLD}{BLUE}╔══════════════════════════════════════════════════════════╗{RESET}"
    )
    print(
        f"{BOLD}{BLUE}║{RESET}  {BOLD}🏹  Arch Linux Pacman Manager{RESET}"
        f"                  {yay_status}  {BOLD}{BLUE}║{RESET}"
    )
    print(
        f"{BOLD}{BLUE}╚══════════════════════════════════════════════════════════╝{RESET}\n"
    )


def _print_menu() -> None:
    _print_header()
    for item in MENU_ITEMS:
        num: str = c(f"{item.choice.value:>2}.", CYAN)
        print(f"  {num}  {item.icon}  {item.label}")
    print()


def _read_choice() -> Choice | None:
    """Read and validate a menu selection; return None on invalid input."""
    try:
        raw: str = input(f"{BOLD}Auswahl [{Choice.QUIT.value} = Beenden]: {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return Choice.QUIT

    if not raw.isdigit():
        return None

    value: int = int(raw)
    try:
        return Choice(value)
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
def main() -> int:
    # Verify we are on Arch Linux
    if not os.path.isfile("/etc/arch-release"):
        warn("Kein Arch Linux erkannt – Skript nur für Arch Linux gedacht.")

    _require_root_capable()

    while True:
        _clear()
        _print_menu()
        choice: Choice | None = _read_choice()

        if choice is None:
            warn("Ungültige Eingabe – bitte eine Zahl aus dem Menü wählen.")
            input(c("  ↵ Weiter …", DIM))
            continue

        if choice is Choice.QUIT:
            print(c("\n  Auf Wiedersehen! 👋\n", GREEN))
            return 0

        handler = HANDLERS.get(choice)
        if handler is None:
            log.error("No handler registered for choice %s", choice)
            continue

        try:
            handler()  # type: ignore[operator]
        except Exception as exc:  # noqa: BLE001
            log.exception("Unerwarteter Fehler: %s", exc)

        input(c("\n  ↵ Zurück zum Menü …", DIM))


if __name__ == "__main__":
    sys.exit(main())
