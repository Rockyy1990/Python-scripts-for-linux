#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PiHole 6 Management CLI
Interactive administration script with comfort UX features.
Requires: Python 3.12+, PiHole v6
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# ── Python version guard ───────────────────────────────────────────────────
if sys.version_info < (3, 12):
    print("Fehler: Python 3.12+ erforderlich.", file=sys.stderr)
    sys.exit(1)

# ── ANSI color codes (Windows 11-inspired palette) ─────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    BLUE   = "\033[38;5;33m"
    CYAN   = "\033[38;5;45m"
    GREEN  = "\033[38;5;82m"
    YELLOW = "\033[38;5;220m"
    RED    = "\033[38;5;196m"
    WHITE  = "\033[38;5;255m"
    GRAY   = "\033[38;5;245m"
    PURPLE = "\033[38;5;135m"
    ORANGE = "\033[38;5;208m"

USE_COLOR: bool = sys.stdout.isatty() and "NO_COLOR" not in os.environ

def col(code: str, text: str) -> str:
    """Apply ANSI color if terminal supports it."""
    return f"{code}{text}{C.RESET}" if USE_COLOR else text

# ── Logging setup ──────────────────────────────────────────────────────────
_LOG_FILE = Path("/tmp") / f"pihole-mgmt-{datetime.now():%Y%m%d}.log"

def _setup_logging() -> None:
    handlers: list[logging.Handler] = []
    try:
        handlers.append(logging.FileHandler(_LOG_FILE, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        handlers=handlers or [logging.NullHandler()],
    )

log = logging.getLogger("pihole_mgmt")

# ── Terminal helpers ───────────────────────────────────────────────────────
TERM_W: int = min(shutil.get_terminal_size((80, 24)).columns, 90)
_RULE = "─" * TERM_W

def clear() -> None:
    os.system("clear")

def header(title: str, icon: str = "") -> None:
    label = f" {icon}  {title}" if icon else f" {title}"
    print(f"\n{col(C.BLUE, _RULE)}")
    print(col(C.BOLD + C.WHITE, label))
    print(col(C.BLUE, _RULE))

def divider() -> None:
    print(col(C.GRAY, "  " + "·" * (TERM_W - 4)))

def info(msg: str) -> None:
    print(f"  {col(C.BLUE, 'ℹ')}  {msg}")

def ok(msg: str) -> None:
    print(f"  {col(C.GREEN, '✔')}  {col(C.GREEN, msg)}")
    log.info("OK: %s", msg)

def warn(msg: str) -> None:
    print(f"  {col(C.YELLOW, '⚠')}  {col(C.YELLOW, msg)}")
    log.warning(msg)

def err(msg: str) -> None:
    print(f"  {col(C.RED, '✘')}  {col(C.RED, msg)}")
    log.error(msg)

def tip(msg: str) -> None:
    """Display a formatted tip/hint."""
    lines = textwrap.wrap(msg, width=min(TERM_W - 14, 68))
    for i, line in enumerate(lines):
        pfx = f"  {col(C.PURPLE, '💡 Tipp:')} " if i == 0 else "            "
        print(f"{pfx}{col(C.GRAY, line)}")

def press_enter() -> None:
    try:
        input(f"\n  {col(C.GRAY, '[ Weiter mit Enter ]')}")
    except (EOFError, KeyboardInterrupt):
        print()

def ask(prompt_text: str, default: str = "") -> str:
    """Styled single-line input."""
    hint = f" {col(C.GRAY, f'[{default}]')}" if default else ""
    try:
        val = input(f"\n  {col(C.CYAN, '›')} {prompt_text}{hint}: ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default

def confirm(msg: str, default: bool = False) -> bool:
    """Yes/No prompt with J/N localisation."""
    hint = col(C.GRAY, "[J/n]" if default else "[j/N]")
    answer = ask(f"{msg} {hint}")
    if not answer:
        return default
    return answer.lower() in ("j", "ja", "y", "yes")

# ── PiHole helpers ─────────────────────────────────────────────────────────

class PiHoleInfo(NamedTuple):
    installed: bool
    version: str
    ftl_version: str
    web_version: str
    binary: str


def _is_root() -> bool:
    return os.geteuid() == 0

def _prepend_sudo(cmd: list[str], force_sudo: bool) -> list[str]:
    """Only prepend sudo when not already root and caller requests it."""
    if force_sudo and not _is_root():
        return ["sudo", "--"] + cmd
    return cmd

def run(
    cmd: list[str],
    *,
    sudo: bool = False,
    capture: bool = False,
    timeout: int = 300,
    check: bool = True,
) -> str | None:
    """
    Execute a command with optional sudo escalation.
    Returns stdout as str when capture=True, else None.
    Logs all invocations and errors.
    """
    full = _prepend_sudo(cmd, sudo)
    log.info("exec: %s", " ".join(full))
    try:
        if capture:
            r = subprocess.run(
                full, capture_output=True, text=True,
                timeout=timeout, check=check,
            )
            return r.stdout.strip()
        subprocess.run(full, timeout=timeout, check=check)
        return None
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        err(f"Fehler (Exit {exc.returncode}): {' '.join(full)}")
        if stderr:
            err(f"Ausgabe: {stderr}")
        log.error("CalledProcessError cmd=%s stderr=%s", full, stderr)
    except subprocess.TimeoutExpired:
        err(f"Timeout nach {timeout}s: {' '.join(full)}")
        log.error("TimeoutExpired cmd=%s", full)
    except FileNotFoundError:
        err(f"Befehl nicht gefunden: {full[0]}")
    return None


def get_pihole_info() -> PiHoleInfo:
    binary = shutil.which("pihole") or ""
    if not binary:
        return PiHoleInfo(False, "–", "–", "–", "")

    version = ftl_version = web_version = "unbekannt"
    raw = run(["pihole", "version"], capture=True, sudo=False, check=False) or ""
    for line in raw.splitlines():
        low = line.lower()
        parts = line.split()
        if not parts:
            continue
        last = parts[-1]
        # Skip lines that are clearly not version lines
        if not any(c.isdigit() for c in last):
            continue
        if "pi-hole" in low and "version" in low and "ftl" not in low:
            version = last
        elif "ftl" in low and "version" in low:
            ftl_version = last
        elif ("web" in low or "adminlte" in low) and "version" in low:
            web_version = last

    return PiHoleInfo(True, version, ftl_version, web_version, binary)

# ── Validators ─────────────────────────────────────────────────────────────
_RE_DOMAIN = re.compile(
    r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
)
_RE_URL = re.compile(r'^https?://[^\s/$.?#].[^\s]*$')

def valid_domain(d: str) -> bool:
    return bool(_RE_DOMAIN.match(d))

def valid_url(u: str) -> bool:
    return bool(_RE_URL.match(u))

def valid_regex(p: str) -> bool:
    try:
        re.compile(p)
        return True
    except re.error:
        return False

# ══════════════════════════════════════════════════════════════════════════════
# ── MENU: Status ──────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def menu_status(ph: PiHoleInfo) -> None:
    clear()
    header("Status & Informationen", "📊")

    print(f"\n  {col(C.BOLD, 'Versionen')}")
    print(f"    Pi-hole : {col(C.CYAN, ph.version)}")
    print(f"    FTL     : {col(C.CYAN, ph.ftl_version)}")
    print(f"    Web     : {col(C.CYAN, ph.web_version)}")
    print(f"    Pfad    : {col(C.GRAY, ph.binary)}")
    divider()

    print(f"\n  {col(C.BOLD, 'Dienststatus')}")
    raw = run(["pihole", "status"], capture=True, sudo=False, check=False) or ""
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if any(k in low for k in ("running", "enabled", "active", "online")):
            print(f"    {col(C.GREEN, '●')} {stripped}")
        elif any(k in low for k in ("stopped", "disabled", "inactive", "offline")):
            print(f"    {col(C.RED, '●')} {stripped}")
        else:
            print(f"    {col(C.GRAY, '·')} {stripped}")

    divider()
    tip("Web-Dashboard: http://<pihole-ip>/admin  |  Log: " + str(_LOG_FILE))
    press_enter()

# ══════════════════════════════════════════════════════════════════════════════
# ── MENU: Gravity ─────────────────────────────────────────────════════════════
# ══════════════════════════════════════════════════════════════════════════════

def menu_gravity() -> None:
    while True:
        clear()
        header("Gravity-Verwaltung", "🔄")
        print(f"""
  {col(C.CYAN, '1')}  Gravity aktualisieren          pihole -g
  {col(C.CYAN, '2')}  Letztes Update-Log anzeigen
  {col(C.CYAN, '3')}  Adlisten-Anzahl prüfen

  {col(C.GRAY, '0')}  Zurück
""")
        match ask("Auswahl"):
            case "0" | "":
                return
            case "1":
                _gravity_update()
            case "2":
                _gravity_log()
            case "3":
                _gravity_stats()

def _gravity_update() -> None:
    clear()
    header("Gravity aktualisieren", "🔄")
    warn("Update kann mehrere Minuten dauern – DNS kurz unterbrochen!")
    tip("Empfohlen: Nachts oder bei geringer Netzlast ausführen")
    if not confirm("Gravity jetzt aktualisieren?", default=True):
        return
    print()
    log.info("gravity update started")
    run(["pihole", "-g"], sudo=True, timeout=600, check=False)
    ok("Gravity-Update abgeschlossen")
    log.info("gravity update finished")
    press_enter()

def _gravity_log() -> None:
    clear()
    header("Gravity-Update-Log", "📋")
    candidates = [
        Path("/var/log/pihole/pihole_updateGravity.log"),
        Path("/var/log/pihole/gravity.log"),
    ]
    for p in candidates:
        if p.exists():
            raw = run(["tail", "-n", "60", str(p)], capture=True, sudo=True, check=False)
            if raw:
                print(f"\n{col(C.GRAY, raw)}")
                press_enter()
                return
    # Fallback: journald
    raw = run(
        ["journalctl", "-u", "pihole-FTL", "-n", "40", "--no-pager"],
        capture=True, sudo=False, check=False,
    ) or "Kein Log gefunden."
    print(f"\n{col(C.GRAY, raw)}")
    press_enter()

def _gravity_stats() -> None:
    clear()
    header("Adlisten-Statistiken", "📊")
    # pihole adlist does not exist in v6 – query gravity.db directly
    rows = _adlist_db_query("SELECT enabled, COUNT(*) FROM adlist GROUP BY enabled")
    enabled = disabled = 0
    for flag, cnt in rows:
        # str("0") is truthy in Python; normalise to int for safe comparison
        if int(str(flag)) != 0:
            enabled = int(str(cnt))
        else:
            disabled = int(str(cnt))
    print(f"\n  Aktiviert : {col(C.GREEN, str(enabled))}")
    print(f"  Deaktiv.  : {col(C.RED, str(disabled))}")
    print(f"  Gesamt    : {col(C.BOLD, str(enabled + disabled))}")
    press_enter()

# ══════════════════════════════════════════════════════════════════════════════
# ── MENU: Domains ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def menu_domains() -> None:
    while True:
        clear()
        header("Domain-Verwaltung", "🌐")
        print(f"""
  {col(C.BOLD, 'Allowlist')}
  {col(C.CYAN, '1')}  Domain hinzufügen
  {col(C.CYAN, '2')}  Domain entfernen
  {col(C.CYAN, '3')}  Liste anzeigen

  {col(C.BOLD, 'Denylist')}
  {col(C.CYAN, '4')}  Domain hinzufügen
  {col(C.CYAN, '5')}  Domain entfernen
  {col(C.CYAN, '6')}  Liste anzeigen

  {col(C.GRAY, '0')}  Zurück
""")
        match ask("Auswahl"):
            case "0" | "": return
            case "1": _domain_modify("allow", delete=False)
            case "2": _domain_modify("allow", delete=True)
            case "3": _domain_list("allow")
            case "4": _domain_modify("deny", delete=False)
            case "5": _domain_modify("deny", delete=True)
            case "6": _domain_list("deny")

def _domain_modify(mode: str, *, delete: bool) -> None:
    clear()
    label = "Allowlist" if mode == "allow" else "Denylist"
    action = "entfernen aus" if delete else "hinzufügen zu"
    header(f"Domain {action} {label}", "🌐")

    if not delete:
        if mode == "allow":
            tip("Füge Domains hinzu, die trotz Blocklisten immer erlaubt sein sollen")
        else:
            warn("Geblockte Domains können Dienste/Apps unterbrechen!")
            tip("Für Subdomains ggf. Regex-Filter nutzen (Menü 4)")

    domain = ask("Domain (z.B. tracker.example.com)")
    if not domain:
        return

    if not valid_domain(domain):
        err(f"Ungültige Domain: '{domain}'")
        tip("Beispiele gültiger Domains: ads.example.com, tracker.google.com")
        press_enter()
        return

    if delete:
        if not confirm(f"'{domain}' aus der {label} entfernen?"):
            return
        cmd = ["pihole", mode, "-d", domain]
    else:
        comment = ask("Kommentar (optional)")
        cmd = ["pihole", mode, domain]
        if comment:
            cmd += ["--comment", comment]

    result = run(cmd, sudo=True, capture=True)
    if result is not None:
        verb = "entfernt" if delete else "hinzugefügt"
        ok(f"'{domain}' {verb} ({label})")
        if not delete:
            tip("Änderungen sind sofort ohne Neustart wirksam")
    press_enter()

def _domain_list(mode: str) -> None:
    clear()
    label = "Allowlist" if mode == "allow" else "Denylist"
    header(label, "📋")
    # pihole allow/deny -l requires root AND output contains rich metadata headers
    # → query domainlist table directly (type: 0=allow-exact, 1=deny-exact)
    db_type = 0 if mode == "allow" else 1
    rows = _adlist_db_query(
        "SELECT domain, enabled, comment FROM domainlist WHERE type = ? ORDER BY domain",
        (db_type,),
    )
    if rows:
        clr = C.GREEN if mode == "allow" else C.RED
        active   = sum(1 for r in rows if int(str(r[1])) != 0)
        inactive = len(rows) - active
        print(f"\n  {col(C.BOLD, str(len(rows)))} Einträge "
              f"({col(C.GREEN, str(active))} aktiv, "
              f"{col(C.GRAY, str(inactive))} deaktiviert):\n")
        for row in rows:
            domain  = str(row[0])
            enabled = int(str(row[1])) != 0 if len(row) > 1 else True
            comment = str(row[2]) if len(row) > 2 and row[2] else ""
            dot = col(clr, "●") if enabled else col(C.GRAY, "○")
            cmt = f"  {col(C.GRAY, comment)}" if comment else ""
            print(f"  {dot} {domain}{cmt}")
    else:
        info(f"{label} ist leer")
    press_enter()

# ══════════════════════════════════════════════════════════════════════════════
# ── MENU: Regex ───────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def menu_regex() -> None:
    while True:
        clear()
        header("Regex-Filter", "🔍")
        print(f"""
  {col(C.BOLD, 'Deny-Regex')}  (Blocken)
  {col(C.CYAN, '1')}  Hinzufügen
  {col(C.CYAN, '2')}  Entfernen
  {col(C.CYAN, '3')}  Anzeigen

  {col(C.BOLD, 'Allow-Regex')}  (Freigeben)
  {col(C.CYAN, '4')}  Hinzufügen
  {col(C.CYAN, '5')}  Entfernen
  {col(C.CYAN, '6')}  Anzeigen

  {col(C.GRAY, '0')}  Zurück
""")
        tip("Pi-hole nutzt POSIX ERE – Test unter https://regex101.com (POSIX ERE)")
        match ask("Auswahl"):
            case "0" | "": return
            case "1": _regex_add("deny")
            case "2": _regex_remove("deny")
            case "3": _regex_list("deny")
            case "4": _regex_add("allow")
            case "5": _regex_remove("allow")
            case "6": _regex_list("allow")

def _regex_add(mode: str) -> None:
    clear()
    label = "Deny" if mode == "deny" else "Allow"
    header(f"{label}-Regex hinzufügen", "➕")

    print(f"\n  {col(C.BOLD, 'Beispiele:')}")
    print(f"    {col(C.GRAY, '(^|\\\\.)ads\\\\.')}           → alle ads.*-Subdomains")
    print(f"    {col(C.GRAY, '.*telemetry.*')}         → alles mit 'telemetry'")
    print(f"    {col(C.GRAY, '(^|\\\\.)doubleclick\\\\.net$')}  → exakt doubleclick.net + Subs")
    print()

    pattern = ask("Regex-Pattern")
    if not pattern:
        return

    if not valid_regex(pattern):
        err(f"Ungültiger Regex: '{pattern}'")
        press_enter()
        return

    # Heuristic overly-broad check
    if re.fullmatch(r'\.?\*\+?|\.', pattern):
        warn("Sehr breites Pattern – kann legitime Domains blockieren!")
        if not confirm("Trotzdem fortfahren?"):
            return

    comment = ask("Kommentar (optional)")
    cmd = ["pihole", "--regex" if mode == "deny" else "--allow-regex", pattern]
    if comment:
        cmd += ["--comment", comment]

    result = run(cmd, sudo=True, capture=True)
    if result is not None:
        ok(f"{label}-Regex hinzugefügt: {pattern}")
        tip("Regex ist sofort aktiv – kein Neustart nötig")
    press_enter()

def _regex_remove(mode: str) -> None:
    clear()
    label = "Deny" if mode == "deny" else "Allow"
    header(f"{label}-Regex entfernen", "🗑")
    _print_regex_list(mode)
    pattern = ask("Zu entfernendes Pattern (exakt)")
    if not pattern:
        return
    if not confirm(f"Regex '{pattern}' entfernen?"):
        return
    cmd = ["pihole", "--regex" if mode == "deny" else "--allow-regex", "-d", pattern]
    result = run(cmd, sudo=True, capture=True)
    if result is not None:
        ok(f"Regex entfernt: {pattern}")
    press_enter()

def _print_regex_list(mode: str) -> None:
    # pihole --regex/-allow-regex -l requires root AND has rich header output
    # → query domainlist directly (type: 3=deny-regex, 2=allow-regex)
    db_type = 3 if mode == "deny" else 2
    rows = _adlist_db_query(
        "SELECT domain, enabled, comment FROM domainlist WHERE type = ? ORDER BY domain",
        (db_type,),
    )
    if rows:
        clr = C.RED if mode == "deny" else C.GREEN
        print(f"\n  {col(C.BOLD, 'Aktuelle Patterns:')}\n")
        for row in rows:
            pattern = str(row[0])
            enabled = int(str(row[1])) != 0 if len(row) > 1 else True
            comment = str(row[2]) if len(row) > 2 and row[2] else ""
            dot = col(clr, "●") if enabled else col(C.GRAY, "○")
            cmt = f"  {col(C.GRAY, comment)}" if comment else ""
            print(f"    {dot} {col(C.GRAY, pattern)}{cmt}")
        print()
    else:
        info("Keine Patterns konfiguriert")

def _regex_list(mode: str) -> None:
    clear()
    label = "Deny" if mode == "deny" else "Allow"
    header(f"{label}-Regex-Liste", "📋")
    _print_regex_list(mode)
    press_enter()

# ══════════════════════════════════════════════════════════════════════════════
# ── MENU: Adlists ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# Curated recommended lists with descriptions
_RECOMMENDED_LISTS: list[tuple[str, str]] = [
    (
        "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/hosts/pro.txt",
        "HaGeZi Pro  – Beste Balance aus Blockrate & Kompatibilität ★",
    ),
    (
        "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/hosts/tif.txt",
        "HaGeZi Threat Intelligence Feeds  – Malware/Phishing",
    ),
    (
        "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
        "StevenBlack  – Ads, Malware, Tracking (kombiniert)",
    ),
    (
        "https://raw.githubusercontent.com/crazy-max/WindowsSpyBlocker/master/data/hosts/spy.txt",
        "WindowsSpyBlocker  – Windows 11 Telemetrie & Spionage",
    ),
    (
        "https://raw.githubusercontent.com/nicehash/NiceHash-Hosts/main/hosts",
        "NiceHash  – Crypto-Miner-Blocker",
    ),
    (
        "https://adguardteam.github.io/HostlistsRegistry/assets/filter_2.txt",
        "AdGuard DNS-Filter  – Werbung & Tracker",
    ),
]

# ── sqlite3 helpers for adlist management (pihole adlist CLI removed in v6) ──

_GRAVITY_DB = Path("/etc/pihole/gravity.db")

def _adlist_db_query(sql: str, params: tuple = ()) -> list[tuple]:
    """Run a read-only SQL query against gravity.db; returns rows or []."""
    # Try without sudo first; fall back to subprocess sqlite3 with sudo
    import sqlite3 as _sq3
    try:
        with _sq3.connect(str(_GRAVITY_DB)) as conn:
            conn.row_factory = _sq3.Row
            return [tuple(r) for r in conn.execute(sql, params).fetchall()]
    except (_sq3.OperationalError, PermissionError):
        # No direct access → use sqlite3 CLI via sudo
        raw = run(
            ["sqlite3", str(_GRAVITY_DB), sql],
            capture=True, sudo=True, check=False,
        ) or ""
        # Parse pipe-separated output
        rows: list[tuple] = []
        for line in raw.splitlines():
            if "|" in line:
                rows.append(tuple(line.split("|")))
            elif line.strip():
                rows.append((line.strip(),))
        return rows

def _adlist_db_write(sql: str, params: tuple = ()) -> bool:
    """Execute a write SQL statement against gravity.db; returns True on success."""
    import sqlite3 as _sq3
    try:
        with _sq3.connect(str(_GRAVITY_DB)) as conn:
            conn.execute(sql, params)
            conn.commit()
            return True
    except (_sq3.OperationalError, PermissionError):
        # Fall back to sqlite3 CLI with sudo
        # Embed params safely via Python f-string (params already validated upstream)
        stmt = sql
        for p in params:
            stmt = stmt.replace("?", f"'{str(p).replace(chr(39), chr(39)*2)}'", 1)
        result = run(
            ["sqlite3", str(_GRAVITY_DB), stmt],
            capture=True, sudo=True, check=False,
        )
        return result is not None


def menu_adlists() -> None:
    while True:
        clear()
        header("Adlist-Verwaltung", "📋")
        print(f"""
  {col(C.CYAN, '1')}  Adlist hinzufügen (URL)
  {col(C.CYAN, '2')}  Adlist entfernen
  {col(C.CYAN, '3')}  Alle Adlists anzeigen
  {col(C.CYAN, '4')}  Empfohlene Listen ⭐

  {col(C.GRAY, '0')}  Zurück
""")
        match ask("Auswahl"):
            case "0" | "": return
            case "1": _adlist_add()
            case "2": _adlist_remove()
            case "3": _adlist_list()
            case "4": _adlist_recommended()

def _adlist_add(url: str = "", comment: str = "") -> None:
    # pihole adlist add/remove was removed in v6 – use gravity.db directly
    if not url:
        clear()
        header("Adlist hinzufügen", "➕")
        tip("Nach dem Hinzufügen Gravity aktualisieren (Menü 2)")
        url = ask("Adlist-URL (https://...)")
        if not url:
            return
        if not valid_url(url):
            err(f"Ungültige URL: '{url}'")
            press_enter()
            return
        comment = ask("Kommentar (optional)")

    ok_write = _adlist_db_write(
        "INSERT OR IGNORE INTO adlist (address, enabled, comment) VALUES (?, 1, ?)",
        (url, comment),
    )
    if ok_write:
        ok("Adlist hinzugefügt")
        log.info("adlist added: %s", url)
        warn("Gravity-Update erforderlich, damit die Liste aktiv wird!")
        if confirm("Gravity jetzt aktualisieren?", default=True):
            print()
            run(["pihole", "-g"], sudo=True, timeout=600, check=False)
            ok("Gravity aktualisiert")
    else:
        err("Fehler beim Schreiben in gravity.db")
    press_enter()

def _adlist_remove() -> None:
    clear()
    header("Adlist entfernen", "🗑")
    _print_adlist()
    url = ask("URL der zu entfernenden Adlist (exakt)")
    if not url:
        return
    if not confirm(f"Adlist entfernen?\n    {col(C.GRAY, url)}"):
        return
    ok_write = _adlist_db_write("DELETE FROM adlist WHERE address = ?", (url,))
    if ok_write:
        ok("Adlist entfernt")
        warn("Gravity-Update empfohlen, damit Einträge sofort entfernt werden")
    else:
        err("Fehler beim Schreiben in gravity.db")
    press_enter()

def _print_adlist() -> None:
    rows = _adlist_db_query(
        "SELECT address, enabled, comment FROM adlist ORDER BY address"
    )
    if not rows:
        info("Keine Adlists konfiguriert")
        return
    print(f"\n  {col(C.BOLD, str(len(rows)) + ' Adlists:')}\n")
    for row in rows:
        address = str(row[0]) if row else "?"
        enabled = bool(int(row[1])) if len(row) > 1 else True
        comment = str(row[2]) if len(row) > 2 and row[2] else ""
        dot = col(C.GREEN, "●") if enabled else col(C.RED, "●")
        cmt = f"  {col(C.GRAY, comment)}" if comment else ""
        print(f"  {dot} {address}{cmt}")
    print()

def _adlist_list() -> None:
    clear()
    header("Adlists", "📋")
    _print_adlist()
    press_enter()

def _adlist_recommended() -> None:
    clear()
    header("Empfohlene Adlists", "⭐")
    print()
    for i, (url, desc) in enumerate(_RECOMMENDED_LISTS, 1):
        print(f"  {col(C.CYAN, str(i))}  {col(C.BOLD, desc)}")
        print(f"     {col(C.GRAY, url)}")
        print()
    tip("HaGeZi Pro + TIF bieten sehr gute Abdeckung ohne Fehlblockierungen")
    tip("WindowsSpyBlocker ist für Windows-11-Clients im Netzwerk empfehlenswert")

    choice = ask("Nummer hinzufügen (0 = zurück)", "0")
    if choice == "0" or not choice.isdigit():
        return
    idx = int(choice) - 1
    if not (0 <= idx < len(_RECOMMENDED_LISTS)):
        warn("Ungültige Auswahl")
        press_enter()
        return
    url, desc = _RECOMMENDED_LISTS[idx]
    if confirm(f"'{desc}' hinzufügen?", default=True):
        _adlist_add(url=url, comment=desc)

# ══════════════════════════════════════════════════════════════════════════════
# ── MENU: DNS Management ──────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def menu_dns() -> None:
    while True:
        clear()
        header("DNS-Verwaltung", "🔧")
        print(f"""
  {col(C.CYAN, '1')}  DNS neu starten
  {col(C.CYAN, '2')}  DNS-Cache leeren
  {col(C.CYAN, '3')}  PiHole deaktivieren (temporär)
  {col(C.CYAN, '4')}  PiHole aktivieren
  {col(C.CYAN, '5')}  Abfrageprotokoll  (live – Strg+C beendet)

  {col(C.GRAY, '0')}  Zurück
""")
        match ask("Auswahl"):
            case "0" | "": return
            case "1": _dns_restart()
            case "2": _dns_flush()
            case "3": _dns_disable()
            case "4": _dns_enable()
            case "5": _dns_tail()

def _dns_restart() -> None:
    warn("DNS-Neustart unterbricht kurz die Namensauflösung im Netzwerk!")
    if confirm("DNS neu starten?", default=True):
        run(["pihole", "restartdns"], sudo=True, check=False)
        ok("DNS neugestartet")
    press_enter()

def _dns_flush() -> None:
    if confirm("DNS-Cache leeren?", default=True):
        run(["pihole", "reloaddns"], sudo=True, check=False)
        ok("DNS-Cache geleert und Listen neu geladen")
        tip("Clients lösen Domains beim nächsten Aufruf frisch auf")
    press_enter()

def _dns_enable() -> None:
    run(["pihole", "enable"], sudo=True, check=False)
    ok("Pi-hole aktiviert – Blocking ist aktiv")
    press_enter()

def _dns_disable() -> None:
    clear()
    header("Pi-hole deaktivieren", "⏸")
    warn("Während der Deaktivierung werden KEINE Domains geblockt!")
    tip("Immer mit Zeitlimit deaktivieren – nie dauerhaft im Produktivbetrieb!")
    print(f"""
  {col(C.CYAN, '1')}  30 Sekunden
  {col(C.CYAN, '2')}  5 Minuten
  {col(C.CYAN, '3')}  30 Minuten
  {col(C.CYAN, '4')}  ⚠  Dauerhaft (bis zur manuellen Aktivierung)
  {col(C.GRAY, '0')}  Abbrechen
""")
    _dur_map = {"1": ("30s", "30 Sekunden"), "2": ("5m", "5 Minuten"),
                "3": ("30m", "30 Minuten"), "4": ("", "dauerhaft")}
    choice = ask("Auswahl")
    if choice not in _dur_map or choice == "0":
        return
    dur_sec, dur_label = _dur_map[choice]

    if choice == "4":
        warn("Dauerhaftes Deaktivieren ist im Produktivbetrieb NICHT empfohlen!")
        if not confirm("Wirklich dauerhaft deaktivieren?"):
            return

    if not confirm(f"Pi-hole {dur_label} deaktivieren?"):
        return

    cmd = ["pihole", "disable"] + ([dur_sec] if dur_sec else [])
    run(cmd, sudo=True, check=False)
    warn(f"Pi-hole deaktiviert ({dur_label})")
    log.warning("pihole disabled for: %s", dur_label)
    press_enter()

def _dns_tail() -> None:
    clear()
    header("Abfrageprotokoll (live)", "📡")
    print(col(C.GRAY, "  Strg+C zum Beenden...\n"))
    # pihole tail reads /var/log/pihole/pihole.log – may need root
    full = _prepend_sudo(["pihole", "tail"], force_sudo=True)
    try:
        subprocess.run(full, check=False)  # interactive; bypass run() wrapper intentionally
    except KeyboardInterrupt:
        pass
    press_enter()

# ══════════════════════════════════════════════════════════════════════════════
# ── MENU: Diagnose ────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def menu_diagnose() -> None:
    while True:
        clear()
        header("Diagnose & Tools", "🩺")
        print(f"""
  {col(C.CYAN, '1')}  Domain-Lookup (Blocktest)
  {col(C.CYAN, '2')}  FTL-Dienststatus
  {col(C.CYAN, '3')}  Log-Dateien anzeigen
  {col(C.CYAN, '4')}  Diagnose-Report erstellen (pihole debug)
  {col(C.CYAN, '5')}  Datenbankgröße prüfen

  {col(C.GRAY, '0')}  Zurück
""")
        match ask("Auswahl"):
            case "0" | "": return
            case "1": _dns_lookup()
            case "2": _ftl_status()
            case "3": _show_logs()
            case "4": _debug_report()
            case "5": _db_sizes()

def _dns_lookup() -> None:
    clear()
    header("Domain-Lookup / Blocktest", "🔍")
    tip("Prüft ob eine Domain von Pi-hole geblockt wird (NXDOMAIN / 0.0.0.0)")
    domain = ask("Domain testen")
    if not domain:
        return

    tool = shutil.which("dig") or shutil.which("nslookup")
    if not tool:
        err("Weder 'dig' noch 'nslookup' gefunden – bitte dnsutils installieren")
        press_enter()
        return

    if "dig" in tool:
        raw = run([tool, domain, "@127.0.0.1", "+short"], capture=True, sudo=False, check=False)
    else:
        raw = run([tool, domain, "127.0.0.1"], capture=True, sudo=False, check=False)

    print(f"\n  {col(C.BOLD, 'Ergebnis:')}\n")
    if raw:
        for line in raw.splitlines():
            if any(x in line for x in ("0.0.0.0", "NXDOMAIN", "::")):
                print(f"  {col(C.RED, '●')} {line}  {col(C.RED, '← wahrscheinlich geblockt')}")
            else:
                print(f"  {col(C.GREEN, '●')} {line}")
    else:
        warn("Keine Antwort – Pi-hole oder DNS nicht erreichbar?")
    press_enter()

def _ftl_status() -> None:
    clear()
    header("FTL-Dienststatus", "⚙")
    raw = run(
        ["systemctl", "status", "pihole-FTL", "--no-pager", "-l"],
        capture=True, sudo=False, check=False,
    )
    print(f"\n{col(C.GRAY, raw or '(kein Ergebnis)')}")
    press_enter()

def _show_logs() -> None:
    clear()
    header("Log-Dateien", "📋")
    candidates = [
        Path("/var/log/pihole/pihole.log"),
        Path("/var/log/pihole/FTL.log"),
        Path("/var/log/pihole/webserver.log"),
    ]
    print()
    available: list[Path] = []
    for i, p in enumerate(candidates, 1):
        try:
            sz = f"{p.stat().st_size // 1024} KB" if p.exists() else None
            if sz:
                print(f"  {col(C.CYAN, str(i))}  {p.name:30s} {col(C.GRAY, sz)}")
                available.append(p)
            else:
                print(f"  {col(C.GRAY, str(i))}  {p.name:30s} {col(C.RED, 'nicht gefunden')}")
        except PermissionError:
            print(f"  {col(C.YELLOW, str(i))}  {p.name:30s} {col(C.YELLOW, 'kein Leserecht')}")

    if not available:
        warn("Keine Log-Dateien gefunden")
        press_enter()
        return

    choice = ask("Log-Nr. öffnen", "1")
    if not choice.isdigit() or not (1 <= int(choice) <= len(available)):
        return
    lines = ask("Letzte N Zeilen", "100")
    n = lines if lines.isdigit() else "100"
    raw = run(["tail", "-n", n, str(available[int(choice) - 1])], capture=True, sudo=True, check=False)
    if raw:
        print(f"\n{col(C.GRAY, raw)}")
    press_enter()

def _debug_report() -> None:
    clear()
    header("Diagnose-Report", "📝")
    warn("Der Report enthält Systeminfos, DNS-Logs und Konfigurationsdaten!")
    tip("Bericht wird auf den Pi-hole Diagnoseserver hochgeladen – URL erscheint danach")
    if not confirm("Diagnose-Report erstellen?"):
        return
    print()
    raw = run(["pihole", "debug"], sudo=True, capture=True, timeout=120)
    if raw:
        for line in raw.splitlines():
            if line.strip().startswith("http"):
                print(f"\n  {col(C.BOLD, 'Report-URL:')} {col(C.CYAN, line.strip())}")
    ok("Report erstellt")
    press_enter()

def _db_sizes() -> None:
    clear()
    header("Datenbankgröße", "💾")
    paths = [
        Path("/etc/pihole/gravity.db"),
        Path("/etc/pihole/pihole-FTL.db"),
        Path("/etc/pihole/pihole.toml"),
    ]
    print()
    total = 0
    for p in paths:
        try:
            sz = p.stat().st_size
            total += sz
            mb = sz / 1_048_576
            clr = C.RED if mb > 100 else (C.YELLOW if mb > 50 else C.GREEN)
            print(f"  {col(clr, '●')} {p.name:28s} {col(C.BOLD, f'{mb:7.2f} MB')}")
        except FileNotFoundError:
            print(f"  {col(C.GRAY, '·')} {p.name:28s} {col(C.GRAY, '(nicht gefunden)')}")
        except PermissionError:
            print(f"  {col(C.YELLOW, '!')} {p.name:28s} {col(C.YELLOW, 'kein Leserecht')}")
    divider()
    total_mb = total / 1_048_576
    print(f"  {'Gesamt':28s} {col(C.BOLD, f'{total_mb:7.2f} MB')}")
    if total_mb > 500:
        warn(f"Datenbank sehr groß ({total_mb:.0f} MB) – Wartung empfohlen")
        tip("pihole-FTL unterstützt VACUUM zur DB-Komprimierung")
    press_enter()

# ══════════════════════════════════════════════════════════════════════════════
# ── MENU: Update ──────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def menu_update() -> None:
    clear()
    header("Pi-hole aktualisieren", "⬆")
    info("Prüfe auf verfügbare Updates...")
    raw = run(["pihole", "-up", "--check-only"], capture=True, sudo=False, check=False) or ""
    if raw:
        print(f"\n{col(C.GRAY, raw)}\n")

    warn("Während des Updates ist Pi-hole kurz nicht verfügbar!")
    tip("Empfohlen: Update außerhalb der Hauptnutzungszeiten durchführen")

    if not confirm("Pi-hole jetzt aktualisieren?"):
        press_enter()
        return

    clear()
    header("Update wird durchgeführt...", "⬆")
    log.info("pihole update started")
    run(["pihole", "-up"], sudo=True, timeout=600, check=False)
    ok("Update abgeschlossen")
    log.info("pihole update finished")
    press_enter()

# ══════════════════════════════════════════════════════════════════════════════
# ── Main menu + entry point ───────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

_BANNER = r"""
  ██████╗ ██╗      ██╗  ██╗ ██████╗ ██╗     ███████╗
  ██╔══██╗██║      ██║  ██║██╔═══██╗██║     ██╔════╝
  ██████╔╝██║█████╗███████║██║   ██║██║     █████╗
  ██╔═══╝ ██║╚════╝██╔══██║██║   ██║██║     ██╔══╝
  ██║     ██║      ██║  ██║╚██████╔╝███████╗███████╗
  ╚═╝     ╚═╝      ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝"""

def _banner_print(ph: PiHoleInfo) -> None:
    clear()
    print(col(C.BLUE + C.BOLD, _BANNER))
    status_clr = C.GREEN if ph.installed else C.RED
    user = os.environ.get("USER", os.environ.get("LOGNAME", "?"))
    root_hint = col(C.ORANGE, " [root]") if _is_root() else ""
    print(f"\n  {col(C.GRAY, 'Version:')} {col(status_clr, ph.version)}  "
          f"{col(C.GRAY, 'FTL:')} {col(status_clr, ph.ftl_version)}  "
          f"{col(C.GRAY, 'User:')} {col(C.CYAN, user)}{root_hint}")
    print(col(C.BLUE, "  " + "─" * (TERM_W - 2)))

_MENU_ITEMS: list[tuple[str, str, str]] = [
    ("1", "📊", "Status & Informationen"),
    ("2", "🔄", "Gravity-Verwaltung"),
    ("3", "🌐", "Domain-Verwaltung  (Allow / Deny)"),
    ("4", "🔍", "Regex-Filter"),
    ("5", "📋", "Adlist-Verwaltung"),
    ("6", "🔧", "DNS-Verwaltung"),
    ("7", "🩺", "Diagnose & Tools"),
    ("8", "⬆ ", "Pi-hole aktualisieren"),
]

def main_loop(ph: PiHoleInfo) -> None:
    # Dispatch without lambdas – menu_status(ph) handled separately
    dispatch: dict[str, object] = {
        "2": menu_gravity, "3": menu_domains, "4": menu_regex,
        "5": menu_adlists, "6": menu_dns, "7": menu_diagnose,
        "8": menu_update,
    }
    while True:
        _banner_print(ph)
        print(f"\n  {col(C.BOLD + C.WHITE, 'Hauptmenü')}\n")
        for key, icon, label in _MENU_ITEMS:
            print(f"  {col(C.CYAN, key)}  {icon}  {label}")
        print(f"\n  {col(C.GRAY, '0')}  🚪 Beenden")

        if not ph.installed:
            warn("Pi-hole wurde nicht gefunden! Bitte Installation prüfen.")

        choice = ask("\nAuswahl")

        if choice in ("0", "q", "exit", "quit"):
            print(f"\n  {col(C.GRAY, 'Auf Wiedersehen!')} 👋\n")
            log.info("exiting normally")
            break
        try:
            if choice == "1":
                menu_status(ph)
            elif choice in dispatch:
                dispatch[choice]()  # type: ignore[operator]
            elif choice:
                warn(f"Ungültige Auswahl: '{choice}'")
        except KeyboardInterrupt:
            print(f"\n  {col(C.YELLOW, 'Abgebrochen (Strg+C)')}")


def main() -> int:
    _setup_logging()
    log.info("pihole_mgmt started  pid=%d user=%s",
             os.getpid(), os.environ.get("USER", "?"))

    if not shutil.which("pihole"):
        print(col(C.RED, "\n  FEHLER: 'pihole' nicht im PATH gefunden!"))
        print(col(C.YELLOW, "  Installation: https://install.pi-hole.net\n"))
        return 1

    try:
        ph = get_pihole_info()
        main_loop(ph)
    except KeyboardInterrupt:
        print(f"\n  {col(C.YELLOW, 'Abgebrochen.')}\n")
        log.info("interrupted by user")
    except Exception as exc:
        err(f"Unerwarteter Fehler: {exc}")
        log.exception("unhandled exception")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
