#!/usr/bin/env python3

import subprocess
import tkinter as tk
from tkinter import messagebox, scrolledtext

def run_command(command):
    """Run a system command and return the output."""
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode('utf-8'), None
    except subprocess.CalledProcessError as e:
        return None, e.stderr.decode('utf-8')

def update_system():
    """Update the system packages and show the output."""
    command = ['pkexec', 'pacman', '-Syu', '--noconfirm']
    output, error = run_command(command)
    display_output(output, error)

def clean_package_cache():
    """Clean the package cache and show the output."""
    command = ['pkexec', 'pacman', '-Scc', '--noconfirm']
    output, error = run_command(command)
    display_output(output, error)

def remove_orphaned_packages():
    """Remove orphaned packages and show the output."""
    command = ['pkexec', 'pacman', '-Rns', '--noconfirm']
    orphaned_packages = run_command(['pacman', '-Qdtq'])[0].strip().splitlines()
    if orphaned_packages:
        command.extend(orphaned_packages)
        output, error = run_command(command)
        display_output(output, error)
    else:
        messagebox.showinfo("Info", "No orphaned packages found.")

def display_output(output, error):
    """Display the output or error in a message box or a text widget."""
    if error:
        messagebox.showerror("Error", f"Error: {error}")
    else:
        messagebox.showinfo("Success", output)

def create_gui():
    """Create the GUI for the maintenance script."""
    root = tk.Tk()
    root.title("Arch Linux Maintenance Tool")

    tk.Label(root, text="Select a maintenance task:").pack(pady=10)

    tk.Button(root, text="Update System", command=update_system).pack(pady=5)
    tk.Button(root, text="Clean Package Cache", command=clean_package_cache).pack(pady=5)
    tk.Button(root, text="Remove Orphaned Packages", command=remove_orphaned_packages).pack(pady=5)

    root.mainloop()

if __name__ == "__main__":
    create_gui()