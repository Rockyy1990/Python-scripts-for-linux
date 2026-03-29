#!/usr/bin/env python3

import os
import subprocess
import sys

# ── Arch Linux Farben ──────────────────────────────────────────────────────────
CYAN        = '\033[96m'        # Arch-Primärfarbe (hell-cyan)
ARCH_BLUE   = '\033[38;5;75m'  # Arch-Blau (logo-nah)
WHITE       = '\033[97m'
DIM         = '\033[2m'
BOLD        = '\033[1m'
RESET       = '\033[0m'

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def clear_screen() -> None:
    os.system('clear')


def pause(msg: str = "Drücke Enter zum Fortfahren...") -> None:
    input(f"\n{DIM}{msg}{RESET}")


def confirm(question: str) -> bool:
    """Ja/Nein-Abfrage – gibt True bei 'j'/'y' zurück."""
    answer = input(f"\n{CYAN}{question} [j/N]: {RESET}").strip().lower()
    return answer in ('j', 'y', 'ja', 'yes')


def print_header() -> None:
    width = 52
    border = f"{ARCH_BLUE}{'━' * width}{RESET}"
    title  = "ARCH LINUX SYSTEM MANAGEMENT"
    padding = (width - len(title)) // 2
    print(border)
    print(f"{ARCH_BLUE}{'━' * padding}{RESET}{BOLD}{WHITE} {title} {RESET}{ARCH_BLUE}{'━' * (padding - 1)}{RESET}")
    print(border)


def print_menu() -> None:
    clear_screen()
    print_header()
    print()
    entries = [
        ("1", "System-Upgrade           ", "sudo pacman -Syu"),
        ("2", "System-Upgrade mit YAY   ", "yay -Syu"),
        ("3", "Pacman-Cache leeren      ", "sudo pacman -Scc"),
        ("4", "Keyring erneuern         ", "pacman-key --init/populate"),
        ("5", "Paketdatenbank updaten   ", "sudo pacman -Fyy"),
        ("6", "Verwaiste Pakete löschen ", "pacman -Rns <orphans>"),
    ]
    for num, label, cmd in entries:
        print(f"  {ARCH_BLUE}{BOLD}[{num}]{RESET}  {CYAN}{label}{RESET}  {DIM}{cmd}{RESET}")

    print()
    print(f"  {ARCH_BLUE}{BOLD}[0]{RESET}  {WHITE}Beenden{RESET}")
    print()


def reboot_prompt() -> None:
    """Fragt nach dem Upgrade ob ein Neustart gewünscht ist."""
    if confirm("System jetzt neu starten?"):
        print(f"\n{CYAN}Starte neu …{RESET}")
        subprocess.run("sudo reboot", shell=True)
    else:
        print(f"{DIM}Neustart übersprungen.{RESET}")


def execute_command(command: str, description: str) -> bool:
    """
    Führt einen Shell-Befehl aus.
    Gibt True zurück wenn erfolgreich, sonst False.
    """
    clear_screen()
    print_header()
    print(f"\n{BOLD}{CYAN}▶  {description}{RESET}")
    print(f"{DIM}   Befehl: {command}{RESET}\n")
    print(f"{ARCH_BLUE}{'─' * 52}{RESET}\n")

    try:
        result = subprocess.run(command, shell=True)
        print(f"\n{ARCH_BLUE}{'─' * 52}{RESET}")
        if result.returncode == 0:
            print(f"\n{CYAN}{BOLD}✔  Erfolgreich abgeschlossen.{RESET}")
            return True
        else:
            print(f"\n{CYAN}✘  Befehl mit Fehlercode {result.returncode} beendet.{RESET}")
            return False
    except FileNotFoundError:
        print(f"\n{CYAN}✘  Befehl nicht gefunden: {command.split()[0]}{RESET}")
        return False
    except Exception as exc:
        print(f"\n{CYAN}✘  Unerwarteter Fehler: {exc}{RESET}")
        return False


def remove_orphans() -> None:
    """Sucht verwaiste Pakete und bietet deren Entfernung an."""
    clear_screen()
    print_header()
    print(f"\n{BOLD}{CYAN}▶  Verwaiste Pakete suchen …{RESET}\n")

    try:
        result = subprocess.run(
            "pacman -Qtdq",
            shell=True,
            capture_output=True,
            text=True
        )
        orphans = result.stdout.strip()

        if not orphans:
            print(f"{CYAN}✔  Keine verwaisten Pakete gefunden.{RESET}")
            pause()
            return

        pkg_list = orphans.splitlines()
        print(f"{WHITE}Gefundene Pakete ({len(pkg_list)}):{RESET}\n")
        for pkg in pkg_list:
            print(f"  {DIM}•{RESET} {CYAN}{pkg}{RESET}")

        if confirm(f"\n{len(pkg_list)} Paket(e) vollständig entfernen?"):
            execute_command(
                "sudo pacman -Rns $(pacman -Qtdq)",
                "Verwaiste Pakete entfernen"
            )
        else:
            print(f"\n{DIM}Abgebrochen – keine Pakete entfernt.{RESET}")

    except Exception as exc:
        print(f"\n{CYAN}✘  Fehler: {exc}{RESET}")

    pause()


# ── Hauptprogramm ──────────────────────────────────────────────────────────────

def main() -> None:
    actions = {
        '1': ('System-Upgrade (pacman)',          'sudo pacman -Syu',    True),
        '2': ('System-Upgrade (YAY)',              'yay -Syu',            True),
        '3': ('Pacman-Cache leeren',               'sudo pacman -Scc --noconfirm', False),
        '4': ('Arch Linux Keyring erneuern',
              'sudo pacman-key --init && sudo pacman-key --populate archlinux', False),
        '5': ('Paketdatenbank aktualisieren',      'sudo pacman -Fyy',    False),
    }

    while True:
        print_menu()
        choice = input(f"{CYAN}Option wählen: {RESET}").strip()

        if choice == '0':
            clear_screen()
            print(f"\n{CYAN}Auf Wiedersehen!{RESET}\n")
            sys.exit(0)

        if choice == '6':
            remove_orphans()
            continue

        if choice in actions:
            desc, cmd, ask_reboot = actions[choice]
            success = execute_command(cmd, desc)
            if success and ask_reboot:
                reboot_prompt()
            pause()
        else:
            print(f"\n{CYAN}✘  Ungültige Eingabe – bitte 0–6 wählen.{RESET}")
            pause("Drücke Enter um zurückzukehren...")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{DIM}Abgebrochen (Ctrl+C).{RESET}\n")
        sys.exit(0)
