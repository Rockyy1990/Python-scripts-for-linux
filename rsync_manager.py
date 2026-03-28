#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSyncManager - Benutzerfreundliches Menü-Script für rsync-Operationen
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Konfiguration ──────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / ".rsync_manager_config.json"

logging.basicConfig(
    filename=Path.home() / ".rsync_manager.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def clear_screen() -> None:
    os.system("clear" if os.name == "posix" else "cls")


def pause(msg: str = "\nDrücken Sie Enter zum Fortfahren...") -> None:
    input(msg)


def print_header(title: str) -> None:
    clear_screen()
    print("=" * 60)
    print(title.center(60))
    print("=" * 60)
    print()


def ask(prompt: str, default: str = "") -> str:
    """Eingabe mit optionalem Standardwert."""
    hint = f" [{default}]" if default else ""
    value = input(f"{prompt}{hint}: ").strip()
    return value or default


def confirm(prompt: str) -> bool:
    return input(f"{prompt} (j/n): ").strip().lower() == "j"


def pick_from_list(items: list[str], label: str = "Option") -> Optional[int]:
    """
    Zeigt eine nummerierte Liste und gibt den gewählten Index zurück.
    Gibt None zurück, wenn der Nutzer abbricht (letzte Option).
    """
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")
    back_num = len(items) + 1
    print(f"  {back_num}. Zurück")
    print()
    try:
        choice = int(input(f"Wählen Sie {label} (1–{back_num}): ")) - 1
        if choice == len(items):
            return None
        if 0 <= choice < len(items):
            return choice
    except ValueError:
        pass
    pause("⚠️  Ungültige Eingabe.")
    return None


# ── Hauptklasse ────────────────────────────────────────────────────────────────

class RsyncManager:
    def __init__(self) -> None:
        self.config: dict = self._load_config()

    # ── Persistenz ──────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.warning("Konfigurationsdatei beschädigt – starte neu.")
        return {"profiles": {}}

    def _save_config(self) -> None:
        CONFIG_FILE.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Sync-Logik ──────────────────────────────────────────────────────────

    def _build_rsync_cmd(self, profile: dict) -> list[str]:
        """Baut den rsync-Befehl als sichere Argumentliste (kein shell=True)."""
        options: str = profile.get("options", "-avz")
        # Optionen als einzelne Tokens aufteilen
        opt_tokens = options.split()
        # Quelle immer mit trailing slash normalisieren, wenn Verzeichnis
        source = profile["source"].rstrip("/") + "/"
        dest   = profile["destination"]
        return ["rsync", *opt_tokens, source, dest]

    def _execute_sync(self, profile_name: str) -> None:
        print_header(f"Synchronisierung: {profile_name}")
        profile = self.config["profiles"][profile_name]
        source  = Path(profile["source"])
        dest    = profile["destination"]
        cmd     = self._build_rsync_cmd(profile)

        # Lokale Quelle prüfen (bei SSH-Zielen nur optional)
        if not source.exists() and not dest.startswith(("ssh://", "rsync://")):
            if not source.is_absolute() or ":" not in str(source):
                print(f"❌ Quelle nicht gefunden: {source}")
                pause()
                return

        print(f"  📂 Quelle : {profile['source']}")
        print(f"  📂 Ziel   : {dest}")
        print(f"  ⚙️  Optionen: {profile.get('options', '-avz')}")
        print(f"\n  Befehl: {' '.join(cmd)}\n")

        if not confirm("Synchronisierung starten?"):
            print("Abgebrochen.")
            pause()
            return

        print("\n⏳ Synchronisierung läuft...\n")
        log.info("Starte Sync '%s': %s", profile_name, " ".join(cmd))

        start = datetime.now()
        try:
            result = subprocess.run(cmd, check=False)
            duration = datetime.now() - start

            if result.returncode == 0:
                print(f"\n✅ Fertig! Dauer: {duration}")
                log.info("Sync '%s' erfolgreich (%s)", profile_name, duration)
            else:
                print(f"\n❌ rsync beendete mit Code {result.returncode}")
                log.error("Sync '%s' fehlgeschlagen (Code %d)", profile_name, result.returncode)
        except FileNotFoundError:
            print("\n❌ rsync nicht gefunden – bitte installieren.")
            log.error("rsync nicht installiert")
        except Exception as exc:
            print(f"\n❌ Unerwarteter Fehler: {exc}")
            log.exception("Sync '%s' Ausnahme", profile_name)

        pause()

    # ── Profil-Verwaltung ───────────────────────────────────────────────────

    def _create_profile(self) -> None:
        print_header("Neues Profil erstellen")

        name = ask("Profilname").strip()
        if not name:
            pause("❌ Name darf nicht leer sein.")
            return
        if name in self.config["profiles"]:
            pause(f"❌ Profil '{name}' existiert bereits.")
            return

        source = ask("Quellverzeichnis")
        if not source:
            pause("❌ Quelle darf nicht leer sein.")
            return

        destination = ask("Zielverzeichnis")
        if not destination:
            pause("❌ Ziel darf nicht leer sein.")
            return

        print("\nRsync-Optionen – häufige Flags:")
        options_help = [
            ("  -a", "Archivmodus (rekursiv + Berechtigungen)"),
            ("  -v", "Verbose – zeigt übertragene Dateien"),
            ("  -z", "Komprimierung während Übertragung"),
            ("  -P", "Fortschrittsanzeige + Resume"),
            ("  --delete", "Löscht Dateien im Ziel, die in der Quelle fehlen"),
            ("  --exclude", "Muster ausschließen (z. B. --exclude='*.tmp')"),
        ]
        for flag, desc in options_help:
            print(f"  {flag:<20} {desc}")
        print()

        options = ask("Optionen", default="-avz")

        self.config["profiles"][name] = {
            "source":      source,
            "destination": destination,
            "options":     options,
            "created":     datetime.now().isoformat(timespec="seconds"),
        }
        self._save_config()
        log.info("Profil erstellt: %s", name)
        pause(f"\n✅ Profil '{name}' gespeichert! Enter...")

    def _edit_profile(self, profile_name: str) -> None:
        profile = self.config["profiles"][profile_name]

        while True:
            print_header(f"Profil bearbeiten: {profile_name}")
            print(f"  1. Quelle    : {profile['source']}")
            print(f"  2. Ziel      : {profile['destination']}")
            print(f"  3. Optionen  : {profile['options']}")
            print(f"  4. Profil löschen")
            print(f"  5. Zurück")
            print()

            choice = input("Option (1–5): ").strip()

            field_map = {"1": ("source", "Neue Quelle"), "2": ("destination", "Neues Ziel"), "3": ("options", "Neue Optionen")}

            if choice in field_map:
                key, prompt = field_map[choice]
                value = ask(prompt, default=profile[key])
                if value:
                    profile[key] = value
                    self._save_config()
                    print("✅ Gespeichert!")
                    pause()
            elif choice == "4":
                if confirm(f"Profil '{profile_name}' wirklich löschen?"):
                    del self.config["profiles"][profile_name]
                    self._save_config()
                    log.info("Profil gelöscht: %s", profile_name)
                    pause(f"✅ '{profile_name}' gelöscht. Enter...")
                    return
            elif choice == "5":
                return
            else:
                pause("⚠️  Ungültige Eingabe.")

    def _manage_profiles(self) -> None:
        while True:
            print_header("Profile verwalten")
            profiles = list(self.config["profiles"])

            if not profiles:
                pause("❌ Keine Profile vorhanden.")
                return

            for i, name in enumerate(profiles, 1):
                p = self.config["profiles"][name]
                created = p.get("created", "–")
                print(f"  {i}. {name}  (erstellt: {created})")
                print(f"     📂 {p['source']}  →  {p['destination']}")
                print()

            idx = pick_from_list(profiles, "Profil")
            if idx is None:
                return
            self._edit_profile(profiles[idx])

    # ── Menüs ───────────────────────────────────────────────────────────────

    def _sync_menu(self) -> None:
        print_header("Synchronisierung durchführen")
        profiles = list(self.config["profiles"])

        if not profiles:
            pause("❌ Keine Profile vorhanden. Bitte zuerst ein Profil erstellen.")
            return

        idx = pick_from_list(profiles, "Profil")
        if idx is not None:
            self._execute_sync(profiles[idx])

    def _settings_menu(self) -> None:
        print_header("Einstellungen")
        print("  1. Konfigurationsdatei anzeigen")
        print("  2. Log-Datei anzeigen (letzte 20 Einträge)")
        print("  3. Alle Profile löschen ⚠️")
        print("  4. Zurück")
        print()

        choice = input("Option (1–4): ").strip()

        if choice == "1":
            print(f"\nDatei: {CONFIG_FILE}\n")
            print(json.dumps(self.config, indent=2, ensure_ascii=False))
            pause()
        elif choice == "2":
            log_file = Path.home() / ".rsync_manager.log"
            if log_file.exists():
                lines = log_file.read_text(encoding="utf-8").splitlines()
                print("\n".join(lines[-20:]))
            else:
                print("Noch keine Log-Einträge.")
            pause()
        elif choice == "3":
            if confirm("⚠️  Alle Profile wirklich löschen?"):
                self.config["profiles"] = {}
                self._save_config()
                log.warning("Alle Profile gelöscht.")
                pause("✅ Alle Profile gelöscht. Enter...")

    def main_menu(self) -> None:
        actions = {
            "1": ("Synchronisierung durchführen",   self._sync_menu),
            "2": ("Neues Profil erstellen",          self._create_profile),
            "3": ("Profile verwalten",               self._manage_profiles),
            "4": ("Einstellungen",                   self._settings_menu),
            "5": ("Beenden",                         None),
        }

        while True:
            print_header("RSyncManager")
            for key, (label, _) in actions.items():
                print(f"  {key}. {label}")
            print()

            choice = input("Option (1–5): ").strip()

            if choice not in actions:
                pause("⚠️  Ungültige Eingabe.")
                continue

            label, fn = actions[choice]
            if fn is None:
                print("\nAuf Wiedersehen!")
                sys.exit(0)
            fn()


# ── Einstiegspunkt ─────────────────────────────────────────────────────────────

def main() -> None:
    try:
        RsyncManager().main_menu()
    except KeyboardInterrupt:
        print("\n\n⚠️  Unterbrochen.")
        sys.exit(0)
    except Exception as exc:
        log.exception("Unbehandelter Fehler")
        print(f"\n❌ Kritischer Fehler: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
