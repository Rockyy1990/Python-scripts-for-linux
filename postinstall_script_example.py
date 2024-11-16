#!/usr/bin/env python
import os
import subprocess
import sys

# Define color variables for output
BOLD_BRIGHT_GREEN = "\033[1;92m"
BOLD_BRIGHT_RED = "\033[1;91m"
RESET = "\033[0m"

def print_green(message):
    print(f"{BOLD_BRIGHT_GREEN}{message}{RESET}")

def print_red(message):
    print(f"{BOLD_BRIGHT_RED}{message}{RESET}")

def run_command(command, check=True):
    """Run a shell command and handle errors."""
    try:
        subprocess.run(command, shell=True, check=check)
    except subprocess.CalledProcessError as e:
        print_red(f"Command failed: {e}")
        sys.exit(1)

def install_packages():
    """Install a list of packages using pacman and yay."""
    # List of packages to install
    packages = [
        'git',          # Version control system
        'base-devel',   # Base development tools
        'steam',        # Steam gaming platform
        'discord',      # Discord communication tool
        'wine',         # Wine compatibility layer for running Windows applications
        'vlc',          # VLC media player
        'gimp',         # GIMP image editor
        'firefox',      # Firefox web browser
        'neofetch',     # System information tool
        'htop',         # Interactive process viewer
        'tmux',         # Terminal multiplexer
        'python-pip',   # Python package installer
        'docker',       # Docker container platform
    ]

    # Install packages using pacman
    print_green("Installing packages using pacman...")
    run_command("sudo pacman -S --needed --noconfirm " + ' '.join(packages))

    # Install AUR packages using yay
    aur_packages = [
        'visual-studio-code-bin',  # Visual Studio Code
        'zoom',                     # Zoom video conferencing
        'microsoft-edge-dev',      # Microsoft Edge browser
    ]

    print_green("Installing AUR packages using yay...")
    for package in aur_packages:
        run_command(f"yay -S --noconfirm {package}")

def enable_services():
    """Enable commonly used services."""
    services = [
        'docker.service',  # Docker service
    ]

    print_green("Enabling services...")
    for service in services:
        run_command(f"sudo systemctl enable {service}")
        run_command(f"sudo systemctl start {service}")

def main():
    print_green("Starting Arch Linux post-install script...")

    install_packages()
    enable_services()

    print_green("Post-installation script completed successfully!")

if __name__ == "__main__":
    main()