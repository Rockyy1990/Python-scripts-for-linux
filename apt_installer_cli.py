#!/usr/bin/env python3
# apt_menu.py — Einfaches APT-Verwaltungsmenü
# Kompatibel mit Python 3.8+

import os
import shutil
import subprocess
import sys

ORANGE = "\033[38;5;208m"
RESET = "\033[0m"
BOLD = "\033[1m"

def is_root() -> bool:
    return os.geteuid() == 0

def relaunch_with_sudo():
    sudo = shutil.which("sudo")
    if not sudo:
        print("Dieses Skript muss als Root ausgeführt werden. Bitte mit sudo starten.")
        sys.exit(1)
    # Baue Kommando neu auf: sudo python3 <script> <args...>
    python = sys.executable or "python3"
    args = [sudo, python] + sys.argv
    try:
        os.execvp(sudo, args)
    except Exception as e:
        print(f"Fehler beim Neustart mit sudo: {e}")
        sys.exit(1)

def run_cmd(cmd: list, capture_output: bool = False) -> int:
    try:
        if capture_output:
            completed = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if completed.stdout:
                print(completed.stdout, end="")
            return completed.returncode
        else:
            return subprocess.call(cmd)
    except FileNotFoundError:
        print(f"{ORANGE}Fehler:{RESET} Befehl nicht gefunden: {cmd[0]}")
        return 127
    except PermissionError:
        print(f"{ORANGE}Fehler:{RESET} Keine Berechtigung, Befehl auszuführen: {cmd[0]}")
        return 126

def apt_update():
    print(f"{ORANGE}-> Aktualisiere Paketquellen (apt update){RESET}")
    run_cmd(["apt", "update"])

def apt_upgrade():
    print(f"{ORANGE}-> Führe Systemupgrade durch (apt upgrade){RESET}")
    run_cmd(["apt", "upgrade", "-y"])

def apt_install():
    pkg = input("Paketname(en) (Leerzeichen getrennt): ").strip()
    if not pkg:
        print("Keine Pakete angegeben.")
        return
    cmd = ["apt", "install", "-y"] + pkg.split()
    print(f"{ORANGE}-> Installiere: {pkg}{RESET}")
    run_cmd(cmd)

def apt_remove():
    pkg = input("Paketname(en) zum Entfernen (Leerzeichen getrennt): ").strip()
    if not pkg:
        print("Keine Pakete angegeben.")
        return
    cmd = ["apt", "remove", "-y"] + pkg.split()
    print(f"{ORANGE}-> Entferne: {pkg}{RESET}")
    rc = run_cmd(cmd)
    if rc == 0:
        print(f"{ORANGE}-> Führe autoremove aus{RESET}")
        run_cmd(["apt", "autoremove", "-y"])

def edit_apt_config():
    editor = shutil.which("nano") or shutil.which("vi") or shutil.which("editor")
    if not editor:
        print("Kein Editor (nano/vi/editor) gefunden.")
        return
    print(f"{ORANGE}-> Editor: {editor}{RESET}")
    paths = [
        "/etc/apt/apt.conf",
        "/etc/apt/apt.conf.d/",
        "/etc/apt/sources.list",
        "/etc/apt/sources.list.d/"
    ]
    print("Zu bearbeitende Pfade:")
    for p in paths:
        print("  -", p)
    target = input("Gib Pfad oder Datei zum Öffnen ein (Enter für /etc/apt/apt.conf): ").strip()
    if not target:
        target = "/etc/apt/apt.conf"
    if not os.path.exists(target):
        create = input("Datei existiert nicht. Erstellen? (j/N): ").strip().lower()
        if create != "j":
            print("Abbruch.")
            return
        parent = os.path.dirname(target)
        if parent and not os.path.exists(parent):
            try:
                os.makedirs(parent, exist_ok=True)
            except PermissionError:
                print("Fehler: Keine Berechtigung, Verzeichnis zu erstellen.")
                return
        try:
            open(target, "a").close()
        except PermissionError:
            print("Fehler: Keine Berechtigung, Datei zu erstellen.")
            return
    try:
        run_cmd([editor, target])
    except Exception as e:
        print("Fehler beim Starten des Editors:", e)

def clear_screen():
    os.system("clear" if os.name == "posix" else "cls")

def print_menu():
    clear_screen()
    title = f"{ORANGE}{BOLD}APT Verwalter{RESET}"
    print(title)
    print()
    print(f"{ORANGE}1){RESET} Paketquellen aktualisieren (apt update)")
    print(f"{ORANGE}2){RESET} System aktualisieren (apt upgrade -y)")
    print(f"{ORANGE}3){RESET} Paket installieren")
    print(f"{ORANGE}4){RESET} Paket entfernen + autoremove")
    print(f"{ORANGE}5){RESET} APT-Konfiguration mit nano/Editor bearbeiten")
    print(f"{ORANGE}6){RESET} Beenden")
    print()

def main():
    if not is_root():
        relaunch_with_sudo()

    while True:
        print_menu()
        choice = input("Wähle eine Option [1-6]: ").strip()
        if choice == "1":
            apt_update()
        elif choice == "2":
            apt_upgrade()
        elif choice == "3":
            apt_install()
        elif choice == "4":
            apt_remove()
        elif choice == "5":
            edit_apt_config()
        elif choice == "6":
            print("Beende.")
            break
        else:
            print("Ungültige Auswahl.")
        input("\nDrücke Enter, um zum Menü zurückzukehren...")

if __name__ == "__main__":
    main()
