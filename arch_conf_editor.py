#!/usr/bin/env python
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import os
import subprocess
import tempfile

class ConfigEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Arch Linux Config Editor")
        
        # Text area for editing config files
        self.text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=100, height=22)
        self.text_area.pack(pady=10)

        # Load and Save buttons for different config files
        self.create_button("Load pacman.conf", self.load_pacman_conf)
        self.create_button("Save pacman.conf", self.save_pacman_conf)
        self.create_button("Load sysctl.conf", self.load_sysctl_conf)
        self.create_button("Save sysctl.conf", self.save_sysctl_conf)
        self.create_button("Load fstab", self.load_fstab)
        self.create_button("Save fstab", self.save_fstab)
        self.create_button("Load bashrc", self.load_bashrc)
        self.create_button("Save bashrc", self.save_bashrc)
        self.create_button("Load systemd service", self.load_systemd_service)
        self.create_button("Save systemd service", self.save_systemd_service)

    def create_button(self, text, command):
        button = tk.Button(self.root, text=text, command=command)
        button.pack(pady=5)

    def load_file(self, filepath):
        try:
            command = ["pkexec", "cat", filepath]
            content = subprocess.check_output(command, text=True)
            self.text_area.delete(1.0, tk.END)  # Clear the text area
            self.text_area.insert(tk.END, content)  # Insert file content
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Failed to load {filepath}: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def save_file(self, filepath):
        try:
            content = self.text_area.get(1.0, tk.END).strip()  # Get content and strip trailing newline
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(content.encode('utf-8'))
                temp_file_path = temp_file.name
            
            # Move the temporary file to the target location
            command = ["pkexec", "mv", temp_file_path, filepath]
            subprocess.run(command, check=True)
            messagebox.showinfo("Success", f"{filepath} saved successfully.")
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Failed to save {filepath}: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def load_pacman_conf(self):
        self.load_file('/etc/pacman.conf')

    def save_pacman_conf(self):
        self.save_file('/etc/pacman.conf')

    def load_sysctl_conf(self):
        self.load_file('/etc/sysctl.conf')

    def save_sysctl_conf(self):
        self.save_file('/etc/sysctl.conf')

    def load_fstab(self):
        self.load_file('/etc/fstab')

    def save_fstab(self):
        self.save_file('/etc/fstab')

    def load_bashrc(self):
        home_bashrc = os.path.expanduser('~/.bashrc')
        self.load_file (home_bashrc)

    def save_bashrc(self):
        home_bashrc = os.path.expanduser('~/.bashrc')
        self.save_file(home_bashrc)

    def load_systemd_service(self):
        service_name = simpledialog.askstring("Input", "Enter the systemd service name (without .service):")
        if service_name:
            filepath = f'/etc/systemd/system/{service_name}.service'
            self.load_file(filepath)

    def save_systemd_service(self):
        service_name = simpledialog.askstring("Input", "Enter the systemd service name (without .service):")
        if service_name:
            filepath = f'/etc/systemd/system/{service_name}.service'
            self.save_file(filepath)

if __name__ == "__main__":
    root = tk.Tk()
    editor = ConfigEditor(root)
    root.mainloop()