#!/usr/bin/env python
import os
import subprocess

# Define the working directory for the ISO build
WORK_DIR = os.path.expanduser("~/build")
ISO_NAME = "custom-manjaro.iso"

def create_working_directory():
    if not os.path.exists(WORK_DIR):
        os.makedirs(WORK_DIR)
    print(f"Working directory created at: {WORK_DIR}")

def clone_manjaro_iso():
    # Clone the Manjaro ISO build scripts
    print("Cloning Manjaro ISO build scripts...")
    subprocess.run(["git", "clone", "https://gitlab.manjaro.org/manjaro/iso.git", WORK_DIR], check=True)

def build_iso():
    # Change to the working directory
    os.chdir(WORK_DIR)
    
    # Run the build command
    print("Building the ISO...")
    subprocess.run(["pkexec", "buildiso", "-p", "xfce", "-o", ISO_NAME], check=True)

def main():
    create_working_directory()
    clone_manjaro_iso()
    build_iso()
    print(f"ISO created successfully: {ISO_NAME}")

if __name__ == "__main__":
    main()