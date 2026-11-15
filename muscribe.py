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

    local_candidates = [
        base_dir / "lilypond" / "bin" / "lilypond.exe",
        base_dir / "lilypond" / "bin" / "lilypond",
        base_dir / "lilypond" / "usr" / "bin" / "lilypond.exe",
        base_dir / "lilypond" / "usr" / "bin" / "lilypond",
    ]
    for candidate in local_candidates:
        if candidate.is_file():
            return str(candidate)

    system_path = shutil.which("lilypond")
    if system_path:
        return system_path

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

        # Application state variables
        self.selected_midi_path: Path | None = None
        self.score_stream: m21stream.Score | None = None

        # Locate LilyPond on startup and configure music21 environment
        self.lilypond_path = locate_lilypond()
        if self.lilypond_path:
            us = environment.UserSettings()
            us["lilypondPath"] = self.lilypond_path
            print(f"[INFO] LilyPond detected at: {self.lilypond_path}")
        else:
            print("[WARNING] LilyPond executable not found.")

        # Build user interface layout
        self.setup_ui()

    def setup_ui(self) -> None:
        """Create the sidebar control panel and main workspace area."""
        # Left Sidebar Frame for controls
        self.sidebar_frame = ctk.CTkFrame(self, width=280, fg_color="#111111", corner_radius=0)
        self.sidebar_frame.pack(side="left", fill="y")

        # App Title Label inside Sidebar
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, text="MUSCRIBE", font=ctk.CTkFont(size=22, weight="bold")
        )
        self.logo_label.pack(padx=20, pady=(30, 20))

        # Select MIDI File Button
        self.select_btn = ctk.CTkButton(
            self.sidebar_frame, text="Select MIDI File", command=self.load_midi_file
        )
        self.select_btn.pack(padx=20, pady=10, fill="x")

        # File Status Label
        self.file_label = ctk.CTkLabel(
            self.sidebar_frame, text="No file selected", text_color="#888888", font=ctk.CTkFont(size=12)
        )
        self.file_label.pack(padx=20, pady=5)

        # Main Content Canvas Area (Right side)
        self.main_area = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0)
        self.main_area.pack(side="right", expand=True, fill="both")

        self.placeholder_label = ctk.CTkLabel(
            self.main_area, text="Sheet music preview will appear here", text_color="#555555"
        )
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor="center")

    def load_midi_file(self) -> None:
        """Open a file dialog to select a MIDI file and parse it using music21."""
        file_path = filedialog.askopenfilename(
            title="Select MIDI File",
            filetypes=[("MIDI Files", "*.mid *.midi"), ("All Files", "*.*")]
        )
        if file_path:
            self.selected_midi_path = Path(file_path)
            self.file_label.configure(text=f"Loaded: {self.selected_midi_path.name}", text_color="#FFFFFF")
            try:
                # Parse MIDI stream using music21 converter
                self.score_stream = converter.parse(str(self.selected_midi_path))
                print(f"[INFO] Successfully parsed MIDI stream: {self.selected_midi_path.name}")
            except Exception as e:
                messagebox.showerror("Parsing Error", f"Failed to parse MIDI file:\n{e}")


if __name__ == "__main__":
    app = MuscribeApp()
    app.mainloop()