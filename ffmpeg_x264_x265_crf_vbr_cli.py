#!/usr/bin/env python3
import shlex
import subprocess
import sys
import os

ORANGE = "\033[38;5;208m"
RESET = "\033[0m"

def print_menu():
    print(ORANGE + "\nffmpeg Video Converter Menü\n" + RESET)
    print("1) x264 (crf 20, preset medium, level 4, aac 224 kbps, stereo, loudnorm)")
    print("2) x265 (vergleichbare qualität, crf 28, aac 224 kbps, stereo, loudnorm)")
    print("3) x264 VBR (keine crf, target 2500k, maxrate 5000k, bufsize 10000k, aac 224 kbps, stereo, loudnorm)")
    print("4) x265 VBR (keine crf, target 2500k, maxrate 5000k, bufsize 10000k, aac 224 kbps, stereo, loudnorm)")
    print("5) beenden\n")

def quote_path(path):
    path = path.strip()
    if (path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'")):
        path = path[1:-1]
    return path

def ask_input_paths():
    src = input("Eingabe Quelldatei (Pfad, unterstützt ' oder \"):\n> ").strip()
    dest = input("Eingabe Zieldatei (Pfad, unterstützt ' oder \"):\n> ").strip()
    src = quote_path(src)
    dest = quote_path(dest)
    if not src or not dest:
        print("Ungültiger Pfad.")
        return None, None
    return src, dest

def run_ffmpeg(cmd_args):
    try:
        print("\nStarte ffmpeg...\n")
        print(" ".join(shlex.quote(a) for a in cmd_args))
        proc = subprocess.run(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print(proc.stdout)
        if proc.returncode == 0:
            print("\nKonvertierung erfolgreich.")
        else:
            print(f"\nffmpeg beendet mit Fehlercode {proc.returncode}.")
    except FileNotFoundError:
        print("ffmpeg nicht gefunden. Bitte installieren und im PATH verfügbar machen.")
    except Exception as e:
        print("Fehler:", e)

# gemeinsamer Audio-Filter: resample async, stereo downmix, loudnorm
AUDIO_FILTER = "aresample=async=1,pan=stereo|c0<c0+c2?c0:c0|c1<c1+c3?c1:c1,loudnorm=I=-16:LRA=7:TP=-1.5"

def convert_x264(src, dest):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-level", "4.0",
        "-c:a", "aac", "-b:a", "224k",
        "-af", AUDIO_FILTER,
        "-map_metadata", "0",
        "-vsync", "2",
        dest
    ]
    run_ffmpeg(cmd)

def convert_x265(src, dest):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx265", "-preset", "medium", "-crf", "28",
        "-c:a", "aac", "-b:a", "224k",
        "-af", AUDIO_FILTER,
        "-map_metadata", "0",
        "-vsync", "2",
        dest
    ]
    run_ffmpeg(cmd)

def convert_x264_vbr(src, dest, target_bitrate="2500k", maxrate="5000k", bufsize="10000k"):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", target_bitrate, "-maxrate", maxrate, "-bufsize", bufsize,
        "-c:a", "aac", "-b:a", "224k",
        "-af", AUDIO_FILTER,
        "-map_metadata", "0",
        "-vsync", "2",
        dest
    ]
    run_ffmpeg(cmd)

def convert_x265_vbr(src, dest, target_bitrate="2500k", maxrate="5000k", bufsize="10000k"):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx265", "-preset", "medium",
        "-b:v", target_bitrate, "-maxrate", maxrate, "-bufsize", bufsize,
        "-c:a", "aac", "-b:a", "224k",
        "-af", AUDIO_FILTER,
        "-map_metadata", "0",
        "-vsync", "2",
        dest
    ]
    run_ffmpeg(cmd)

def ensure_dir_for_file(path):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            print("Kann Zielverzeichnis nicht erstellen:", e)

def main():
    while True:
        print_menu()
        choice = input("Wähle Option (1-5): ").strip()
        if choice == "1":
            src, dest = ask_input_paths()
            if not src or not dest:
                continue
            ensure_dir_for_file(dest)
            convert_x264(src, dest)
            input("\nDrücke Enter, um zum Menü zurückzukehren...")
        elif choice == "2":
            src, dest = ask_input_paths()
            if not src or not dest:
                continue
            ensure_dir_for_file(dest)
            convert_x265(src, dest)
            input("\nDrücke Enter, um zum Menü zurückzukehren...")
        elif choice == "3":
            src, dest = ask_input_paths()
            if not src or not dest:
                continue
            ensure_dir_for_file(dest)
            convert_x264_vbr(src, dest)
            input("\nDrücke Enter, um zum Menü zurückzukehren...")
        elif choice == "4":
            src, dest = ask_input_paths()
            if not src or not dest:
                continue
            ensure_dir_for_file(dest)
            convert_x265_vbr(src, dest)
            input("\nDrücke Enter, um zum Menü zurückzukehren...")
        elif choice == "5":
            print("Beende.")
            sys.exit(0)
        else:
            print("Ungültige Auswahl.")

if __name__ == "__main__":
    main()
