#!/usr/bin/env python3
import tkinter as tk
from tkinter import messagebox
import math

class Calculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simple Calculator")
        self.geometry("400x600")
        self.resizable(0, 0)

        self.expression = ""

        # Entry widget to display the expression
        self.entry = tk.Entry(self, font=("Arial", 24), bd=10, insertwidth=4, width=14, borderwidth=4)
        self.entry.grid(row=0, column=0, columnspan=4)

        # Button layout
        buttons = [
            '7', '8', '9', '/',
            '4', '5', '6', '*',
            '1', '2', '3', '-',
            '0', '.', '=', '+',
            'C', '√', '^', 'Exit'
        ]

        row_val = 1
        col_val = 0

        for button in buttons:
            action = lambda x=button: self.on_button_click(x)
            tk.Button(self, text=button, padx=20, pady=20, font=("Arial", 18), command=action).grid(row=row_val, column=col_val)
            col_val += 1
            if col_val > 3:
                col_val = 0
                row_val += 1

    def on_button_click(self, char):
        if char == 'C':
            self.expression = ""
            self.entry.delete(0, tk.END)
        elif char == 'Exit':
            self.quit()
        elif char == '=':
            try:
                # Evaluate the expression
                result = eval(self.expression)
                self.entry.delete(0, tk.END)
                self.entry.insert(tk.END, str(result))
                self.expression = str(result)
            except Exception as e:
                messagebox.showerror("Error", "Invalid Input")
                self.expression = ""
                self.entry.delete(0, tk.END)
        elif char == '√':
            try:
                result = math.sqrt(float(self.expression))
                self.entry.delete(0, tk.END)
                self.entry.insert(tk.END, str(result))
                self.expression = str(result)
            except Exception as e:
                messagebox.showerror("Error", "Invalid Input")
                self.expression = ""
                self.entry.delete(0, tk.END)
        elif char == '^':
            self.expression += '**'
            self.entry.delete(0, tk.END)
            self.entry.insert(tk.END, self.expression)
        else:
            self.expression += char
            self.entry.delete(0, tk.END)
            self.entry.insert(tk.END, self.expression)

if __name__ == "__main__":
    calculator = Calculator()
    calculator.mainloop()