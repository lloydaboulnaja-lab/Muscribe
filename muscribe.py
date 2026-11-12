from __future__ import annotations
"""
Muscribe — MIDI to Sheet Music Converter
EPQ Artefact Project
"""

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


class MuscribeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        # Window setup matching Stage 2 Design Specifications
        self.title("Muscribe — MIDI to Sheet Music Converter")
        self.geometry("1100x700")
        self.minsize(900, 600)

        # Apply Option B Primary Window Canvas Colour (#000000 Pure Black)
        self.configure(fg_color="#000000")


if __name__ == "__main__":
    app = MuscribeApp()
    app.mainloop()