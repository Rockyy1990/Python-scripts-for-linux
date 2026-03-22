#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ffmpeg Audio-Konverter Menü (Python)
Unterstützte Codecs: mp3 (VBR ~320 kbps), aac (VBR ~256 kbps), opus (music ~320 kbps), flac (level configurable)
Menütext wird in Orange ausgegeben (ANSI).
Alle Pfade/Optionen können im Abschnitt CONFIG am Anfang angepasst werden.
Nach jeder Konvertierung kehrt das Programm zum Menü zurück.
Benötigt: ffmpeg in PATH, Python 3.7+
"""

import os
import shlex
import subprocess
import sys

# -----------------------
# CONFIG (Anpassbare Pfade & Einstellungen)
# -----------------------
FFMPEG_CMD = "ffmpeg"  # Pfad zu ffmpeg, z.B. "/usr/bin/ffmpeg" oder "C:\\ffmpeg\\bin\\ffmpeg.exe"
INPUT_DIR = "./in"     # Quellverzeichnis (kann Datei oder Ordner sein)
OUTPUT_DIR = "./out"   # Zielverzeichnis (wird erstellt, falls nicht vorhanden)
# Standard-Optionen für Codecs (können hier geändert werden)
MP3_VBR_QUALITY = 0    # LAME VBR quality: 0 = highest bitrate (≈320kbps), 4 = default, 9 = lowest
AAC_CODEC = "aac"      # ffmpeg encoder (native) oder "libfdk_aac" falls vorhanden
AAC_BITRATE = "256k"   # Ziel als obere Richtlinie (ffmpeg native aac ist CBR/VBR hybrid)
OPUS_APPLICATION = "audio"  # "music" would be better for music, keep "audio" or "music"
OPUS_BITRATE = "320k"  # target bitrate (note: Opus typical max ~510kbps; 320k is fine)
FLAC_LEVEL = 5         # 0 (fast) .. 12 (slow) for flac
# -----------------------

# ANSI-Farben (Orange approximiert mit yellow+red blend isn't standard; use bright yellow)
ORANGE = "\033[38;5;208m"  # 256-color orange
RESET = "\033[0m"

SUPPORTED_CODECS = [
    "mp3 (VBR, bis ~320 kbps via LAME quality 0)",
    "aac (VBR/CBR bis ~256 kbps)",
    "opus (music, target 320 kbps)",
    "flac (lossless, einstellbare Level)"
]

def ensure_dirs():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def safe_run(cmd):
    print(">>>", cmd)
    try:
        completed = subprocess.run(cmd, shell=True)
        return completed.returncode == 0
    except Exception as e:
        print("Fehler beim Ausführen von ffmpeg:", e)
        return False

def build_output_path(input_path, ext):
    base = os.path.splitext(os.path.basename(input_path))[0]
    safe_name = base + ext
    return os.path.join(OUTPUT_DIR, safe_name)

def convert_mp3(input_path):
    out = build_output_path(input_path, ".mp3")
    # Use libmp3lame with VBR quality scale (0..9), 0 best
    cmd = f'{shlex.quote(FFMPEG_CMD)} -y -i {shlex.quote(input_path)} -vn -codec:a libmp3lame -qscale:a {MP3_VBR_QUALITY} {shlex.quote(out)}'
    return safe_run(cmd)

def convert_aac(input_path):
    out = build_output_path(input_path, ".m4a")
    # native aac: -c:a aac -b:a 256k ; if libfdk_aac available, prefer it for VBR
    if AAC_CODEC == "libfdk_aac":
        cmd = f'{shlex.quote(FFMPEG_CMD)} -y -i {shlex.quote(input_path)} -vn -c:a libfdk_aac -vbr 4 -b:a {AAC_BITRATE} {shlex.quote(out)}'
    else:
        cmd = f'{shlex.quote(FFMPEG_CMD)} -y -i {shlex.quote(input_path)} -vn -c:a aac -b:a {AAC_BITRATE} {shlex.quote(out)}'
    return safe_run(cmd)

def convert_opus(input_path):
    out = build_output_path(input_path, ".opus")
    # Opus encoder with music application and target bitrate
    cmd = f'{shlex.quote(FFMPEG_CMD)} -y -i {shlex.quote(input_path)} -vn -c:a libopus -b:a {OPUS_BITRATE} -vbr on -application {OPUS_APPLICATION} {shlex.quote(out)}'
    return safe_run(cmd)

def convert_flac(input_path):
    out = build_output_path(input_path, ".flac")
    cmd = f'{shlex.quote(FFMPEG_CMD)} -y -i {shlex.quote(input_path)} -vn -c:a flac -compression_level {FLAC_LEVEL} {shlex.quote(out)}'
    return safe_run(cmd)

def list_input_files():
    # List audio files in INPUT_DIR
    entries = []
    for root, _, files in os.walk(INPUT_DIR):
        for f in files:
            if f.startswith('.'):
                continue
            path = os.path.join(root, f)
            entries.append(path)
    return sorted(entries)

def print_menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(ORANGE + "=== ffmpeg Audio-Konverter Menü ===" + RESET)
    print("Unterstützte Codecs:")
    for c in SUPPORTED_CODECS:
        print(" -", c)
    print()
    print("Konfigurierbare Pfade (anpassbar im Skript):")
    print(" - INPUT_DIR :", INPUT_DIR)
    print(" - OUTPUT_DIR:", OUTPUT_DIR)
    print()
    files = list_input_files()
    if not files:
        print("Keine Dateien im INPUT_DIR gefunden.")
    else:
        print("Gefundene Eingabedateien:")
        for i, f in enumerate(files, 1):
            print(f" {i}. {f}")
    print()
    print("Optionen:")
    print(" 1) Konvertiere Einzeldatei zu MP3 (VBR ~320 kbps)")
    print(" 2) Konvertiere Einzeldatei zu AAC (VBR/CBR ~256 kbps)")
    print(" 3) Konvertiere Einzeldatei zu Opus (music, target 320 kbps)")
    print(" 4) Konvertiere Einzeldatei zu FLAC (lossless)")
    print(" 5) Batch: Alle Dateien im INPUT_DIR zu MP3")
    print(" 6) Batch: Alle Dateien im INPUT_DIR zu AAC")
    print(" 7) Batch: Alle Dateien im INPUT_DIR zu Opus")
    print(" 8) Batch: Alle Dateien im INPUT_DIR zu FLAC")
    print(" 9) Einstellungen anzeigen (CONFIG)")
    print(" 0) Beenden")
    print()

def choose_file():
    files = list_input_files()
    if not files:
        input("Keine Dateien. Lege Dateien in INPUT_DIR und drücke Enter...")
        return None
    for i, f in enumerate(files, 1):
        print(f" {i}) {f}")
    try:
        sel = int(input("Wähle Dateinummer: ").strip())
        if 1 <= sel <= len(files):
            return files[sel-1]
    except Exception:
        pass
    print("Ungültige Auswahl.")
    return None

def show_config():
    print("CONFIG aktuell:")
    print(f" FFMPEG_CMD = {FFMPEG_CMD}")
    print(f" INPUT_DIR  = {INPUT_DIR}")
    print(f" OUTPUT_DIR = {OUTPUT_DIR}")
    print(f" MP3_VBR_QUALITY = {MP3_VBR_QUALITY}")
    print(f" AAC_CODEC = {AAC_CODEC}")
    print(f" AAC_BITRATE = {AAC_BITRATE}")
    print(f" OPUS_APPLICATION = {OPUS_APPLICATION}")
    print(f" OPUS_BITRATE = {OPUS_BITRATE}")
    print(f" FLAC_LEVEL = {FLAC_LEVEL}")
    input("\nDrücke Enter, um zum Menü zurückzukehren...")

def main_loop():
    ensure_dirs()
    while True:
        print_menu()
        choice = input("Wähle Option: ").strip()
        if choice == "0":
            print("Beende.")
            break
        if choice in {"1","2","3","4"}:
            f = choose_file()
            if not f:
                continue
            if choice == "1":
                success = convert_mp3(f)
            elif choice == "2":
                success = convert_aac(f)
            elif choice == "3":
                success = convert_opus(f)
            else:
                success = convert_flac(f)
            print("Erfolg." if success else "Fehler bei der Konvertierung.")
            input("Drücke Enter, um zum Menü zurückzukehren...")
            continue
        if choice in {"5","6","7","8"}:
            files = list_input_files()
            if not files:
                input("Keine Dateien. Lege Dateien in INPUT_DIR und drücke Enter...")
                continue
            for f in files:
                print("\nVerarbeite:", f)
                if choice == "5":
                    convert_mp3(f)
                elif choice == "6":
                    convert_aac(f)
                elif choice == "7":
                    convert_opus(f)
                else:
                    convert_flac(f)
            input("\nBatch abgeschlossen. Drücke Enter, um zum Menü zurückzukehren...")
            continue
        if choice == "9":
            show_config()
            continue
        print("Ungültige Option. Bitte erneut wählen.")

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\nAbbruch durch Benutzer.")
