#!/usr/bin/env python
import subprocess
import tkinter as tk
from tkinter import messagebox
import threading

class UpgradeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("System Upgrade")
        self.root.geometry("300x150")

        self.status_var = tk.StringVar(value="Upgrading system, please wait...")
        self.label = tk.Label(root, textvariable=self.status_var)
        self.label.pack(pady=20)

        self.close_button = tk.Button(root, text="Close", command=self.close_window)
        self.close_button.pack(pady=10)
        self.close_button.config(state=tk.DISABLED)  # Disable the button initially

        self.upgrade_thread = threading.Thread(target=self.upgrade_system)
        self.upgrade_thread.start()

    def upgrade_system(self):
        try:
            # Run the system upgrade command
            subprocess.run(['pkexec', 'pacman', '-Syu', '--noconfirm'], check=True)
            self.update_status("System upgrade completed successfully.")
        except subprocess.CalledProcessError as e:
            self.update_status(f"An error occurred: {e}")
        except Exception as e:
            self.update_status(f"Unexpected error: {e}")
        finally:
            self.close_button.config(state=tk.NORMAL)  # Enable the close button

    def update_status(self, message):
        self.status_var.set(message)

    def close_window(self):
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = UpgradeApp(root)
    root.mainloop()