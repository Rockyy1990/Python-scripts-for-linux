#!/usr/bin/env python

import subprocess

def install_package(package_name):
    """Installiert ein Paket mit dem Paketmanager apt."""
    try:
        subprocess.run(['sudo', 'apt', 'install', package_name, '-y'], check=True)
        print(f"Paket '{package_name}' wurde erfolgreich installiert.")
    except subprocess.CalledProcessError:
        print(f"Fehler beim Installieren des Pakets '{package_name}'.")

def remove_package(package_name):
    """Entfernt ein Paket mit dem Paketmanager apt."""
    try:
        subprocess.run(['sudo', 'apt', 'remove', package_name, '-y'], check=True)
        print(f"Paket '{package_name}' wurde erfolgreich entfernt.")
    except subprocess.CalledProcessError:
        print(f"Fehler beim Entfernen des Pakets '{package_name}'.")

def update_system():
    """Aktualisiert die Paketliste und installiert verfügbare Updates."""
    try:
        subprocess.run(['sudo', 'apt', 'update'], check=True)
        subprocess.run(['sudo', 'apt', 'upgrade', '-y'], check=True)
        print("System wurde erfolgreich aktualisiert.")
    except subprocess.CalledProcessError:
        print("Fehler beim Aktualisieren des Systems.")

def show_menu():
    """Zeigt das Hauptmenü an."""
    print("\n--- System Management Menü ---")
    print("1. Paket installieren")
    print("2. Paket entfernen")
    print("3. System aktualisieren")
    print("4. Beenden")

def main():
    while True:
        show_menu()
        choice = input("Bitte wählen Sie eine Option (1-4): ")

        if choice == '1':
            package_name = input("Geben Sie den Namen des zu installierenden Pakets ein: ")
            install_package(package_name)
        elif choice == '2':
            package_name = input("Geben Sie den Namen des zu entfernenden Pakets ein: ")
            remove_package(package_name)
        elif choice == '3':
            update_system()
        elif choice == '4':
            print("Programm wird beendet.")
            break
        else:
            print("Ungültige Auswahl. Bitte versuchen Sie es erneut.")

if __name__ == "__main__":
    main()