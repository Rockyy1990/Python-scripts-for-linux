#!/usr/bin/env python
import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import threading

def download_file():
    url = url_entry.get()
    output_file = output_entry.get()

    if not url or not output_file:
        messagebox.showerror("Input Error", "Please enter both URL and output file name.")
        return

    # Disable the download button and clear the progress bar
    download_button.config(state=tk.DISABLED)
    progress_bar['value'] = 0
    progress_bar.start()

    # Start the download in a separate thread
    threading.Thread(target=run_curl, args=(url, output_file)).start()

def run_curl(url, output_file):
    try:
        # Call curl to download the file
        result = subprocess.run(['curl', '-o', output_file, url], check=True, capture_output=True, text=True)
        # Stop the progress bar
        progress_bar.stop()
        messagebox.showinfo("Success", f"File downloaded successfully to {output_file}")
    except subprocess.CalledProcessError as e:
        # Stop the progress bar
        progress_bar.stop()
        messagebox.showerror("Download Error", f"Failed to download file: {e.stderr}")

    # Re-enable the download button
    download_button.config(state=tk.NORMAL)

# Create the main window
root = tk.Tk()
root.title("Curl File Downloader")

# Create and place the URL label and entry
url_label = tk.Label(root, text="Enter URL:")
url_label.pack(pady=5)
url_entry = tk.Entry(root, width=50)
url_entry.pack(pady=5)

# Create and place the output file label and entry
output_label = tk.Label(root, text="Enter output file name:")
output_label.pack(pady=5)
output_entry = tk.Entry(root, width=50)
output_entry.pack(pady=5)

# Create and place the download button
download_button = tk.Button(root, text="Download", command=download_file)
download_button.pack(pady=20)

# Create and place the progress bar
progress_bar = ttk.Progressbar(root, mode='indeterminate')
progress_bar.pack(pady=10, fill=tk.X)

# Start the GUI event loop
root.mainloop()