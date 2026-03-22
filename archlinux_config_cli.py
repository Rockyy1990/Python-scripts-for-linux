#!/usr/bin/env python3
# config_menu_arch_min.py
# Arch Linux Konfigurations-Menü (Orange Schrift) mit Kurzanleitung

import os, shutil, subprocess, tempfile

ORANGE = "\033[38;5;208m"
RESET = "\033[0m"
BOLD = "\033[1m"

CONFIG_FILES = [
    ("Kurzanleitung", "help:"),
    ("Pacman config", "/etc/pacman.conf"),
    ("Pacman mirrors (rankmirrors/etc)", "/etc/pacman.d/mirrorlist"),
    ("Makepkg config", "/etc/makepkg.conf"),
    ("systemd journal conf", "/etc/systemd/journald.conf"),
    ("systemd network example", "/etc/systemd/network/"),
    ("NetworkManager (system wide)", "/etc/NetworkManager/NetworkManager.conf"),
    ("Netctl profile dir", "/etc/netctl/"),
    ("Hostname", "/etc/hostname"),
    ("Hosts", "/etc/hosts"),
    ("resolv.conf (DNS)", "/etc/resolv.conf"),
    ("fstab", "/etc/fstab"),
    ("mkinitcpio config", "/etc/mkinitcpio.conf"),
    ("GRUB config", "/etc/default/grub"),
    ("bootloader (systemd-boot entries)", "/boot/loader/entries/"),
    ("sudoers (use visudo!)", "/etc/sudoers"),
    ("Pacman hooks dir", "/etc/pacman.d/hooks/"),
    ("Locale config", "/etc/locale.conf"),
    ("Environment (system)", "/etc/environment"),
    ("Bashrc (user)", os.path.expanduser("~/.bashrc")),
    ("Profile (user)", os.path.expanduser("~/.profile")),
    ("Crontab (user)", "crontab:"),
    ("Exit", None),
]

def has_command(cmd): return shutil.which(cmd) is not None
def clear(): os.system("clear" if os.name != "nt" else "cls")

def ensure_parent(path):
    parent = os.path.dirname(path) or "."
    try:
        os.makedirs(parent, exist_ok=True)
    except PermissionError:
        return False
    return True

def show_help():
    clear()
    print(f"{ORANGE}{BOLD}Kurzanleitung{RESET}\n")
    print("1) Wähle eine Nummer, um die jeweilige Konfigurationsdatei zu öffnen.")
    print("2) Falls EDITOR gesetzt ist, wird dieser verwendet; sonst nano → vi.")
    print("3) Für systemweite Dateien sind meist root-Rechte nötig (sudo).")
    print("4) 'sudoers' bitte nur mit visudo bearbeiten.")
    print("5) Verzeichnisse werden als Dateiliste in einem temporären File angezeigt.")
    print("\nDrücke Enter, um zum Menü zurückzukehren.")
    input()

def open_with_editor(path):
    if path == "help:":
        show_help()
        return
    if path == "crontab:":
        try:
            subprocess.run([os.environ.get("EDITOR", "nano"), "-c"], check=False)
            subprocess.run(["crontab", "-e"], check=True)
        except subprocess.CalledProcessError:
            print("Fehler: crontab konnte nicht geöffnet werden.")
        return

    editor_env = os.environ.get("EDITOR")
    if editor_env and has_command(editor_env.split()[0]):
        editor_cmd = editor_env.split()
    else:
        if has_command("nano"):
            editor_cmd = ["nano"]
        elif has_command("vi"):
            editor_cmd = ["vi"]
        else:
            print("Kein geeigneter Editor (nano/vi) gefunden.")
            return

    if path.endswith("/") or os.path.isdir(path):
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except PermissionError:
                print("Keine Berechtigung, Verzeichnis zu erstellen.")
                return
        listing = "\n".join(sorted(os.listdir(path)))
        tf = tempfile.NamedTemporaryFile(mode="w+", delete=False, prefix="dirlist_", suffix=".txt")
        tf.write(f"Directory: {path}\n\n{listing}\n")
        tf.close()
        cmd = editor_cmd + [tf.name]
    else:
        if not os.path.exists(path):
            if not ensure_parent(path):
                print("Keine Berechtigung, Datei/Verzeichnis zu erstellen.")
                return
            try:
                open(path, "a").close()
            except PermissionError:
                print("Keine Berechtigung, Datei zu erstellen.")
                return
        cmd = editor_cmd + [path]

    try:
        subprocess.run(cmd)
    except Exception as e:
        print(f"Fehler beim Starten des Editors: {e}")

def print_menu():
    clear()
    print(f"{ORANGE}{BOLD}Arch Linux Konfigurations-Menü{RESET}\n")
    for i, (label, path) in enumerate(CONFIG_FILES, start=1):
        path_display = path if path is not None else ""
        print(f"{ORANGE}{i:2}. {RESET}{label} {ORANGE}{path_display}{RESET}")
    print()

def main():
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print(f"{ORANGE}Hinweis: Für viele Systemdateien ist root-Recht erforderlich. Starte ggf. mit sudo.{RESET}\n")
    if not has_command("nano") and not has_command("vi") and not os.environ.get("EDITOR"):
        print("Warnung: Weder 'nano' noch 'vi' gefunden und EDITOR nicht gesetzt.")
    try:
        while True:
            print_menu()
            try:
                choice = input(f"{ORANGE}Wahl (Nummer): {RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not choice.isdigit(): continue
            idx = int(choice) - 1
            if idx < 0 or idx >= len(CONFIG_FILES): continue
            label, path = CONFIG_FILES[idx]
            if label.lower().startswith("exit"): break
            print(f"\n{ORANGE}Öffne: {label} -> {path}{RESET}\n")
            open_with_editor(path)
    except KeyboardInterrupt:
        pass
    print("\nFertig.")

if __name__ == "__main__":
    main()
