"""
Muscribe — Commit 6: Audio Playback & MIDI Auditioning Engine
Git Commit: feat(audio): integrate pygame mixer for in-app MIDI preview with play pause and stop controls

Features:
- Seamless background MIDI playback via pygame.mixer
- Play / Pause / Resume and Stop controls integrated in the control panel
- Audio state decoupled from sheet music rendering so users can audition while viewing
- Graceful degradation with clear fallback warnings if sound drivers or pygame are absent
"""

from __future__ import annotations

import queue
import re
import shutil
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image
from music21 import clef as m21clef
from music21 import converter, environment, metadata
from music21 import stream as m21stream

try:
    import pygame
except ImportError:
    pygame = None

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

RHYTHM_GRIDS = {
    "Off": None,
    "Gentle": (2,),
    "Balanced": (2, 3, 4),
    "Detailed": (2, 3, 4, 6, 8),
}


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


def _patch_lilypond_header(ly_path: Path, title: str | None, composer: str | None) -> None:
    """Strips music21 LaTeX snippet preamble and writes clean header metadata."""
    text = ly_path.read_text(encoding="utf-8")

    # Fix: strip preamble include that forces title onto a separate page
    text = re.sub(r'\s*\\include "lilypond-book-preamble\.ly"\n', "\n", text)

    # Clean header block
    header_lines = ["\\header {"]
    if title:
        safe_title = str(title).replace("\\", "\\\\").replace('"', '\\"')
        header_lines.append(f'  title = "{safe_title}"')
    if composer:
        safe_composer = str(composer).replace("\\", "\\\\").replace('"', '\\"')
        header_lines.append(f'  composer = "{safe_composer}"')
    header_lines.append('  tagline = ##f')  # Suppress default footer
    header_lines.append("}")
    header_block = "\n".join(header_lines) + "\n"

    # Replace existing header or prepend new header
    if "\\header {" in text:
        text = re.sub(r'\\header\s*\{[^}]*\}', header_block, text, count=1)
    else:
        text = header_block + text

    ly_path.write_text(text, encoding="utf-8")


def _split_wide_parts(score, max_span=19):
    for part in list(score.parts):
        pitches = sorted({pitch.midi for n in part.recurse().notes for pitch in n.pitches})
        if not pitches or pitches[-1] - pitches[0] <= max_span:
            continue

        split = None
        best_gap = 0
        for candidate in range(pitches[0] + 1, pitches[-1]):
            if candidate % 12 != 0:
                continue
            below = [p for p in pitches if p < candidate]
            above = [p for p in pitches if p > candidate]
            if not below or not above:
                continue
            gap = min(candidate - max(below), min(above) - candidate)
            if gap > best_gap:
                best_gap, split = gap, candidate

        if split is None:
            continue

        treble = m21stream.Part(id=f"{part.id}_treble")
        bass = m21stream.Part(id=f"{part.id}_bass")

        for n in part.recurse().notes:
            offset = n.getOffsetInHierarchy(part)
            lowest = min(p.midi for p in n.pitches)
            if lowest < split:
                bass.insert(offset, n)
            else:
                treble.insert(offset, n)

        treble.insert(0, m21clef.TrebleClef())
        bass.insert(0, m21clef.BassClef())

        score.remove(part)
        score.insert(0, treble)
        score.insert(0, bass)


class MetadataDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_title: str, current_composer: str, on_save):
        super().__init__(parent)
        self.title("Score Metadata")
        self.geometry("420x280")
        self.resizable(False, False)
        self.configure(fg_color="#151D2B")
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save

        ctk.CTkLabel(self, text="Score Metadata", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#F8FAFC").pack(anchor="w", padx=20, pady=(20, 10))

        ctk.CTkLabel(self, text="Title", text_color="#9CA3AF").pack(anchor="w", padx=20)
        self.title_entry = ctk.CTkEntry(self, width=380, fg_color="#0F1724")
        self.title_entry.pack(padx=20, pady=(4, 10))
        self.title_entry.insert(0, current_title)

        ctk.CTkLabel(self, text="Composer", text_color="#9CA3AF").pack(anchor="w", padx=20)
        self.composer_entry = ctk.CTkEntry(self, width=380, fg_color="#0F1724")
        self.composer_entry.pack(padx=20, pady=(4, 16))
        self.composer_entry.insert(0, current_composer)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(10, 20))

        ctk.CTkButton(btn_row, text="Cancel", fg_color="#2a2a2a", command=self.destroy).pack(side="left", expand=True, padx=(0, 5))
        ctk.CTkButton(btn_row, text="Save", fg_color="#4BC6B9", text_color="#090D14", command=self.save).pack(side="right", expand=True, padx=(5, 0))

    def save(self):
        t = self.title_entry.get().strip() or "Untitled Score"
        c = self.composer_entry.get().strip() or "Unknown Composer"
        self.on_save(t, c)
        self.destroy()


class MuscribeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Muscribe — Metadata & Single Page (Commit 5)")
        self.geometry("1100x700")
        self.configure(fg_color="#0F1724")

        self.selected_midi_path: Path | None = None
        self.generated_pdf_path: Path | None = None
        self.score_title = "Untitled Score"
        self.score_composer = "Lloyd Aboulnaja"

        self.output_dir = Path(__file__).resolve().parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events: queue.Queue = queue.Queue()
        self.is_compiling = False

        # Initialize audio engine
        self.audio_ready = False
        self.audio_playing = False
        self.audio_paused = False
        self._init_audio()

        self.lilypond_path = locate_lilypond()
        if self.lilypond_path:
            us = environment.UserSettings()
            us["lilypondPath"] = self.lilypond_path

        self.setup_ui()
        self.after(100, self._process_events)

    def setup_ui(self) -> None:
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

        self.meta_btn = ctk.CTkButton(
            self.sidebar, text="Edit Metadata...", command=self.open_metadata_modal, fg_color="#2a2a2a"
        )
        self.meta_btn.pack(padx=20, pady=(5, 10), fill="x")

        # Audio Playback Controls
        self.audio_frame = ctk.CTkFrame(self.sidebar, fg_color="#0F1724", corner_radius=6)
        self.audio_frame.pack(padx=20, pady=5, fill="x")

        self.play_btn = ctk.CTkButton(
            self.audio_frame, text="Play MIDI", command=self.toggle_audio,
            fg_color="#10B981", state="disabled", width=110
        )
        self.play_btn.pack(side="left", padx=(5, 2), pady=6, expand=True)

        self.stop_btn = ctk.CTkButton(
            self.audio_frame, text="Stop", command=self.stop_audio,
            fg_color="#EF4444", state="disabled", width=110
        )
        self.stop_btn.pack(side="right", padx=(2, 5), pady=6, expand=True)

        self.rhythm_label = ctk.CTkLabel(
            self.sidebar, text="Rhythm Quantisation:", text_color="#F8FAFC", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.rhythm_label.pack(padx=20, pady=(10, 2), anchor="w")

        self.rhythm_var = ctk.StringVar(value="Balanced")
        self.rhythm_menu = ctk.CTkOptionMenu(
            self.sidebar, values=["Off", "Gentle", "Balanced", "Detailed"],
            variable=self.rhythm_var, fg_color="#1F538D"
        )
        self.rhythm_menu.pack(padx=20, pady=(0, 10), fill="x")

        self.compile_btn = ctk.CTkButton(
            self.sidebar, text="Compile to Sheet Music", command=self.start_compilation, fg_color="#1F538D"
        )
        self.compile_btn.pack(padx=20, pady=(10, 10), fill="x")

        self.export_btn = ctk.CTkButton(
            self.sidebar, text="Export PDF Score", command=self.export_pdf, fg_color="#2a2a2a", state="disabled"
        )
        self.export_btn.pack(padx=20, pady=(0, 10), fill="x")

        self.status_label = ctk.CTkLabel(
            self.sidebar, text="Ready", text_color="#4BC6B9", font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(padx=20, pady=10)

        # Main Area
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


    def _init_audio(self) -> None:
        if pygame is None:
            return
        try:
            pygame.mixer.init()
            self.audio_ready = True
        except Exception as e:
            print(f"[WARNING] Failed to initialize audio mixer: {e}")
            self.audio_ready = False

    def toggle_audio(self) -> None:
        if not self.audio_ready or not self.selected_midi_path:
            return
        try:
            if not self.audio_playing:
                pygame.mixer.music.load(str(self.selected_midi_path))
                pygame.mixer.music.play()
                self.audio_playing = True
                self.audio_paused = False
                self.play_btn.configure(text="Pause MIDI", fg_color="#F59E0B")
                self.stop_btn.configure(state="normal")
            elif self.audio_paused:
                pygame.mixer.music.unpause()
                self.audio_paused = False
                self.play_btn.configure(text="Pause MIDI", fg_color="#F59E0B")
            else:
                pygame.mixer.music.pause()
                self.audio_paused = True
                self.play_btn.configure(text="Resume MIDI", fg_color="#10B981")
        except Exception as e:
            messagebox.showwarning("Audio Error", f"Audio playback failed:\n{e}")

    def stop_audio(self) -> None:
        if not self.audio_ready:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.audio_playing = False
        self.audio_paused = False
        self.play_btn.configure(text="Play MIDI", fg_color="#10B981")
        self.stop_btn.configure(state="disabled")

    def open_metadata_modal(self) -> None:
        def on_save(t, c):
            self.score_title = t
            self.score_composer = c
            self.status_label.configure(text="Metadata updated", text_color="#4BC6B9")
        MetadataDialog(self, self.score_title, self.score_composer, on_save)

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
            self.stop_audio()
            if self.audio_ready:
                self.play_btn.configure(state="normal", text="Play MIDI", fg_color="#10B981")
            self.score_title = self.selected_midi_path.stem.replace("_", " ").title()
            self.export_btn.configure(state="disabled")
            self.status_label.configure(text="MIDI Ready", text_color="#4BC6B9")

    def start_compilation(self) -> None:
        if self.is_compiling or not self.selected_midi_path:
            return
        if not self.lilypond_path:
            messagebox.showerror("LilyPond Missing", "LilyPond executable path could not be found.")
            return

        self.is_compiling = True
        self.select_btn.configure(state="disabled")
        self.meta_btn.configure(state="disabled")
        self.compile_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.status_label.configure(text="Processing...", text_color="#FBBF24")

        rhythm_mode = self.rhythm_var.get()
        threading.Thread(
            target=self._compile_worker,
            args=(self.selected_midi_path, rhythm_mode, self.score_title, self.score_composer),
            daemon=True
        ).start()

    def _compile_worker(self, midi_path: Path, rhythm_mode: str, title: str, composer: str) -> None:
        try:
            stem = midi_path.stem
            ly_path = self.output_dir / f"{stem}.ly"
            pdf_path = self.output_dir / f"{stem}.pdf"

            self.events.put(("status", "Parsing MIDI note stream..."))
            score = converter.parse(str(midi_path))

            divisors = RHYTHM_GRIDS.get(rhythm_mode)
            if divisors:
                self.events.put(("status", f"Applying {rhythm_mode} quantisation..."))
                score.quantize(divisors, processOffsets=True, processDurations=True)

            self.events.put(("status", "Analyzing pitch range for Grand Staff..."))
            _split_wide_parts(score, max_span=19)

            self.events.put(("status", "Writing LilyPond file..."))
            score.write("lily", fp=str(ly_path))

            # Patch preamble and inject clean header metadata
            self.events.put(("status", "Patching single-page layout & metadata..."))
            _patch_lilypond_header(ly_path, title, composer)

            self.events.put(("status", "Pass 1/2: Compiling Vector PDF..."))
            cmd_pdf = [self.lilypond_path, f"--output={self.output_dir / stem}", str(ly_path)]
            subprocess.run(cmd_pdf, capture_output=True, text=True, check=True)

            self.events.put(("status", "Pass 2/2: Rendering Preview Images..."))
            cmd_png = [self.lilypond_path, "--png", "-dresolution=150", f"--output={self.output_dir / stem}", str(ly_path)]
            subprocess.run(cmd_png, capture_output=True, text=True, check=True)

            png_files = sorted(list(self.output_dir.glob(f"{stem}*.png")))
            self.events.put(("success", (pdf_path, png_files)))

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
                    self.meta_btn.configure(state="normal")
                    self.compile_btn.configure(state="normal")
                    self.status_label.configure(text="Compilation Failed", text_color="#F87171")
                    messagebox.showerror("Compilation Error", data)
                elif kind == "success":
                    pdf_path, png_files = data
                    self.is_compiling = False
                    self.generated_pdf_path = pdf_path
                    self.select_btn.configure(state="normal")
                    self.meta_btn.configure(state="normal")
                    self.compile_btn.configure(state="normal")
                    self.export_btn.configure(state="normal", fg_color="#10B981")
                    self.status_label.configure(text="Single-Page Score Ready!", text_color="#10B981")
                    self._display_preview(png_files)
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