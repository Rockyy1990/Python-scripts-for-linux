#!/usr/bin/env python
import os
import subprocess
import sys
import shutil

# Define constants
ISO_NAME = "custom-archlinux.iso"
OUTPUT_DIR = "archlinux-iso"
WORKING_DIR = os.path.join(OUTPUT_DIR, "work")
PROFILE_DIR = os.path.join(OUTPUT_DIR, "airootfs")
PACKAGES_FILE = os.path.join(OUTPUT_DIR, "releng", "packages.x86_64")

# Check if pacstrap is available
if subprocess.call(["which", "pacstrap"], stdout=subprocess.PIPE, stderr=subprocess.PIPE) != 0:
    print("Error: 'pacstrap' command not found. Please ensure it is installed and in your PATH.")
    sys.exit(1)

# Define the packages to include in the ISO
packages = [
    'linux-zen',
    'linux-firmware',
    'base',
    'base-devel',
    'archinstall',
    'grub',
    'networkmanager',
    'dhcpcd',
    'xfce4',
    'xorg-server',
    'xorg-xinit',
    'xterm',
    'lightdm',
    'lightdm-gtk-greeter',
    'chromium',
    'thunderbird',
    'pipewire',
    'pavucontrol',
    'alsa-firmware',
    'nano',
    'gnome-disk-utility',
    'mesa',
    'xf86-video-amdgpu',
    'vulkan-radeon',
    'gtk3',
    'gtk2',
    'fontconfig',
    'ttf-dejavu',
    'ttf-liberation',
    'xorg-twm',
    'xorg-xclock',
]

# Create the output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Check if the working directory already exists and clean it if necessary
if os.path.exists(WORKING_DIR):
    print(f"Cleaning existing working directory: {WORKING_DIR}")
    shutil.rmtree(WORKING_DIR)

# Create necessary directories
os.makedirs(WORKING_DIR, exist_ok=True)
os.makedirs(PROFILE_DIR, exist_ok=True)
os.makedirs(os.path.join(PROFILE_DIR, "etc"), exist_ok=True)
os.makedirs(os.path.join(PROFILE_DIR, "etc", "lightdm"), exist_ok=True)
os.makedirs(os.path.join(PROFILE_DIR, "home", "arch"), exist_ok=True)

# Create a basic pacman.conf for the ISO
pacman_conf = """
[options]
SigLevel = Never
Include = /etc/pacman.d/mirrorlist
"""
with open(os.path.join(PROFILE_DIR, "etc", "pacman.conf"), "w") as f:
    f.write(pacman_conf)

# Install the required packages in the airootfs
try:
    print("Installing packages in airootfs...")
    subprocess.run(["pacstrap", "-c", PROFILE_DIR] + packages, check=True)
except subprocess.CalledProcessError as e:
    print(f"Error during pacstrap: {e}")
    sys.exit(1)

# Copy the necessary files for archiso
try:
    print("Copying archiso files...")
    subprocess.run(["cp", "-r", "/usr/share/archiso/configs/releng", OUTPUT_DIR], check=True)
except subprocess.CalledProcessError as e:
    print(f"Error copying archiso files: {e}")
    sys.exit(1)

# Modify the profile's packages.x86_64 file to include our packages
with open(PACKAGES_FILE, "a") as f:
    for package in packages:
        f.write(package + "\n")

# Create a lightdm configuration to start XFCE4
lightdm_conf = """
[Seat:*]
autologin-user=arch
autologin-user-timeout=0
 user-session=xfce
greeter-session=lightdm-gtk-greeter
"""
with open(os.path.join(PROFILE_DIR, "etc", "lightdm", "lightdm.conf"), "w") as f:
    f.write(lightdm_conf)

# Create a .xinitrc file for the default user
xinitrc_content = """
#!/bin/sh
exec startxfce4
"""
with open(os.path.join(PROFILE_DIR, "home", "arch", ".xinitrc"), "w") as f:
    f.write(xinitrc_content)
os.chmod(os.path.join(PROFILE_DIR, "home", "arch", ".xinitrc"), 0o755)

# Create a default user and set password
try:
    print("Creating default user 'arch'...")
    subprocess.run(["useradd", "-m", "-G", "wheel", "arch"], check=True)
    subprocess.run(["echo", "arch:password", "|", "chpasswd"], check=True)
except subprocess.CalledProcessError as e:
    print(f"Error creating user: {e}")
    sys.exit(1)

# Set the default locale and timezone
locale_conf = """
LANG=en_US.UTF-8
"""
with open(os.path.join(PROFILE_DIR, "etc", "locale.conf"), "w") as f:
    f.write(locale_conf)

# Set timezone (example: UTC)
timezone = "UTC"
with open(os.path.join(PROFILE_DIR, "etc", "timezone"), "w") as f:
    f.write(timezone)

# Create a README file for user instructions
readme_content = """
Welcome to Arch XFCE ISO!

To log in, use the following credentials:
Username: arch
Password: password

To start the XFCE desktop environment, you can either:
1. Use LightDM (default) - it will automatically log you in.
2. Use startx command after logging in.

Enjoy your custom Arch Linux experience!
"""
with open(os.path.join(PROFILE_DIR, "README.txt"), "w") as f:
    f.write(readme_content)

# Build the ISO
try:
    print("Building the ISO...")
    subprocess.run(["mkarchiso", "-v", "-w", WORKING_DIR, "-o", OUTPUT_DIR, os.path.join(OUTPUT_DIR, "releng")], check=True)
except subprocess.CalledProcessError as e:
    print(f"Error during mkarchiso: {e}")
    sys.exit(1)

print("ISO build completed successfully!")