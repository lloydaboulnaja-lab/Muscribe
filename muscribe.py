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
        self.batch_running: bool = False
        self.events: queue.Queue = queue.Queue()

        # Locate LilyPond on startup and configure music21 environment
        self.lilypond_path = locate_lilypond()
        if self.lilypond_path:
            us = environment.UserSettings()
            us["lilypondPath"] = self.lilypond_path
            print(f"[INFO] LilyPond detected at: {self.lilypond_path}")
        else:
            print("[WARNING] LilyPond executable not found.")

        # Build user interface layout and start background event polling
        self.setup_ui()
        self.after(100, self._process_events)

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
        self.select_btn.pack(padx=20, pady=(10, 6), fill="x")

        # Batch Convert Folder Button
        self.batch_btn = ctk.CTkButton(
            self.sidebar_frame,
            text="Batch Convert Folder",
            command=self.open_batch_folder,
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
        )
        self.batch_btn.pack(padx=20, pady=(0, 10), fill="x")

        # File Status Label
        self.file_label = ctk.CTkLabel(
            self.sidebar_frame, text="No file selected", text_color="#888888", font=ctk.CTkFont(size=12)
        )
        self.file_label.pack(padx=20, pady=5)

        # Compile Button
        self.compile_btn = ctk.CTkButton(
            self.sidebar_frame, text="Compile to Sheet Music", command=self.compile_score, fg_color="#1f538d"
        )
        self.compile_btn.pack(padx=20, pady=(20, 10), fill="x")

        # Main Content Canvas Area (Right side)
        self.main_area = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0)
        self.main_area.pack(side="right", expand=True, fill="both")

        self.placeholder_label = ctk.CTkLabel(
            self.main_area, text="Sheet music preview will appear here", text_color="#555555"
        )
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor="center")

    def load_midi_file(self) -> None:
        """Open a file dialog to select a MIDI file and parse it using music21."""
        if self.batch_running:
            return

        file_path = filedialog.askopenfilename(
            title="Select MIDI File",
            filetypes=[("MIDI Files", "*.mid *.midi"), ("All Files", "*.*")]
        )
        if file_path:
            self.selected_midi_path = Path(file_path)
            self.file_label.configure(text=f"Loaded: {self.selected_midi_path.name}", text_color="#FFFFFF")
            try:
                self.score_stream = converter.parse(str(self.selected_midi_path))
                print(f"[INFO] Successfully parsed MIDI stream: {self.selected_midi_path.name}")
            except Exception as e:
                messagebox.showerror("Parsing Error", f"Failed to parse MIDI file:\n{e}")

    def open_batch_folder(self) -> None:
        """Select a folder of MIDI files and compile all of them in a background thread."""
        if self.batch_running:
            return

        if not self.lilypond_path:
            messagebox.showerror("LilyPond Missing", "LilyPond executable path could not be found.")
            return

        folder = filedialog.askdirectory(title="Select Folder Containing MIDI Files")
        if not folder:
            return

        folder_path = Path(folder)
        midi_files = sorted(list(folder_path.glob("*.mid")) + list(folder_path.glob("*.midi")))
        if not midi_files:
            messagebox.showinfo("No MIDI Files", "No .mid or .midi files were found in that folder.")
            return

        self.batch_running = True
        self.select_btn.configure(state="disabled")
        self.batch_btn.configure(state="disabled")
        self.compile_btn.configure(state="disabled")

        threading.Thread(
            target=self._batch_worker,
            args=(midi_files,),
            daemon=True,
        ).start()

    def _batch_worker(self, midi_files: list[Path]) -> None:
        """Background worker that parses and compiles each MIDI file sequentially."""
        output_dir = Path(__file__).resolve().parent / "output"
        output_dir.mkdir(exist_ok=True)

        success_count = 0
        fail_count = 0
        total = len(midi_files)

        for idx, midi_path in enumerate(midi_files, start=1):
            self.events.put(("progress", f"Batch ({idx}/{total}): {midi_path.name}"))
            try:
                parsed_stream = converter.parse(str(midi_path))
                stem = midi_path.stem
                ly_path = output_dir / f"{stem}.ly"
                parsed_stream.write("lily", fp=str(ly_path))

                cmd = [self.lilypond_path, f"--output={output_dir / stem}", str(ly_path)]
                subprocess.run(cmd, capture_output=True, text=True, check=True)
                success_count += 1
            except Exception as exc:
                fail_count += 1
                print(f"[ERROR] Batch failed for {midi_path.name}: {exc}")

        self.events.put(("batch_finished", (success_count, fail_count, total, output_dir)))

    def _process_events(self) -> None:
        """Poll the thread-safe event queue to update UI status safely."""
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    self.file_label.configure(text=payload, text_color="#FFFFFF")
                elif kind == "batch_finished":
                    success, fail, total, output_dir = payload
                    self.batch_running = False
                    self.select_btn.configure(state="normal")
                    self.batch_btn.configure(state="normal")
                    self.compile_btn.configure(state="normal")
                    self.file_label.configure(
                        text=f"Batch done: {success}/{total} compiled", text_color="#FFFFFF"
                    )
                    messagebox.showinfo(
                        "Batch Conversion Complete",
                        f"Processed {total} files.\nSuccessful: {success}\nFailed: {fail}\n\nSaved to:\n{output_dir}",
                    )
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_events)

    def compile_score(self) -> None:
        """Export the parsed score to LilyPond format and compile it into sheet music."""
        if not self.score_stream:
            messagebox.showwarning("No Score", "Please load and parse a MIDI file first.")
            return

        if not self.lilypond_path:
            messagebox.showerror("LilyPond Missing", "LilyPond executable path could not be found.")
            return

        try:
            # Ensure output directory exists
            output_dir = Path(__file__).resolve().parent / "output"
            output_dir.mkdir(exist_ok=True)

            ly_path = output_dir / "output_score.ly"

            # Write music21 stream out to a LilyPond file format
            self.score_stream.write('lily', fp=str(ly_path))
            print(f"[INFO] Exported LilyPond file to: {ly_path}")

            # Execute LilyPond compiler via subprocess
            cmd = [self.lilypond_path, f"--output={output_dir / 'output_score'}", str(ly_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            print(f"[INFO] LilyPond compilation successful: {result.stdout}")
            messagebox.showinfo("Success", f"Sheet music compiled successfully!\nSaved to: {output_dir}")

        except subprocess.CalledProcessError as e:
            messagebox.showerror("Compilation Error", f"LilyPond failed to compile:\n{e.stderr}")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred during compilation:\n{e}")


if __name__ == "__main__":
    app = MuscribeApp()
    app.mainloop()