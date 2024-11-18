#!/usr/bin/env python3
import tkinter as tk
import math

class ScientificCalculator:
    def __init__(self, master):
        self.master = master
        master.title("Wissenschaftlicher Rechner")

        self.result_var = tk.StringVar()

        self.result_entry = tk.Entry(master, textvariable=self.result_var, font=("Arial", 13), bd=10, insertwidth=2, width=15, borderwidth=3)
        self.result_entry.grid(row=0, column=0, columnspan=4)

        self.create_buttons()

    def create_buttons(self):
        buttons = [
            ('7', 1, 0), ('8', 1, 1), ('9', 1, 2), ('/', 1, 3),
            ('4', 2, 0), ('5', 2, 1), ('6', 2, 2), ('*', 2, 3),
            ('1', 3, 0), ('2', 3, 1), ('3', 3, 2), ('-', 3, 3),
            ('0', 4, 0), ('.', 4, 1), ('+', 4, 2), ('=', 4, 3),
            ('sin', 5, 0), ('cos', 5, 1), ('tan', 5, 2), ('log', 5, 3),
            ('C', 6, 0), ('(', 6, 1), (')', 6, 2), ('^', 6, 3),
        ]

        for (text, row, column) in buttons:
            button = tk.Button(self.master, text=text, padx=18, pady=18, font=("Arial", 13),
                               command=lambda t=text: self.on_button_click(t))
            button.grid(row=row, column=column)

    def on_button_click(self, char):
        if char == '=':
            try:
                expression = self.result_var.get()
                result = eval(expression)
                self.result_var.set(result)
            except Exception as e:
                self.result_var.set("Error")
        elif char == 'C':
            self.result_var.set("")
        elif char in ['sin', 'cos', 'tan', 'log']:
            try:
                value = float(self.result_var.get())
                if char == 'sin':
                    self.result_var.set(math.sin(math.radians(value)))
                elif char == 'cos':
                    self.result_var.set(math.cos(math.radians(value)))
                elif char == 'tan':
                    self.result_var.set(math.tan(math.radians(value)))
                elif char == 'log':
                    self.result_var.set(math.log10(value))
            except Exception as e:
                self.result_var.set("Error")
        else:
            current_text = self.result_var.get()
            self.result_var.set(current_text + char)

if __name__ == "__main__":
    root = tk.Tk()
    calculator = ScientificCalculator(root)
    root.mainloop()