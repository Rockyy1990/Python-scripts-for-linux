#!/usr/bin/env python3

import os
import sys
import subprocess
import getpass
import platform

# ANSI-Farbcode für orange
ORANGE = "\033[38;5;214m"
RESET = "\033[0m"

# Globale Variable für Sudo-Passwort
sudo_password = None

def check_platform():
    """Prüft, ob das Skript auf einem Linux/Unix-System läuft."""
    if platform.system() not in ['Linux', 'Darwin']:
        print(f"{ORANGE}Dieses Skript funktioniert nur auf Linux/Unix-Systemen.{RESET}")
        sys.exit(1)

def get_sudo_password():
    """Fordert das Sudo-Passwort an (nur einmal)."""
    global sudo_password
    if sudo_password is None:
        sudo_password = getpass.getpass(f"{ORANGE}Sudo-Passwort eingeben: {RESET}")
    return sudo_password

def run_command(command):
    """Führt einen Shell-Befehl mit sudo aus und gibt die Ausgabe zurück."""
    global sudo_password
    try:
        # Befehl mit sudo ausführen
        full_command = f"echo '{sudo_password}' | sudo -S {command}"
        result = subprocess.run(full_command, shell=True, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        if "incorrect password" in error_msg.lower():
            print(f"{ORANGE}Fehler: Falsches Passwort.{RESET}")
            sudo_password = None  # Passwort zurücksetzen
        else:
            print(f"{ORANGE}Fehler bei der Ausführung: {error_msg}{RESET}")
        return None

def menu():
    """Zeigt das Menü an und verarbeitet die Benutzerauswahl."""
    get_sudo_password()  # Passwort am Anfang abfragen

    while True:
        print(f"\n{ORANGE}--- UFW Firewall Verwaltung ---{RESET}")
        print("1. Neue Regel hinzufügen")
        print("2. Regel löschen")
        print("3. Firewall-Status anzeigen")
        print("4. Gesetzte UFW-Regeln anzeigen")
        print("5. UFW aktivieren (enable)")
        print("6. UFW deaktivieren (disable)")
        print("7. UFW neu laden (reload)")
        print("8. Standard-Policy setzen")
        print("9. Limit-Regel hinzufügen")
        print("10. Beenden")
        choice = input("Bitte eine Option wählen (1-10): ").strip()

        if choice == '1':
            add_rule()
        elif choice == '2':
            delete_rule()
        elif choice == '3':
            show_status()
        elif choice == '4':
            show_rules()
        elif choice == '5':
            enable_ufw()
        elif choice == '6':
            disable_ufw()
        elif choice == '7':
            reload_ufw()
        elif choice == '8':
            set_default_policy()
        elif choice == '9':
            add_limit_rule()
        elif choice == '10':
            print("Beende das Programm.")
            break
        else:
            print(f"{ORANGE}Ungültige Eingabe. Bitte erneut versuchen.{RESET}")

def add_rule():
    """Fügt eine neue UFW-Regel hinzu."""
    try:
        port = input("Portnummer eingeben: ").strip()
        protocol = input("Protokoll wählen (tcp/udp): ").strip().lower()
        description = input("Beschreibung für die Regel (optional): ").strip()

        # Validierung der Eingaben
        if not port.isdigit() or int(port) < 1 or int(port) > 65535:
            print(f"{ORANGE}Ungültige Portnummer (1-65535).{RESET}")
            return
        if protocol not in ('tcp', 'udp'):
            print(f"{ORANGE}Ungültiges Protokoll. Bitte 'tcp' oder 'udp' eingeben.{RESET}")
            return

        command = f"ufw allow {port}/{protocol}"
        if description:
            command += f" comment '{description}'"

        result = run_command(command)
        if result is not None:
            print(f"{ORANGE}✓ Regel hinzugefügt: {port}/{protocol}{RESET}")
    except Exception as e:
        print(f"{ORANGE}Fehler beim Hinzufügen der Regel: {e}{RESET}")

def delete_rule():
    """Löscht eine bestehende UFW-Regel anhand der Regelnummer."""
    show_status()
    rule_number = input("\nNummer der zu löschenden Regel eingeben: ").strip()
    if not rule_number.isdigit():
        print(f"{ORANGE}Ungültige Nummer.{RESET}")
        return
    command = f"ufw delete {rule_number}"
    result = run_command(command)
    if result is not None:
        print(f"{ORANGE}✓ Regel gelöscht: Regelnummer {rule_number}{RESET}")

def show_status():
    """Zeigt den Status der Firewall an."""
    result = run_command("ufw status")
    if result is not None:
        print(f"\n{ORANGE}UFW Status:{RESET}")
        print(result)

def show_rules():
    """Zeigt alle gesetzten UFW-Regeln mit Nummern an."""
    result = run_command("ufw status numbered")
    if result is not None:
        print(f"\n{ORANGE}Gesetzte UFW-Regeln:{RESET}")
        print(result)

def enable_ufw():
    """Aktiviert UFW."""
    result = run_command("ufw enable")
    if result is not None:
        print(f"{ORANGE}✓ UFW aktiviert.{RESET}")

def disable_ufw():
    """Deaktiviert UFW."""
    confirm = input(f"{ORANGE}Wirklich deaktivieren? (ja/nein): {RESET}").strip().lower()
    if confirm in ('ja', 'yes', 'y'):
        result = run_command("ufw disable")
        if result is not None:
            print(f"{ORANGE}✓ UFW deaktiviert.{RESET}")
    else:
        print("Abgebrochen.")

def reload_ufw():
    """Lädt UFW neu."""
    result = run_command("ufw reload")
    if result is not None:
        print(f"{ORANGE}✓ UFW neu geladen.{RESET}")

def set_default_policy():
    """Setzt die Standard-Policy für incoming und outgoing Verbindungen."""
    incoming = input("Standard-Policy für incoming (allow/deny/reject): ").strip().lower()
    outgoing = input("Standard-Policy für outgoing (allow/deny/reject): ").strip().lower()

    if incoming not in ('allow', 'deny', 'reject'):
        print(f"{ORANGE}Ungültige Policy für incoming.{RESET}")
        return
    if outgoing not in ('allow', 'deny', 'reject'):
        print(f"{ORANGE}Ungültige Policy für outgoing.{RESET}")
        return

    cmd_in = f"ufw default {incoming} incoming"
    cmd_out = f"ufw default {outgoing} outgoing"

    res_in = run_command(cmd_in)
    res_out = run_command(cmd_out)

    if res_in is not None:
        print(f"{ORANGE}✓ Standard-Policy für incoming gesetzt: {incoming}{RESET}")
    if res_out is not None:
        print(f"{ORANGE}✓ Standard-Policy für outgoing gesetzt: {outgoing}{RESET}")

def add_limit_rule():
    """Fügt eine Limit-Regel hinzu, um z.B. Brute-Force-Angriffe zu verhindern."""
    port = input("Portnummer für die Limit-Regel eingeben: ").strip()
    protocol = input("Protokoll wählen (tcp/udp): ").strip().lower()

    if not port.isdigit() or int(port) < 1 or int(port) > 65535:
        print(f"{ORANGE}Ungültige Portnummer (1-65535).{RESET}")
        return
    if protocol not in ('tcp', 'udp'):
        print(f"{ORANGE}Ungültiges Protokoll. Bitte 'tcp' oder 'udp' eingeben.{RESET}")
        return

    command = f"ufw limit {port}/{protocol}"
    result = run_command(command)
    if result is not None:
        print(f"{ORANGE}✓ Limit-Regel hinzugefügt: {port}/{protocol}{RESET}")

if __name__ == "__main__":
    check_platform()
    menu()
