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
    'linux',
    'linux-lts',
    'linux-headers',
    'linux-firmware',
    'base',
    'base-devel',
    'arrayfire',
    'asio',
    'fakeroot',
    'amd-ucode',
    'intel-ucode',
    'iucode-tool',
    'git',
    'wget',
    'curl',
    'archinstall',
    'arch-install-scripts',
    'archlinux-keyring',
    'archiso',
    'archlinux-contrib',
    'grub',
    'grub-customizer',
    'networkmanager',
    'fwupd',
    'dhcpcd',
    'xfce4',
    'gvfs',
    'gvfs-smb',
    'gvfs-nfs',
    'xfce4-session',
    'xfce4-terminal',
    'gnome-system-monitor',
    'xfce4-mixer',
    'file-roller',
    'xdg-utils',
    'xdg-desktop-portal',
    'xdg-desktop-portal-gtk',
    'xdg-user-dirs',
    'gsmartcontrol',
    'procps-ng',
    'mousepad',
    'xorg-server',
    'xorg-server-xvfb',
    'xorg-xinit',
    'xorg-xauth',
    'xorg-xinput',
    'xorg-xrandr',
    'xorg-xkill',
    'xorg-twm',
    'libxcomposite',
    'xterm',
    'lightdm',
    'lightdm-gtk-greeter',
    'firefox',
    'firefox-i18n-de',
    'transmission-gtk',
    'soundconverter',
    'gstreamer',
    'gstreamer-vaapi',
    'gst-plugins-base',
    'gst-plugins-ugly',
    'gst-plugins-good',
    'gst-plugins-bad',
    'gst-plugin-mp4',
    'ffmpeg',
    'lame',
    'flac',
    'thunderbird',
    'pipewire',
    'pipewire-zeroconf',
    'pipewire-alsa',
    'pipewire-pulse',
    'alsa-firmware',
    'gst-plugin-pipewire',
    'wireplumber',
    'pavucontrol',
    'python',
    'python-reportlab',
    'tcl',
    'tk',
    'nano',
    'timeshift',
    'deja-dup',
    'fsarchiver',
    'gnome-disk-utility',
    'gparted',
    'mtools',
    'dosfstools',
    'fuse2',
    'fuseiso',
    'xfsdump',
    'jfsutils',
    'btrfs-progs',
    'exfatprogs',
    'f2fs-tools',
    'ext4magic',
    'rsync',
    'ddrescue',
    'clonezilla',
    'mesa',
    'mesa-utils',
    'xf86-video-vesa',
    'xf86-video-fbdev',
    'xf86-video-intel',
    'xf86-video-amdgpu',
    'vulkan-radeon',
    'gtk3',
    'gtk2',
    'gtkmm',
    'fontconfig',
    'ttf-dejavu',
    'ttf-liberation',
    'ttf-droid',
    'ttf-ubuntu-font-family',
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

# Create a script to add the user during the installation
user_script = """
#!/bin/bash
# Create a default user and set password
if ! id "arch" &>/dev/null; then
    useradd -m -G wheel arch
    echo 'arch:password' | chpasswd
fi
"""
with open(os.path.join(PROFILE_DIR, "usr", "local", "bin", "create_user.sh"), "w") as f:
    f.write(user_script)
os.chmod(os.path.join(PROFILE_DIR, "usr", "local", "bin", "create_user.sh"), 0o755)

# Note: The systemd service creation and enabling has been removed
# as it cannot be enabled during the ISO build process.

# Set the default locale and timezone
locale_conf = """
LANG=de_DE.UTF-8
"""
with open(os.path.join(PROFILE_DIR, "etc", "locale.conf"), "w") as f:
    f.write(locale_conf)

# Set timezone to Europe/Berlin
timezone = "Europe/Berlin"
with open(os.path.join(PROFILE_DIR, "etc", "timezone"), "w") as f:
    f.write(timezone)

# Add complete German language variables to /etc/environment
environment_vars = """
# German Language Variables
LANG=de_DE.UTF-8
LC_ALL=de_DE.UTF-8
LANGUAGE=de_DE:de
LC_CTYPE=de_DE.UTF-8
LC_NUMERIC=de_DE.UTF-8
LC_TIME=de_DE.UTF-8
LC_COLLATE=de_DE.UTF-8
LC_MONETARY=de_DE.UTF-8
LC_MESSAGES=de_DE.UTF-8
LC_PAPER=de_DE.UTF-8
LC_NAME=de_DE.UTF-8
LC_ADDRESS=de_DE.UTF-8
LC_TELEPHONE=de_DE.UTF-8
LC_MEASUREMENT=de_DE.UTF-8
LC_IDENTIFICATION=de_DE.UTF-8
"""

with open(os.path.join(PROFILE_DIR, "etc", "environment"), "w") as f:
    f.write(environment_vars)

# Create a README file for user instructions
readme_content = """
Welcome to Arch XFCE ISO!

To log in, use the following credentials:
Username: arch
Password: password

To start the XFCE desktop environment, you can either:
1. Use LightDM (default) - it will automatically log you in.
2. Use startx command after logging in.

To create the user, run the following command after booting into the live environment:
sudo /usr/local/bin/create_user.sh

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