#!/usr/bin/env python3

import os
import subprocess
import sys

# Farben definieren
ORANGE = '\033[38;5;208m'
BLUE = '\033[34m'
RESET = '\033[0m'

def clear_screen():
    os.system('clear')

def print_menu():
    clear_screen()
    print(f"{ORANGE}{'='*50}")
    print(f"{'='*50}{RESET}")
    print(f"{ORANGE}        ARCH LINUX SYSTEM MANAGEMENT{RESET}")
    print(f"{ORANGE}{'='*50}")
    print(f"{'='*50}{RESET}\n")

    print(f"{ORANGE}1. System Upgrade{RESET}")
    print(f"{ORANGE}2. System Upgrade mit YAY{RESET}")
    print(f"{ORANGE}3. Pacman Cache leeren{RESET}")
    print(f"{ORANGE}4. Arch Linux Keyring erneuern{RESET}")
    print(f"{ORANGE}5. Pacman Datenbank aktualisieren{RESET}")
    print(f"{ORANGE}6. Beenden{RESET}\n")

def success_message():
    print(f"\n{BLUE}Erfolgreich ausgeführt!{RESET}\n")
    input("Drücke Enter zum Fortfahren...")

def execute_command(command, description):
    print(f"\n{ORANGE}Führe aus: {description}{RESET}")
    print(f"{ORANGE}Befehl: {command}{RESET}\n")

    try:
        result = subprocess.run(command, shell=True, check=True)
        if result.returncode == 0:
            success_message()
        else:
            print(f"{ORANGE}Fehler beim Ausführen des Befehls!{RESET}")
            input("Drücke Enter zum Fortfahren...")
    except subprocess.CalledProcessError as e:
        print(f"{ORANGE}Fehler: {e}{RESET}")
        input("Drücke Enter zum Fortfahren...")
    except Exception as e:
        print(f"{ORANGE}Fehler: {e}{RESET}")
        input("Drücke Enter zum Fortfahren...")

def main():
    while True:
        print_menu()
        choice = input(f"{ORANGE}Wähle eine Option (1-6): {RESET}").strip()

        if choice == '1':
            execute_command('sudo pacman -Syu', 'System Upgrade')
        elif choice == '2':
            execute_command('yay -Syu', 'System Upgrade mit YAY')
        elif choice == '3':
            execute_command('sudo pacman -Scc --noconfirm', 'Pacman Cache leeren')
        elif choice == '4':
            execute_command('sudo pacman-key --init && sudo pacman-key --populate archlinux', 'Arch Linux Keyring erneuern')
        elif choice == '5':
            execute_command('sudo pacman -Fyy', 'Pacman Datenbank aktualisieren')
        elif choice == '6':
            clear_screen()
            print(f"{ORANGE}Auf Wiedersehen!{RESET}")
            sys.exit(0)
        else:
            print(f"{ORANGE}Ungültige Auswahl. Bitte versuche es erneut.{RESET}")
            input("Drücke Enter zum Fortfahren...")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{ORANGE}Skript beendet.{RESET}")
        sys.exit(0)
