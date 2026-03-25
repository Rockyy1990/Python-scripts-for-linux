#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Einfacher systemd-Manager mit Terminal-Menü.
Benötigt Python 3.8+ (empfohlen 3.11+).
Farbige Ausgabe: Orange (ANSI).
Hinweis: Viele systemctl-Befehle erfordern root-Rechte.
"""

from __future__ import annotations
import os
import subprocess
import sys
import shlex
from typing import Optional

# ANSI-Farben (Orange approximiert mit 38;5;208)
ORANGE = "\033[38;5;208m"
BOLD = "\033[1m"
RESET = "\033[0m"

def colored(text: str, color: str = ORANGE, bold: bool = False) -> str:
    return f"{BOLD if bold else ''}{color}{text}{RESET}"

def run_command(cmd: str, capture_output: bool = False, check: bool = False) -> subprocess.CompletedProcess:
    """Führt einen Shell-Befehl sicher aus und gibt CompletedProcess zurück."""
    args = shlex.split(cmd)
    try:
        return subprocess.run(args, capture_output=capture_output, text=True, check=check)
    except subprocess.CalledProcessError as e:
        return e  # type: ignore
    except FileNotFoundError as e:
        # Erzeuge ein CompletedProcess-ähnliches Objekt minimal
        cp = subprocess.CompletedProcess(args, 127, stdout="", stderr=str(e))
        return cp

def os_geteuid() -> int:
    try:
        return os.geteuid()
    except Exception:
        return -1

def relaunch_with_sudo_if_needed() -> None:
    if sys.platform != "linux":
        return
    if os_geteuid() == 0:
        return
    sudo = shutil_which("sudo")
    if not sudo:
        print(colored("Dieses Skript sollte als Root ausgeführt werden. Bitte mit sudo starten.", bold=True))
        return
    python = sys.executable or "python3"
    args = [sudo, python] + sys.argv
    try:
        os.execvp(sudo, args)
    except Exception as e:
        print(colored(f"Fehler beim Neustart mit sudo: {e}", bold=True))

def shutil_which(name: str) -> Optional[str]:
    # kleine Hilfsfunktion, um shutil nicht an mehreren Stellen zu importieren
    try:
        import shutil
        return shutil.which(name)
    except Exception:
        return None

def require_root_warn() -> None:
    if sys.platform != "linux":
        print(colored("Warnung: Dieses Skript ist für Linux/systemd gedacht.", bold=True))
    if (sys.platform == "linux") and (os_geteuid() != 0):
        print(colored("Hinweis: Viele Aktionen benötigen root. Starte mit sudo für volle Funktionalität.", bold=True))

def prompt_service_name(default: Optional[str] = None) -> str:
    prompt = "Dienstname (z. B. ssh.service)"
    if default:
        prompt += f" [{default}]"
    prompt += ": "
    s = input(colored(prompt))
    return s.strip() if s.strip() else (default or "")

def show_menu() -> None:
    print()
    print(colored("Systemd Manager", bold=True))
    print(colored("-----------------", bold=True))
    print(colored("1) Status anzeigen"))
    print(colored("2) Starten"))
    print(colored("3) Stoppen"))
    print(colored("4) Neustarten"))
    print(colored("5) Enable (Autostart aktivieren)"))
    print(colored("6) Disable (Autostart deaktivieren)"))
    print(colored("7) Journal anzeigen (journald)"))
    print(colored("8) Liste aller Units (kurz)"))
    print(colored("9) Exit"))
    print()

def action_status(service: str) -> None:
    print(colored(f"\n=== Status: {service} ===\n", bold=True))
    res = run_command(f"systemctl status {service}", capture_output=True)
    out = getattr(res, "stdout", None) or getattr(res, "stderr", None) or str(res)
    print(out)

def action_start(service: str) -> None:
    print(colored(f"\n=== Start: {service} ===\n", bold=True))
    res = run_command(f"systemctl start {service}")
    if getattr(res, "returncode", 0) == 0:
        print(colored("Erfolgreich gestartet."))
    else:
        print(colored(f"Fehler beim Starten (RC={getattr(res, 'returncode', '?')})."))

def action_stop(service: str) -> None:
    print(colored(f"\n=== Stop: {service} ===\n", bold=True))
    res = run_command(f"systemctl stop {service}")
    if getattr(res, "returncode", 0) == 0:
        print(colored("Erfolgreich gestoppt."))
    else:
        print(colored(f"Fehler beim Stoppen (RC={getattr(res, 'returncode', '?')})."))

def action_restart(service: str) -> None:
    print(colored(f"\n=== Restart: {service} ===\n", bold=True))
    res = run_command(f"systemctl restart {service}")
    if getattr(res, "returncode", 0) == 0:
        print(colored("Erfolgreich neu gestartet."))
    else:
        print(colored(f"Fehler beim Neustart (RC={getattr(res, 'returncode', '?')})."))

def action_enable(service: str) -> None:
    print(colored(f"\n=== Enable: {service} ===\n", bold=True))
    res = run_command(f"systemctl enable {service}", capture_output=True)
    if getattr(res, "returncode", 0) == 0:
        print(colored("Autostart aktiviert."))
    else:
        err = getattr(res, "stderr", "") or getattr(res, "stdout", "")
        print(colored(f"Fehler beim Aktivieren: {err}"))

def action_disable(service: str) -> None:
    print(colored(f"\n=== Disable: {service} ===\n", bold=True))
    res = run_command(f"systemctl disable {service}", capture_output=True)
    if getattr(res, "returncode", 0) == 0:
        print(colored("Autostart deaktiviert."))
    else:
        err = getattr(res, "stderr", "") or getattr(res, "stdout", "")
        print(colored(f"Fehler beim Deaktivieren: {err}"))

def action_journal(service: str) -> None:
    print(colored(f"\n=== Journal: {service} (letzte 200 Zeilen) ===\n", bold=True))
    res = run_command(f"journalctl -u {service} -n 200 --no-pager", capture_output=True)
    if getattr(res, "stdout", None):
        print(res.stdout)
    else:
        err = getattr(res, "stderr", "") or ""
        print(colored("Keine Journal-Einträge gefunden oder Fehler." + (f" ({err})" if err else "")))

def action_list_units() -> None:
    print(colored("\n=== Units (kurz) ===\n", bold=True))
    res = run_command("systemctl list-units --type=service --no-pager --all --no-legend", capture_output=True)
    out = getattr(res, "stdout", "") or ""
    lines = [l for l in out.splitlines() if l.strip()]
    for i, line in enumerate(lines[:200], start=1):
        parts = line.split()
        name = parts[0] if parts else line
        state = parts[3] if len(parts) > 3 else ""
        print(colored(f"{i:3d}. {name}  {state}"))

def main_loop() -> None:
    # Prüfe und ggf. versuche Neustart mit sudo
    relaunch_with_sudo_if_needed()
    require_root_warn()
    while True:
        show_menu()
        choice = input(colored("Wähle Option [1-9]: ", bold=True)).strip()
        if choice == "9":
            print(colored("Beende."))
            break
        if choice not in {"1","2","3","4","5","6","7","8"}:
            print(colored("Ungültige Auswahl.", bold=True))
            continue

        if choice == "8":
            action_list_units()
            continue

        default_service = "ssh.service"
        svc = prompt_service_name(default_service)
        if not svc:
            print(colored("Kein Dienstname angegeben."))
            continue

        if choice == "1":
            action_status(svc)
        elif choice == "2":
            action_start(svc)
        elif choice == "3":
            action_stop(svc)
        elif choice == "4":
            action_restart(svc)
        elif choice == "5":
            action_enable(svc)
        elif choice == "6":
            action_disable(svc)
        elif choice == "7":
            action_journal(svc)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n" + colored("Abbruch durch Benutzer.", bold=True))
        sys.exit(0)
