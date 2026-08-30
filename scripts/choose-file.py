#!/usr/bin/env python3
"""
Lightweight file/directory chooser for Omarchy Cursor Switcher.
Uses standard Python tkinter with fallback.
"""

import sys
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="Open file/folder chooser")
    parser.add_argument("--directory", action="store_true", help="Choose directory instead of file")
    parser.add_argument("--title", default="Select Cursor Theme or Archive", help="Dialog title")
    args = parser.parse_args()

    chosen = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if args.directory:
            chosen = filedialog.askdirectory(title=args.title)
        else:
            chosen = filedialog.askopenfilename(
                title=args.title,
                filetypes=[
                    ("Cursor Archives & Themes", "*.tar.gz *.tgz *.tar.xz *.txz *.tar.bz2 *.tbz2 *.tar *.zip *.theme"),
                    ("All Files", "*.*")
                ]
            )
        root.destroy()
    except Exception:
        chosen = ""

    if chosen:
        print(chosen.strip())
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
