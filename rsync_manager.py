#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSyncManager - Ein benutzerfreundliches Menu-Script für rsync-Operationen
"""

import os
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

CONFIG_FILE = os.path.expanduser("~/.rsync_manager_config.json")

class RsyncManager:
    def __init__(self):
        self.config = self.load_config()
    
    def load_config(self):
        """Lädt gespeicherte Konfigurationen"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {"profiles": {}}
    
    def save_config(self):
        """Speichert Konfigurationen"""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def clear_screen(self):
        """Löscht den Bildschirm"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def print_header(self, title):
        """Druckt einen formatierten Header"""
        self.clear_screen()
        print("=" * 60)
        print(f"  {title}".center(60))
        print("=" * 60)
        print()
    
    def main_menu(self):
        """Hauptmenü"""
        while True:
            self.print_header("RSyncManager - Hauptmenü")
            print("1. Synchronisierung durchführen")
            print("2. Neue Synchronisierungsprofil erstellen")
            print("3. Synchronisierungsprofile verwalten")
            print("4. Einstellungen")
            print("5. Beenden")
            print()
            
            choice = input("Bitte wählen Sie eine Option (1-5): ").strip()
            
            if choice == '1':
                self.sync_menu()
            elif choice == '2':
                self.create_profile()
            elif choice == '3':
                self.manage_profiles()
            elif choice == '4':
                self.settings_menu()
            elif choice == '5':
                print("\nAuf Wiedersehen!")
                sys.exit(0)
            else:
                input("\n⚠️  Ungültige Eingabe. Drücken Sie Enter...")
    
    def sync_menu(self):
        """Menü für Synchronisierungen"""
        self.print_header("Synchronisierung durchführen")
        
        if not self.config["profiles"]:
            print("❌ Keine Profile vorhanden. Bitte erstellen Sie zuerst ein Profil.")
            input("\nDrücken Sie Enter zum Fortfahren...")
            return
        
        profiles = list(self.config["profiles"].keys())
        for i, profile in enumerate(profiles, 1):
            print(f"{i}. {profile}")
        print(f"{len(profiles) + 1}. Zurück")
        print()
        
        try:
            choice = int(input("Wählen Sie ein Profil: ")) - 1
            if choice == len(profiles):
                return
            if 0 <= choice < len(profiles):
                profile_name = profiles[choice]
                self.execute_sync(profile_name)
            else:
                input("\n⚠️  Ungültige Eingabe. Drücken Sie Enter...")
        except ValueError:
            input("\n⚠️  Ungültige Eingabe. Drücken Sie Enter...")
    
    def execute_sync(self, profile_name):
        """Führt rsync mit dem angegebenen Profil aus"""
        self.print_header(f"Synchronisierung: {profile_name}")
        
        profile = self.config["profiles"][profile_name]
        source = profile["source"]
        destination = profile["destination"]
        options = profile.get("options", "-avz")
        
        # Validierung
        if not os.path.exists(source):
            print(f"❌ Quelle existiert nicht: {source}")
            input("\nDrücken Sie Enter zum Fortfahren...")
            return
        
        # rsync-Befehl zusammenstellen
        cmd = f"rsync {options} '{source}' '{destination}'"
        
        print(f"📁 Quelle: {source}")
        print(f"📁 Ziel: {destination}")
        print(f"⚙️  Optionen: {options}")
        print()
        print("Befehl:")
        print(f"  {cmd}")
        print()
        
        confirm = input("Synchronisierung starten? (j/n): ").strip().lower()
        if confirm != 'j':
            print("❌ Abgebrochen.")
            input("\nDrücken Sie Enter zum Fortfahren...")
            return
        
        print("\n⏳ Synchronisierung läuft...\n")
        
        try:
            start_time = datetime.now()
            result = subprocess.run(cmd, shell=True, capture_output=False)
            end_time = datetime.now()
            duration = end_time - start_time
            
            if result.returncode == 0:
                print(f"\n✅ Synchronisierung erfolgreich abgeschlossen!")
                print(f"⏱️  Dauer: {duration}")
            else:
                print(f"\n❌ Fehler bei der Synchronisierung (Code: {result.returncode})")
        except Exception as e:
            print(f"\n❌ Fehler: {e}")
        
        input("\nDrücken Sie Enter zum Fortfahren...")
    
    def create_profile(self):
        """Erstellt ein neues Synchronisierungsprofil"""
        self.print_header("Neues Profil erstellen")
        
        name = input("Profilname: ").strip()
        if not name:
            print("❌ Name darf nicht leer sein.")
            input("\nDrücken Sie Enter zum Fortfahren...")
            return
        
        if name in self.config["profiles"]:
            print(f"❌ Profil '{name}' existiert bereits.")
            input("\nDrücken Sie Enter zum Fortfahren...")
            return
        
        source = input("Quellverzeichnis: ").strip()
        if not source:
            print("❌ Quelle darf nicht leer sein.")
            input("\nDrücken Sie Enter zum Fortfahren...")
            return
        
        destination = input("Zielverzeichnis: ").strip()
        if not destination:
            print("❌ Ziel darf nicht leer sein.")
            input("\nDrücken Sie Enter zum Fortfahren...")
            return
        
        print("\nRsync-Optionen (Standard: -avz)")
        print("  -a  : Archivmodus")
        print("  -v  : Verbose")
        print("  -z  : Komprimierung")
        print("  -e  : Remote shell")
        print("  --delete : Lösche Dateien im Ziel, die nicht in der Quelle existieren")
        print()
        
        options = input("Optionen (Enter für Standard): ").strip()
        if not options:
            options = "-avz"
        
        self.config["profiles"][name] = {
            "source": source,
            "destination": destination,
            "options": options
        }
        self.save_config()
        
        print(f"\n✅ Profil '{name}' erfolgreich erstellt!")
        input("\nDrücken Sie Enter zum Fortfahren...")
    
    def manage_profiles(self):
        """Verwaltet Synchronisierungsprofile"""
        while True:
            self.print_header("Profile verwalten")
            
            if not self.config["profiles"]:
                print("❌ Keine Profile vorhanden.")
                input("\nDrücken Sie Enter zum Fortfahren...")
                return
            
            profiles = list(self.config["profiles"].keys())
            for i, profile in enumerate(profiles, 1):
                p = self.config["profiles"][profile]
                print(f"{i}. {profile}")
                print(f"   Quelle: {p['source']}")
                print(f"   Ziel: {p['destination']}")
                print()
            
            print(f"{len(profiles) + 1}. Zurück")
            print()
            
            try:
                choice = int(input("Wählen Sie ein Profil zum Bearbeiten: ")) - 1
                if choice == len(profiles):
                    return
                if 0 <= choice < len(profiles):
                    profile_name = profiles[choice]
                    self.edit_profile(profile_name)
                else:
                    input("\n⚠️  Ungültige Eingabe. Drücken Sie Enter...")
            except ValueError:
                input("\n⚠️  Ungültige Eingabe. Drücken Sie Enter...")
    
    def edit_profile(self, profile_name):
        """Bearbeitet ein Profil"""
        self.print_header(f"Profil bearbeiten: {profile_name}")
        
        profile = self.config["profiles"][profile_name]
        print(f"1. Quelle ändern: {profile['source']}")
        print(f"2. Ziel ändern: {profile['destination']}")
        print(f"3. Optionen ändern: {profile['options']}")
        print("4. Profil löschen")
        print("5. Zurück")
        print()
        
        choice = input("Wählen Sie eine Option: ").strip()
        
        if choice == '1':
            new_source = input("Neue Quelle: ").strip()
            if new_source:
                profile['source'] = new_source
                self.save_config()
                print("✅ Gespeichert!")
        elif choice == '2':
            new_dest = input("Neues Ziel: ").strip()
            if new_dest:
                profile['destination'] = new_dest
                self.save_config()
                print("✅ Gespeichert!")
        elif choice == '3':
            new_options = input("Neue Optionen: ").strip()
            if new_options:
                profile['options'] = new_options
                self.save_config()
                print("✅ Gespeichert!")
        elif choice == '4':
            confirm = input(f"Profil '{profile_name}' wirklich löschen? (j/n): ").strip().lower()
            if confirm == 'j':
                del self.config["profiles"][profile_name]
                self.save_config()
                print(f"✅ Profil '{profile_name}' gelöscht!")
        
        input("\nDrücken Sie Enter zum Fortfahren...")
    
    def settings_menu(self):
        """Einstellungsmenü"""
        self.print_header("Einstellungen")
        
        print("1. Konfigurationsdatei anzeigen")
        print("2. Alle Profile löschen (⚠️  Vorsicht!)")
        print("3. Zurück")
        print()
        
        choice = input("Wählen Sie eine Option: ").strip()
        
        if choice == '1':
            print("\nKonfigurationsdatei: " + CONFIG_FILE)
            print("\nInhalt:")
            print(json.dumps(self.config, indent=2))
        elif choice == '2':
            confirm = input("\n⚠️  Alle Profile wirklich löschen? (j/n): ").strip().lower()
            if confirm == 'j':
                self.config["profiles"] = {}
                self.save_config()
                print("✅ Alle Profile gelöscht!")
        
        input("\nDrücken Sie Enter zum Fortfahren...")

def main():
    """Hauptfunktion"""
    try:
        manager = RsyncManager()
        manager.main_menu()
    except KeyboardInterrupt:
        print("\n\n⚠️  Unterbrochen durch Benutzer.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
