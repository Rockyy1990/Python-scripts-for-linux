#!/usr/bin/env python
import tkinter as tk
from tkinter import messagebox, simpledialog
import subprocess

class FlatpakManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Flatpak Manager")

        self.search_label = tk.Label(root, text="Search Flatpaks:")
        self.search_label.pack()

        self.search_entry = tk.Entry(root)
        self.search_entry.pack()

        self.search_button = tk.Button(root, text="Search", command=self.search_flatpaks)
        self.search_button.pack()

        self.results_label = tk.Label(root, text="Results:")
        self.results_label.pack()

        self.results_text = tk.Text(root, height=10, width=50)
        self.results_text.pack()

        self.install_button = tk.Button(root, text="Install Selected", command=self.install_flatpak)
        self.install_button.pack()

        self.remove_button = tk.Button(root, text="Remove Selected", command=self.remove_flatpak)
        self.remove_button.pack()

    def search_flatpaks(self):
        query = self.search_entry.get()
        if not query:
            messagebox.showwarning("Input Error", "Please enter a search term.")
            return

        try:
            result = subprocess.run(['flatpak', 'search', query], capture_output=True, text=True, check=True)
            self.results_text.delete(1.0, tk.END)  # Clear previous results
            self.results_text.insert(tk.END, result.stdout)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    def install_flatpak(self):
        selected = self.results_text.get("1.0", tk.END).strip()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select a Flatpak to install.")
            return

        app_id = simpledialog.askstring("Install Flatpak", "Enter the Flatpak ID to install:")
        if app_id:
            try:
                subprocess.run(['flatpak', 'install', '-y', app_id], check=True)
                messagebox.showinfo("Success", f"Flatpak {app_id} installed successfully.")
            except subprocess.CalledProcessError as e:
                messagebox.showerror("Error", f"An error occurred: {e}")

    def remove_flatpak(self):
        selected = self.results_text.get("1.0", tk.END).strip()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select a Flatpak to remove.")
            return

        app_id = simpledialog.askstring("Remove Flatpak", "Enter the Flatpak ID to remove:")
        if app_id:
            try:
                subprocess.run(['flatpak', 'uninstall', '-y', app_id], check=True)
                messagebox.showinfo("Success", f"Flatpak {app_id} removed successfully.")
            except subprocess.CalledProcessError as e:
                messagebox.showerror("Error", f"An error occurred: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FlatpakManager(root)
    root.mainloop()