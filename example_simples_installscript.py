#!/usr/bin/env python

import subprocess
import sys

def install_package(package_name):
    try:
        # Hier den Platzhalter für den Paketmanager ersetzen
        # Beispiel: 'apt install' für Debian-basierte Systeme
        subprocess.run(['sudo', 'apt', 'install', '-y', package_name], check=True)
        print(f"{package_name} wurde erfolgreich installiert.")
    except subprocess.CalledProcessError:
        print(f"Fehler bei der Installation von {package_name}.")
    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")

def main():
    print("Willkommen zum Programm-Installer!")
    print("Bitte wähle die Programme, die du installieren möchtest:")
    print("1. Programm A")
    print("2. Programm B")
    print("3. Programm C")
    print("4. Programm D")
    
    # Eingabeaufforderung für die Auswahl der Programme
    user_input = input("Gib die Nummern der Programme ein, die du installieren möchtest (z.B. 1,2,3): ")
    selected_programs = user_input.split(',')

    # Mapping der Programmnummern zu den tatsächlichen Paketnamen
    program_mapping = {
        '1': 'programm-a',  # Ersetze durch den tatsächlichen Paketnamen
        '2': 'programm-b',  # Ersetze durch den tatsächlichen Paketnamen
        '3': 'programm-c',  # Ersetze durch den tatsächlichen Paketnamen
        '4': 'programm-d'   # Ersetze durch den tatsächlichen Paketnamen
    }

    for program in selected_programs:
        program = program.strip()  # Entferne Leerzeichen
        if program in program_mapping:
            install_package(program_mapping[program])
        else:
            print(f"Ungültige Auswahl: {program}")

if __name__ == "__main__":
    main()