"""
Muscribe — Commit 2: Asynchronous Multi-Threading & Embedded Canvas Preview
Git Commit: feat(concurrency): offload compilation to worker thread and add score preview canvas

Features:
- Background compilation thread preventing desktop UI freezing
- Thread-safe queue.Queue event dispatching
- Embedded preview canvas on the right side using PIL and CustomTkinter
- Progress and status indicators
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image
from music21 import converter, environment

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def locate_lilypond() -> str | None:
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

        self.title("Muscribe — Async Threading & Preview (Commit 2)")
        self.geometry("1100x700")
        self.configure(fg_color="#0F1724")

        self.selected_midi_path: Path | None = None
        self.score_stream = None
        self.output_dir = Path(__file__).resolve().parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events: queue.Queue = queue.Queue()
        self.is_compiling = False

        self.lilypond_path = locate_lilypond()
        if self.lilypond_path:
            us = environment.UserSettings()
            us["lilypondPath"] = self.lilypond_path

        self.setup_ui()
        self.after(100, self._process_events)

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
            self.sidebar, text="Compile to Sheet Music", command=self.start_compilation, fg_color="#1F538D"
        )
        self.compile_btn.pack(padx=20, pady=(20, 10), fill="x")

        self.status_label = ctk.CTkLabel(
            self.sidebar, text="Ready", text_color="#4BC6B9", font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(padx=20, pady=10)

        # Right Preview Area
        self.main_area = ctk.CTkFrame(self, fg_color="#090D14", corner_radius=0)
        self.main_area.pack(side="right", expand=True, fill="both")

        self.preview_scroll = ctk.CTkScrollableFrame(self.main_area, fg_color="#090D14")
        self.preview_scroll.pack(expand=True, fill="both", padx=10, pady=10)

        self.placeholder_label = ctk.CTkLabel(
            self.preview_scroll, text="Sheet music preview will appear here once compiled.",
            text_color="#555555", font=ctk.CTkFont(size=14)
        )
        self.placeholder_label.pack(expand=True, pady=100)
        self.preview_images: list[ctk.CTkImage] = []

    def load_midi_file(self) -> None:
        if self.is_compiling:
            return
        file_path = filedialog.askopenfilename(
            title="Select MIDI File",
            filetypes=[("MIDI Files", "*.mid *.midi"), ("All Files", "*.*")]
        )
        if file_path:
            self.selected_midi_path = Path(file_path)
            self.file_label.configure(text=f"Loaded: {self.selected_midi_path.name}", text_color="#F8FAFC")
            try:
                self.score_stream = converter.parse(str(self.selected_midi_path))
                self.status_label.configure(text="MIDI Loaded Successfully", text_color="#4BC6B9")
            except Exception as e:
                messagebox.showerror("Parsing Error", f"Failed to parse MIDI:\n{e}")

    def start_compilation(self) -> None:
        if self.is_compiling:
            return
        if not self.score_stream or not self.selected_midi_path:
            messagebox.showwarning("No Score", "Please select a valid MIDI file first.")
            return
        if not self.lilypond_path:
            messagebox.showerror("LilyPond Missing", "LilyPond executable path could not be found.")
            return

        self.is_compiling = True
        self.select_btn.configure(state="disabled")
        self.compile_btn.configure(state="disabled")
        self.status_label.configure(text="Compiling in background...", text_color="#FBBF24")

        # Launch background worker thread
        threading.Thread(
            target=self._compile_worker,
            args=(self.selected_midi_path, self.score_stream),
            daemon=True
        ).start()

    def _compile_worker(self, midi_path: Path, stream) -> None:
        try:
            stem = midi_path.stem
            ly_path = self.output_dir / f"{stem}.ly"

            self.events.put(("status", "Exporting LilyPond syntax..."))
            stream.write("lily", fp=str(ly_path))

            self.events.put(("status", "Invoking LilyPond compiler..."))
            # Initial compilation command attempting PNG output
            cmd = [self.lilypond_path, "--png", f"-dresolution=150", f"--output={self.output_dir / stem}", str(ly_path)]
            subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Discover generated preview PNGs
            png_files = sorted(list(self.output_dir.glob(f"{stem}*.png")))
            self.events.put(("success", (png_files, stem)))

        except subprocess.CalledProcessError as err:
            self.events.put(("error", f"LilyPond exited with code {err.returncode}:\n{err.stderr}"))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _process_events(self) -> None:
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "status":
                    self.status_label.configure(text=data, text_color="#FBBF24")
                elif kind == "error":
                    self.is_compiling = False
                    self.select_btn.configure(state="normal")
                    self.compile_btn.configure(state="normal")
                    self.status_label.configure(text="Compilation Failed", text_color="#F87171")
                    messagebox.showerror("Compilation Error", data)
                elif kind == "success":
                    png_files, stem = data
                    self.is_compiling = False
                    self.select_btn.configure(state="normal")
                    self.compile_btn.configure(state="normal")
                    self.status_label.configure(text="Compilation Succeeded!", text_color="#4BC6B9")
                    self._display_preview(png_files)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_events)

    def _display_preview(self, png_files: list[Path]) -> None:
        # Clear existing widgets
        for child in self.preview_scroll.winfo_children():
            child.destroy()
        self.preview_images.clear()

        if not png_files:
            lbl = ctk.CTkLabel(self.preview_scroll, text="No preview images found.", text_color="#F87171")
            lbl.pack(pady=50)
            return

        for img_path in png_files:
            pil_img = Image.open(img_path)
            # Calculate display scale
            max_width = 750
            scale = min(1.0, max_width / pil_img.width)
            disp_size = (int(pil_img.width * scale), int(pil_img.height * scale))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=disp_size)
            self.preview_images.append(ctk_img)

            img_label = ctk.CTkLabel(self.preview_scroll, image=ctk_img, text="")
            img_label.pack(pady=10)


if __name__ == "__main__":
    app = MuscribeApp()
    app.mainloop()