#!/usr/bin/env python3

import os
import sys
import shlex
import subprocess
import shutil

def run_command(cmd, use_sudo=False):
    try:
        full_cmd = cmd
        if use_sudo:
            # sudo -E bewahrt Umgebungsvariablen; keine exec/Relauch des ganzen Skripts
            full_cmd = "sudo -E " + cmd
        print(f"\nAusführen: {full_cmd}\n")
        proc = subprocess.run(shlex.split(full_cmd), check=False)
        return proc.returncode
    except FileNotFoundError:
        print("Fehler: Befehl nicht gefunden.")
        return 1
    except Exception as e:
        print("Fehler beim Ausführen:", e)
        return 1

def pacman_install():
    pkg = input("Pacman - Paketname zum Installieren: ").strip()
    if not pkg:
        print("Kein Paketname angegeben.")
        return
    noconfirm = input("Mit --noconfirm installieren? (j/N): ").strip().lower() == "j"
    cmd = f"pacman -S {pkg}"
    if noconfirm:
        cmd += " --noconfirm"
    run_command(cmd, use_sudo=True)

def yay_install():
    pkg = input("Yay - Paketname zum Installieren: ").strip()
    if not pkg:
        print("Kein Paketname angegeben.")
        return
    noconfirm = input("Mit --noconfirm installieren? (j/N): ").strip().lower() == "j"
    cmd = f"yay -S {pkg}"
    if noconfirm:
        cmd += " --noconfirm"
    # Bitte: yay sollte als normaler Benutzer laufen; yay fragt bei Bedarf nach Passwort
    run_command(cmd, use_sudo=False)

def yay_remove():
    pkg = input("Yay - Paketname zum Entfernen: ").strip()
    if not pkg:
        print("Kein Paketname angegeben.")
        return
    noconfirm = input("Mit --noconfirm entfernen? (j/N): ").strip().lower() == "j"
    cmd = f"yay -R {pkg}"
    if noconfirm:
        cmd += " --noconfirm"
    run_command(cmd, use_sudo=False)

def yay_search():
    term = input("Yay - Suchbegriff: ").strip()
    if not term:
        print("Kein Suchbegriff angegeben.")
        return
    cmd = f"yay -Ss {term}"
    run_command(cmd, use_sudo=False)

def check_dependencies():
    missing = []
    for prog in ("pacman", "yay", "sudo"):
        if not shutil.which(prog):
            missing.append(prog)
    if missing:
        print("Hinweis: Folgende Programme wurden nicht gefunden:", ", ".join(missing))

def menu():
    while True:
        print("\n--- Paket-Menü ---")
        print("1) Paket mit pacman installieren (sudo)")
        print("2) Paket mit yay installieren (als User)")
        print("3) Paket mit yay suchen (als User)")
        print("4) Paket mit yay entfernen (als User, yay -R)")
        print("5) Beenden")
        choice = input("Auswahl (1-5): ").strip()
        if choice == "1":
            pacman_install()
        elif choice == "2":
            yay_install()
        elif choice == "3":
            yay_search()
        elif choice == "4":
            yay_remove()
        elif choice == "5":
            print("Beenden.")
            break
        else:
            print("Ungültige Auswahl.")

if __name__ == "__main__":
    print("Hinweis: Dieses Skript führt Systembefehle aus. Verwende es mit Vorsicht.")
    check_dependencies()
    menu()
