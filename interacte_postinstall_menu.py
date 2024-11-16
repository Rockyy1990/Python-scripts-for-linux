#!/usr/bin/env python

import os
import subprocess

# Function to display the menu
def display_menu():
    os.system('clear')
    print("          Archlinux Post-Installer")
    print("-----------------------------------------------")
    print("1)  Install Chaotic-Repo (Compiled AUR)")
    print("2)  Install Needed-packages and system tweaks")
    print("3)  Install bashrc-tweaks")
    print("4)  Install Programs")
    print("5)  Install Docker")
    print("6)  Install Pipewire-full (Sound)")
    print("7)  Install AMD GPU Driver")
    print("8)  Install Nvidia GPU Driver")
    print("9)  Install Print Support")
    print("10) Install Flatpak Support")
    print("11) Install Wine (Windows support)")
    print("12) Install Steam Gaming Platform")
    print("13) Install Pamac-AUR Helper (GUI for Pacman)")
    print("14) Install Chromium Browser")
    print("15) Install Firefox Browser")
    print("16) Archlinux to CachyOS Converter")
    print("17) Install and config nfs (server)")
    print("18) Install and config nfs (client)")
    print("19) Install and config samba (share)")
    print("20) Install virt-manager (Virtualisation)")
    print("21) Install Libreoffice (fresh)")
    print("22) Final steps (System cleaning and Backup)")
    print("0) EXIT installer and reboot")
    print("-----------------------------------------------")

# Function to execute commands
def run_command(command, wait=True):
    """Run a shell command."""
    print(f"Running: {command}")
    if wait:
        subprocess.run(command, shell=True, check=True)
    else:
        subprocess.Popen(command, shell=True)

# Example function implementation
def install_chaotic_aur():
    print("Installing chaotic-aur...")
    
    # Step 1: Update pacman.conf
    run_command("grep -q '^Color' /etc/pacman.conf || sudo sed -i -e 's/^#Color$/Color/' /etc/pacman.conf")
    run_command("grep -q 'ILoveCandy' /etc/pacman.conf || sudo sed -i -e '/#VerbosePkgLists/a ILoveCandy' /etc/pacman.conf")
    run_command("sudo sed -i -e s'/\\#VerbosePkgLists/VerbosePkgLists/'g /etc/pacman.conf")
    run_command("sudo sed -i -e s'/\\#ParallelDownloads.*/ParallelDownloads = 2/'g /etc/pacman.conf")
    
    # Install chaotic-aur repo
    run_command("sudo pacman-key --recv-key 3056513887B78AEB --keyserver keyserver.ubuntu.com")
    run_command("sudo pacman-key --lsign-key 3056513887B78AEB")
    run_command("sudo pacman -U --noconfirm 'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-keyring.pkg.tar.zst'")
    run_command("sudo pacman -U --noconfirm 'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-mirrorlist.pkg.tar.zst'")
    
    # Update pacman.conf to include the repo
    with open("/etc/pacman.conf", "a") as pacman_conf:
        pacman_conf.write("\n## Chaotic AUR Repo ##\n")
        pacman_conf.write("[chaotic-aur]\n")
        pacman_conf.write("Include = /etc/pacman.d/chaotic-mirrorlist") 
    
    run_command("sudo pacman -Sy")
    print("chaotic-aur installed successfully!")
    input("Press [Enter] to continue...")

# An example of how you might implement another install function
def install_needed_packages():
    print("Installing Needed-packages and system tweaks...")
    run_command("sudo pacman -S --needed --noconfirm dbus-broker dkms kmod amd-ucode pacman-contrib bash-completion yay samba bind ethtool rsync timeshift timeshift-autosnap")
    run_command("sudo pacman -S --needed --noconfirm gufw gsmartcontrol mtools xfsdump f2fs-tools udftools gnome-disk-utility")
    # ... add more packages and your tweaks here ...
    
    print("Needed packages and System tweaks installed successfully!")
    input("Press [Enter] to continue...")

# Main script loop
def main():
    run_command("echo \"You should read this script first!\"")
    input("It's recommended to install the chaotic aur repo for some packages. Press any key to continue...")

    while True:
        display_menu()
        option = input("Select an option [0-22]: ")
        
        if option == "1":
            install_chaotic_aur()
        elif option == "2":
            install_needed_packages()
        # Add other options' implementations here...
        elif option == "0":
            print("Exiting... Rebooting now.")
            run_command("sudo reboot")
            break
        else:
            print("Invalid option! Please try again.")

if __name__ == '__main__':
    main()
