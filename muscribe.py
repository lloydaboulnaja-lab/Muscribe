from __future__ import annotations

"""
Muscribe — MIDI to Sheet Music Converter
EPQ Artefact Project
"""

import copy
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import mido
from PIL import Image
from music21 import chord as m21chord
from music21 import converter, environment, meter, metadata, note as m21note
from music21 import stream as m21stream

try:
    import pygame
except ImportError:
    pygame = None


# Configure global CustomTkinter dark mode appearance
ctk.set_appearance_mode("dark")


def locate_lilypond() -> str | None:
    """Search local project folders and system PATH for the LilyPond executable."""
    base_dir = Path(__file__).resolve().parent

    # Check common local bundle paths inside the Muscribe/lilypond directory first
    local_candidates = [
        base_dir / "lilypond" / "bin" / "lilypond.exe",
        base_dir / "lilypond" / "bin" / "lilypond",
        base_dir / "lilypond" / "usr" / "bin" / "lilypond.exe",
        base_dir / "lilypond" / "usr" / "bin" / "lilypond",
    ]
    for candidate in local_candidates:
        if candidate.is_file():
            return str(candidate)

    # Fallback: check if lilypond is registered in the system PATH
    system_path = shutil.which("lilypond")
    if system_path:
        return system_path

    # Fallback: check standard Windows/macOS/Linux installation folders
    standard_paths = [
        Path(r"C:\Program Files (x86)\LilyPond\usr\bin\lilypond.exe"),
        Path(r"C:\Program Files\LilyPond\usr\bin\lilypond.exe"),
        Path("/usr/local/bin/lilypond"),
        Path("/usr/bin/lilypond"),
    ]
    for path in standard_paths:
        if path.is_file():
            return str(path)

    return None


class MuscribeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        # Window setup
        self.title("Muscribe — MIDI to Sheet Music Converter")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(fg_color="#000000")

        # Locate LilyPond on startup and configure music21 environment
        self.lilypond_path = locate_lilypond()
        if self.lilypond_path:
            us = environment.UserSettings()
            us["lilypondPath"] = self.lilypond_path
            print(f"[INFO] LilyPond detected at: {self.lilypond_path}")
        else:
            print("[WARNING] LilyPond executable not found.")


if __name__ == "__main__":
    app = MuscribeApp()
    app.mainloop()