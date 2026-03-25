#!/usr/bin/env python3
# video_player.py
# Simple terminal menu video player for Linux
# Supports: mp4, mkv, webm
# Uses ffplay (ffmpeg) for playback; PipeWire should be active for audio routing.
# Menu color: orange
# New: Option "p" to pick a path (file or directory)

import os
import subprocess
import sys
from pathlib import Path

ORANGE = "\033[38;5;208m"
RESET = "\033[0m"
BOLD = "\033[1m"

SUPPORTED_EXT = {".mp4", ".mkv", ".webm"}

def clear():
    os.system("clear" if os.name == "posix" else "cls")

def find_videos(directory: Path):
    if not directory.is_dir():
        return []
    files = [p for p in directory.iterdir() if p.suffix.lower() in SUPPORTED_EXT and p.is_file()]
    files.sort()
    return files

def print_menu(videos, cwd):
    clear()
    print(f"{ORANGE}{BOLD}Simple Video Player (ffplay + PipeWire) {RESET}")
    print()
    print(f"Current directory: {cwd}")
    print()
    if not videos:
        print("No supported video files found in current directory.")
        print()
    else:
        print("Available videos:")
        for i, v in enumerate(videos, start=1):
            print(f"  {ORANGE}{i:2d}{RESET}. {v.name}")
        print()
    print("Controls:")
    print("  Enter number to play")
    print("  (p) Pick path (file or directory)")
    print("  (s) Stream URL")
    print("  (r) Refresh list  (q) Quit")
    print()

def run_ffplay(target: str):
    args = ["ffplay", "-autoexit", "-loglevel", "warning", target]
    try:
        subprocess.run(args)
    except FileNotFoundError:
        print("ffplay not found. Install ffmpeg (provides ffplay).")
        input("Press Enter to continue...")

def handle_pick_path():
    inp = input("Enter file or directory path: ").strip()
    if not inp:
        return None, None
    p = Path(inp).expanduser()
    if not p.exists():
        print("Path does not exist.")
        input("Press Enter to continue...")
        return None, None
    if p.is_dir():
        return p, "dir"
    if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
        return p, "file"
    print("Unsupported file type.")
    input("Press Enter to continue...")
    return None, None

def stream_url(url: str):
    run_ffplay(url)

def main():
    cwd = Path.cwd()
    videos = find_videos(cwd)

    while True:
        print_menu(videos, cwd)
        choice = input(f"{ORANGE}Choice:{RESET} ").strip()
        if choice == "":
            continue
        if choice.lower() == "q":
            break
        if choice.lower() == "r":
            videos = find_videos(cwd)
            continue
        if choice.lower() == "s":
            url = input("Enter stream URL: ").strip()
            if url:
                stream_url(url)
            continue
        if choice.lower() == "p":
            path, kind = handle_pick_path()
            if path is None:
                continue
            if kind == "dir":
                cwd = path
                videos = find_videos(cwd)
                continue
            if kind == "file":
                print(f"Playing file: {path}")
                run_ffplay(str(path))
                continue
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(videos):
                print(f"Playing: {videos[idx].name}")
                run_ffplay(str(videos[idx]))
            else:
                print("Invalid selection.")
                input("Press Enter to continue...")
            continue
        # treat input as path attempt
        p = Path(choice).expanduser()
        if p.exists() and p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
            run_ffplay(str(p))
            continue

        print("Unknown option.")
        input("Press Enter to continue...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
