#!/usr/bin/env python
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os

class PartedGUI:
    def __init__(self, master):
        self.master = master
        master.title("Parted GUI")

        # Frame for disk selection
        self.disk_frame = ttk.Frame(master)
        self.disk_frame.pack(pady=10)

        # Disk selection
        self.disk_label = ttk.Label(self.disk_frame, text="Select Disk:")
        self.disk_label.pack(side=tk.LEFT)
        self.disk_var = tk.StringVar()
        self.disk_combobox = ttk.Combobox(self.disk_frame, textvariable=self.disk_var)
        self.disk_combobox.pack(side=tk.LEFT)
        self.populate_disks()

        # Frame for size entry and filesystem selection
        self.partition_frame = ttk.Frame(master)
        self.partition_frame.pack(pady=10)

        # Size selection using scale
        self.size_label = ttk.Label(self.partition_frame, text="Partition Size (% of Disk):")
        self.size_label.pack(side=tk.LEFT)
        self.size_scale = tk.Scale(self.partition_frame, from_=1, to=100, orient=tk.HORIZONTAL)
        self.size_scale.pack(side=tk.LEFT)

        # Filesystem selection
        self.fs_label = ttk.Label(self.partition_frame, text="Filesystem Type:")
        self.fs_label.pack(side=tk.LEFT)
        self.fs_var = tk.StringVar()
        self.fs_combobox = ttk.Combobox(self.partition_frame, textvariable=self.fs_var, values=["ext4", "exfat", "xfs", "f2fs"])
        self.fs_combobox.pack(side=tk.LEFT)
        self.fs_combobox.current(0)

        # Create button
        self.create_button = ttk.Button(master, text="Create Partition", command=self.create_partition)
        self.create_button.pack(pady=10)

        # Format entire drive button
        self.format_button = ttk.Button(master, text="Format Entire Drive", command=self.format_entire_drive)
        self.format_button.pack(pady=10)

        # Status label
        self.status_label = ttk.Label(master, text="")
        self.status_label.pack()

    def populate_disks(self):
        # Get list of disks
        try:
            # List block devices
            devices = subprocess.check_output(["lsblk", "-d", "-n", "-p", "-o", "NAME"]).decode().strip().split('\n')
            self.disk_combobox['values'] = devices
            if devices:
                self.disk_combobox.current(0)  # Select the first disk by default
        except Exception as e:
            messagebox.showerror("Error", f"Failed to list disks: {str(e)}")

    def create_partition(self):
        size_percentage = self.size_scale.get()
        filesystem = self.fs_var.get()
        drive = self.disk_var.get()

        if size_percentage <= 0:
            messagebox.showerror("Input Error", "Please select a valid size percentage.")
            return

        # Confirmation dialog
        if not messagebox.askyesno("Confirm", "Are you sure you want to create a partition? This may erase data!"):
            return

        try:
            # Create a new partition using parted
            subprocess.run(["pkexec", "parted", drive, "mkpart", filesystem, f"0%", f"{size_percentage}%"], check=True)

            # Format the new partition
            partition_name = f"{drive}1"  # Assuming the first partition after creation
            if filesystem == "ext4":
                subprocess.run(["pkexec", "mkfs.ext4", partition_name], check=True)
            elif filesystem == "exfat":
                subprocess.run(["pkexec", "mkfs.exfat", partition_name], check=True)
            elif filesystem == "xfs":
                subprocess.run(["pkexec", "mkfs.xfs", partition_name], check=True)
            elif filesystem == "f2fs":
                subprocess.run(["pkexec", "mkfs.f2fs", partition_name], check=True)

            self.status_label.config(text=f"Partition and format successful: {filesystem} {size_percentage}% of {drive}")
        except subprocess.CalledProcessError as e:
            messagebox.showerror ("Error", f"Command failed: {e}")
            self.status_label.config(text="")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_label.config(text="")

    def format_entire_drive(self):
        drive = self.disk_var.get()
        filesystem = self.fs_var.get()

        # Confirmation dialog
        if not messagebox.askyesno("Confirm", "Are you sure you want to format the entire drive? This will erase all data!"):
            return

        try:
            if filesystem == "ext4":
                subprocess.run(["pkexec", "mkfs.ext4", drive], check=True)
            elif filesystem == "exfat":
                subprocess.run(["pkexec", "mkfs.exfat", drive], check=True)
            elif filesystem == "xfs":
                subprocess.run(["pkexec", "mkfs.xfs", drive], check=True)
            elif filesystem == "f2fs":
                subprocess.run(["pkexec", "mkfs.f2fs", drive], check=True)

            self.status_label.config(text=f"Drive formatted successfully: {filesystem}")
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Command failed: {e}")
            self.status_label.config(text="")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_label.config(text="")

def main():
    root = tk.Tk()
    gui = PartedGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()