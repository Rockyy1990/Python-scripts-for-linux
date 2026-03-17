#!/usr/bin/env python

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

# Konfiguration
HOME = Path.home()
COOKIES_FILE = HOME / ".config" / "yt-dlp" / "cookies.txt"
DOWNLOAD_DIR = HOME / "Downloads" / "yt-dlp"

# Verzeichnisse erstellen
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)

# Menü anzeigen
def show_menu():
    print("\n" + "="*40)
    print("yt-dlp Download Manager".center(40))
    print("="*40)
    print("1) Audio (High-Res AAC)")
    print("2) Video (Best Quality)")
    print("3) Audio + Video (Best Quality)")
    print("4) Playlist (Audio AAC)")
    print("5) Playlist (Video Best)")
    print("6) Cookies aus Browser importieren")
    print("7) Download-Verzeichnis öffnen")
    print("8) Beenden")
    print("="*40)

# Eingabe der URL
def get_url():
    url = input("URL eingeben: ").strip()
    if not url:
        print("Fehler: URL ist erforderlich")
        return None
    return url

# Cookies-Optionen
def get_cookie_option():
    if COOKIES_FILE.exists():
        return ["--cookies", str(COOKIES_FILE)]
    else:
        return []

# yt-dlp Befehl ausführen
def run_yt_dlp(args):
    command = ["yt-dlp"] + get_cookie_option() + args
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        print("Fehler bei der Ausführung von yt-dlp.")

# Download Funktionen
def download_audio():
    url = get_url()
    if not url:
        return
    print("Downloade Audio...")
    args = [
        "--extract-audio",
        "--audio-format", "aac",
        "--audio-quality", "0",
        "-o", str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
        url
    ]
    run_yt_dlp(args)
    print("✓ Download abgeschlossen")
    input("Weiter mit Enter...")

def download_video():
    url = get_url()
    if not url:
        return
    print("Downloade Video in bester Qualität...")
    args = [
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
        url
    ]
    run_yt_dlp(args)
    print("✓ Download abgeschlossen")
    input("Weiter mit Enter...")

def download_audio_video():
    url = get_url()
    if not url:
        return
    print("Downloade Audio + Video...")
    args = [
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
        url
    ]
    run_yt_dlp(args)
    print("✓ Download abgeschlossen")
    input("Weiter mit Enter...")

def download_playlist_audio():
    url = get_url()
    if not url:
        return
    print("Downloade Playlist (Audio)...")
    args = [
        "--extract-audio",
        "--audio-format", "aac",
        "--audio-quality", "0",
        "-o", str(DOWNLOAD_DIR / "%(playlist)s" / "%(playlist_index)s - %(title)s.%(ext)s"),
        url
    ]
    run_yt_dlp(args)
    print("✓ Download abgeschlossen")
    input("Weiter mit Enter...")

def download_playlist_video():
    url = get_url()
    if not url:
        return
    print("Downloade Playlist (Video)...")
    args = [
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", str(DOWNLOAD_DIR / "%(playlist)s" / "%(playlist_index)s - %(title)s.%(ext)s"),
        url
    ]
    run_yt_dlp(args)
    print("✓ Download abgeschlossen")
    input("Weiter mit Enter...")

# Cookies importieren
def import_cookies():
    print("Browser auswählen:")
    print("1) Firefox")
    print("2) Vivaldi")
    print("3) Abbrechen")
    choice = input("Wahl (1-3): ").strip()
    if choice == "1":
        print("Importiere Cookies von Firefox...")
        cmd = ["yt-dlp", "--cookies-from-browser", "firefox", "--cookies", str(COOKIES_FILE), "https://www.youtube.com"]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✓ Cookies erfolgreich importiert")
        except subprocess.CalledProcessError:
            print("Fehler beim Importieren von Firefox-Cookies")
    elif choice == "2":
        print("Importiere Cookies von Chrome...")
        cmd = ["yt-dlp", "--cookies-from-browser", "vivaldi", "--cookies", str(COOKIES_FILE), "https://www.youtube.com"]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✓ Cookies erfolgreich importiert")
        except subprocess.CalledProcessError:
            print("Fehler beim Importieren von Vivaldi-Browser-Cookies")
    elif choice == "3":
        return
    else:
        print("Ungültige Wahl")
    input("Weiter mit Enter...")

# Hauptschleife
def main():
    while True:
        os.system("clear" if os.name == "posix" else "cls")
        show_menu()
        choice = input("Wähle eine Option (1-8): ").strip()
        if choice == "1":
            download_audio()
        elif choice == "2":
            download_video()
        elif choice == "3":
            download_audio_video()
        elif choice == "4":
            download_playlist_audio()
        elif choice == "5":
            download_playlist_video()
        elif choice == "6":
            import_cookies()
        elif choice == "7":
            try:
                # Versucht, das Verzeichnis im Explorer zu öffnen
                if sys.platform.startswith('darwin'):
                    subprocess.run(["open", str(DOWNLOAD_DIR)])
                elif os.name == 'nt':
                    os.startfile(str(DOWNLOAD_DIR))
                else:
                    subprocess.run(["xdg-open", str(DOWNLOAD_DIR)])
            except Exception:
                print(f"Öffne: {DOWNLOAD_DIR}")
            input("Weiter mit Enter...")
        elif choice == "8":
            print("Auf Wiedersehen!")
            break
        else:
            print("Ungültige Wahl")
            input("Weiter mit Enter...")

if __name__ == "__main__":
    main()
