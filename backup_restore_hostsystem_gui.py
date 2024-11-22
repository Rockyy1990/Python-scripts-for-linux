#!/usr/bin/env python
import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog

class PartcloneBackupRestore:
    def __init__(self, root):
        self.root = root
        self.root.title("Partclone Backup and Restore")

        self.filesystem_var = tk.StringVar(value="ext4")  # Default filesystem
        
        # Dropdown for filesystem selection
        self.filesystem_label = tk.Label(root, text="Select Filesystem Type:")
        self.filesystem_label.pack(pady=5)

        self.filesystem_options = ["ext4", "xfs", "f2fs", "btrfs"]
        self.filesystem_menu = tk.OptionMenu(root, self.filesystem_var, *self.filesystem_options)
        self.filesystem_menu.pack(pady=5)

        self.backup_button = tk.Button(root, text="Backup", command=self.backup)
        self.backup_button.pack(pady=10)

        self.restore_button = tk.Button(root, text="Restore", command=self.restore)
        self.restore_button.pack(pady=10)

    def backup(self):
        src_partition = filedialog.askdirectory(title="Select Source Directory")
        dest_image = filedialog.asksaveasfilename(defaultextension=".img",
                                                    title="Save Backup Image As")
        
        if src_partition and dest_image:
            filesystem_type = self.filesystem_var.get()
            command = ["pkexec", f"partclone.{filesystem_type}", "-c", "-s", src_partition, "-o", dest_image]

            try:
                subprocess.run(command, check=True)
                messagebox.showinfo("Success", f"Backup completed successfully:\n{dest_image}")
            except subprocess.CalledProcessError as e:
                messagebox.showerror("Error", f"Backup failed:\n{e}")

    def restore(self):
        src_image = filedialog.askopenfilename(defaultextension=".img", title="Select Backup Image")
        dest_partition = filedialog.askdirectory(title="Select Destination Directory")
        
        if src_image and dest_partition:
            filesystem_type = self.filesystem_var.get()
            command = ["pkexec", f"partclone.{filesystem_type}", "-r", "-s", src_image, "-o", dest_partition]

            try:
                subprocess.run(command, check=True)
                messagebox.showinfo("Success", "Restore completed successfully.")
            except subprocess.CalledProcessError as e:
                messagebox.showerror("Error", f"Restore failed:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PartcloneBackupRestore(root)
    root.mainloop()
