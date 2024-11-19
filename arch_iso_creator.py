#!/usr/bin/env python
import os
import subprocess

# Define the packages to include in the ISO
packages = [
    'linux',              # Linux kernel
    'linux-firmware',     # Firmware for hardware
    'base',               # Base system
    'base-devel',         # Development tools
    'grub',               # Bootloader
    'networkmanager',     # Network management
    'dhcpcd',             # DHCP client
    'xfce4',              # XFCE desktop environment
    'xorg-server',        # X server
    'chromium',           # Web browser
    'thunderbird',        # Email client
    'pipewire',           # Multimedia framework
    'pavucontrol',        # Volume control for PulseAudio
    'git',                # Version control
    'vim',                # Text editor
    'man-db',             # Man pages
    'man-pages',          # Man pages
]

# Define the ISO name and output directory
iso_name = "custom-archlinux.iso"
output_dir = "archlinux-iso"

# Create the output directory
os.makedirs(output_dir, exist_ok=True)

# Create the working directory for archiso
working_dir = os.path.join(output_dir, "work")
os.makedirs(working_dir, exist_ok=True)

# Create the profile directory
profile_dir = os.path.join(output_dir, "airootfs")
os.makedirs(profile_dir, exist_ok=True)

# Create necessary directories in airootfs
os.makedirs(os.path.join(profile_dir, "etc"), exist_ok=True)

# Create a basic pacman.conf for the ISO
pacman_conf = """
[options]
SigLevel = Never
Include = /etc/pacman.d/mirrorlist
"""

with open(os.path.join(profile_dir, "etc", "pacman.conf"), "w") as f:
    f.write(pacman_conf)

# Install the required packages in the airootfs
try:
    subprocess.run(["pacstrap", "-c", profile_dir] + packages, check=True)
except subprocess.CalledProcessError as e:
    print(f"Error during pacstrap: {e}")
    exit(1)

# Copy the necessary files for archiso
try:
    subprocess.run(["cp", "-r", "/usr/share/archiso/configs/releng", output_dir], check=True)
except subprocess.CalledProcessError as e:
    print(f"Error copying archiso files: {e}")
    exit(1)

# Modify the profile's packages.x86_64 file to include our packages
packages_file = os.path.join(output_dir, "releng", "packages.x86_64")

with open(packages_file, "a") as f:
    for package in packages:
        f.write(package + "\n")

# Build the ISO
try:
    subprocess.run(["mkarchiso", "-v", "-w", working_dir, "-o", output_dir, os.path.join(output_dir, "releng")], check=True)
except subprocess.CalledProcessError as e:
    print(f"Error during mkarchiso: {e}")
    exit(1)

# Move the ISO to the output directory
iso_path = os.path.join(output_dir, "releng", iso_name)
final_iso_path = os.path.join(output_dir, iso_name)

if os.path.exists(iso_path):
    os.rename(iso_path, final_iso_path)

print(f"Custom Arch Linux ISO created: {final_iso_path}")