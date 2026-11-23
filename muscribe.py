"""
Muscribe — Commit 1: Initial Baseline Core-First Prototype
Git Commit: feat(core): initial synchronous midi to lilypond compiler prototype

Features:
- Basic CustomTkinter desktop interface
- Direct synchronous MIDI parsing with music21
- Synchronous LilyPond compilation via subprocess
- Basic file loading and single compilation button
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from music21 import converter, environment

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def locate_lilypond() -> str | None:
    """Search system PATH and standard directories for LilyPond."""
    found = shutil.which("lilypond") or shutil.which("lilypond.exe")
    if found:
        return str(Path(found).resolve())

    standard_paths = [
        Path(r"C:\Program Files (x86)\LilyPond\usr\bin\lilypond.exe"),
        Path(r"C:\Program Files\LilyPond\usr\bin\lilypond.exe"),
        Path(r"C:\lilypond\bin\lilypond.exe"),
        Path("/usr/local/bin/lilypond"),
        Path("/usr/bin/lilypond"),
    ]
    for p in standard_paths:
        if p.is_file():
            return str(p.resolve())
    return None


class MuscribeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Muscribe — Baseline Prototype (Commit 1)")
        self.geometry("900x600")
        self.configure(fg_color="#0F1724")

        self.selected_midi_path: Path | None = None
        self.score_stream = None
        self.output_dir = Path(__file__).resolve().parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.lilypond_path = locate_lilypond()
        if self.lilypond_path:
            us = environment.UserSettings()
            us["lilypondPath"] = self.lilypond_path
            print(f"[INFO] LilyPond detected at: {self.lilypond_path}")
        else:
            print("[WARNING] LilyPond executable not found.")

        self.setup_ui()

    def setup_ui(self) -> None:
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=280, fg_color="#151D2B", corner_radius=0)
        self.sidebar.pack(side="left", fill="y")

        self.logo_label = ctk.CTkLabel(
            self.sidebar, text="MUSCRIBE", font=ctk.CTkFont(size=22, weight="bold"), text_color="#F8FAFC"
        )
        self.logo_label.pack(padx=20, pady=(30, 20))

        self.select_btn = ctk.CTkButton(
            self.sidebar, text="Select MIDI File", command=self.load_midi_file, fg_color="#4BC6B9", text_color="#090D14"
        )
        self.select_btn.pack(padx=20, pady=10, fill="x")

        self.file_label = ctk.CTkLabel(
            self.sidebar, text="No file selected", text_color="#9CA3AF", font=ctk.CTkFont(size=12)
        )
        self.file_label.pack(padx=20, pady=5)

        self.compile_btn = ctk.CTkButton(
            self.sidebar, text="Compile to Sheet Music", command=self.compile_score, fg_color="#1F538D"
        )
        self.compile_btn.pack(padx=20, pady=(20, 10), fill="x")

        # Main Area
        self.main_area = ctk.CTkFrame(self, fg_color="#090D14", corner_radius=0)
        self.main_area.pack(side="right", expand=True, fill="both")

        self.placeholder_label = ctk.CTkLabel(
            self.main_area, text="Sheet music output will be saved to disk.\n(Preview canvas not yet implemented in Commit 1)",
            text_color="#555555", font=ctk.CTkFont(size=14)
        )
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor="center")

    def load_midi_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select MIDI File",
            filetypes=[("MIDI Files", "*.mid *.midi"), ("All Files", "*.*")]
        )
        if file_path:
            self.selected_midi_path = Path(file_path)
            self.file_label.configure(text=f"Loaded: {self.selected_midi_path.name}", text_color="#F8FAFC")
            try:
                self.score_stream = converter.parse(str(self.selected_midi_path))
                print(f"[INFO] Parsed MIDI: {self.selected_midi_path.name}")
            except Exception as e:
                messagebox.showerror("Parsing Error", f"Failed to parse MIDI:\n{e}")

    def compile_score(self) -> None:
        """Synchronous compile method that runs on the main UI thread."""
        if not self.score_stream or not self.selected_midi_path:
            messagebox.showwarning("No Score", "Please load a MIDI file first.")
            return

        if not self.lilypond_path:
            messagebox.showerror("LilyPond Missing", "LilyPond executable path could not be found.")
            return

        try:
            stem = self.selected_midi_path.stem
            ly_path = self.output_dir / f"{stem}.ly"

            # Export LilyPond source
            self.score_stream.write("lily", fp=str(ly_path))
            print(f"[INFO] Exported LilyPond source: {ly_path}")

            # Run LilyPond synchronously (freezes UI during compilation)
            cmd = [self.lilypond_path, f"--output={self.output_dir / stem}", str(ly_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            print(f"[INFO] LilyPond stdout: {result.stdout}")
            messagebox.showinfo("Success", f"Compilation completed!\nSaved to: {self.output_dir}")

        except subprocess.CalledProcessError as e:
            messagebox.showerror("Compilation Error", f"LilyPond error:\n{e.stderr}")
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error:\n{e}")


if __name__ == "__main__":
    app = MuscribeApp()
    app.mainloop()