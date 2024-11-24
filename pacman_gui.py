#!/usr/bin/env python
import tkinter as tk
from tkinter import messagebox, scrolledtext
import subprocess
import threading

class PacmanGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Pacman GUI")
        
        # Create a frame for the input
        self.frame = tk.Frame(self.root)
        self.frame.pack(pady=10)

        # Create a text area for command input
        self.command_entry = tk.Entry(self.frame, width=50)
        self.command_entry.pack(side=tk.LEFT, padx=10)

        # Create a button to execute the command
        self.execute_button = tk.Button(self.frame, text="Execute", command=self.run_command)
        self.execute_button.pack(side=tk.LEFT)

        # Create a button for the specific command
        self.update_button = tk.Button(self.frame, text="Update System", command=self.update_system)
        self.update_button.pack(side=tk.LEFT)

        # Create a button for removing packages
        self.remove_button = tk.Button(self.frame, text="Remove Package", command=self.remove_package)
        self.remove_button.pack(side=tk.LEFT)

        # Create a scrolled text area for output
        self.output_area = scrolledtext.ScrolledText(self.root, width=80, height=20)
        self.output_area.pack(padx=10, pady=10)

    def run_command(self):
        command = self.command_entry.get()
        if not command.startswith('pkexec pacman'):
            messagebox.showerror("Error", "Please use 'pkexec pacman' commands only.")
            return
        
        self.output_area.delete(1.0, tk.END)  # Clear previous output
        self.output_area.insert(tk.END, f"Executing: {command}\n")
        
        # Run the command in a separate thread to keep the GUI responsive
        thread = threading.Thread(target=self.execute_command, args=(command,))
        thread.start()

    def update_system(self):
        command = "pkexec pacman -Syu --noconfirm"
        self.output_area.delete(1.0, tk.END)  # Clear previous output
        self.output_area.insert(tk.END, f"Executing: {command}\n")
        
        # Run the command in a separate thread
        thread = threading.Thread(target=self.execute_command, args=(command,))
        thread.start()

    def remove_package(self):
        package_name = self.command_entry.get()
        if not package_name:
            messagebox.showerror("Error", "Please enter a package name to remove.")
            return
        
        command = f"pkexec pacman -R --noconfirm {package_name}"
        self.output_area.delete(1.0, tk.END)  # Clear previous output
        self.output_area.insert(tk.END, f"Executing: {command}\n")
        
        # Run the command in a separate thread
        thread = threading.Thread(target=self.execute_command, args=(command,))
        thread.start()

    def execute_command(self, command):
        try:
            # Execute the command
            process = subprocess.run(command.split(), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.output_area.insert(tk.END, process.stdout)
        except subprocess.CalledProcessError as e:
            self.output_area.insert(tk.END, f"Error: {e.stderr}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PacmanGUI(root)
    root.mainloop()