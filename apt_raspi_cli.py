#!/usr/bin/env python3
# apt_menu.py — APT-Verwaltungsmenü für Raspberry Pi 5 (Debian)
# Kompatibel mit Python 3.12+

import os
import shutil
import subprocess
import sys

# Farbcodes für die Konsole
ORANGE = "\033[38;5;208m"
RESET = "\033[0m"
BOLD = "\033[1m"

def is_root() -> bool:
    """Prüft, ob das Skript mit Root-Rechten läuft."""
    return os.geteuid() == 0

def relaunch_with_sudo():
    """Neu starten des Skripts mit sudo, falls nicht root."""
    sudo = shutil.which("sudo")
    if not sudo:
        print("Dieses Skript muss als Root ausgeführt werden. Bitte mit sudo starten.")
        sys.exit(1)
    python = sys.executable or "python3"
    args = [sudo, python] + sys.argv
    try:
        os.execvp(sudo, args)
    except Exception as e:
        print(f"Fehler beim Neustart mit sudo: {e}")
        sys.exit(1)

def run_cmd(cmd: list, capture_output: bool = False) -> tuple[int, str]:
    """
    Führt einen Systembefehl aus.

    Args:
        cmd: Liste mit Befehls-Argumenten
        capture_output: Wenn True, wird die Ausgabe erfasst

    Returns:
        Tuple aus (Return-Code, Ausgabe-String)
    """
    try:
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.STDOUT if capture_output else None,
            text=True
        )
        output = result.stdout if capture_output else ""
        return result.returncode, output
    except FileNotFoundError:
        print(f"{ORANGE}Fehler:{RESET} Befehl nicht gefunden: {cmd[0]}")
        return 127, ""
    except PermissionError:
        print(f"{ORANGE}Fehler:{RESET} Keine Berechtigung, Befehl auszuführen: {cmd[0]}")
        return 126, ""

def apt_update():
    """Aktualisiert die Paketquellen."""
    print(f"{ORANGE}-> Aktualisiere Paketquellen (apt update){RESET}")
    rc, _ = run_cmd(["apt", "update"])
    return rc == 0

def apt_upgrade():
    """Führt ein System-Upgrade durch."""
    print(f"{ORANGE}-> Führe Systemupgrade durch (apt dist-upgrade -y){RESET}")
    rc, _ = run_cmd(["apt", "dist-upgrade", "-y"])
    return rc == 0

def apt_install():
    """Installiert eine oder mehrere Pakete."""
    pkg = input("Paketname(en) (Leerzeichen getrennt): ").strip()
    if not pkg:
        print("Keine Pakete angegeben.")
        return False
    cmd = ["apt", "install", "-y"] + pkg.split()
    print(f"{ORANGE}-> Installiere: {pkg}{RESET}")
    rc, _ = run_cmd(cmd)
    return rc == 0

def apt_remove():
    """Entfernt eine oder mehrere Pakete und führt autoremove aus."""
    pkg = input("Paketname(en) zum Entfernen (Leerzeichen getrennt): ").strip()
    if not pkg:
        print("Keine Pakete angegeben.")
        return False
    cmd = ["apt", "remove", "-y"] + pkg.split()
    print(f"{ORANGE}-> Entferne: {pkg}{RESET}")
    rc, _ = run_cmd(cmd)
    if rc == 0:
        print(f"{ORANGE}-> Führe autoremove aus{RESET}")
        rc, _ = run_cmd(["apt", "autoremove", "-y"])
    return rc == 0

def apt_autoclean():
    """Bereinigt nicht mehr benötigte Pakete."""
    print(f"{ORANGE}-> Führe apt autoclean aus{RESET}")
    rc, _ = run_cmd(["apt", "autoclean"])
    return rc == 0

def edit_apt_config():
    """Bearbeitet die APT-Konfiguration mit nano/vi/editor."""
    editor = shutil.which("nano") or shutil.which("vi") or shutil.which("editor")
    if not editor:
        print("Kein Editor (nano/vi/editor) gefunden.")
        return False

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
            return False
        parent = os.path.dirname(target)
        if parent and not os.path.exists(parent):
            try:
                os.makedirs(parent, exist_ok=True)
            except PermissionError:
                print("Fehler: Keine Berechtigung, Verzeichnis zu erstellen.")
                return False
        try:
            open(target, "a").close()
        except PermissionError:
            print("Fehler: Keine Berechtigung, Datei zu erstellen.")
            return False

    rc, _ = run_cmd([editor, target])
    return rc == 0

def raspi_config():
    """Startet raspi-config für Raspberry Pi Konfiguration."""
    print(f"{ORANGE}-> Starte raspi-config{RESET}")
    rc, _ = run_cmd(["raspi-config"])
    return rc == 0

def firmware_upgrade():
    """Upgrade der Raspberry Pi Firmware mit rpi-update."""
    print(f"{ORANGE}-> Prüfe und aktualisiere Raspberry Pi Firmware{RESET}")
    print(f"{ORANGE}-> Installiere/aktualisiere rpi-update Tool{RESET}")
    run_cmd(["apt", "install", "-y", "rpi-update"])

    confirm = input("Firmware-Update durchführen? (j/N): ").strip().lower()
    if confirm != "j":
        print("Abbruch.")
        return False

    print(f"{ORANGE}-> Führe Firmware-Update durch (rpi-update){RESET}")
    rc, _ = run_cmd(["rpi-update"])
    if rc == 0:
        print(f"{ORANGE}✓ Firmware erfolgreich aktualisiert!{RESET}")
        reboot_prompt()
        return True
    else:
        print(f"{ORANGE}Fehler:{RESET} Firmware-Update fehlgeschlagen.")
        return False

def show_kernel_info():
    """Zeigt Informationen zum aktuell installierten Kernel an."""
    print(f"\n{ORANGE}=== Kernel-Informationen ==={RESET}")

    # Kernel-Version
    rc, output = run_cmd(["uname", "-r"], capture_output=True)
    if rc == 0 and output:
        print(f"Kernel-Version: {output.strip()}")

    # Kernel-Name (vollständig)
    rc, output = run_cmd(["uname", "-a"], capture_output=True)
    if rc == 0 and output:
        print(f"Vollständig: {output.strip()}")

    # Linux-Kernel Release
    rc, output = run_cmd(["uname", "-s"], capture_output=True)
    if rc == 0 and output:
        print(f"Betriebssystem: {output.strip()}")

    # Architektur
    rc, output = run_cmd(["uname", "-m"], capture_output=True)
    if rc == 0 and output:
        print(f"Architektur: {output.strip()}")

    # Kernel-Releasedatum (falls verfügbar)
    if os.path.exists("/proc/version"):
        try:
            with open("/proc/version", "r") as f:
                print(f"Prozess-Info: {f.read().strip()[:80]}...")
        except PermissionError:
            pass

    print()

def system_reboot():
    """Reboot des Systems."""
    print(f"{ORANGE}-> System-Neustart{RESET}")
    confirm = input("System wirklich neu starten? (j/N): ").strip().lower()
    if confirm != "j":
        print("Abbruch.")
        return False
    print(f"{ORANGE}System wird in 10 Sekunden neu gestartet...{RESET}")
    rc, _ = run_cmd(["reboot"])
    return rc == 0

def reboot_prompt():
    """Fragt, ob der Benutzer neu starten möchte."""
    reboot = input(f"\n{ORANGE}System neu starten? (j/N):{RESET} ").strip().lower()
    if reboot == "j":
        system_reboot()

def clear_screen():
    """Bildschirm löschen."""
    os.system("clear" if os.name == "posix" else "cls")

def print_menu():
    """Menü anzeigen mit detaillierten Beschreibungen und neuen Optionen."""
    clear_screen()
    title = f"{ORANGE}{BOLD}APT Verwalter - Raspberry Pi 5 (Debian){RESET}"
    print(title)
    print()
    print(f"{ORANGE}1){RESET} Paketquellen aktualisieren (apt update)")
    print(f"{ORANGE}2){RESET} System aktualisieren (apt dist-upgrade -y)")
    print(f"{ORANGE}3){RESET} Paket installieren")
    print(f"{ORANGE}4){RESET} Paket entfernen + autoremove")
    print(f"{ORANGE}5){RESET} APT-Konfiguration mit nano/Editor bearbeiten")
    print(f"{ORANGE}6){RESET} Raspberry Pi Konfiguration (raspi-config)")
    print(f"{ORANGE}7){RESET} Firmware aktualisieren (rpi-update)")
    print(f"{ORANGE}8){RESET} Autoclean ausführen")
    print(f"{ORANGE}9){RESET} System neu starten (Reboot)")
    print(f"{ORANGE}10){RESET} System Packages / Entwickler-Tools installieren")
    print(f"{ORANGE}11){RESET} Netzwerk-Tools installieren")
    print(f"{ORANGE}12){RESET} Kernel-Informationen anzeigen")
    print(f"{ORANGE}13){RESET} Beenden")
    print()

def install_dev_tools():
    """Installiert Entwickler-Tools."""
    print(f"{ORANGE}-> Installiere System-Packages / Entwickler-Tools{RESET}")
    packages = [
        "build-essential", "fakeroot", "git", "htop", "cmake",
        "gdb", "xfsdump", "f2fs-tools", "nginx", "rsync", "quota"
    ]
    rc, _ = run_cmd(["apt", "install", "-y"] + packages)
    return rc == 0

def install_network_tools():
    """Installiert Netzwerk-Tools."""
    print(f"{ORANGE}-> Installiere Netzwerk-Tools{RESET}")
    packages = ["nmap", "net-tools", "iproute2", "samba", "ufw"]
    rc, _ = run_cmd(["apt", "install", "-y"] + packages)
    return rc == 0

def main():
    """Hauptprogramm mit Menüschleife."""
    if not is_root():
        relaunch_with_sudo()

    while True:
        print_menu()
        choice = input("Wähle eine Option [1-13]: ").strip()

        success = False
        match choice:
            case "1":
                success = apt_update()
            case "2":
                success = apt_upgrade()
            case "3":
                success = apt_install()
            case "4":
                success = apt_remove()
            case "5":
                success = edit_apt_config()
            case "6":
                success = raspi_config()
            case "7":
                success = firmware_upgrade()
            case "8":
                success = apt_autoclean()
            case "9":
                success = system_reboot()
            case "10":
                success = install_dev_tools()
            case "11":
                success = install_network_tools()
            case "12":
                show_kernel_info()
                success = True
            case "13":
                print("Beende.")
                break
            case _:
                print("Ungültige Auswahl.")

        if success:
            print(f"{ORANGE}✓ Erfolgreich abgeschlossen!{RESET}")

        input("\nDrücke Enter, um zum Menü zurückzukehren...")

if __name__ == "__main__":
    main()
