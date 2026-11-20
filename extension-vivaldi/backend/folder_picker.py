"""Open the system folder picker in an isolated process."""
import sys
import tkinter as tk
from tkinter import filedialog

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    carpeta = filedialog.askdirectory(title="Destino de YouTube Downloader", parent=root)
    root.destroy()
    print(carpeta)
