#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║      Arch Linux Package Manager — ncurses TUI v3         ║
║      Pacman + Yay | Mausgesteuert | Python ≥ 3.8         ║
╚══════════════════════════════════════════════════════════╝
Steuerung : Nur Maus — Klick auswählen, Scrollrad scrollen
Abhängigkeiten: python, pacman, yay, reflector, sudo
"""
from __future__ import annotations   # tuple[…] auf Python 3.8 kompatibel

import curses
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ─── Farb-Paare ────────────────────────────────────────────────────────────────
C_NORMAL   = 1   # Weiß / Dunkelblau
C_HEADER   = 2   # Schwarz / Cyan
C_SELECTED = 3   # Schwarz / Grün
C_ERROR    = 4   # Weiß / Rot
C_SUCCESS  = 5   # Schwarz / Grün
C_TITLE    = 6   # Gelb / Dunkelblau
C_BORDER   = 7   # Cyan / Dunkelblau
C_DIM      = 8   # Weiß / Dunkelblau (dim)
C_WARN     = 9   # Schwarz / Gelb
C_INPUT    = 10  # Weiß / Schwarz
C_PKG_REPO = 11  # Cyan      — Repository (core, extra …)
C_PKG_NAME = 12  # Weiß+Bold — Paketname
C_PKG_VER  = 13  # Grün      — Versionsnummer
C_PKG_FLAG = 14  # Gelb      — [installed], [outdated] …
C_PKG_AUR  = 15  # Magenta   — AUR-Präfix
C_PKG_DESC = 16  # dim       — Paketbeschreibungszeile


# ─── Anzeigebreite (Emoji = 2 Spalten) ─────────────────────────────────────────
def _dw(s: str) -> int:
    """Terminal-Anzeigebreite: Wide/Fullwidth-Zeichen zählen als 2."""
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _ljust(s: str, width: int, fill: str = " ") -> str:
    """Linksbündig auffüllen basierend auf Terminal-Anzeigebreite."""
    return s + fill * max(0, width - _dw(s))


def _center(s: str, width: int, fill: str = " ") -> str:
    """Zentrieren basierend auf Terminal-Anzeigebreite."""
    pad = max(0, width - _dw(s))
    return fill * (pad // 2) + s + fill * (pad - pad // 2)


# ─── Datenmodell ───────────────────────────────────────────────────────────────
@dataclass
class MenuItem:
    label:         str
    cmd:           Optional[List[str]] = None
    submenu:       Optional[List["MenuItem"]] = None
    needs_input:   bool = False
    input_prompt:  str  = ""
    description:   str  = ""
    dangerous:     bool = False
    is_search:     bool = False   # farbige Suchergebnisdarstellung
    is_editor:     bool = False   # curses pausieren, Editor im Vordergrund
    needs_confirm: bool = False   # Ja/Nein-Modal vor Ausführung
    is_separator:  bool = False   # visuelle Trennlinie, nicht ausführbar


# ─── Menüstruktur ──────────────────────────────────────────────────────────────
def build_menu() -> List[MenuItem]:
    ed = os.environ.get("EDITOR", "nano")
    return [
        # ── 1 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="🔄  System Update",
            description="Systemaktualisierung und Datenbank-Sync",
            submenu=[
                MenuItem("Vollständiges Update  (pacman)",
                         cmd=["sudo", "pacman", "-Syu", "--noconfirm"],
                         description="Alle Pakete aus offiziellen Repos"),
                MenuItem("Vollständiges Update  (yay + AUR)",
                         cmd=["yay", "-Syu", "--noconfirm"],
                         description="Alle Pakete inkl. AUR — kein sudo nötig"),
                MenuItem("Nur DB synchronisieren  (-Sy)",
                         cmd=["sudo", "pacman", "-Sy"],
                         description="Repo-Datenbank einlesen ohne Update"),
                MenuItem("Aktualisierbare Pakete anzeigen",
                         cmd=["pacman", "-Qu"],
                         description="Pakete mit verfügbarem Update"),
                MenuItem("Explizit installierte Pakete",
                         cmd=["pacman", "-Qe"],
                         description="Nur manuell installierte Pakete"),
            ],
        ),
        # ── 2 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="📦  Pakete installieren",
            description="Pakete suchen, Info abrufen und installieren",
            submenu=[
                MenuItem("🔍 Paket suchen  (pacman — offiziell)",
                         cmd=["pacman", "-Ss", "{INPUT}"],
                         needs_input=True, input_prompt="Suchbegriff (pacman): ",
                         description="Offizielle Repos — farbige scrollbare Ausgabe",
                         is_search=True),
                MenuItem("🔍 Paket suchen  (yay — AUR + offiziell)",
                         cmd=["yay", "-Ss", "{INPUT}"],
                         needs_input=True, input_prompt="Suchbegriff (AUR/yay): ",
                         description="AUR + offizielle Repos — farbige scrollbare Ausgabe",
                         is_search=True),
                MenuItem("Paket installieren  (pacman)",
                         cmd=["sudo", "pacman", "-S", "--noconfirm", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Paketname(n) [Leerzeichen getrennt]: ",
                         description="Aus offiziellen Arch-Repos installieren"),
                MenuItem("Paket installieren  (yay — AUR)",
                         cmd=["yay", "-S", "--noconfirm", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Paketname(n) [Leerzeichen getrennt]: ",
                         description="Aus AUR oder offiziellen Repos — kein sudo"),
                MenuItem("Lokales Paket installieren  (.pkg.tar.zst)",
                         cmd=["sudo", "pacman", "-U", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Pfad zur .pkg.tar.zst-Datei: ",
                         description="Lokale Paketdatei installieren"),
                MenuItem("Paketinfo  (pacman -Si)",
                         cmd=["pacman", "-Si", "{INPUT}"],
                         needs_input=True, input_prompt="Paketname: ",
                         description="Detaillierte Paketinformationen aus Repo"),
                MenuItem("Paketinfo  (yay -Si — AUR)",
                         cmd=["yay", "-Si", "{INPUT}"],
                         needs_input=True, input_prompt="Paketname (AUR): ",
                         description="Detaillierte AUR-Paketinformationen"),
            ],
        ),
        # ── 3 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="🗑️  Pakete entfernen",
            description="Pakete deinstallieren und bereinigen",
            submenu=[
                MenuItem("Paket entfernen  (-R)",
                         cmd=["sudo", "pacman", "-R", "--noconfirm", "{INPUT}"],
                         needs_input=True, input_prompt="Paketname(n): ",
                         description="Nur das Paket selbst entfernen"),
                MenuItem("Paket + Abhängigkeiten  (-Rs)",
                         cmd=["sudo", "pacman", "-Rs", "--noconfirm", "{INPUT}"],
                         needs_input=True, input_prompt="Paketname(n): ",
                         description="Paket + nicht mehr benötigte Abhängigkeiten"),
                MenuItem("Paket + Konfig-Dateien  (-Rns)  ⚠",
                         cmd=["sudo", "pacman", "-Rns", "--noconfirm", "{INPUT}"],
                         needs_input=True, input_prompt="Paketname(n): ",
                         description="Vollständig entfernen inkl. Konfiguration",
                         dangerous=True, needs_confirm=True),
                MenuItem("Verwaiste Pakete anzeigen  (Orphans)",
                         cmd=["pacman", "-Qdt"],
                         description="Nicht mehr benötigte Pakete auflisten"),
                MenuItem("Alle Orphans entfernen  ⚠",
                         cmd=["bash", "-c",
                              "orphans=$(pacman -Qdtq 2>/dev/null); "
                              "[ -z \"$orphans\" ] "
                              "&& echo 'Keine Orphans gefunden.' "
                              "|| sudo pacman -Rns --noconfirm $orphans"],
                         description="Alle verwaisten Pakete automatisch bereinigen",
                         dangerous=True, needs_confirm=True),
            ],
        ),
        # ── 4 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="🔧  Datenbank & Reparatur",
            description="Datenbankprobleme beheben und reparieren",
            submenu=[
                MenuItem("DB-Konsistenz prüfen",
                         cmd=["sudo", "pacman", "-Dk"],
                         description="Paketdatenbank auf Fehler prüfen"),
                MenuItem("DB erzwungen synchronisieren  (-Syy)",
                         cmd=["sudo", "pacman", "-Syy"],
                         description="Vollständige DB-Synchronisation erzwingen"),
                MenuItem("DB-Lock entfernen  ⚠",
                         cmd=["sudo", "rm", "-f", "/var/lib/pacman/db.lck"],
                         description="Gesperrte DB entsperren (nach Absturz)",
                         dangerous=True, needs_confirm=True),
                MenuItem("Fehlende Paketdateien suchen",
                         cmd=["sudo", "pacman", "-Qkk"],
                         description="Prüft ob alle Paketdateien vorhanden sind"),
                MenuItem("Datei-Integrität prüfen  (paccheck)",
                         cmd=["sudo", "paccheck", "--md5sum", "--quiet"],
                         description="MD5-Prüfsummen aller Pakete verifizieren"),
                MenuItem("Keyring initialisieren",
                         cmd=["sudo", "pacman-key", "--init"],
                         description="GPG-Schlüsselbund neu initialisieren",
                         dangerous=True, needs_confirm=True),
                MenuItem("Arch-Schlüssel reimportieren",
                         cmd=["sudo", "pacman-key", "--populate", "archlinux"],
                         description="Arch-Signatur-Schlüssel neu einlesen"),
                MenuItem("archlinux-keyring neu installieren",
                         cmd=["sudo", "pacman", "-Sy", "--noconfirm",
                              "archlinux-keyring"],
                         description="Keyring-Paket neu installieren"),
            ],
        ),
        # ── 5 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="🪞  Mirror Ranking",
            description="Pacman Mirrors ranken und verwalten",
            submenu=[
                MenuItem("Mirrors ranken — Deutschland  (Top 10, HTTPS)",
                         cmd=["sudo", "reflector",
                              "--country", "Germany",
                              "--age", "12", "--protocol", "https",
                              "--sort", "rate", "--number", "10",
                              "--save", "/etc/pacman.d/mirrorlist",
                              "--verbose"],
                         description="Top-10 DE-Mirrors — speichert Mirrorlist",
                         dangerous=True, needs_confirm=True),
                MenuItem("Mirrors ranken — Europa  (Top 20, HTTPS)",
                         cmd=["sudo", "reflector",
                              "--country",
                              "Germany,Austria,Switzerland,France,Netherlands",
                              "--age", "24", "--protocol", "https",
                              "--sort", "rate", "--number", "20",
                              "--save", "/etc/pacman.d/mirrorlist",
                              "--verbose"],
                         description="Top-20 DACH+Europa — speichert Mirrorlist",
                         dangerous=True, needs_confirm=True),
                MenuItem("Mirror-Ranking anzeigen  (kein Speichern)",
                         cmd=["reflector",
                              "--country", "Germany",
                              "--age", "12", "--protocol", "https",
                              "--sort", "rate", "--number", "10",
                              "--verbose"],
                         description="Ranking ohne Mirrorlist zu überschreiben"),
                MenuItem("Mirrorlist anzeigen",
                         cmd=["cat", "/etc/pacman.d/mirrorlist"],
                         description="Aktuelle /etc/pacman.d/mirrorlist anzeigen"),
                MenuItem("Mirrorlist sichern  (Backup)",
                         cmd=["sudo", "cp", "/etc/pacman.d/mirrorlist",
                              f"/etc/pacman.d/mirrorlist.bak.{int(time.time())}"],
                         description="Mirrorlist mit Zeitstempel sichern"),
                MenuItem("✏  Mirrorlist bearbeiten  (sudo nano)",
                         cmd=["sudo", "nano", "/etc/pacman.d/mirrorlist"],
                         description="Öffnet /etc/pacman.d/mirrorlist in nano",
                         is_editor=True),
                MenuItem("✏  Mirrorlist bearbeiten  (sudo vim)",
                         cmd=["sudo", "vim", "/etc/pacman.d/mirrorlist"],
                         description="Öffnet /etc/pacman.d/mirrorlist in vim",
                         is_editor=True),
            ],
        ),
        # ── 6 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="🧹  Cache bereinigen",
            description="Paket-Cache und Build-Dateien bereinigen",
            submenu=[
                MenuItem("Cache-Größe anzeigen",
                         cmd=["du", "-sh", "/var/cache/pacman/pkg/"],
                         description="Aktuellen Speicherbedarf des Caches zeigen"),
                MenuItem("Nicht-installierte aus Cache  (-Sc)  ⚠",
                         cmd=["sudo", "pacman", "-Sc", "--noconfirm"],
                         description="Nicht-installierte Pakete aus Cache löschen",
                         dangerous=True, needs_confirm=True),
                MenuItem("Kompletten Cache leeren  (-Scc)  ⚠",
                         cmd=["sudo", "pacman", "-Scc", "--noconfirm"],
                         description="GESAMTEN Cache löschen — keine Rollbacks",
                         dangerous=True, needs_confirm=True),
                MenuItem("paccache: 2 Versionen behalten",
                         cmd=["sudo", "paccache", "-rk2"],
                         description="Alle außer 2 neueste Versionen löschen",
                         dangerous=True, needs_confirm=True),
                MenuItem("paccache: nur 1 Version behalten  ⚠",
                         cmd=["sudo", "paccache", "-rk1"],
                         description="Nur die neueste Version behalten",
                         dangerous=True, needs_confirm=True),
                MenuItem("yay AUR-Cache bereinigen",
                         cmd=["yay", "-Sc", "--noconfirm"],
                         description="Temporäre yay Build-Dateien löschen",
                         dangerous=True, needs_confirm=True),
                MenuItem("yay Build-Verzeichnis anzeigen",
                         cmd=["bash", "-c",
                              "ls -lh ~/.cache/yay/ 2>/dev/null "
                              "|| echo 'Leer oder nicht vorhanden'"],
                         description="Inhalt des yay Build-Cache-Verzeichnisses"),
            ],
        ),
        # ── 7 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="📊  Systeminfo & Pakete",
            description="Paketlisten und Systeminformationen",
            submenu=[
                MenuItem("Alle installierten Pakete  (-Q)",
                         cmd=["pacman", "-Q"],
                         description="Vollständige Liste aller Pakete"),
                MenuItem("Explizit installierte Pakete  (-Qe)",
                         cmd=["pacman", "-Qe"],
                         description="Nur manuell installierte (keine Abhängigkeiten)"),
                MenuItem("AUR / Fremd-Pakete  (-Qm)",
                         cmd=["pacman", "-Qm"],
                         description="Pakete aus AUR oder externen Quellen"),
                MenuItem("Paketanzahl gesamt",
                         cmd=["bash", "-c", "pacman -Q | wc -l"],
                         description="Gesamtanzahl aller installierten Pakete"),
                MenuItem("Datei -> Paket herausfinden  (-Qo)",
                         cmd=["pacman", "-Qo", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Dateipfad (z.B. /usr/bin/nano): ",
                         description="Zugehöriges Paket einer Datei finden"),
                MenuItem("Dateien eines Pakets anzeigen  (-Ql)",
                         cmd=["pacman", "-Ql", "{INPUT}"],
                         needs_input=True, input_prompt="Paketname: ",
                         description="Alle installierten Dateien eines Pakets"),
                MenuItem("pacman-Version",
                         cmd=["pacman", "--version"],
                         description="Installierte pacman-Version"),
                MenuItem("Pacman-Log  (letzte 100 Zeilen)",
                         cmd=["tail", "-n", "100", "/var/log/pacman.log"],
                         description="Letzte 100 Zeilen des pacman-Protokolls"),
            ],
        ),
        # ── 8 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="⚙️  AUR / yay",
            description="AUR-Operationen und yay-Konfiguration",
            submenu=[
                MenuItem("yay-Version",
                         cmd=["yay", "--version"],
                         description="Installierte yay-Version anzeigen"),
                MenuItem("yay Statistik  (-Ps)",
                         cmd=["yay", "-Ps"],
                         description="yay-Statistik und Paketzustand"),
                MenuItem("yay selbst aktualisieren",
                         cmd=["yay", "-Syu", "--noconfirm", "yay"],
                         description="yay aus AUR neu bauen und aktualisieren"),
                MenuItem("VCS/Git-Pakete aktualisieren  (--devel)",
                         cmd=["yay", "-Syu", "--devel", "--noconfirm"],
                         description="Entwicklerpakete (git, svn ...) auf HEAD"),
                MenuItem("AUR-Paket manuell klonen & bauen",
                         cmd=["bash", "-c",
                              'PKG={INPUT}; cd /tmp && git clone '
                              '"https://aur.archlinux.org/$PKG.git" '
                              '&& cd "$PKG" && makepkg -si --noconfirm'],
                         needs_input=True,
                         input_prompt="AUR-Paketname (exakt, fuer git clone): ",
                         description="PKGBUILD aus AUR klonen und bauen"),
            ],
        ),
        # ── 9 ─────────────────────────────────────────────────────────────────
        MenuItem(
            label="📝  Konfiguration",
            description="pacman.conf, Mirrorlist und makepkg.conf bearbeiten",
            submenu=[
                MenuItem("pacman.conf anzeigen",
                         cmd=["cat", "/etc/pacman.conf"],
                         description="Aktuelle /etc/pacman.conf im Output anzeigen"),
                MenuItem("✏  pacman.conf  (sudo nano)",
                         cmd=["sudo", "nano", "/etc/pacman.conf"],
                         description="Öffnet /etc/pacman.conf in nano",
                         is_editor=True),
                MenuItem("✏  pacman.conf  (sudo vim)",
                         cmd=["sudo", "vim", "/etc/pacman.conf"],
                         description="Öffnet /etc/pacman.conf in vim",
                         is_editor=True),
                MenuItem(f"✏  pacman.conf  (sudo $EDITOR={ed})",
                         cmd=["sudo", ed, "/etc/pacman.conf"],
                         description=f"Öffnet /etc/pacman.conf in {ed}",
                         is_editor=True),
                MenuItem("pacman.conf sichern  (Backup)",
                         cmd=["sudo", "cp", "/etc/pacman.conf",
                              f"/etc/pacman.conf.bak.{int(time.time())}"],
                         description="pacman.conf mit Zeitstempel sichern"),
                MenuItem("Mirrorlist anzeigen  (Konfiguration)",
                         cmd=["cat", "/etc/pacman.d/mirrorlist"],
                         description="Aktuelle /etc/pacman.d/mirrorlist anzeigen"),
                MenuItem("✏  Mirrorlist  (sudo nano)",
                         cmd=["sudo", "nano", "/etc/pacman.d/mirrorlist"],
                         description="Öffnet /etc/pacman.d/mirrorlist in nano",
                         is_editor=True),
                MenuItem("✏  Mirrorlist  (sudo vim)",
                         cmd=["sudo", "vim", "/etc/pacman.d/mirrorlist"],
                         description="Öffnet /etc/pacman.d/mirrorlist in vim",
                         is_editor=True),
                MenuItem("pacman Hooks-Verzeichnis",
                         cmd=["bash", "-c",
                              "ls -la /etc/pacman.d/hooks/ 2>/dev/null "
                              "|| echo 'Kein hooks/-Verzeichnis vorhanden'"],
                         description="Installierte pacman-Hooks auflisten"),
                MenuItem("makepkg.conf anzeigen",
                         cmd=["cat", "/etc/makepkg.conf"],
                         description="Aktuelle /etc/makepkg.conf anzeigen"),
                MenuItem("✏  makepkg.conf  (sudo nano)",
                         cmd=["sudo", "nano", "/etc/makepkg.conf"],
                         description="Öffnet /etc/makepkg.conf in nano",
                         is_editor=True),
            ],
        ),
        # ── 10 ────────────────────────────────────────────────────────────────
        MenuItem(
            label="🌀  Chaotic-AUR",
            description="Chaotic-AUR Drittanbieter-Repo einrichten und verwalten",
            submenu=[
                MenuItem("Status: Chaotic-AUR aktiv?",
                         cmd=["bash", "-c",
                              "grep -q 'chaotic-aur' /etc/pacman.conf "
                              "&& echo 'OK: Chaotic-AUR ist in pacman.conf eingetragen.' "
                              "|| echo 'FEHLT: Chaotic-AUR ist NICHT in pacman.conf.'"],
                         description="Prüft ob Chaotic-AUR in /etc/pacman.conf steht"),
                MenuItem("Schritt 1 — GPG-Schluessel empfangen",
                         cmd=["sudo", "pacman-key",
                              "--recv-key", "3056513887B78AEB",
                              "--keyserver", "keyserver.ubuntu.com"],
                         description="Chaotic-AUR GPG-Schlüssel vom Keyserver laden",
                         dangerous=True),
                MenuItem("Schritt 2 — Schluessel lokal signieren",
                         cmd=["sudo", "pacman-key",
                              "--lsign-key", "3056513887B78AEB"],
                         description="Chaotic-AUR Schlüssel lokal vertrauen",
                         dangerous=True),
                MenuItem("Schritt 3 — chaotic-keyring installieren",
                         cmd=["sudo", "pacman", "-U", "--noconfirm",
                              "https://cdn-mirror.chaotic.cx/chaotic-aur/"
                              "chaotic-keyring.pkg.tar.zst"],
                         description="Chaotic-AUR Keyring-Paket installieren",
                         dangerous=True),
                MenuItem("Schritt 4 — chaotic-mirrorlist installieren",
                         cmd=["sudo", "pacman", "-U", "--noconfirm",
                              "https://cdn-mirror.chaotic.cx/chaotic-aur/"
                              "chaotic-mirrorlist.pkg.tar.zst"],
                         description="Chaotic-AUR Mirrorlist-Paket installieren",
                         dangerous=True),
                MenuItem("Schritt 5 — Repo in pacman.conf eintragen  ⚠",
                         cmd=["bash", "-c",
                              "grep -q 'chaotic-aur' /etc/pacman.conf "
                              "&& echo 'Bereits eingetragen — uebersprungen.' "
                              "|| (printf '\\n[chaotic-aur]\\n"
                              "Include = /etc/pacman.d/chaotic-mirrorlist\\n' "
                              "| sudo tee -a /etc/pacman.conf "
                              "&& echo 'OK: Chaotic-AUR eingetragen.')"],
                         description="Fügt [chaotic-aur] in pacman.conf ein (idempotent)",
                         dangerous=True, needs_confirm=True),
                MenuItem("Schritt 6 — Datenbank synchronisieren",
                         cmd=["sudo", "pacman", "-Sy"],
                         description="Paketdatenbank nach Repo-Einrichtung aktualisieren"),
                MenuItem("KOMPLETT-SETUP — alle 6 Schritte  ⚠",
                         cmd=["bash", "-c",
                              "set -e; "
                              "echo '== Schritt 1: Schluessel herunterladen =='; "
                              "sudo pacman-key --recv-key 3056513887B78AEB "
                              "  --keyserver keyserver.ubuntu.com; "
                              "echo '== Schritt 2: Schluessel signieren =='; "
                              "sudo pacman-key --lsign-key 3056513887B78AEB; "
                              "echo '== Schritt 3: Keyring installieren =='; "
                              "sudo pacman -U --noconfirm "
                              "  'https://cdn-mirror.chaotic.cx/chaotic-aur/"
                              "chaotic-keyring.pkg.tar.zst'; "
                              "echo '== Schritt 4: Mirrorlist installieren =='; "
                              "sudo pacman -U --noconfirm "
                              "  'https://cdn-mirror.chaotic.cx/chaotic-aur/"
                              "chaotic-mirrorlist.pkg.tar.zst'; "
                              "echo '== Schritt 5: pacman.conf aktualisieren =='; "
                              "grep -q chaotic-aur /etc/pacman.conf "
                              "  && echo '  Bereits eingetragen.' "
                              "  || (printf '\\n[chaotic-aur]\\n"
                              "Include = /etc/pacman.d/chaotic-mirrorlist\\n' "
                              "      | sudo tee -a /etc/pacman.conf); "
                              "echo '== Schritt 6: Datenbank synchronisieren =='; "
                              "sudo pacman -Sy; "
                              "echo ''; echo 'OK: Chaotic-AUR eingerichtet!'"],
                         description="Alle 6 Schritte automatisch — braucht Internetverbindung",
                         dangerous=True, needs_confirm=True),
                MenuItem("Installierte Chaotic-AUR-Pakete",
                         cmd=["bash", "-c",
                              "pacman -Sl chaotic-aur 2>/dev/null | grep ' installed' "
                              "|| echo 'Keine Pakete oder Repo nicht aktiv.'"],
                         description="Liste aller aus Chaotic-AUR installierten Pakete"),
                MenuItem("Chaotic-AUR aus pacman.conf entfernen  ⚠",
                         cmd=["bash", "-c",
                              "sudo sed -i '/\\[chaotic-aur\\]/,/^$/d' "
                              "/etc/pacman.conf "
                              "&& echo 'OK: Chaotic-AUR entfernt.' "
                              "|| echo 'Fehler beim Entfernen.'"],
                         description="Entfernt [chaotic-aur] Block aus /etc/pacman.conf",
                         dangerous=True, needs_confirm=True),
            ],
        ),
        # ── 11 ────────────────────────────────────────────────────────────────
        MenuItem(
            label="🥾  Bootloader",
            description="GRUB, systemd-boot und Limine verwalten",
            submenu=[
                # ─────────── GRUB ───────────
                MenuItem("━━━━  GRUB  ━━━━",
                         cmd=None, description="GNU GRUB 2 Bootloader",
                         is_separator=True),
                MenuItem("GRUB: Status & Version anzeigen",
                         cmd=["bash", "-c",
                              "grub-install --version 2>/dev/null "
                              "|| echo 'grub nicht installiert'; "
                              "ls -la /boot/grub/grub.cfg 2>/dev/null "
                              "|| echo 'Keine grub.cfg in /boot/grub'"],
                         description="GRUB-Version und Config-Datei anzeigen"),
                MenuItem("GRUB-Config aktualisieren  (update-grub)",
                         cmd=["sudo", "grub-mkconfig", "-o", "/boot/grub/grub.cfg"],
                         description="grub.cfg neu generieren — entspricht update-grub",
                         dangerous=True, needs_confirm=True),
                MenuItem("GRUB BIOS installieren  (Geraet angeben)",
                         cmd=["sudo", "grub-install", "--target=i386-pc", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Geraet (z.B. /dev/sda, /dev/nvme0n1): ",
                         description="GRUB in MBR/BIOS-Bereich eines Geraets installieren",
                         dangerous=True, needs_confirm=True),
                MenuItem("GRUB UEFI installieren  (EFI-Verz. angeben)",
                         cmd=["sudo", "grub-install",
                              "--target=x86_64-efi",
                              "--efi-directory={INPUT}",
                              "--bootloader-id=ARCH", "--recheck"],
                         needs_input=True,
                         input_prompt="EFI-Verzeichnis (z.B. /boot oder /boot/efi): ",
                         description="GRUB fuer UEFI-Boot installieren",
                         dangerous=True, needs_confirm=True),
                MenuItem("GRUB Paket aktualisieren",
                         cmd=["sudo", "pacman", "-Syu", "--noconfirm", "grub"],
                         description="grub-Paket aus offiziellen Repos aktualisieren"),
                MenuItem("GRUB-Config anzeigen",
                         cmd=["cat", "/boot/grub/grub.cfg"],
                         description="Aktuelle /boot/grub/grub.cfg anzeigen"),
                MenuItem("✏  /etc/default/grub bearbeiten  (nano)",
                         cmd=["sudo", "nano", "/etc/default/grub"],
                         description="GRUB-Standardkonfiguration in nano bearbeiten",
                         is_editor=True),
                # ─────────── systemd-boot ───────────
                MenuItem("━━━━  systemd-boot  ━━━━",
                         cmd=None, description="systemd-boot Bootloader (EFI)",
                         is_separator=True),
                MenuItem("systemd-boot: Status anzeigen",
                         cmd=["bash", "-c",
                              "bootctl status 2>/dev/null "
                              "|| echo 'bootctl nicht verfuegbar / nicht aktiv'"],
                         description="systemd-boot Status und Version anzeigen"),
                MenuItem("systemd-boot aktualisieren  (bootctl update)",
                         cmd=["sudo", "bootctl", "update"],
                         description="systemd-boot Binary und Dateien aktualisieren",
                         dangerous=True, needs_confirm=True),
                MenuItem("systemd-boot installieren  (bootctl install)",
                         cmd=["sudo", "bootctl", "install"],
                         description="systemd-boot in ESP installieren",
                         dangerous=True, needs_confirm=True),
                MenuItem("Boot-Eintraege anzeigen  (bootctl list)",
                         cmd=["bash", "-c",
                              "bootctl list 2>/dev/null "
                              "|| echo 'Keine Eintraege / bootctl fehlt'"],
                         description="Alle systemd-boot Eintraege auflisten"),
                MenuItem("✏  /boot/loader/loader.conf bearbeiten  (nano)",
                         cmd=["sudo", "nano", "/boot/loader/loader.conf"],
                         description="systemd-boot Hauptkonfiguration bearbeiten",
                         is_editor=True),
                # ─────────── Limine ───────────
                MenuItem("━━━━  Limine  ━━━━",
                         cmd=None, description="Limine moderner Bootloader",
                         is_separator=True),
                MenuItem("Limine: Status anzeigen",
                         cmd=["bash", "-c",
                              "limine --version 2>/dev/null "
                              "|| echo 'Limine nicht installiert'"],
                         description="Limine-Version anzeigen"),
                MenuItem("Limine installieren  (pacman)",
                         cmd=["sudo", "pacman", "-S", "--noconfirm", "limine"],
                         description="Limine-Paket aus Arch-Repos installieren"),
                MenuItem("Limine BIOS-Install  (Geraet angeben)",
                         cmd=["sudo", "limine", "bios-install", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Zielgeraet (z.B. /dev/sda): ",
                         description="Limine BIOS-Stage auf MBR schreiben",
                         dangerous=True, needs_confirm=True),
                MenuItem("Limine EFI in ESP deployen  (ESP angeben)",
                         cmd=["bash", "-c",
                              "sudo mkdir -p {INPUT}/EFI/BOOT && "
                              "sudo cp /usr/share/limine/BOOTX64.EFI "
                              "{INPUT}/EFI/BOOT/ "
                              "&& echo 'OK: Limine EFI-Datei kopiert.' "
                              "|| echo 'Fehler — Pfad pruefen!'"],
                         needs_input=True,
                         input_prompt="ESP-Pfad (z.B. /boot oder /efi): ",
                         description="Limine EFI-Binary in ESP-Partition kopieren",
                         dangerous=True, needs_confirm=True),
                MenuItem("✏  limine.conf bearbeiten  (nano)",
                         cmd=["bash", "-c",
                              "f=$(ls /boot/limine.conf /efi/limine.conf "
                              "2>/dev/null | head -1); "
                              "[ -n \"$f\" ] && sudo nano \"$f\" "
                              "|| echo 'limine.conf nicht gefunden'"],
                         description="Limine-Konfigurationsdatei in nano öffnen",
                         is_editor=True),
                # ─────────── Initramfs ───────────
                MenuItem("━━━━  Initramfs  ━━━━",
                         cmd=None, description="mkinitcpio — initramfs-Generator",
                         is_separator=True),
                MenuItem("Initramfs-Images anzeigen",
                         cmd=["bash", "-c",
                              "ls -lh /boot/initramfs*.img 2>/dev/null "
                              "|| echo 'Keine initramfs-Images in /boot'"],
                         description="Vorhandene initramfs-Images anzeigen"),
                MenuItem("Initramfs neu generieren  (mkinitcpio -P)",
                         cmd=["sudo", "mkinitcpio", "-P"],
                         description="Alle initramfs-Images fuer alle Kernel neu bauen",
                         dangerous=True, needs_confirm=True),
                MenuItem("Initramfs fuer einen Kernel  (mkinitcpio -p)",
                         cmd=["sudo", "mkinitcpio", "-p", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Preset (z.B. linux, linux-lts, linux-zen): ",
                         description="Initramfs fuer einen bestimmten Kernel bauen",
                         dangerous=True, needs_confirm=True),
            ],
        ),
        # ── 12 ────────────────────────────────────────────────────────────────
        MenuItem(
            label="⚡  Strom & System",
            description="Neustart, Herunterfahren und Energie-Optionen",
            submenu=[
                MenuItem("System-Status  (systemctl status)",
                         cmd=["systemctl", "status", "--no-pager"],
                         description="Allgemeinen systemd-Status anzeigen"),
                MenuItem("Fehlgeschlagene Units anzeigen",
                         cmd=["systemctl", "--failed", "--no-pager"],
                         description="Alle fehlgeschlagenen systemd-Dienste"),
                MenuItem("Uptime anzeigen",
                         cmd=["bash", "-c", "uptime -p; echo ''; who -b"],
                         description="Systemlaufzeit und letzten Boot-Zeitpunkt"),
                MenuItem("Journal — letzte 50 Eintraege",
                         cmd=["journalctl", "-xe", "--no-pager", "-n", "50"],
                         description="Letzte 50 Systemlog-Eintraege mit Kontext"),
                # Neustart
                MenuItem("[ NEUSTART ]",
                         cmd=["bash", "-c", "echo 'Neustart-Optionen:'"],
                         description="Neustart-Optionen",
                         is_separator=True),
                MenuItem("NEUSTARTEN  (systemctl reboot)  ⚠",
                         cmd=["sudo", "systemctl", "reboot"],
                         description="System sofort neu starten!",
                         dangerous=True, needs_confirm=True),
                MenuItem("Neustart in 1 Minute  (shutdown -r +1)",
                         cmd=["sudo", "shutdown", "-r", "+1",
                              "Neustart in 1 Minute"],
                         description="Geplanter Neustart in 1 Minute",
                         dangerous=True, needs_confirm=True),
                MenuItem("Geplanten Neustart abbrechen  (shutdown -c)",
                         cmd=["sudo", "shutdown", "-c"],
                         description="Laufenden shutdown/reboot-Countdown abbrechen"),
                # Herunterfahren
                MenuItem("[ HERUNTERFAHREN ]",
                         cmd=["bash", "-c", "echo 'Shutdown-Optionen:'"],
                         description="Herunterfahren-Optionen",
                         is_separator=True),
                MenuItem("HERUNTERFAHREN  (systemctl poweroff)  ⚠",
                         cmd=["sudo", "systemctl", "poweroff"],
                         description="System sofort ausschalten!",
                         dangerous=True, needs_confirm=True),
                MenuItem("Herunterfahren in 5 Minuten  (shutdown +5)",
                         cmd=["sudo", "shutdown", "+5",
                              "System in 5 Minuten herunterfahren"],
                         description="Geplantes Herunterfahren in 5 Minuten",
                         dangerous=True, needs_confirm=True),
                # Energie
                MenuItem("[ ENERGIE-OPTIONEN ]",
                         cmd=["bash", "-c", "echo 'Energie-Optionen:'"],
                         description="Energie-Optionen",
                         is_separator=True),
                MenuItem("Suspend  (RAM-Sleep / S3)",
                         cmd=["sudo", "systemctl", "suspend"],
                         description="System in RAM-Schlafmodus (S3) versetzen",
                         needs_confirm=True),
                MenuItem("Hibernate  (Swap / S4)",
                         cmd=["sudo", "systemctl", "hibernate"],
                         description="System auf Swap hibernieren (S4)",
                         needs_confirm=True),
                MenuItem("Hybrid-Sleep  (RAM + Swap)",
                         cmd=["sudo", "systemctl", "hybrid-sleep"],
                         description="Suspend-to-both: RAM und Swap gleichzeitig",
                         needs_confirm=True),
            ],
        ),
        # ── 13 — Downgrade ────────────────────────────────────────────────────
        MenuItem(
            label="⏪  Downgrade",
            description="Pakete auf ältere Versionen zurücksetzen (Cache & ARM)",
            submenu=[
                # ── Info ──────────────────────────────────────────────────────
                MenuItem("[ INFO & VORAUSSETZUNGEN ]",
                         cmd=None, description="Downgrade-Werkzeuge und Quellen",
                         is_separator=True),
                MenuItem("downgrade-Tool installieren  (AUR)",
                         cmd=["yay", "-S", "--noconfirm", "downgrade"],
                         description="Das 'downgrade'-Hilfsprogramm aus dem AUR installieren"),
                MenuItem("downgrade-Version anzeigen",
                         cmd=["bash", "-c",
                              "downgrade --version 2>/dev/null "
                              "|| echo 'downgrade nicht installiert — bitte zuerst installieren'"],
                         description="Zeigt ob downgrade verfuegbar ist"),
                # ── Pakete via downgrade-Tool ─────────────────────────────────
                MenuItem("[ DOWNGRADE VIA downgrade-TOOL ]",
                         cmd=None, description="Interaktives Downgrade-Programm",
                         is_separator=True),
                MenuItem("Paket downgraden  (interaktiv, Cache + ARM)",
                         cmd=["bash", "-c",
                              "command -v downgrade >/dev/null 2>&1 "
                              "|| { echo 'FEHLER: downgrade nicht installiert.'; exit 1; }; "
                              "sudo downgrade {INPUT}"],
                         needs_input=True,
                         input_prompt="Paketname zum Downgraden: ",
                         description="Listet alle verfuegbaren Versionen aus Cache und ARM auf",
                         dangerous=True, needs_confirm=True),
                MenuItem("Mehrere Pakete downgraden  (Leerzeichen getrennt)",
                         cmd=["bash", "-c",
                              "command -v downgrade >/dev/null 2>&1 "
                              "|| { echo 'FEHLER: downgrade nicht installiert.'; exit 1; }; "
                              "sudo downgrade {INPUT}"],
                         needs_input=True,
                         input_prompt="Paketnamen (z.B. mesa lib32-mesa): ",
                         description="Mehrere Pakete gleichzeitig downgraden",
                         dangerous=True, needs_confirm=True),
                # ── Manuell aus Cache ─────────────────────────────────────────
                MenuItem("[ MANUELL AUS PAKET-CACHE ]",
                         cmd=None, description="Direkt aus /var/cache/pacman/pkg/",
                         is_separator=True),
                MenuItem("Verfuegbare Cache-Versionen anzeigen",
                         cmd=["bash", "-c",
                              "PKG={INPUT}; "
                              "ls /var/cache/pacman/pkg/${PKG}-*.pkg.tar.* 2>/dev/null "
                              "|| echo 'Keine Pakete fuer \"'$PKG'\" im Cache gefunden.'"],
                         needs_input=True,
                         input_prompt="Paketname (fuer Cache-Suche): ",
                         description="Listet alle gecachten Versionen eines Pakets auf"),
                MenuItem("Paket aus Cache installieren  (Pfad angeben)",
                         cmd=["sudo", "pacman", "-U", "--noconfirm", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Vollstaendiger Pfad zur .pkg.tar.zst-Datei: ",
                         description="Konkrete Version aus dem Cache direkt installieren",
                         dangerous=True, needs_confirm=True),
                # ── Version einfrieren ────────────────────────────────────────
                MenuItem("[ VERSION EINFRIEREN (IgnorePkg) ]",
                         cmd=None, description="Pakete vom Update ausschliessen",
                         is_separator=True),
                MenuItem("Aktuell eingefrorene Pakete anzeigen",
                         cmd=["bash", "-c",
                              "grep -i 'IgnorePkg' /etc/pacman.conf "
                              "|| echo 'Keine IgnorePkg-Eintraege in pacman.conf'"],
                         description="Zeigt aktuelle IgnorePkg-Zeile in pacman.conf"),
                MenuItem("Paket zu IgnorePkg hinzufuegen",
                         cmd=["bash", "-c",
                              "PKG={INPUT}; "
                              "grep -q \"^IgnorePkg\" /etc/pacman.conf && "
                              "sudo sed -i \"/^IgnorePkg/ s/$/ $PKG/\" /etc/pacman.conf || "
                              "echo \"IgnorePkg = $PKG\" | sudo tee -a /etc/pacman.conf; "
                              "echo 'OK: '\"$PKG\"' zu IgnorePkg hinzugefuegt.'; "
                              "grep 'IgnorePkg' /etc/pacman.conf"],
                         needs_input=True,
                         input_prompt="Paketname einfrieren (IgnorePkg): ",
                         description="Fuegt Paket zur IgnorePkg-Liste in pacman.conf hinzu",
                         dangerous=True, needs_confirm=True),
                MenuItem("Paket aus IgnorePkg entfernen",
                         cmd=["bash", "-c",
                              "PKG={INPUT}; "
                              "sudo sed -i "
                              "\"s/\\bIgnorePkg\\s*=\\s*$PKG\\b//;"
                              "s/\\s\\+$PKG\\b//;"
                              "s/$PKG\\b\\s\\+//g\" "
                              "/etc/pacman.conf; "
                              "echo 'OK: '\"$PKG\"' aus IgnorePkg entfernt.'; "
                              "grep 'IgnorePkg' /etc/pacman.conf || "
                              "echo '(IgnorePkg-Zeile ist jetzt leer)'"],
                         needs_input=True,
                         input_prompt="Paketname aus IgnorePkg entfernen: ",
                         description="Entfernt Paket aus der IgnorePkg-Liste",
                         dangerous=True, needs_confirm=True),
                # ── Arch Rollback Machine ─────────────────────────────────────
                MenuItem("[ ARCH ROLLBACK MACHINE (ARM) ]",
                         cmd=None, description="Paketarchiv archive.archlinux.org",
                         is_separator=True),
                MenuItem("ARM-Archivseite oeffnen  (Browserlinkausgabe)",
                         cmd=["bash", "-c",
                              "echo 'Arch Rollback Machine (Paketarchiv):'; "
                              "echo 'https://archive.archlinux.org/packages/'; "
                              "echo ''; "
                              "echo 'Tipp: Mit downgrade wird ARM automatisch abgefragt.'"],
                         description="Zeigt ARM-URL — alle alten Paketversionen verfuegbar"),
                MenuItem("ARM-Repo temporaer einbinden  (Einmaldownload)",
                         cmd=["bash", "-c",
                              "echo 'Beispiel-Befehl fuer direkten ARM-Download:'; "
                              "echo ''; "
                              "echo 'sudo pacman -U https://archive.archlinux.org/';"
                              "echo 'packages/<buchstabe>/<paket>/<paket>-<ver>-<arch>.pkg.tar.zst';"
                              "echo ''; "
                              "echo 'Einfacher: downgrade-Tool verwenden (oben im Menue)'"],
                         description="Erklaert direkten Paketbezug vom ARM-Archiv"),
            ],
        ),
        # ── 14 — Flatpak ──────────────────────────────────────────────────────
        MenuItem(
            label="📦  Flatpak",
            description="Flatpak-Anwendungen verwalten (Flathub und andere Repos)",
            submenu=[
                # ── Einrichtung ───────────────────────────────────────────────
                MenuItem("[ EINRICHTUNG ]",
                         cmd=None, description="Flatpak installieren und konfigurieren",
                         is_separator=True),
                MenuItem("Flatpak-Status pruefen",
                         cmd=["bash", "-c",
                              "flatpak --version 2>/dev/null "
                              "|| echo 'Flatpak nicht installiert'; "
                              "echo ''; "
                              "echo 'Konfigurierte Remotes:'; "
                              "flatpak remotes 2>/dev/null "
                              "|| echo '(Flatpak nicht verfuegbar)'"],
                         description="Flatpak-Version und konfigurierte Repos anzeigen"),
                MenuItem("Flatpak installieren  (pacman)",
                         cmd=["sudo", "pacman", "-S", "--noconfirm", "flatpak"],
                         description="Flatpak-Paket aus offiziellen Arch-Repos installieren"),
                MenuItem("Flathub einrichten  (System-weit)",
                         cmd=["sudo", "flatpak", "remote-add", "--if-not-exists",
                              "flathub",
                              "https://dl.flathub.org/repo/flathub.flatpakrepo"],
                         description="Flathub als System-Remote hinzufuegen (sudo)",
                         needs_confirm=True),
                MenuItem("Flathub einrichten  (nur aktueller User)",
                         cmd=["flatpak", "remote-add", "--if-not-exists", "--user",
                              "flathub",
                              "https://dl.flathub.org/repo/flathub.flatpakrepo"],
                         description="Flathub als User-Remote hinzufuegen (kein sudo)"),
                MenuItem("Alle Remotes anzeigen",
                         cmd=["flatpak", "remotes", "--show-details"],
                         description="Konfigurierte Flatpak-Repositories mit Details"),
                MenuItem("Remote entfernen",
                         cmd=["sudo", "flatpak", "remote-delete", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Remote-Name (z.B. flathub): ",
                         description="Flatpak-Repository entfernen",
                         dangerous=True, needs_confirm=True),
                # ── Suchen & Installieren ─────────────────────────────────────
                MenuItem("[ SUCHEN & INSTALLIEREN ]",
                         cmd=None, description="Flatpak-Anwendungen finden und installieren",
                         is_separator=True),
                MenuItem("Anwendung suchen  (flathub)",
                         cmd=["flatpak", "search", "{INPUT}"],
                         needs_input=True,
                         input_prompt="Suchbegriff (Flatpak): ",
                         description="In allen konfigurierten Flatpak-Repos suchen",
                         is_search=True),
                MenuItem("Anwendung installieren  (System-weit)",
                         cmd=["sudo", "flatpak", "install", "--noninteractive",
                              "flathub", "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID oder Name (z.B. org.gimp.GIMP): ",
                         description="Flatpak-Anwendung systemweit installieren",
                         needs_confirm=True),
                MenuItem("Anwendung installieren  (nur aktueller User)",
                         cmd=["flatpak", "install", "--noninteractive", "--user",
                              "flathub", "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID oder Name (z.B. com.spotify.Client): ",
                         description="Flatpak-Anwendung nur fuer diesen User installieren"),
                MenuItem("Anwendungsinfo anzeigen",
                         cmd=["flatpak", "info", "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID (z.B. org.videolan.VLC): ",
                         description="Detaillierte Informationen zu einer Flatpak-App"),
                # ── Verwaltung ────────────────────────────────────────────────
                MenuItem("[ VERWALTUNG ]",
                         cmd=None, description="Installierte Flatpaks verwalten",
                         is_separator=True),
                MenuItem("Alle installierten Flatpaks auflisten",
                         cmd=["flatpak", "list", "--app", "--columns=app,name,version,origin"],
                         description="Alle installierten Anwendungen mit Version und Quelle"),
                MenuItem("Laufende Flatpak-Prozesse anzeigen",
                         cmd=["flatpak", "ps"],
                         description="Aktuell ausgefuehrte Flatpak-Anwendungen"),
                MenuItem("Anwendung starten",
                         cmd=["flatpak", "run", "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID (z.B. org.gimp.GIMP): ",
                         description="Flatpak-Anwendung direkt starten"),
                MenuItem("Anwendung entfernen  (System)",
                         cmd=["sudo", "flatpak", "uninstall", "--noninteractive",
                              "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID zum Entfernen: ",
                         description="Systemweite Flatpak-Anwendung deinstallieren",
                         dangerous=True, needs_confirm=True),
                MenuItem("Anwendung entfernen  (User)",
                         cmd=["flatpak", "uninstall", "--noninteractive",
                              "--user", "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID zum Entfernen (User): ",
                         description="User-Flatpak-Anwendung deinstallieren",
                         dangerous=True, needs_confirm=True),
                MenuItem("Nicht verwendete Runtimes entfernen",
                         cmd=["sudo", "flatpak", "uninstall", "--unused",
                              "--noninteractive"],
                         description="Verwaiste Flatpak-Runtimes und -Extensions bereinigen",
                         dangerous=True, needs_confirm=True),
                # ── Update ────────────────────────────────────────────────────
                MenuItem("[ UPDATE ]",
                         cmd=None, description="Flatpak-Anwendungen aktualisieren",
                         is_separator=True),
                MenuItem("Alle Flatpaks aktualisieren  (System + User)",
                         cmd=["flatpak", "update", "--noninteractive"],
                         description="Alle installierten Flatpak-Apps auf neueste Version"),
                MenuItem("Einzelne App aktualisieren",
                         cmd=["flatpak", "update", "--noninteractive", "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID zum Aktualisieren: ",
                         description="Nur eine bestimmte Flatpak-App aktualisieren"),
                MenuItem("Verfuegbare Updates pruefen  (ohne install)",
                         cmd=["flatpak", "remote-ls", "--updates"],
                         description="Zeigt verfuegbare Updates ohne sie zu installieren"),
                # ── Berechtigungen ────────────────────────────────────────────
                MenuItem("[ BERECHTIGUNGEN ]",
                         cmd=None, description="Sandbox-Berechtigungen verwalten",
                         is_separator=True),
                MenuItem("Berechtigungen einer App anzeigen",
                         cmd=["flatpak", "info", "--show-permissions", "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID: ",
                         description="Sandbox-Berechtigungen einer Flatpak-App anzeigen"),
                MenuItem("Berechtigung entziehen  (override)",
                         cmd=["sudo", "flatpak", "override", "--nofilesystem=home",
                              "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID (Heimverzeichnis wird gesperrt): ",
                         description="Entzieht App Zugriff auf Home-Verzeichnis",
                         dangerous=True, needs_confirm=True),
                MenuItem("Alle Overrides einer App zuruecksetzen",
                         cmd=["sudo", "flatpak", "override", "--reset", "{INPUT}"],
                         needs_input=True,
                         input_prompt="App-ID (Overrides zuruecksetzen): ",
                         description="Alle manuellen Berechtigungsaenderungen rueckgaengig machen",
                         needs_confirm=True),
                MenuItem("Alle App-Overrides anzeigen",
                         cmd=["flatpak", "override", "--show"],
                         description="Alle gesetzten Flatpak-Berechtigungs-Overrides auflisten"),
                # ── Disk-Nutzung ──────────────────────────────────────────────
                MenuItem("[ SPEICHER & DISK ]",
                         cmd=None, description="Flatpak-Speichernutzung",
                         is_separator=True),
                MenuItem("Flatpak Gesamtspeicher anzeigen",
                         cmd=["bash", "-c",
                              "du -sh /var/lib/flatpak 2>/dev/null; "
                              "du -sh ~/.local/share/flatpak 2>/dev/null; "
                              "echo ''; "
                              "echo 'Installierte Apps:'; "
                              "flatpak list --app 2>/dev/null | wc -l; "
                              "echo 'Installierte Runtimes:'; "
                              "flatpak list --runtime 2>/dev/null | wc -l"],
                         description="Speicherverbrauch von System- und User-Flatpaks"),
                MenuItem("Flatpak-Installationsverzeichnisse anzeigen",
                         cmd=["bash", "-c",
                              "echo '=== System (/var/lib/flatpak) ==='; "
                              "ls /var/lib/flatpak/app/ 2>/dev/null || echo 'leer'; "
                              "echo ''; "
                              "echo '=== User (~/.local/share/flatpak) ==='; "
                              "ls ~/.local/share/flatpak/app/ 2>/dev/null || echo 'leer'"],
                         description="Installierte Apps in System- und User-Verzeichnissen"),
            ],
        ),
    ]


# ─── Hilfsfunktionen ───────────────────────────────────────────────────────────
def check_tool(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(cmd: List[str], input_val: str = "") -> Tuple[int, str]:
    """Nicht-interaktiven Befehl ausführen; gibt (returncode, ausgabe) zurück.
    Nur für reine Lesebefehle (pacman -Q, cat, ls ...) — NIEMALS für sudo/yay."""
    resolved: List[str] = [p.replace("{INPUT}", input_val) for p in cmd]
    try:
        proc = subprocess.run(
            resolved, capture_output=True, text=True, timeout=300
        )
        out = proc.stdout
        if proc.stderr.strip():
            out += "\n-- stderr --\n" + proc.stderr
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return -1, "Timeout: Befehl >300 s abgebrochen."
    except FileNotFoundError as exc:
        return -1, f"Programm nicht gefunden: {exc}"
    except Exception as exc:
        return -1, f"Fehler: {exc}"


def run_interactive(cmd: List[str]) -> int:
    """Befehl interaktiv im Vordergrund ausführen (curses pausiert).

    Notwendig für alle Befehle die TTY brauchen:
    - sudo (Passwort-Prompt)
    - yay (PKGBUILD-Review, Benutzerabfragen)
    - pacman -Syu (langer Output, lesbar halten)
    - systemctl reboot/poweroff (sofortige Aktion)
    """
    curses.endwin()
    rc = -1
    try:
        # Trennlinie für bessere Lesbarkeit
        print("\n" + "═" * 70)
        print(f"  $ {' '.join(cmd)}")
        print("═" * 70 + "\n")
        result = subprocess.run(cmd, check=False)
        rc = result.returncode
        print("\n" + "═" * 70)
        if rc == 0:
            print(f"  ✓ Befehl erfolgreich ausgefuehrt  (Exit-Code 0)")
        else:
            print(f"  ✗ Befehl fehlgeschlagen  (Exit-Code {rc})")
        print("═" * 70)
        print("\n  Druecke ENTER um zum Package Manager zurueckzukehren...")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
    except FileNotFoundError as exc:
        print(f"\n✗ Programm nicht gefunden: {exc}")
        print("  Druecke ENTER...")
        try: input()
        except: pass
    except Exception as exc:
        print(f"\n✗ Fehler: {exc}")
        print("  Druecke ENTER...")
        try: input()
        except: pass
    finally:
        curses.doupdate()
    return rc


def is_interactive_cmd(cmd: Optional[List[str]]) -> bool:
    """Entscheidet ob ein Befehl interaktiv laufen muss.

    Regel:
    - sudo als erstes Argument  -> interaktiv (Passwort-Prompt)
    - yay mit -S/-R/-U/-Syu     -> interaktiv (PKGBUILD-Review, sudo intern)
    - bash -c "... sudo ..."    -> interaktiv
    - bash -c "... yay -S ..."  -> interaktiv
    - Alles andere              -> captured (stdout im Output-Panel)
    """
    if not cmd:
        return False
    # Direkter sudo-Aufruf
    if cmd[0] == "sudo":
        return True
    # yay-Operationen die sudo-Passwort brauchen oder PKGBUILD-Review zeigen
    if cmd[0] == "yay" and len(cmd) > 1:
        op = cmd[1]
        # -S, -Sy, -Syu, -R, -Rs, -Rns, -U, ... alle brauchen sudo intern
        if op.startswith(("-S", "-R", "-U")):
            # Ausnahme: -Ss (Suche) und -Si (Info) sind read-only
            if op in ("-Ss", "-Si"):
                return False
            return True
    # bash -c Skripte mit sudo/yay drin
    if cmd[0] == "bash" and len(cmd) >= 3 and cmd[1] == "-c":
        script = cmd[2]
        if ("sudo " in script or script.startswith("sudo")
                or " yay " in script or script.startswith("yay ")
                or "| sudo " in script or "&& sudo" in script
                or "flatpak install" in script
                or "makepkg" in script):
            return True
    return False


def run_editor(cmd: List[str]) -> None:
    """Editor interaktiv im Vordergrund; curses wird pausiert."""
    curses.endwin()
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError as exc:
        print(f"\nEditor nicht gefunden: {exc}")
        time.sleep(2)
    except Exception as exc:
        print(f"\nFehler: {exc}")
        time.sleep(2)
    finally:
        curses.doupdate()


# ─── Suchergebnis-Parser ───────────────────────────────────────────────────────
# Fix: Regex-Gruppe heißt "n" — m.group("name") wäre ein KeyError
_RE_PKG = re.compile(
    r"^(?P<repo>[a-zA-Z0-9_-]+)/(?P<n>\S+)\s+(?P<ver>\S+)(?P<rest>.*)$"
)

# Segment = (text, color_pair_id, bold)
Segment = Tuple[str, int, bool]


def parse_search_line(line: str) -> List[Segment]:
    """Zerlegt eine pacman/yay -Ss Zeile in farbige Segmente."""
    if line and line[0] in (" ", "\t"):
        return [(line, C_PKG_DESC, False)]
    m = _RE_PKG.match(line)
    if m:
        repo = m.group("repo")
        pair = C_PKG_AUR if repo == "aur" else C_PKG_REPO
        # Fix: m.group("n") nicht m.group("name")
        segs: List[Segment] = [
            (repo + "/",    pair,       True),
            (m.group("n"),  C_PKG_NAME, True),
            (" ",           C_NORMAL,   False),
            (m.group("ver"), C_PKG_VER, False),
        ]
        rest = m.group("rest")
        if rest:
            segs.append((rest, C_PKG_FLAG, False))
        return segs
    ll = line.lower()
    if any(k in ll for k in ("error", "fehler", "failed")):
        return [(line, C_ERROR, False)]
    if any(k in ll for k in ("warning", "warn")):
        return [(line, C_WARN, False)]
    return [(line, C_NORMAL, False)]


# ─── Haupt-Applikation ─────────────────────────────────────────────────────────
class PackageManager:
    LEFT_W = 36   # Anzeigebreite der linken Menüspalte (Spalten)

    def __init__(self, stdscr: "curses.window") -> None:
        self.stdscr        = stdscr
        self.menu          = build_menu()
        self.sel_main      = 0
        self.sel_sub       = 0
        self.sub_scroll    = 0   # Scroll-Offset für das Submenü
        self.show_sub      = False
        self.output_lines: List[str] = []
        self.output_scroll = 0
        self.output_search = False
        self.status_msg    = ""
        self.status_ok     = True
        self.running       = True
        # Input-Modal
        self.input_mode    = False
        self.input_text    = ""
        self.input_prompt  = ""
        self.pending_item: Optional[MenuItem] = None
        # Bestätigungs-Modal
        self.confirm_mode      = False
        self.confirm_item:  Optional[MenuItem] = None
        self.confirm_input_val = ""
        self._yes_btn          = (0, 0, 0)  # (y, x, cols) — beim Zeichnen gesetzt
        self._no_btn           = (0, 0, 0)
        # Hilfe-Overlay
        self.show_help         = False
        # Row-Mappings für Maus-Hit-Test (y_coord -> item_index)
        self._menu_rows: dict  = {}
        self._sub_rows:  dict  = {}
        self._menu_start       = 0
        self._sub_start        = 0
        self._init_colors()
        self._init_mouse()

    # ── Init ──────────────────────────────────────────────────────────────────
    def _init_colors(self) -> None:
        curses.start_color()
        curses.use_default_colors()

        # ── Echtes Schwarz erzwingen ──────────────────────────────────────────
        # ANSI-Farbe 0 (COLOR_BLACK) wird von vielen Dark-Themes als dunkelgrau
        # gerendert. Im 256-Color-Modus ist Index 16 garantiert reines #000000.
        # Fallback auf COLOR_BLACK bei nur 8 Farben.
        TRUE_BLACK = 16 if curses.COLORS >= 256 else curses.COLOR_BLACK

        # ── Schwarzer Hintergrund — alle Paare auf TRUE_BLACK ─────────────────
        curses.init_pair(C_NORMAL,   curses.COLOR_WHITE,   TRUE_BLACK)
        # Invertierte Paare: TRUE_BLACK als Vordergrund -> echtes Schwarz
        curses.init_pair(C_HEADER,   TRUE_BLACK,           curses.COLOR_CYAN)
        curses.init_pair(C_SELECTED, TRUE_BLACK,           curses.COLOR_GREEN)
        curses.init_pair(C_ERROR,    curses.COLOR_WHITE,   curses.COLOR_RED)
        curses.init_pair(C_SUCCESS,  TRUE_BLACK,           curses.COLOR_GREEN)
        curses.init_pair(C_TITLE,    curses.COLOR_YELLOW,  TRUE_BLACK)
        curses.init_pair(C_BORDER,   curses.COLOR_CYAN,    TRUE_BLACK)
        curses.init_pair(C_DIM,      curses.COLOR_CYAN,    TRUE_BLACK)
        curses.init_pair(C_WARN,     TRUE_BLACK,           curses.COLOR_YELLOW)
        curses.init_pair(C_INPUT,    TRUE_BLACK,           curses.COLOR_WHITE)
        # ── Suchergebnis-Farben (alle auf Schwarz) ────────────────────────────
        curses.init_pair(C_PKG_REPO, curses.COLOR_CYAN,    TRUE_BLACK)
        curses.init_pair(C_PKG_NAME, curses.COLOR_WHITE,   TRUE_BLACK)
        curses.init_pair(C_PKG_VER,  curses.COLOR_GREEN,   TRUE_BLACK)
        curses.init_pair(C_PKG_FLAG, curses.COLOR_YELLOW,  TRUE_BLACK)
        curses.init_pair(C_PKG_AUR,  curses.COLOR_MAGENTA, TRUE_BLACK)
        curses.init_pair(C_PKG_DESC, curses.COLOR_CYAN,    TRUE_BLACK)

    def _init_mouse(self) -> None:
        curses.mousemask(
            curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION
        )
        curses.mouseinterval(0)

    # ── Zeichenhelfer ─────────────────────────────────────────────────────────
    def _cp(self, pair: int, bold: bool = False) -> int:
        a = curses.color_pair(pair)
        return (a | curses.A_BOLD) if bold else a

    def _put(self, y: int, x: int, text: str, attr: int = 0) -> None:
        """Sicheres addstr — ignoriert Randüberschreitung."""
        h, w = self.stdscr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        avail = w - x - 1
        if avail <= 0:
            return
        try:
            self.stdscr.addstr(y, x, text[:avail], attr)
        except curses.error:
            pass

    # ── Hauptzeichenroutine ───────────────────────────────────────────────────
    def draw(self) -> None:
        h, w = self.stdscr.getmaxyx()
        # Hintergrund: Weiß auf Schwarz
        self.stdscr.bkgd(" ", self._cp(C_NORMAL))
        self.stdscr.erase()

        # ── Zeile 0: Titelleiste ──────────────────────────────────────────────
        title = " Arch Linux Package Manager  *  Pacman + Yay  v4 "
        self._put(0, 0, " " * w, self._cp(C_HEADER))
        self._put(0, max(0, (w - len(title)) // 2), title,
                  self._cp(C_HEADER) | curses.A_BOLD)

        # ── Zeile 1: Trennlinie + kompakter Shortcut-Hinweis ─────────────────
        self._put(1, 0, "─" * w, self._cp(C_BORDER))
        shortcut = " H=Hilfe  C=Clear  Q=Beenden "
        self._put(1, max(0, w - len(shortcut) - 1),
                  shortcut, self._cp(C_DIM) | curses.A_BOLD)

        lw = self.LEFT_W
        rx = lw + 1
        rw = w - rx
        ch = h - 4   # Content-Höhe: ohne 2× Header + 2× Status

        self._draw_left(lw, ch)

        # Trennlinie Mitte
        for y in range(2, h - 2):
            self._put(y, lw, "│", self._cp(C_BORDER))

        if self.show_sub and self.menu[self.sel_main].submenu:
            self._draw_sub(rx, rw, ch)
        else:
            self._draw_output(rx, rw, ch)

        self._draw_status(h, w)

        # Modale — Reihenfolge: zuerst Input, dann Confirm, dann Help (oben)
        if self.input_mode:
            self._draw_input(h, w)
        if self.confirm_mode:
            self._draw_confirm(h, w)
        if self.show_help:
            self._draw_help(h, w)

        self.stdscr.refresh()

    # ── Linke Spalte: Hauptmenü mit Scroll + Zeilenabstand ────────────────────
    def _draw_left(self, lw: int, ch: int) -> None:
        """Hauptmenü mit Leerzeile zwischen Einträgen — besser fürs Klicken.

        Jeder Eintrag belegt 2 Zeilen (Label + Spacer). Das erhöht die
        Klickfläche und die Lesbarkeit.
        """
        self._put(2, 1, "[ HAUPTMENU ]",
                  self._cp(C_TITLE) | curses.A_BOLD)
        # Trennlinie unter Überschrift
        self._put(3, 0, "─" * lw, self._cp(C_BORDER))

        max_vis_rows = ch - 3   # Nutzbare Zeilen ab y=4
        # Jeder Eintrag = 2 Zeilen (Label + Spacer)
        ROW_HEIGHT   = 2
        items_visible = max(1, max_vis_rows // ROW_HEIGHT)

        # Scroll so dass sel_main immer sichtbar
        ms = max(0, self.sel_main - items_visible + 1)
        ms = min(ms, max(0, len(self.menu) - items_visible))
        self._menu_start = ms

        # Map: visible_slot -> item_index (wird vom Mouse-Handler gebraucht)
        self._menu_rows = {}   # {y_coord: item_idx}

        for slot in range(items_visible):
            idx = ms + slot
            if idx >= len(self.menu):
                break
            y    = 4 + slot * ROW_HEIGHT   # Label-Zeile
            item = self.menu[idx]
            sel  = (idx == self.sel_main)

            if sel and self.show_sub:
                attr = self._cp(C_SELECTED) | curses.A_BOLD
            elif sel:
                attr = self._cp(C_SELECTED)
            else:
                attr = self._cp(C_NORMAL)

            # Volle Zeile füllen (Klickfläche)
            self._put(y, 0, " " + _ljust(item.label, lw - 4), attr)
            if sel:
                self._put(y, lw - 3, " > ", self._cp(C_TITLE) | curses.A_BOLD)

            # Mapping für Mouse-Handler: sowohl Label-Zeile als auch Spacer
            # werden demselben Item zugeordnet
            self._menu_rows[y]     = idx
            self._menu_rows[y + 1] = idx   # Spacer-Zeile ist auch klickbar

        # Scroll-Indikatoren
        if ms > 0:
            self._put(4, lw - 2, "▲", self._cp(C_BORDER) | curses.A_BOLD)
        if ms + items_visible < len(self.menu):
            self._put(2 + ch - 1, lw - 2, "▼",
                      self._cp(C_BORDER) | curses.A_BOLD)

    # ── Rechte Seite: Submenü mit Scroll + Gruppenabstand ─────────────────────
    def _draw_sub(self, rx: int, rw: int, ch: int) -> None:
        """Submenü mit Leerzeile VOR jedem Separator und Zeilenabstand.

        Layout-Regeln:
        - Separator: eine Leerzeile davor (außer wenn erstes Element)
                     eine Leerzeile danach (vor erstem Kind)
        - Normale Einträge: 1 Zeile pro Eintrag (Submenüs können lang sein)
        """
        sub   = self.menu[self.sel_main].submenu or []
        title = "[ " + self.menu[self.sel_main].label.strip() + " ]"
        self._put(2, rx + 1, title[:rw - 2],
                  self._cp(C_TITLE) | curses.A_BOLD)
        # Trennlinie unter Überschrift
        self._put(3, rx, "─" * (rw - 1), self._cp(C_BORDER))

        # ── Schritt 1: Virtuelles Zeilen-Layout planen ────────────────────────
        # Liste von (typ, item_idx_or_None)
        # typ ∈ {"item", "item_gap", "sep", "gap"}
        # - "item"     : echter klickbarer Eintrag
        # - "item_gap" : Leerzeile NACH einem Item (Klick zählt zum Item)
        # - "sep"      : Gruppen-Separator (nicht klickbar)
        # - "gap"      : reine Leerzeile (bei Separator vor/nach)
        layout = []
        prev_was_item = False
        for idx, item in enumerate(sub):
            if item.is_separator:
                # Leerzeile VOR Separator (außer erstes Element)
                if layout:
                    layout.append(("gap", None))
                layout.append(("sep", idx))
                # Leerzeile NACH Separator (vor erstem Kind)
                layout.append(("gap", None))
                prev_was_item = False
            else:
                # Option A: Leerzeile zwischen zwei aufeinander folgenden Items
                if prev_was_item:
                    layout.append(("item_gap", idx - 1))
                layout.append(("item", idx))
                prev_was_item = True

        # ── Schritt 2: Scroll-Offset berechnen ────────────────────────────────
        # Finde die virtuelle Zeile des aktuell selektierten Items
        sel_row = 0
        for row, (typ, idx) in enumerate(layout):
            if typ == "item" and idx == self.sel_sub:
                sel_row = row
                break

        max_vis = ch - 5   # Platz für Titel+Linie+Desc+Hinweis
        # Scroll so dass sel_row immer sichtbar
        ss = max(0, sel_row - max_vis + 1)
        ss = min(ss, max(0, len(layout) - max_vis))
        self._sub_start = ss
        self.sub_scroll = ss

        # Map: y_coord -> sub_idx (für Mouse-Handler)
        self._sub_rows = {}

        # ── Schritt 3: Zeichnen ───────────────────────────────────────────────
        for slot in range(max_vis):
            row_idx = ss + slot
            if row_idx >= len(layout):
                break
            y    = 4 + slot
            typ, idx = layout[row_idx]

            if typ == "gap":
                # Leerzeile vor/nach Separator — nichts zeichnen
                continue

            if typ == "item_gap":
                # Leerzeile zwischen zwei Items — klickbar dem vorigen Item
                # zurechnen (größere Klickfläche, natürlicher fürs Auge)
                if idx is not None:
                    self._sub_rows[y] = idx
                continue

            if typ == "sep":
                item = sub[idx]
                lbl = item.label.strip()
                if lbl.startswith("━"):
                    sep_text = _center(lbl, rw - 3)
                else:
                    sep_text = _center(f"  {lbl}  ", rw - 3, "━")
                self._put(y, rx, " " + sep_text,
                          self._cp(C_TITLE) | curses.A_BOLD)
                continue

            # Normaler Eintrag (typ == "item")
            item = sub[idx]
            sel  = (idx == self.sel_sub)
            if sel:
                attr = self._cp(C_SELECTED) | curses.A_BOLD
            elif item.dangerous:
                attr = self._cp(C_ERROR)
            else:
                attr = self._cp(C_NORMAL)
            self._put(y, rx, " " + _ljust(item.label, rw - 3), attr)
            # Mapping für Mouse-Handler
            self._sub_rows[y] = idx

        # ── Schritt 4: Scroll-Indikatoren ─────────────────────────────────────
        if ss > 0:
            self._put(4, rx + rw - 2, "▲",
                      self._cp(C_BORDER) | curses.A_BOLD)
        if ss + max_vis < len(layout):
            self._put(2 + ch - 3, rx + rw - 2, "▼",
                      self._cp(C_BORDER) | curses.A_BOLD)

        # Beschreibung des markierten Eintrags
        desc_y = 4 + max_vis
        if 0 <= self.sel_sub < len(sub) and not sub[self.sel_sub].is_separator:
            for di, dl in enumerate(
                self._wrap(sub[self.sel_sub].description, rw - 2)[:2]
            ):
                if desc_y + di < 2 + ch - 1:
                    self._put(desc_y + di, rx + 1, dl, self._cp(C_DIM))

        # Hinweiszeile unten
        self._put(2 + ch - 1, rx + 1,
                  "[ Klick=Auswaehlen | 2xKlick=Ausfuehren | Scroll=Scrollen ]",
                  self._cp(C_DIM))

    # ── Output-Bereich ────────────────────────────────────────────────────────
    def _draw_output(self, rx: int, rw: int, ch: int) -> None:
        badge = "  [SUCHE — farbig]" if self.output_search else ""
        self._put(2, rx + 1, f"[ OUTPUT{badge} ]",
                  self._cp(C_TITLE) | curses.A_BOLD)

        visible   = ch - 2
        lines     = self.output_lines
        max_start = max(0, len(lines) - visible)
        start     = max(0, min(self.output_scroll, max_start))

        for i, line in enumerate(lines[start:start + visible]):
            y = 3 + i
            if self.output_search:
                self._draw_search_line(y, rx + 1, line, rw - 3)
            else:
                self._draw_plain_line(y, rx + 1, line, rw - 3)

        if lines:
            bar_y = 2 + ch - 1
            pct   = int((start / max_start) * 100) if max_start > 0 else 100
            info  = (f" {start+1}-{min(start+visible, len(lines))}"
                     f"/{len(lines)} ({pct}%) ")
            self._put(bar_y, rx + 1, info[:rw - 3], self._cp(C_DIM))

            # Mini-Scrollbar
            bar_h   = max(1, (visible * visible) // max(len(lines), 1))
            bar_pos = int((start / max(max_start, 1)) * max(0, visible - bar_h))
            for bi in range(visible):
                sym = "#" if bar_pos <= bi < bar_pos + bar_h else ":"
                sy  = 3 + bi
                if sy < 2 + ch - 1:
                    self._put(sy, rx + rw - 2, sym, self._cp(C_BORDER))

    def _draw_plain_line(self, y: int, x: int, line: str, max_w: int) -> None:
        ll = line.lower()
        if any(k in ll for k in ("error", "fehler", "failed")):
            attr = self._cp(C_ERROR)
        elif any(k in ll for k in ("erfolgreich", "installed", "fertig", "ok:")):
            attr = self._cp(C_SUCCESS)
        elif any(k in ll for k in ("warning", "warn")):
            attr = self._cp(C_WARN)
        elif line.startswith("$") or line.startswith("=="):
            attr = self._cp(C_TITLE) | curses.A_BOLD
        elif line.startswith("--") or line.startswith("──"):
            attr = self._cp(C_BORDER)
        else:
            attr = self._cp(C_NORMAL)
        self._put(y, x, line[:max_w], attr)

    def _draw_search_line(self, y: int, x: int, line: str, max_w: int) -> None:
        """Suchergebnis-Zeile segmentweise farbig rendern."""
        if line.startswith("$") or not line.strip():
            self._draw_plain_line(y, x, line, max_w)
            return
        segs = parse_search_line(line)
        cx = x
        for text, pair, bold in segs:
            if cx >= x + max_w:
                break
            avail = (x + max_w) - cx
            try:
                self.stdscr.addstr(y, cx, text[:avail], self._cp(pair, bold))
            except curses.error:
                pass
            cx += len(text)
        if cx < x + max_w:
            try:
                self.stdscr.addstr(y, cx, " " * (x + max_w - cx),
                                   self._cp(C_NORMAL))
            except curses.error:
                pass

    # ── Status ────────────────────────────────────────────────────────────────
    def _draw_status(self, h: int, w: int) -> None:
        msg  = self.status_msg or "Bereit — Klicke einen Menuepunkt an."
        attr = self._cp(C_SUCCESS) if self.status_ok else self._cp(C_ERROR)
        self._put(h - 2, 0, "─" * w, self._cp(C_BORDER))
        self._put(h - 1, 0, _ljust(" " + msg, w), attr)

    # ── Input-Modal ───────────────────────────────────────────────────────────
    def _draw_input(self, h: int, w: int) -> None:
        bw = min(w - 6, 74)
        bx = (w - bw) // 2
        by = max(2, h // 2 - 3)
        for row in range(by, by + 6):
            self._put(row, bx - 1, " " * (bw + 2), self._cp(C_INPUT))
        self._put(by,     bx, "+" + "-" * (bw - 2) + "+",
                  self._cp(C_INPUT) | curses.A_BOLD)
        self._put(by + 1, bx,
                  "|" + _center("  EINGABE ERFORDERLICH", bw - 2) + "|",
                  self._cp(C_WARN) | curses.A_BOLD)
        self._put(by + 2, bx, "+" + "-" * (bw - 2) + "+", self._cp(C_INPUT))
        prompt_str = self.input_prompt[:bw - 4]
        self._put(by + 3, bx,
                  "| " + _ljust(prompt_str, bw - 4) + " |",
                  self._cp(C_INPUT))
        inp_display = self.input_text[-(bw - 6):]
        self._put(by + 4, bx,
                  "| > " + _ljust(inp_display, bw - 6) + " |",
                  self._cp(C_INPUT) | curses.A_UNDERLINE)
        self._put(by + 5, bx,
                  "+" + " Enter=Bestaetigen  Esc=Abbrechen ".center(bw - 2, "-") + "+",
                  self._cp(C_DIM))

    # ── Bestätigungs-Modal ────────────────────────────────────────────────────
    def _draw_confirm(self, h: int, w: int) -> None:
        item = self.confirm_item
        if item is None:
            return
        bw = min(w - 4, 70)
        bx = (w - bw) // 2
        by = max(2, h // 2 - 4)

        for row in range(by, by + 9):
            self._put(row, bx - 1, " " * (bw + 2), self._cp(C_ERROR))

        self._put(by,     bx, "╔" + "═" * (bw - 2) + "╗",
                  self._cp(C_ERROR) | curses.A_BOLD)
        self._put(by + 8, bx, "╚" + "═" * (bw - 2) + "╝",
                  self._cp(C_ERROR) | curses.A_BOLD)
        self._put(by + 1, bx,
                  "║" + _center("  BESTAETIGUNG ERFORDERLICH", bw - 2) + "║",
                  self._cp(C_ERROR) | curses.A_BOLD)
        self._put(by + 2, bx, "╠" + "═" * (bw - 2) + "╣", self._cp(C_ERROR))

        # Aktionszeile — Emoji aus Label entfernen für sauberes Layout
        action = item.label.replace("⚠", "").replace("!", "").strip()
        inner  = bw - 14  # "║  Aktion:  " + " ║"
        self._put(by + 3, bx,
                  "║  Aktion: " + _ljust(action[:inner], inner) + " ║",
                  self._cp(C_ERROR))

        desc_lines = self._wrap(item.description, bw - 6)[:2]
        for di, dl in enumerate(desc_lines):
            self._put(by + 4 + di, bx,
                      "║  " + _ljust(dl, bw - 4) + " ║",
                      self._cp(C_WARN))
        if len(desc_lines) < 2:
            self._put(by + 5, bx, "║" + " " * (bw - 2) + "║", self._cp(C_ERROR))

        self._put(by + 6, bx, "╠" + "═" * (bw - 2) + "╣", self._cp(C_ERROR))

        # Buttons — ASCII-Labels für exakte Spaltenberechnung (kein Emoji-Width-Bug)
        yes_label = "  [ JA, AUSFUEHREN ]  "
        no_label  = "  [ NEIN / ABBRECHEN ]  "
        inner_w   = bw - 2
        gap       = max(2, inner_w - len(yes_label) - len(no_label))
        pad       = " " * (gap // 2)

        btn_y = by + 7
        yes_x = bx + 1
        no_x  = yes_x + len(yes_label) + len(pad)

        self._put(btn_y, bx, "║", self._cp(C_ERROR))
        self._put(btn_y, yes_x, yes_label, self._cp(C_SUCCESS) | curses.A_BOLD)
        self._put(btn_y, yes_x + len(yes_label), pad, self._cp(C_ERROR))
        self._put(btn_y, no_x,  no_label,  self._cp(C_INPUT)   | curses.A_BOLD)
        rest_x = no_x + len(no_label)
        rest_w = bx + bw - 1 - rest_x
        if rest_w > 0:
            self._put(btn_y, rest_x, " " * rest_w, self._cp(C_ERROR))
        self._put(btn_y, bx + bw - 1, "║", self._cp(C_ERROR))

        # Button-Regionen für Hit-Test (y, x_start, col_width)
        self._yes_btn = (btn_y, yes_x, len(yes_label))
        self._no_btn  = (btn_y, no_x,  len(no_label))

    # ── Hilfe-Overlay (H-Taste) ───────────────────────────────────────────────
    def _draw_help(self, h: int, w: int) -> None:
        """Zeigt ein Hilfe-Modal — erscheint nur wenn H gedrückt wird."""
        bw = min(w - 4, 72)
        bx = (w - bw) // 2
        by = max(1, h // 2 - 13)

        HELP_LINES = [
            ("╔", "═", "╗", C_BORDER),  # Rahmen oben
            ("║", _center(" HILFE — Arch Linux Package Manager  v4 ", bw - 2), "║", C_TITLE),
            ("╠", "═", "╣", C_BORDER),
            ("║", " MAUSSTEUERUNG:                                        ", "║", C_DIM),
            ("║", "  1x Klick Hauptmenu    Eintrag markieren              ", "║", C_NORMAL),
            ("║", "  2x Klick Hauptmenu    Submenu oeffnen / schliessen   ", "║", C_NORMAL),
            ("║", "  1x Klick Submenu      Eintrag markieren              ", "║", C_NORMAL),
            ("║", "  2x Klick Submenu      Eintrag ausfuehren             ", "║", C_NORMAL),
            ("║", "  Scrollrad             Output-Bereich scrollen         ", "║", C_NORMAL),
            ("╠", "═", "╣", C_BORDER),
            ("║", " TASTATURKUERZEL:                                       ", "║", C_DIM),
            ("║", "  H / h                 Diese Hilfe anzeigen / schliessen", "║", C_NORMAL),
            ("║", "  C / c                 Output-Bereich leeren          ", "║", C_NORMAL),
            ("║", "  Q / q                 Programm beenden               ", "║", C_NORMAL),
            ("║", "  J / j / Y / Enter     Bestaetigung: JA               ", "║", C_NORMAL),
            ("║", "  N / n / Esc           Bestaetigung: NEIN / Abbrechen ", "║", C_NORMAL),
            ("║", "  Backspace             Eingabe: letztes Zeichen loeschen", "║", C_NORMAL),
            ("╠", "═", "╣", C_BORDER),
            ("║", " SYMBOLE IM SUBMENU:                                    ", "║", C_DIM),
            ("║", "  Rote Eintraege        Destruktive Aktion — Bestaetigung noetig", "║", C_ERROR),
            ("║", "  ── Trennlinie ──       Kategorie-Trenner, nicht klickbar", "║", C_BORDER),
            ("║", "  [SUCHE]               Farbige, scrollbare Paketausgabe", "║", C_PKG_VER),
            ("║", "  [EDIT]                Editor startet im Vordergrund   ", "║", C_PKG_FLAG),
            ("╠", "═", "╣", C_BORDER),
            ("║", " HINWEISE:                                              ", "║", C_DIM),
            ("║", "  - yay-Befehle brauchen kein sudo                     ", "║", C_NORMAL),
            ("║", "  - Editor: $EDITOR-Variable wird beachtet             ", "║", C_NORMAL),
            ("║", "  - Mindest-Terminalgroesse: 90x24 Zeichen             ", "║", C_NORMAL),
            ("╠", "═", "╣", C_BORDER),
            ("║", _center("  H oder Esc = Hilfe schliessen  ", bw - 2), "║", C_TITLE),
            ("╚", "═", "╝", C_BORDER),  # Rahmen unten
        ]

        for i, row in enumerate(HELP_LINES):
            y = by + i
            if y >= h - 1:
                break
            left, mid, right, pair = row
            # Rahmenzeile (Linie)
            if mid in ("═",):
                line = left + mid * (bw - 2) + right
                self._put(y, bx, line[:w - bx - 1], self._cp(C_BORDER) | curses.A_BOLD)
            else:
                # Inhaltszeile: Rahmen + Inhalt
                inner = _ljust(mid, bw - 2)[:bw - 2]
                self._put(y, bx,          left,  self._cp(C_BORDER) | curses.A_BOLD)
                self._put(y, bx + 1,      inner, self._cp(pair))
                self._put(y, bx + bw - 1, right, self._cp(C_BORDER) | curses.A_BOLD)

    # ── Mouse-Handler ─────────────────────────────────────────────────────────
    def handle_mouse(self, mx: int, my: int, bstate: int) -> None:
        h, _ = self.stdscr.getmaxyx()
        ch    = h - 4
        lw    = self.LEFT_W

        # Scrollrad
        if bstate & curses.BUTTON4_PRESSED:
            self.output_scroll = max(0, self.output_scroll - 3)
            return
        if bstate & curses.BUTTON5_PRESSED:
            self.output_scroll = min(
                max(0, len(self.output_lines) - 1), self.output_scroll + 3
            )
            return
        if not (bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED)):
            return

        # Bestätigungs-Modal — höchste Priorität
        if self.confirm_mode:
            yy, yx, yw = self._yes_btn
            if my == yy and yx <= mx < yx + yw:
                self._confirm_yes()
            else:
                self._confirm_no()
            return

        # Input-Modal aktiv — Klicks ignorieren
        if self.input_mode:
            return

        # ── Linke Spalte: Hauptmenü (via _menu_rows Map) ──────────────────────
        if mx < lw:
            menu_rows = getattr(self, "_menu_rows", {})
            idx = menu_rows.get(my)
            if idx is not None and 0 <= idx < len(self.menu):
                if idx == self.sel_main:
                    if self.menu[idx].submenu:
                        self.show_sub   = not self.show_sub
                        self.sel_sub    = 0
                        self.sub_scroll = 0
                    else:
                        self._execute(self.menu[idx])
                else:
                    self.sel_main      = idx
                    self.show_sub      = False
                    self.sel_sub       = 0
                    self.sub_scroll    = 0
                    self.output_scroll = 0
                    # Auto-Clear: Output leeren und neuen Kontext anzeigen
                    item = self.menu[idx]
                    self.output_lines = [
                        f"  [ {item.label.strip()} ]",
                        "",
                        f"  {item.description}",
                        "",
                        "  2x Klick oeffnet das Submenue.",
                    ]
                    self.output_search = False
                    self.status_msg    = f"Bereit: {item.label.strip()}"
                    self.status_ok     = True
            return

        # ── Rechte Seite: Submenü (via _sub_rows Map) ─────────────────────────
        rx = lw + 1
        if mx >= rx and self.show_sub:
            sub_rows = getattr(self, "_sub_rows", {})
            sub      = self.menu[self.sel_main].submenu or []
            idx = sub_rows.get(my)
            if idx is not None and 0 <= idx < len(sub) and not sub[idx].is_separator:
                if idx == self.sel_sub:
                    self._execute(sub[idx])
                else:
                    self.sel_sub = idx

    # ── Tastatur-Handler ──────────────────────────────────────────────────────
    def handle_key(self, key: int) -> None:
        """Confirm-Modal, Input-Modal, Help-Overlay und Q über Tastatur."""
        # Hilfe-Overlay: Esc oder H schließt es
        if self.show_help:
            if key in (27, ord("h"), ord("H")):
                self.show_help = False
            return

        if self.confirm_mode:
            if key in (curses.KEY_ENTER, 10, 13,
                       ord("j"), ord("J"), ord("y"), ord("Y")):
                self._confirm_yes()
            elif key in (27, ord("n"), ord("N")):
                self._confirm_no()
            return

        if self.input_mode:
            if key in (curses.KEY_ENTER, 10, 13):
                self._confirm_input()
            elif key == 27:
                self.input_mode   = False
                self.input_text   = ""
                self.pending_item = None
                self.status_msg   = "Eingabe abgebrochen."
                self.status_ok    = True
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                self.input_text = self.input_text[:-1]
            elif 32 <= key < 256:
                self.input_text += chr(key)
            return

        # Normalmodus
        if key in (ord("h"), ord("H")):
            self.show_help = True
        elif key in (ord("c"), ord("C")):
            self._clear_output()
        elif key in (ord("q"), ord("Q")):
            self.running = False

    def _clear_output(self) -> None:
        """Output-Bereich leeren und kurze Bestätigung zeigen."""
        self.output_lines  = [
            "",
            "  Output-Bereich geleert.",
            "",
            "  Waehle einen Menuepunkt um einen neuen Befehl auszufuehren.",
            "  Druecke H fuer Hilfe, Q zum Beenden.",
            "",
        ]
        self.output_scroll = 0
        self.output_search = False
        self.status_msg    = "Output geleert."
        self.status_ok     = True

    # ── Ausführungslogik ──────────────────────────────────────────────────────
    def _execute(self, item: MenuItem, input_val: str = "") -> None:
        if item.is_separator:
            return
        if item.needs_input and not input_val:
            self.input_mode   = True
            self.input_text   = ""
            self.input_prompt = item.input_prompt
            self.pending_item = item
            self.status_msg   = f"Eingabe: {item.input_prompt}"
            self.status_ok    = True
        elif item.needs_confirm:
            self.confirm_mode      = True
            self.confirm_item      = item
            self.confirm_input_val = input_val
        elif item.is_editor:
            self._run_editor(item, input_val)
        else:
            self._run_item(item, input_val)

    def _confirm_yes(self) -> None:
        item = self.confirm_item
        val  = self.confirm_input_val
        self.confirm_mode      = False
        self.confirm_item      = None
        self.confirm_input_val = ""
        if item is None:
            return
        if item.is_editor:
            self._run_editor(item, val)
        else:
            self._run_item(item, val)

    def _confirm_no(self) -> None:
        self.confirm_mode      = False
        self.confirm_item      = None
        self.confirm_input_val = ""
        self.status_msg        = "Abgebrochen."
        self.status_ok         = True

    def _confirm_input(self) -> None:
        if not self.input_text.strip():
            self.status_msg = "Keine Eingabe — Abgebrochen."
            self.status_ok  = False
            self.input_mode = False
            return
        item = self.pending_item
        val  = self.input_text.strip()
        self.input_mode   = False
        self.input_text   = ""
        self.pending_item = None
        if item is None:
            return
        if item.needs_confirm:
            self.confirm_mode      = True
            self.confirm_item      = item
            self.confirm_input_val = val
        elif item.is_editor:
            self._run_editor(item, val)
        else:
            self._run_item(item, val)

    def _run_editor(self, item: MenuItem, input_val: str = "") -> None:
        self.show_sub = False
        self.draw()
        resolved = [p.replace("{INPUT}", input_val) for p in (item.cmd or [])]
        run_editor(resolved)
        self.stdscr.clear()
        self.output_lines  = [
            f"$ {' '.join(resolved)}", "",
            "OK: Editor beendet — Datei ggf. gespeichert.",
        ]
        self.output_scroll = 0
        self.output_search = False
        self.status_msg    = f"Editor geschlossen: {item.label[:55]}"
        self.status_ok     = True

    def _run_item(self, item: MenuItem, input_val: str = "") -> None:
        resolved = [p.replace("{INPUT}", input_val) for p in (item.cmd or [])]
        display_cmd = " ".join(resolved)

        # ── Interaktive Befehle (sudo, yay install, etc.) im Vordergrund ──────
        if is_interactive_cmd(item.cmd):
            self.show_sub = False
            self.status_msg = f"Interaktiv: {display_cmd[:60]}..."
            self.status_ok  = True
            self.draw()
            rc = run_interactive(resolved)
            # Nach Rückkehr: Bildschirm neu aufbauen
            self.stdscr.clear()
            self.output_lines = [
                f"$ {display_cmd}",
                "",
                "Hinweis: Dieser Befehl wurde interaktiv im Terminal ausgefuehrt,",
                "         damit sudo nach dem Passwort fragen konnte und Ausgaben",
                "         in Echtzeit sichtbar waren.",
                "",
                "─" * 44,
            ]
            if rc == 0:
                self.output_lines.append("OK: Erfolgreich abgeschlossen (Exit-Code 0).")
                self.status_msg = f"OK: {item.label[:60]}"
                self.status_ok  = True
            else:
                self.output_lines.append(f"FEHLER: Exit-Code {rc}")
                self.status_msg = f"Fehler: {item.label[:55]}"
                self.status_ok  = False
            self.output_scroll = 0
            self.output_search = False
            return

        # ── Captured-Output Befehle (read-only: pacman -Q, cat, ls ...) ───────
        self.status_msg    = f"Ausfuehren: {display_cmd[:60]}..."
        self.status_ok     = True
        self.output_lines  = [f"$ {display_cmd}", ""]
        self.output_scroll = 0
        self.output_search = item.is_search
        self.show_sub      = False
        self.draw()

        rc, out = run_command(item.cmd or [], input_val)
        self.output_lines += out.splitlines() if out.strip() else ["(keine Ausgabe)"]

        if rc == 0:
            self.output_lines += ["", "─" * 44, "OK: Erfolgreich abgeschlossen."]
            self.status_msg    = f"Fertig: {item.label[:60]}"
            self.status_ok     = True
        else:
            self.output_lines += ["", "─" * 44, f"FEHLER: Exit-Code {rc}"]
            self.status_msg    = f"Fehler: {item.label[:55]}"
            self.status_ok     = False

        # Ans Ende scrollen
        visible = self.stdscr.getmaxyx()[0] - 4 - 2
        self.output_scroll = max(0, len(self.output_lines) - visible)

    # ── Zeilenumbruch ─────────────────────────────────────────────────────────
    @staticmethod
    def _wrap(text: str, width: int) -> List[str]:
        words = text.split()
        lines: List[str] = []
        cur   = ""
        for w in words:
            candidate = (cur + " " + w).lstrip() if cur else w
            if _dw(candidate) <= width:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    # ── Hauptschleife ─────────────────────────────────────────────────────────
    def run(self) -> None:
        self.stdscr.timeout(40)
        curses.curs_set(0)
        self._menu_start = 0
        self._sub_start  = 0

        tools = [
            ("pacman",       "BENOETIGT"),
            ("sudo",         "BENOETIGT"),
            ("yay",          "optional — AUR / Downgrade"),
            ("reflector",    "optional — Mirror-Ranking"),
            ("downgrade",    "optional — Paket-Downgrade"),
            ("flatpak",      "optional — Flatpak-Verwaltung"),
            ("grub-mkconfig","optional — GRUB"),
            ("bootctl",      "optional — systemd-boot"),
            ("limine",       "optional — Limine"),
            ("nano",         "optional — Editor"),
            ("vim",          "optional — Editor"),
        ]
        self.output_lines = [
            "╔══════════════════════════════════════════════════════════╗",
            "║      Arch Linux Package Manager — ncurses TUI  v4        ║",
            "╠══════════════════════════════════════════════════════════╣",
            "║  Steuerung (nur Maus):                                    ║",
            "║   1x Klick Hauptmenu   -> Eintrag markieren              ║",
            "║   2x Klick Hauptmenu   -> Submenu oeffnen/schliessen     ║",
            "║   1x Klick im Submenu  -> Eintrag markieren              ║",
            "║   2x Klick im Submenu  -> Ausfuehren                     ║",
            "║   Scrollrad            -> Output-Bereich scrollen         ║",
            "║   Q                    -> Beenden                         ║",
            "╠══════════════════════════════════════════════════════════╣",
            "║  Symbole:                                                 ║",
            "║   [SUCHE]  -> farbige, scrollbare Paketliste             ║",
            "║   [EDIT]   -> Editor startet im Vordergrund              ║",
            "║   Rot      -> destructive Aktion (Bestaetigung noetig)   ║",
            "║   Bestaet. -> rotes Modal: JA/NEIN per Mausklick         ║",
            "╠══════════════════════════════════════════════════════════╣",
            "║  Menueuebersicht (14 Module):                             ║",
            "║   System Update    Pakete install.  Pakete entfernen     ║",
            "║   DB & Reparatur   Mirror-Ranking   Cache-Bereinigung    ║",
            "║   Systeminfo       AUR/yay           Konfiguration       ║",
            "║   Chaotic-AUR      Bootloader        Strom & System      ║",
            "║   Downgrade        Flatpak                               ║",
            "╠══════════════════════════════════════════════════════════╣",
        ]
        for name, role in tools:
            ok  = check_tool(name)
            sym = "OK  " if ok else "----"
            self.output_lines.append(
                f"║  [{sym}] {_ljust(name, 14)} {role:<34}║"
            )
        self.output_lines.append(
            "╚══════════════════════════════════════════════════════════╝"
        )

        while self.running:
            self.draw()
            try:
                key = self.stdscr.getch()
            except KeyboardInterrupt:
                self.running = False
                break
            if key == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, bstate = curses.getmouse()
                    self.handle_mouse(mx, my, bstate)
                except curses.error:
                    pass
            elif key != -1:
                self.handle_key(key)


# ─── Einstiegspunkt ────────────────────────────────────────────────────────────
def main(stdscr: "curses.window") -> None:
    PackageManager(stdscr).run()


def entry() -> None:
    if os.geteuid() == 0:
        print("Nicht als root starten — sudo wird intern verwendet!")
        sys.exit(1)
    try:
        sz = os.get_terminal_size()
        if sz.lines < 24 or sz.columns < 90:
            print(
                f"Terminal zu klein ({sz.columns}x{sz.lines})."
                f" Mindestgroesse: 90x24"
            )
            sys.exit(1)
    except OSError:
        pass
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nAuf Wiedersehen!")


if __name__ == "__main__":
    entry()
