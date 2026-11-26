"""
Muscribe — Commit 3: Decoupled Dual-Pass Engraving & Robust Output File Validation
Git Commit: fix(compiler): decouple vector PDF export from raster preview and add file validation

Features:
- Decoupled two-pass LilyPond pipeline: Pass 1 (vector PDF) and Pass 2 (raster PNG previews)
- Strict file validation: checks file existence and non-zero byte size
- Graceful degradation: treats valid PDF as success even if raster previews fail
- "Export PDF" button enabled upon successful compilation
"""

from __future__ import annotations

import os
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

        self.title("Muscribe — Dual-Pass Validation (Commit 3)")
        self.geometry("1100x700")
        self.configure(fg_color="#0F1724")

        self.selected_midi_path: Path | None = None
        self.score_stream = None
        self.generated_pdf_path: Path | None = None
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

        self.export_btn = ctk.CTkButton(
            self.sidebar, text="Export PDF Score", command=self.export_pdf, fg_color="#2a2a2a", state="disabled"
        )
        self.export_btn.pack(padx=20, pady=(0, 10), fill="x")

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
            self.export_btn.configure(state="disabled")
            try:
                self.score_stream = converter.parse(str(self.selected_midi_path))
                self.status_label.configure(text="MIDI Loaded", text_color="#4BC6B9")
            except Exception as e:
                messagebox.showerror("Parsing Error", f"Failed to parse MIDI:\n{e}")

    def start_compilation(self) -> None:
        if self.is_compiling or not self.score_stream or not self.selected_midi_path:
            return
        if not self.lilypond_path:
            messagebox.showerror("LilyPond Missing", "LilyPond executable path could not be found.")
            return

        self.is_compiling = True
        self.select_btn.configure(state="disabled")
        self.compile_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.status_label.configure(text="Starting Dual-Pass Compilation...", text_color="#FBBF24")

        threading.Thread(
            target=self._dual_pass_worker,
            args=(self.selected_midi_path, self.score_stream),
            daemon=True
        ).start()

    def _dual_pass_worker(self, midi_path: Path, stream) -> None:
        try:
            stem = midi_path.stem
            ly_path = self.output_dir / f"{stem}.ly"
            pdf_path = self.output_dir / f"{stem}.pdf"

            self.events.put(("status", "Generating LilyPond source..."))
            stream.write("lily", fp=str(ly_path))

            # Pass 1: Render vector PDF
            self.events.put(("status", "Pass 1/2: Compiling Vector PDF..."))
            cmd_pdf = [self.lilypond_path, f"--output={self.output_dir / stem}", str(ly_path)]
            res_pdf = subprocess.run(cmd_pdf, capture_output=True, text=True)
            if res_pdf.returncode != 0:
                raise RuntimeError(f"PDF compilation failed:\n{res_pdf.stderr}")

            # Validate PDF output file
            if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
                raise FileNotFoundError(f"PDF was reported created but missing or empty: {pdf_path}")

            # Pass 2: Render raster PNG previews for GUI
            self.events.put(("status", "Pass 2/2: Rendering Preview Images..."))
            cmd_png = [self.lilypond_path, "--png", "-dresolution=150", f"--output={self.output_dir / stem}", str(ly_path)]
            res_png = subprocess.run(cmd_png, capture_output=True, text=True)

            png_files = sorted(list(self.output_dir.glob(f"{stem}*.png")))
            self.events.put(("success", (pdf_path, png_files, res_png.returncode == 0)))

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
                    pdf_path, png_files, png_ok = data
                    self.is_compiling = False
                    self.generated_pdf_path = pdf_path
                    self.select_btn.configure(state="normal")
                    self.compile_btn.configure(state="normal")
                    self.export_btn.configure(state="normal", fg_color="#10B981")

                    pdf_kb = pdf_path.stat().st_size // 1024
                    self.status_label.configure(text=f"PDF Ready ({pdf_kb} KB)", text_color="#10B981")
                    self._display_preview(png_files)
                    if not png_ok:
                        messagebox.showwarning("Preview Warning", "PDF created successfully, but preview rendering had warnings.")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_events)

    def _display_preview(self, png_files: list[Path]) -> None:
        for child in self.preview_scroll.winfo_children():
            child.destroy()
        self.preview_images.clear()

        if not png_files:
            lbl = ctk.CTkLabel(self.preview_scroll, text="No preview images found.", text_color="#F87171")
            lbl.pack(pady=50)
            return

        for img_path in png_files:
            pil_img = Image.open(img_path)
            max_width = 750
            scale = min(1.0, max_width / pil_img.width)
            disp_size = (int(pil_img.width * scale), int(pil_img.height * scale))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=disp_size)
            self.preview_images.append(ctk_img)

            img_label = ctk.CTkLabel(self.preview_scroll, image=ctk_img, text="")
            img_label.pack(pady=10)

    def export_pdf(self) -> None:
        if not self.generated_pdf_path or not self.generated_pdf_path.is_file():
            messagebox.showwarning("No PDF", "No compiled PDF is available for export.")
            return

        dest = filedialog.asksaveasfilename(
            title="Save Sheet Music PDF",
            defaultextension=".pdf",
            initialfile=self.generated_pdf_path.name,
            filetypes=[("PDF Document", "*.pdf")]
        )
        if dest:
            shutil.copy(str(self.generated_pdf_path), dest)
            messagebox.showinfo("Exported", f"Saved PDF to:\n{dest}")


if __name__ == "__main__":
    app = MuscribeApp()
    app.mainloop()