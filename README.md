# Muscribe

Muscribe is a Python desktop app that converts MIDI files (`.mid` / `.midi`) into clean sheet music PDFs and previews. I built this as my EPQ project to combine music theory processing with a functional graphical interface.

---

## What It Does

* **Automated LilyPond Detection:** Searches your system paths and local directories for the LilyPond binary on startup so it works out of the box.
* **MIDI Parsing & Quantisation:** Uses `music21` to read note data and offers different rhythm cleanup settings (*Off*, *Gentle*, *Balanced*, *Detailed*) to fix timing issues.
* **Smart Grand Staff Splitting:** Automatically splits wide-ranging notes across treble and bass staves.
* **Dual-Pass Rendering:** Runs LilyPond separately for the PDF export and the PNG previews so a minor preview hiccup won't break your final score.
* **Built-in Playback:** Uses `pygame` to let you preview MIDI files right inside the app before converting them.

---

## Requirements & Tech Stack

* **Python 3.8+**
* **Libraries:** `customtkinter`, `pillow`, `mido`, `music21`, `pygame`
* **Engraving Engine:** [LilyPond](https://lilypond.org/) (must be installed on your machine)

---

## Setup & Running

1. **Clone the repo:**
   ```bash
   git clone [https://github.com/your-username/muscribe.git](https://github.com/your-username/muscribe.git)
   cd muscribet 