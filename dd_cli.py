#!/usr/bin/env python3
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ORANGE = "\033[38;5;208m"
RESET = "\033[0m"

def need_sudo():
    return os.geteuid() != 0

def run_with_sudo(cmd):
    if need_sudo():
        cmd = ["sudo"] + cmd
    return subprocess.run(cmd)

def safe_input_paths(prompt):
    print(prompt + " (Mehrere Pfade durch Komma getrennt, z.B. /dev/sdb,image.iso)")
    raw = input("> ").strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts

def confirm(prompt):
    ans = input(f"{ORANGE}{prompt} [j/N]: {RESET}").strip().lower()
    return ans == "j" or ans == "y"

def check_exists_any(paths):
    for p in paths:
        if Path(p).exists():
            return True
    return False

def run_dd(if_path, of_path, bs="4M", count=None, conv=None):
    cmd = ["dd", f"if={if_path}", f"of={of_path}", f"bs={bs}", "status=progress"]
    if count:
        cmd.append(f"count={count}")
    if conv:
        cmd.append(f"conv={conv}")
    print(ORANGE + "Ausführen: " + " ".join(shlex.quote(c) for c in cmd) + RESET)
    # Use subprocess.run so dd output appears in terminal (no capture)
    return run_with_sudo(cmd)

def write_image_to_devices():
    inputs = safe_input_paths("Eingabedatei(en) (Image-Dateien)")
    outputs = safe_input_paths("Zielgerät(e) (z. B. /dev/sdX) - gleiche Anzahl wie Eingaben oder eine einzelne für Broadcast")
    bs = input("Blockgröße (Standard 4M): ").strip() or "4M"
    if len(outputs) not in (1, len(inputs)):
        print("Anzahl der Ausgaben muss 1 oder gleich der Anzahl der Eingaben sein.")
        return
    if len(outputs) == 1 and len(inputs) > 1:
        # broadcast same output to many inputs? disallow ambiguous mapping
        print("Wenn mehrere Eingabedateien angegeben sind, gib gleiche Anzahl Ausgabegeräte an.")
        return
    for idx, ifp in enumerate(inputs):
        ofp = outputs[0] if len(outputs) == 1 else outputs[idx]
        if not Path(ifp).exists():
            print(f"{ORANGE}Eingabedatei nicht gefunden: {ifp}{RESET}")
            continue
        if not confirm(f"Schreibe {ifp} -> {ofp}? (Daten auf {ofp} werden gelöscht)"):
            print("Übersprungen.")
            continue
        res = run_dd(ifp, ofp, bs=bs, conv="fdatasync")
        if res.returncode == 0:
            print(f"{ORANGE}Fertig: {ifp} -> {ofp}{RESET}")
        else:
            print(f"{ORANGE}Fehler beim Schreiben von {ifp} auf {ofp} (Exit {res.returncode}){RESET}")

def backup_devices_to_images():
    sources = safe_input_paths("Quellgerät(e) (z. B. /dev/sda, /dev/nvme0n1)")
    dests = safe_input_paths("Zieldatei(en) (z. B. backup.img) - gleiche Anzahl wie Quellen oder eine einzelne mit Platzhalter {i}")
    bs = input("Blockgröße (Standard 64K): ").strip() or "64K"
    if len(dests) not in (1, len(sources)):
        print("Anzahl der Zieldateien muss 1 oder gleich der Anzahl der Quellen sein.")
        return
    for idx, src in enumerate(sources):
        dst = dests[0] if len(dests) == 1 else dests[idx]
        # Allow placeholder {i} to create distinct names
        dst = dst.format(i=idx+1)
        if not Path(src).exists():
            print(f"{ORANGE}Quellgerät nicht gefunden: {src}{RESET}")
            continue
        if Path(dst).exists():
            if not confirm(f"Zieldatei {dst} existiert. Überschreiben?"):
                print("Übersprungen.")
                continue
        print(f"{ORANGE}Sichere {src} -> {dst}{RESET}")
        res = run_dd(src, dst, bs=bs)
        if res.returncode == 0:
            print(f"{ORANGE}Backup abgeschlossen: {dst}{RESET}")
        else:
            print(f"{ORANGE}Fehler beim Backup von {src} (Exit {res.returncode}){RESET}")

def wipe_devices():
    targets = safe_input_paths("Zielgerät(e) zum Überschreiben (z. B. /dev/sdb)")
    bs = input("Blockgröße (Standard 1M): ").strip() or "1M"
    passes = input("Mit /dev/zero (1) oder /dev/urandom (2)? (Standard 1): ").strip() or "1"
    filler = "/dev/zero" if passes == "1" else "/dev/urandom"
    for t in targets:
        if not Path(t).exists():
            print(f"{ORANGE}Gerät nicht gefunden: {t}{RESET}")
            continue
        if not confirm(f"Wirklich löschen: {t}? Alle Daten werden unwiederbringlich entfernt."):
            print("Übersprungen.")
            continue
        res = run_dd(filler, t, bs=bs)
        if res.returncode == 0:
            print(f"{ORANGE}Löschen abgeschlossen: {t}{RESET}")
        else:
            print(f"{ORANGE}Fehler beim Löschen von {t} (Exit {res.returncode}){RESET}")

def ensure_dependencies():
    if shutil.which("dd") is None:
        print("Das Programm 'dd' wurde nicht gefunden. Bitte installieren.")
        sys.exit(1)

def main_menu():
    ensure_dependencies()
    while True:
        print(ORANGE + "\nDD-Menu\n1) Image(s) -> USB/Device\n2) Device(s) -> Image(s) (Backup)\n3) Löschen / Überschreiben (zero/urandom)\n4) Beenden" + RESET)
        choice = input("> ").strip()
        if choice == "1":
            write_image_to_devices()
        elif choice == "2":
            backup_devices_to_images()
        elif choice == "3":
            wipe_devices()
        elif choice == "4":
            print("Beende.")
            break
        else:
            print("Ungültige Auswahl.")

if __name__ == "__main__":
    main_menu()
