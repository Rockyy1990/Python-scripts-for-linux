#!/usr/bin/env python3

import shlex
import subprocess
import sys
import os
import shutil

ORANGE = "\033[38;5;208m"
RESET = "\033[0m"

# audio: resample async, downmix to stereo, loudnorm (if available)
PAN_STEREO = "pan=stereo|c0=0.5*c0+0.5*c2|c1=0.5*c1+0.5*c3"
AUDIO_FILTER = f"aresample=async=1,{PAN_STEREO},loudnorm=I=-16:LRA=7:TP=-1.5"
FPS_MODE = "passthrough"

def ffmpeg_supports_filter(filter_name):
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return filter_name in out.stdout
    except Exception:
        return False

def print_menu():
    print(ORANGE + "\nffmpeg Video Converter Menü\n" + RESET)
    print("1) x264 (crf 20, preset medium, level 4, aac 224 kbps, stereo, loudnorm)")
    print("2) x265 (vergleichbare qualität, crf 23, aac 224 kbps, stereo, loudnorm)")
    print("3) x264 VBR (target 2500k, maxrate 5000k, bufsize 10000k, aac 224 kbps, stereo, loudnorm)")
    print("4) x265 VBR (target 2500k, maxrate 5000k, bufsize 10000k, aac 224 kbps, stereo, loudnorm)")
    print("5) beenden\n")

def normalize_input_path(p):
    if not p:
        return ""
    p = p.strip()
    # remove surrounding quotes if present
    if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
        p = p[1:-1]
    # expand ~ and environment variables
    p = os.path.expanduser(os.path.expandvars(p))
    return p

def ask_input_paths():
    print("Gib Pfade ein. Du kannst Anführungszeichen verwenden; Escapes und Sonderzeichen werden unterstützt.")
    raw_src = input("Quelldatei:\n> ")
    raw_dest = input("Zieldatei:\n> ")
    src = normalize_input_path(raw_src)
    dest = normalize_input_path(raw_dest)
    if not src or not dest:
        print("Ungültige Eingabe.")
        return None, None
    # If src contains a glob/wildcard, expand
    if any(c in src for c in "*?[]"):
        matches = list(sorted(glob.glob(src)))
        if len(matches) == 1:
            src = matches[0]
        elif len(matches) == 0:
            print("Kein Treffer für Quelldatei-Pattern.")
            return None, None
        else:
            print("Mehrere Treffer für Quelldatei-Pattern; bitte genaue Datei angeben.")
            return None, None
    if not os.path.isfile(src):
        print(f"Quelldatei nicht gefunden: {src}")
        return None, None
    return src, dest

def run_ffmpeg(cmd_args):
    try:
        print("\nStarte ffmpeg:\n", " ".join(shlex.quote(a) for a in cmd_args), "\n")
        proc = subprocess.Popen(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            print(line, end="")
        proc.wait()
        if proc.returncode == 0:
            print("\nKonvertierung erfolgreich.")
        else:
            print(f"\nffmpeg beendet mit Fehlercode {proc.returncode}.")
    except FileNotFoundError:
        print("ffmpeg nicht gefunden. Bitte installieren und im PATH verfügbar machen.")
    except Exception as e:
        print("Fehler:", e)

def ensure_dir_for_file(path):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            print("Kann Zielverzeichnis nicht erstellen:", e)

def base_audio_args():
    # verify loudnorm support; if not present, remove it from filter
    af = AUDIO_FILTER
    if not ffmpeg_supports_filter("loudnorm"):
        af = f"aresample=async=1,{PAN_STEREO}"
    return ["-c:a", "aac", "-b:a", "224k", "-af", af]

def convert_x264(src, dest):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-level", "4.0",
    ] + base_audio_args() + [
        "-map_metadata", "0",
        "-fps_mode", FPS_MODE,
        dest
    ]
    run_ffmpeg(cmd)

def convert_x265(src, dest):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx265", "-preset", "medium", "-crf", "23",
    ] + base_audio_args() + [
        "-map_metadata", "0",
        "-fps_mode", FPS_MODE,
        dest
    ]
    run_ffmpeg(cmd)

def convert_x264_vbr(src, dest, target_bitrate="2500k", maxrate="5000k", bufsize="10000k"):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", target_bitrate, "-maxrate", maxrate, "-bufsize", bufsize,
    ] + base_audio_args() + [
        "-map_metadata", "0",
        "-fps_mode", FPS_MODE,
        dest
    ]
    run_ffmpeg(cmd)

def convert_x265_vbr(src, dest, target_bitrate="2500k", maxrate="5000k", bufsize="10000k"):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-c:v", "libx265", "-preset", "medium",
        "-b:v", target_bitrate, "-maxrate", maxrate, "-bufsize", bufsize,
    ] + base_audio_args() + [
        "-map_metadata", "0",
        "-fps_mode", FPS_MODE,
        dest
    ]
    run_ffmpeg(cmd)

def main():
    # quick ffmpeg check
    if not shutil.which("ffmpeg"):
        print("ffmpeg nicht gefunden. Bitte installieren und im PATH verfügbar machen.")
        sys.exit(1)

    import glob  # lokal import für ask_input_paths
    while True:
        print_menu()
        choice = input("Wähle Option (1-5): ").strip()
        if choice in ("1","2","3","4"):
            src_dest = ask_input_paths()
            if not src_dest or src_dest == (None, None):
                input("\nDrücke Enter, um zum Menü zurückzukehren...")
                continue
            src, dest = src_dest
            ensure_dir_for_file(dest)
            if choice == "1":
                convert_x264(src, dest)
            elif choice == "2":
                convert_x265(src, dest)
            elif choice == "3":
                convert_x264_vbr(src, dest)
            elif choice == "4":
                convert_x265_vbr(src, dest)
            input("\nDrücke Enter, um zum Menü zurückzukehren...")
        elif choice == "5":
            print("Beende.")
            sys.exit(0)
        else:
            print("Ungültige Auswahl.")

if __name__ == "__main__":
    main()
