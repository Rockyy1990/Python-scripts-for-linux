#!/usr/bin/env python3
"""
Rechteverwaltung.py
Interaktives Tool zur Benutzer- und Rechteverwaltung für Linux.

Features:
  - Automatischer Neustart mit sudo wenn nicht root
  - Vollständig deutsches, kategorisiertes Menü
  - Benutzer anlegen, auflisten, sperren/entsperren, löschen
  - Bulk-Anlage aus CSV mit Zeilenfeedback
  - Passwort setzen (interaktiv & non-interaktiv) mit Stärkeprüfung
  - Gruppen anlegen, auflisten, Mitglieder verwalten, Gruppen löschen
  - Kontoinformationen anzeigen
  - Passwort ablaufen lassen (Pflichtänderung bei nächstem Login)
  - sudoers prüfen
  - Audit-Log: /var/log/user_admin_audit.log (UTC-Zeitstempel)
  - ANSI-Farbgebung für alle Ausgabetypen
"""

from __future__ import annotations
import os
import re
import sys
import subprocess
import csv
from datetime import datetime, timezone
import getpass
from typing import List, Optional, Tuple

# ── Farben ─────────────────────────────────────────────────────────────────────
ORANGE  = "\033[38;5;214m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
CYAN    = "\033[36m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"

AUDIT_LOG = "/var/log/user_admin_audit.log"

# Bekannte Login-Shells auf gängigen Linux-Systemen
BEKANNTE_SHELLS = ["/bin/bash", "/bin/zsh", "/bin/sh", "/usr/bin/fish",
                   "/bin/dash", "/usr/bin/zsh", "/sbin/nologin", "/bin/false"]

# Kritische Systemgruppen, die nicht versehentlich gelöscht werden sollen
KRITISCHE_GRUPPEN = {"root", "wheel", "sudo", "users", "adm", "daemon",
                     "sys", "bin", "disk", "shadow", "nogroup"}

# ── Sudo-Neustart ──────────────────────────────────────────────────────────────
def neustart_als_sudo() -> None:
    python = sys.executable or "/usr/bin/env python3"
    sudo_cmd = ["sudo", "-p", "[sudo] Passwort für Rechteverwaltung: ", "--",
                python] + sys.argv
    try:
        os.execvp("sudo", sudo_cmd)
    except Exception as e:
        print(f"{RED}Fehler beim Neustart mit sudo: {e}{RESET}")
        sys.exit(1)

if os.geteuid() != 0:
    print(f"{ORANGE}Root-Rechte erforderlich — starte neu mit sudo …{RESET}")
    neustart_als_sudo()

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────
def audit_log(eintrag: str) -> None:
    """Schreibt einen Eintrag mit UTC-Zeitstempel in die Audit-Logdatei."""
    zeitstempel = datetime.now(timezone.utc).isoformat()
    zeile = f"{zeitstempel}  {eintrag}\n"
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(zeile)
    except PermissionError:
        print(f"{YELLOW}⚠  Audit-Log konnte nicht geschrieben werden: {AUDIT_LOG}{RESET}")



def befehl(cmd: List[str], capture: bool = False,
           eingabe: Optional[str] = None) -> subprocess.CompletedProcess:
    """Führt einen Systembefehl aus und gibt das Ergebnis zurück."""
    try:
        return subprocess.run(
            cmd, capture_output=capture, text=True,
            input=eingabe, check=False
        )
    except FileNotFoundError:
        msg = f"Befehl nicht gefunden: {cmd[0]}"
        return subprocess.CompletedProcess(cmd, returncode=127, stdout="", stderr=msg)
    except Exception as e:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(e))


def benutzer_existiert(name: str) -> bool:
    return befehl(["id", name], capture=True).returncode == 0


def gruppe_existiert(gruppe: str) -> bool:
    return befehl(["getent", "group", gruppe], capture=True).returncode == 0


def gruppe_anlegen_falls_fehlt(gruppe: str) -> bool:
    if gruppe_existiert(gruppe):
        return True
    res = befehl(["groupadd", gruppe], capture=True)
    audit_log(f"groupadd {gruppe} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Gruppe '{gruppe}' konnte nicht angelegt werden: "
              f"{res.stderr.strip()}{RESET}")
        return False
    print(f"{GREEN}✓  Gruppe '{gruppe}' angelegt{RESET}")
    return True


def trennlinie(titel: str = "") -> None:
    breite = 60
    if titel:
        pad = (breite - len(titel) - 2) // 2
        print(f"{DIM}{'─' * pad} {titel} {'─' * pad}{RESET}")
    else:
        print(f"{DIM}{'─' * breite}{RESET}")


def eingabe_nicht_leer(prompt: str) -> str:
    while True:
        wert = input(prompt).strip()
        if wert:
            return wert
        print(f"{YELLOW}  Eingabe darf nicht leer sein.{RESET}")


def benutzername_gueltig(name: str) -> Tuple[bool, str]:
    """Prüft, ob ein Benutzername den Linux-Konventionen entspricht."""
    if not name:
        return False, "Benutzername darf nicht leer sein."
    if len(name) > 32:
        return False, "Benutzername zu lang (max. 32 Zeichen)."
    if not re.match(r'^[a-z_][a-z0-9_\-]*$', name):
        return False, ("Benutzername darf nur Kleinbuchstaben, Ziffern, "
                       "Unter- und Bindestriche enthalten und muss mit "
                       "einem Buchstaben oder _ beginnen.")
    return True, ""


def passwort_staerke(pwd: str) -> Tuple[bool, str]:
    """Einfache Passwort-Stärkeprüfung."""
    if len(pwd) < 8:
        return False, "Passwort zu kurz (mindestens 8 Zeichen)."
    if pwd.isdigit():
        return False, "Passwort darf nicht nur aus Zahlen bestehen."
    if pwd.islower() or pwd.isupper():
        return False, "Passwort sollte Groß- und Kleinbuchstaben enthalten."
    return True, ""


def shell_auswaehlen() -> str:
    """Zeigt verfügbare Shells an und lässt den Benutzer eine wählen."""
    verfuegbar = [s for s in BEKANNTE_SHELLS if os.path.isfile(s)]
    if not verfuegbar:
        return eingabe_nicht_leer("Shell [/bin/bash]: ") or "/bin/bash"
    print(f"{CYAN}  Verfügbare Shells:{RESET}")
    for i, s in enumerate(verfuegbar, 1):
        print(f"    {i}) {s}")
    auswahl = input(f"  Shell wählen [1={verfuegbar[0]}]: ").strip()
    if auswahl.isdigit() and 1 <= int(auswahl) <= len(verfuegbar):
        return verfuegbar[int(auswahl) - 1]
    if auswahl == "":
        return verfuegbar[0]
    # Direkteingabe erlauben
    return auswahl or verfuegbar[0]


# ── Kernoperationen ────────────────────────────────────────────────────────────
def benutzer_anlegen(benutzername: str, vollname: Optional[str] = None,
                     shell: str = "/bin/bash", gruppen: Optional[List[str]] = None,
                     home_erstellen: bool = True,
                     uid: Optional[int] = None) -> bool:
    gueltig, fehler = benutzername_gueltig(benutzername)
    if not gueltig:
        print(f"{RED}✗  Ungültiger Benutzername: {fehler}{RESET}")
        return False
    if benutzer_existiert(benutzername):
        print(f"{YELLOW}⚠  Benutzer '{benutzername}' existiert bereits — übersprungen.{RESET}")
        return False

    cmd = ["useradd"]
    if home_erstellen:
        cmd.append("-m")
    if vollname:
        cmd += ["-c", vollname]
    if shell:
        cmd += ["-s", shell]
    if gruppen:
        for g in gruppen:
            gruppe_anlegen_falls_fehlt(g)
        cmd += ["-G", ",".join(gruppen)]
    if uid is not None:
        cmd += ["-u", str(uid)]
    cmd.append(benutzername)

    print(f"{ORANGE}  Erstelle Benutzer '{benutzername}' …{RESET}")
    res = befehl(cmd, capture=True)
    audit_log(f"useradd user={benutzername} vollname={vollname} "
              f"shell={shell} gruppen={gruppen} uid={uid} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Fehler: {res.stderr.strip() or res.returncode}{RESET}")
        return False
    print(f"{GREEN}✓  Benutzer '{benutzername}' erfolgreich angelegt.{RESET}")
    return True


def passwort_setzen(benutzername: str, passwort: str) -> bool:
    if not benutzer_existiert(benutzername):
        print(f"{RED}✗  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return False
    res = befehl(["chpasswd"], capture=True, eingabe=f"{benutzername}:{passwort}\n")
    audit_log(f"chpasswd user={benutzername} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Passwort konnte nicht gesetzt werden: "
              f"{(res.stderr or res.stdout).strip()}{RESET}")
        return False
    print(f"{GREEN}✓  Passwort für '{benutzername}' gesetzt.{RESET}")
    return True


def passwort_interaktiv(benutzername: str) -> bool:
    if not benutzer_existiert(benutzername):
        print(f"{RED}✗  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return False
    # passwd gibt direkt auf das Terminal aus — kein capture
    res = befehl(["passwd", benutzername])
    audit_log(f"passwd_interactive user={benutzername} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  passwd beendete sich mit Fehlercode {res.returncode}.{RESET}")
        return False
    return True


def passwort_ablaufen_lassen(benutzername: str) -> bool:
    """Erzwingt Passwortänderung beim nächsten Login."""
    if not benutzer_existiert(benutzername):
        print(f"{RED}✗  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return False
    res = befehl(["passwd", "--expire", benutzername], capture=True)
    audit_log(f"passwd_expire user={benutzername} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Fehler: {res.stderr.strip()}{RESET}")
        return False
    print(f"{GREEN}✓  Passwort von '{benutzername}' wurde abgelaufen gesetzt "
          f"(Änderung beim nächsten Login erforderlich).{RESET}")
    return True


def konto_sperren(benutzername: str) -> bool:
    if not benutzer_existiert(benutzername):
        print(f"{RED}✗  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return False
    res = befehl(["usermod", "-L", benutzername], capture=True)
    audit_log(f"usermod_lock user={benutzername} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Fehler beim Sperren: {res.stderr.strip()}{RESET}")
        return False
    print(f"{GREEN}✓  Konto '{benutzername}' gesperrt.{RESET}")
    return True


def konto_entsperren(benutzername: str) -> bool:
    if not benutzer_existiert(benutzername):
        print(f"{RED}✗  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return False
    res = befehl(["usermod", "-U", benutzername], capture=True)
    audit_log(f"usermod_unlock user={benutzername} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Fehler beim Entsperren: {res.stderr.strip()}{RESET}")
        return False
    print(f"{GREEN}✓  Konto '{benutzername}' entsperrt.{RESET}")
    return True


def gruppen_aendern(benutzername: str, hinzufuegen: Optional[List[str]] = None,
                    entfernen: Optional[List[str]] = None) -> bool:
    if not benutzer_existiert(benutzername):
        print(f"{RED}✗  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return False
    cur = befehl(["id", "-nG", benutzername], capture=True)
    aktuelle = set(cur.stdout.strip().split()) if cur.returncode == 0 else set()

    if hinzufuegen:
        for g in hinzufuegen:
            gruppe_anlegen_falls_fehlt(g)
            aktuelle.add(g)
    if entfernen:
        for g in entfernen:
            aktuelle.discard(g)

    gruppen_str = ",".join(sorted(aktuelle)) if aktuelle else ""
    res = befehl(["usermod", "-G", gruppen_str, benutzername], capture=True)
    audit_log(f"modify_groups user={benutzername} add={hinzufuegen} "
              f"remove={entfernen} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Fehler beim Ändern der Gruppen: "
              f"{(res.stderr or res.stdout).strip()}{RESET}")
        return False
    print(f"{GREEN}✓  Gruppenänderungen für '{benutzername}' übernommen.{RESET}")
    return True


def benutzer_loeschen(benutzername: str, home_entfernen: bool = False) -> bool:
    if not benutzer_existiert(benutzername):
        print(f"{YELLOW}⚠  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return False
    cmd = ["userdel"]
    if home_entfernen:
        cmd.append("-r")
    cmd.append(benutzername)
    print(f"{ORANGE}  Lösche Benutzer '{benutzername}' …{RESET}")
    res = befehl(cmd, capture=True)
    audit_log(f"userdel user={benutzername} home_entfernt={home_entfernen} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Fehler: {(res.stderr or res.stdout).strip()}{RESET}")
        return False
    print(f"{GREEN}✓  Benutzer '{benutzername}' gelöscht.{RESET}")
    return True


def gruppe_loeschen(gruppe: str, erzwingen: bool = False) -> bool:
    if not gruppe_existiert(gruppe):
        print(f"{YELLOW}⚠  Gruppe '{gruppe}' existiert nicht.{RESET}")
        return False
    if gruppe in KRITISCHE_GRUPPEN and not erzwingen:
        print(f"{RED}✗  '{gruppe}' ist eine kritische Systemgruppe. "
              f"Nur mit expliziter Bestätigung löschbar.{RESET}")
        return False
    res = befehl(["groupdel", gruppe], capture=True)
    audit_log(f"groupdel group={gruppe} erzwungen={erzwingen} rc={res.returncode}")
    if res.returncode != 0:
        print(f"{RED}✗  Fehler: {(res.stderr or res.stdout).strip()}{RESET}")
        return False
    print(f"{GREEN}✓  Gruppe '{gruppe}' gelöscht.{RESET}")
    return True


def massenanlage_aus_csv(pfad: str, standard_shell: str = "/bin/bash",
                          home_erstellen: bool = True) -> None:
    erstellt: List[str] = []
    fehlgeschlagen: List[str] = []

    if not os.path.isfile(pfad):
        print(f"{RED}✗  CSV-Datei nicht gefunden: {pfad}{RESET}")
        return

    try:
        with open(pfad, newline="", encoding="utf-8") as csvdatei:
            leser = csv.DictReader(csvdatei)
            for zeile_nr, zeile in enumerate(leser, start=2):
                benutzername = (
                    zeile.get("username") or zeile.get("user") or
                    zeile.get("login") or ""
                ).strip()
                if not benutzername:
                    print(f"{YELLOW}⚠  Zeile {zeile_nr}: Kein Benutzername — übersprungen.{RESET}")
                    continue

                vollname = (zeile.get("fullname") or zeile.get("gecos") or "").strip() or None
                shell = (zeile.get("shell") or standard_shell).strip()
                gruppen_feld = (zeile.get("groups") or "").strip()
                gruppen = [g.strip() for g in gruppen_feld.split(",")] if gruppen_feld else None
                pwd = (zeile.get("password") or "").strip() or None

                ok = benutzer_anlegen(benutzername, vollname=vollname, shell=shell,
                                       gruppen=gruppen, home_erstellen=home_erstellen)
                if ok:
                    erstellt.append(benutzername)
                    if pwd:
                        passwort_setzen(benutzername, pwd)
                else:
                    fehlgeschlagen.append(benutzername)

    except PermissionError:
        print(f"{RED}✗  Keine Leseberechtigung für: {pfad}{RESET}")
        return
    except Exception as e:
        print(f"{RED}✗  Fehler beim Lesen der CSV: {e}{RESET}")
        return

    trennlinie("Ergebnis")
    print(f"{GREEN}  Erfolgreich angelegt ({len(erstellt)}): {', '.join(erstellt) or '—'}{RESET}")
    if fehlgeschlagen:
        print(f"{YELLOW}  Fehlgeschlagen ({len(fehlgeschlagen)}): "
              f"{', '.join(fehlgeschlagen)}{RESET}")


def benutzer_info(benutzername: str) -> None:
    """Zeigt detaillierte Informationen zu einem Benutzer."""
    if not benutzer_existiert(benutzername):
        print(f"{RED}✗  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return
    trennlinie(f"Kontoinformation: {benutzername}")
    # id-Ausgabe
    res_id = befehl(["id", benutzername], capture=True)
    if res_id.returncode == 0:
        print(f"  {res_id.stdout.strip()}")
    # passwd-Eintrag
    res_p = befehl(["getent", "passwd", benutzername], capture=True)
    if res_p.returncode == 0:
        teile = res_p.stdout.strip().split(":")
        if len(teile) >= 7:
            print(f"  Vollname : {teile[4] or '(nicht gesetzt)'}")
            print(f"  Home     : {teile[5]}")
            print(f"  Shell    : {teile[6]}")
    # Kontostatus (gesperrt?)
    res_s = befehl(["passwd", "-S", benutzername], capture=True)
    if res_s.returncode == 0:
        status_teile = res_s.stdout.strip().split()
        if len(status_teile) >= 2:
            status_code = status_teile[1]
            stati = {"P": "Aktiv", "L": "Gesperrt", "NP": "Kein Passwort"}
            status_text = stati.get(status_code, status_code)
            farbe = GREEN if status_code == "P" else RED
            print(f"  Status   : {farbe}{status_text}{RESET}")
    trennlinie()


def benutzer_auflisten() -> None:
    """Listet alle nicht-system-Benutzer (UID ≥ 1000) auf."""
    res = befehl(["getent", "passwd"], capture=True)
    if res.returncode != 0:
        print(f"{RED}✗  Konnte Benutzerliste nicht abrufen.{RESET}")
        return
    trennlinie("Normale Benutzerkonten (UID ≥ 1000)")
    gefunden = 0
    for zeile in res.stdout.splitlines():
        teile = zeile.split(":")
        if len(teile) < 7:
            continue
        try:
            uid = int(teile[2])
        except ValueError:
            continue
        if uid >= 1000 and teile[0] != "nobody":
            gefunden += 1
            print(f"  {CYAN}{teile[0]:<20}{RESET} UID={uid:<6} "
                  f"Home={teile[5]}  Shell={teile[6]}")
    if gefunden == 0:
        print(f"  {DIM}(Keine normalen Benutzerkonten gefunden){RESET}")
    trennlinie()


def gruppen_auflisten() -> None:
    """Listet alle Gruppen mit ihren Mitgliedern auf."""
    res = befehl(["getent", "group"], capture=True)
    if res.returncode != 0:
        print(f"{RED}✗  Konnte Gruppenliste nicht abrufen.{RESET}")
        return
    trennlinie("Alle Gruppen")
    for zeile in sorted(res.stdout.splitlines()):
        teile = zeile.split(":")
        if len(teile) < 4:
            continue
        mitglieder = teile[3] or DIM + "(leer)" + RESET
        print(f"  {CYAN}{teile[0]:<20}{RESET} GID={teile[2]:<6}  "
              f"Mitglieder: {mitglieder}")
    trennlinie()


def sudoers_pruefen(sudoers_pfad: str = "/etc/sudoers",
                    sudoers_verz: str = "/etc/sudoers.d") -> List[str]:
    """Prüft sudoers-Syntax und sucht nach Referenzen auf nicht existierende Benutzer."""
    probleme: List[str] = []

    # Hauptdatei
    res = befehl(["visudo", "-c", "-f", sudoers_pfad], capture=True)
    if res.returncode != 0:
        probleme.append(f"{sudoers_pfad}: Syntaxfehler — "
                        f"{(res.stderr or res.stdout).strip()}")

    # sudoers.d
    if os.path.isdir(sudoers_verz):
        for dateiname in sorted(os.listdir(sudoers_verz)):
            vollpfad = os.path.join(sudoers_verz, dateiname)
            if not os.path.isfile(vollpfad):
                continue
            r = befehl(["visudo", "-c", "-f", vollpfad], capture=True)
            if r.returncode != 0:
                probleme.append(f"{vollpfad}: Syntaxfehler — "
                                 f"{(r.stderr or r.stdout).strip()}")
            # Nach nicht-existierenden Benutzern suchen
            # Nur Tokens direkt nach dem Beginn einer Regel prüfen (vor dem ersten Leerzeichen),
            # nicht Keywords wie ALL, NOPASSWD etc.
            sudoers_keywords = {
                "ALL", "NOPASSWD", "PASSWD", "NOEXEC", "EXEC",
                "SETENV", "NOSETENV", "LOG_INPUT", "LOG_OUTPUT",
                "NOLOG_INPUT", "NOLOG_OUTPUT", "MAIL", "NOMAIL",
                "Defaults", "User_Alias", "Runas_Alias",
                "Host_Alias", "Cmnd_Alias"
            }
            try:
                with open(vollpfad, encoding="utf-8") as f:
                    for zeilennr, zeile in enumerate(f, 1):
                        zeile = zeile.strip()
                        if not zeile or zeile.startswith("#"):
                            continue
                        # Nur erstes Token als potenziellen Benutzernamen prüfen
                        erstes_token = zeile.split()[0]
                        if (erstes_token not in sudoers_keywords
                                and not erstes_token.startswith("%")
                                and re.match(r'^[a-z_][a-z0-9_\-]*$', erstes_token)
                                and not benutzer_existiert(erstes_token)):
                            probleme.append(
                                f"{vollpfad}:{zeilennr}: Referenz auf "
                                f"nicht existierenden Benutzer '{erstes_token}'"
                            )
            except Exception:
                pass

    audit_log(f"sudoers_check probleme={len(probleme)}")
    return probleme


# ── Menü-Aktionen ──────────────────────────────────────────────────────────────
def menue_benutzer_anlegen() -> None:
    trennlinie("Benutzer anlegen")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    gueltig, fehler = benutzername_gueltig(benutzername)
    if not gueltig:
        print(f"{RED}✗  {fehler}{RESET}")
        return
    vollname = input("  Vollständiger Name (optional): ").strip() or None
    shell = shell_auswaehlen()
    gruppen_feld = input("  Zusätzliche Gruppen (kommagetrennt, optional): ").strip()
    gruppen = [g.strip() for g in gruppen_feld.split(",") if g.strip()] or None
    home_erstellen = input("  Home-Verzeichnis erstellen? [J/n]: ").strip().lower() != "n"

    ok = benutzer_anlegen(benutzername, vollname=vollname, shell=shell,
                           gruppen=gruppen, home_erstellen=home_erstellen)
    if ok and input("  Passwort jetzt setzen? [J/n]: ").strip().lower() != "n":
        _passwort_abfragen_und_setzen(benutzername)


def menue_massenanlage() -> None:
    trennlinie("Massenanlage aus CSV")
    print(f"{DIM}  Erwartete Spalten: username, fullname, shell, groups, password{RESET}")
    pfad = eingabe_nicht_leer("  Pfad zur CSV-Datei: ")
    massenanlage_aus_csv(pfad)


def menue_passwort_setzen() -> None:
    trennlinie("Passwort setzen (nicht-interaktiv)")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    _passwort_abfragen_und_setzen(benutzername)


def _passwort_abfragen_und_setzen(benutzername: str) -> None:
    """Gemeinsame Passwort-Eingabe mit Stärkeprüfung."""
    for versuch in range(3):
        pwd = getpass.getpass("  Neues Passwort: ")
        ok, hinweis = passwort_staerke(pwd)
        if not ok:
            print(f"{YELLOW}⚠  {hinweis}{RESET}")
            if versuch < 2:
                weiter = input("  Trotzdem verwenden? [j/N]: ").strip().lower()
                if weiter != "j":
                    continue
        pwd2 = getpass.getpass("  Passwort bestätigen: ")
        if pwd != pwd2:
            print(f"{RED}✗  Passwörter stimmen nicht überein.{RESET}")
            continue
        passwort_setzen(benutzername, pwd)
        return
    print(f"{RED}✗  Zu viele Fehlversuche. Abgebrochen.{RESET}")


def menue_passwort_interaktiv() -> None:
    trennlinie("Passwort interaktiv setzen")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    passwort_interaktiv(benutzername)


def menue_passwort_ablaufen() -> None:
    trennlinie("Passwort ablaufen lassen")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    passwort_ablaufen_lassen(benutzername)


def menue_konto_sperren() -> None:
    trennlinie("Konto sperren")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    konto_sperren(benutzername)


def menue_konto_entsperren() -> None:
    trennlinie("Konto entsperren")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    konto_entsperren(benutzername)


def menue_gruppen_aendern() -> None:
    trennlinie("Gruppen eines Benutzers verwalten")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    if not benutzer_existiert(benutzername):
        print(f"{RED}✗  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return
    # Aktuelle Gruppen anzeigen
    cur = befehl(["id", "-nG", benutzername], capture=True)
    if cur.returncode == 0:
        print(f"  Aktuelle Gruppen: {CYAN}{cur.stdout.strip()}{RESET}")
    add_feld = input("  Hinzufügen (kommagetrennt, leer = keine): ").strip()
    rem_feld = input("  Entfernen  (kommagetrennt, leer = keine): ").strip()
    hinzufuegen = [g.strip() for g in add_feld.split(",") if g.strip()] or None
    entfernen   = [g.strip() for g in rem_feld.split(",") if g.strip()] or None
    gruppen_aendern(benutzername, hinzufuegen=hinzufuegen, entfernen=entfernen)


def menue_benutzer_loeschen() -> None:
    trennlinie("Benutzer löschen")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    if not benutzer_existiert(benutzername):
        print(f"{YELLOW}⚠  Benutzer '{benutzername}' existiert nicht.{RESET}")
        return
    benutzer_info(benutzername)
    bestaetigung = input(
        f"{YELLOW}  ⚠  Benutzernamen zur Bestätigung erneut eingeben: {RESET}"
    ).strip()
    if bestaetigung != benutzername:
        print(f"{YELLOW}  Abgebrochen.{RESET}")
        return
    home_entfernen = input("  Home-Verzeichnis ebenfalls entfernen? [j/N]: ").strip().lower() == "j"
    benutzer_loeschen(benutzername, home_entfernen=home_entfernen)


def menue_gruppe_loeschen() -> None:
    trennlinie("Gruppe löschen")
    gruppe = eingabe_nicht_leer("  Gruppenname: ")
    if not gruppe_existiert(gruppe):
        print(f"{YELLOW}⚠  Gruppe '{gruppe}' existiert nicht.{RESET}")
        return
    if gruppe in KRITISCHE_GRUPPEN:
        print(f"{RED}  ⚠  '{gruppe}' ist eine kritische Systemgruppe!{RESET}")
        erzwingen = input("  Trotzdem erzwingen? [j/N]: ").strip().lower() == "j"
    else:
        erzwingen = False
    bestaetigung = input(
        f"{YELLOW}  Gruppennamen zur Bestätigung erneut eingeben: {RESET}"
    ).strip()
    if bestaetigung != gruppe:
        print(f"{YELLOW}  Abgebrochen.{RESET}")
        return
    gruppe_loeschen(gruppe, erzwingen=erzwingen)


def menue_benutzer_info() -> None:
    trennlinie("Benutzerinformation")
    benutzername = eingabe_nicht_leer("  Benutzername: ")
    benutzer_info(benutzername)


def menue_benutzer_auflisten() -> None:
    benutzer_auflisten()


def menue_gruppen_auflisten() -> None:
    gruppen_auflisten()


def menue_sudoers_pruefen() -> None:
    trennlinie("sudoers-Prüfung")
    probleme = sudoers_pruefen()
    if probleme:
        print(f"{RED}  Gefundene Probleme ({len(probleme)}):{RESET}")
        for p in probleme:
            print(f"    {RED}•{RESET} {p}")
    else:
        print(f"{GREEN}  ✓  Keine Probleme in der sudoers-Konfiguration gefunden.{RESET}")
    trennlinie()


# ── Hauptmenü ──────────────────────────────────────────────────────────────────
def hauptmenue() -> None:
    # Einträge: (schluessel, beschreibung, funktion)
    # Kategorie-Trennzeilen verwenden schluessel=None
    kategorien = [
        (None, f"{BOLD}── Benutzer ──────────────────────────────{RESET}",  None),
        ("1",  "Benutzer anlegen",                    menue_benutzer_anlegen),
        ("2",  "Massenanlage aus CSV-Datei",           menue_massenanlage),
        ("3",  "Benutzer auflisten",                   menue_benutzer_auflisten),
        ("4",  "Benutzerinformation anzeigen",         menue_benutzer_info),
        ("5",  "Benutzer löschen",                     menue_benutzer_loeschen),
        (None, f"{BOLD}── Konto & Passwort ──────────────────────{RESET}", None),
        ("6",  "Passwort setzen (nicht-interaktiv)",  menue_passwort_setzen),
        ("7",  "Passwort setzen (interaktiv)",         menue_passwort_interaktiv),
        ("8",  "Passwort ablaufen lassen",             menue_passwort_ablaufen),
        ("9",  "Konto sperren",                        menue_konto_sperren),
        ("10", "Konto entsperren",                     menue_konto_entsperren),
        (None, f"{BOLD}── Gruppen ───────────────────────────────{RESET}",  None),
        ("11", "Gruppen eines Benutzers verwalten",   menue_gruppen_aendern),
        ("12", "Alle Gruppen auflisten",               menue_gruppen_auflisten),
        ("13", "Gruppe löschen",                       menue_gruppe_loeschen),
        (None, f"{BOLD}── System ────────────────────────────────{RESET}",  None),
        ("14", "sudoers-Konfiguration prüfen",         menue_sudoers_pruefen),
        ("0",  "Beenden",                              None),
    ]

    # Aktionen-Dict für schnellen Lookup (nur echte Menüpunkte, keine Trennzeilen)
    aktionen = {k: (desc, fn) for k, desc, fn in kategorien if k is not None}

    while True:
        print()
        print(f"{ORANGE}{BOLD}  ╔══════════════════════════════════════════╗")
        print(f"  ║       Rechteverwaltung — Hauptmenü       ║")
        print(f"  ╚══════════════════════════════════════════╝{RESET}")
        print()
        for schluessel, beschreibung, _ in kategorien:
            if schluessel is None:
                # Kategorieüberschrift
                print(f"  {beschreibung}")
            elif schluessel == "0":
                print(f"  {DIM}  0) Beenden{RESET}")
            else:
                print(f"  {CYAN}{schluessel:>2}{RESET}) {beschreibung}")
        print()

        auswahl = input(f"{ORANGE}  Option wählen: {RESET}").strip()

        if auswahl == "0":
            print(f"\n{GREEN}  Auf Wiedersehen.{RESET}\n")
            break

        if auswahl not in aktionen:
            print(f"{YELLOW}  ⚠  Ungültige Eingabe. Bitte eine der angezeigten Nummern wählen.{RESET}")
            continue

        _, fn = aktionen[auswahl]
        if fn is None:
            break
        print()
        try:
            fn()
        except KeyboardInterrupt:
            print(f"\n{YELLOW}  Abgebrochen (Strg+C).{RESET}")
        except Exception as e:
            print(f"{RED}  ✗  Unerwarteter Fehler: {e}{RESET}")
            audit_log(f"FEHLER menue={auswahl} exception={e}")


# ── Einstiegspunkt ─────────────────────────────────────────────────────────────
def main() -> None:
    print(f"\n{ORANGE}{BOLD}  Rechteverwaltung gestartet.{RESET}")
    print(f"{DIM}  Audit-Log: {AUDIT_LOG}{RESET}")
    audit_log("START Rechteverwaltung")
    try:
        hauptmenue()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}  Programm durch Benutzer beendet (Strg+C).{RESET}\n")
    finally:
        audit_log("END Rechteverwaltung")


if __name__ == "__main__":
    main()
