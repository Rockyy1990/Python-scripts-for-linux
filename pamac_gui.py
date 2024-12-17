import tkinter as tk
from tkinter import messagebox, scrolledtext
import subprocess

class PamacGUI:
    def __init__(self, master):
        self.master = master
        master.title("Pamac GUI")

        self.label = tk.Label(master, text="Package Management with Pamac")
        self.label.pack()

        self.search_label = tk.Label(master, text="Search Package:")
        self.search_label.pack()

        self.search_entry = tk.Entry(master)
        self.search_entry.pack()

        self.search_button = tk.Button(master, text="Search", command=self.search_package)
        self.search_button.pack()

        self.install_label = tk.Label(master, text="Install Package:")
        self.install_label.pack()

        self.install_entry = tk.Entry(master)
        self.install_entry.pack()

        self.install_button = tk.Button(master, text="Install", command=self.install_package)
        self.install_button.pack()

        self.remove_label = tk.Label(master, text="Remove Package:")
        self.remove_label.pack()

        self.remove_entry = tk.Entry(master)
        self.remove_entry.pack()

        self.remove_button = tk.Button(master, text="Remove", command=self.remove_package)
        self.remove_button.pack()

        self.upgrade_button = tk.Button(master, text="System Upgrade", command=self.upgrade_system)
        self.upgrade_button.pack()

        self.result_text = scrolledtext.ScrolledText(master, width=50, height=15)
        self.result_text.pack()

    def run_command(self, command):
        try:
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            return e.stderr

    def search_package(self):
        package_name = self.search_entry.get()
        command = ['pkexec', 'pamac', 'search', package_name]
        output = self.run_command(command)
        self.show_result(output)

    def install_package(self):
        package_name = self.install_entry.get()
        command = ['pkexec', 'pamac', 'install', package_name]
        output = self.run_command(command)
        self.show_result(output)

    def remove_package(self):
        package_name = self.remove_entry.get()
        command = ['pkexec', 'pamac', 'remove', package_name]
        output = self.run_command(command)
        self.show_result(output)

    def upgrade_system(self):
        command = ['pkexec', 'pamac', 'upgrade', '-a']
        output = self.run_command(command)
        self.show_result(output)

    def show_result(self, output):
        self.result_text.delete(1.0, tk.END)  # Clear previous output
        self.result_text.insert(tk.END, output)  # Insert new output

if __name__ == "__main__":
    root = tk.Tk()
    app = PamacGUI(root)
    root.mainloop()