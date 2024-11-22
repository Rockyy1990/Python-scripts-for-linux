#!/usr/bin/env python
import subprocess
import os
import sys

def create_bootable_iso(source, target):
    try:
        # Ensure source exists
        if not os.path.exists(source):
            print(f"Source path '{source}' does not exist.")
            return

        # Command to create bootable ISO using dd
        command = ['dd', f'if={source}', f'of={target}', 'bs=4M', 'conv=fdatasync']

        print(f"Creating bootable ISO from {source} to {target}...")
        subprocess.run(command, check=True)
        print("Bootable ISO created successfully.")

    except subprocess.CalledProcessError as e:
        print(f"An error occurred while creating the ISO: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Check for correct number of arguments
    if len(sys.argv) != 3:
        print("Usage: python create_bootable_iso.py <source_device> <target_iso>")
        sys.exit(1)

    source_device = sys.argv[1]  # e.g., /dev/sda
    target_iso = sys.argv[2]      # e.g., /path/to/output.iso

    create_bootable_iso(source_device, target_iso)