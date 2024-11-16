#!/usr/bin/env python

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

class SimpleEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simple Notepad++ Clone")
        self.geometry("800x600")

        # Textfeld
        self.text_area = scrolledtext.ScrolledText(self, wrap=tk.WORD)
        self.text_area.pack(expand=True, fill='both')

        # Menü
        self.create_menu()

    def create_menu(self):
        menu = tk.Menu(self)
        self.config(menu=menu)

        file_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="Datei", menu=file_menu)
        file_menu.add_command(label="Öffnen", command=self.open_file)
        file_menu.add_command(label="Speichern", command=self.save_file)
        file_menu.add_separator()
        file_menu.add_command(label="Beenden", command=self.quit)

        edit_menu = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="Bearbeiten", menu=edit_menu)
        edit_menu.add_command(label="Rückgängig", command=self.undo)
        edit_menu.add_command(label="Wiederholen", command=self.redo)

    def open_file(self):
        file_path = filedialog.askopenfilename(defaultextension=".txt",
                                                filetypes=[("Textdateien", "*.txt"),
                                                           ("Alle Dateien", "*.*")])
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    self.text_area.delete(1.0, tk.END)  # Textbereich leeren
                    self.text_area.insert(tk.END, content)  # Inhalt einfügen
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim Öffnen der Datei: {e}")

    def save_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                   filetypes=[("Textdateien", "*.txt"),
                                                              ("Alle Dateien", "*.*")])
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    content = self.text_area.get(1.0, tk.END)  # Textarea-Inhalt bekommen
                    file.write(content)  # Inhalt in die Datei schreiben
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim Speichern der Datei: {e}")

    def undo(self):
        self.text_area.event_generate("<<Undo>>")

    def redo(self):
        self.text_area.event_generate("<<Redo>>")

if __name__ == "__main__":
    editor = SimpleEditor()
    editor.mainloop()
