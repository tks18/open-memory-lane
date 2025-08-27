# 🧠 Open Memory Lane

**Open-source, Memory-efficient & usable version of Windows Recall** — lightweight background capture + timelapse summaries, built for daily use. 🚀

---

## ✨ What it does
- 📸 Capture desktop screenshots as **WebP** (small, fast).  
- 🔎 Detect meaningful changes using **dhash_bits (OpenCV)** — fast perceptual hash; ignores tiny cursor flickers.  
- 🗄️ Store images + metadata (timestamp, session, wintitle, app name) in an **SQLite** index.  
- 🎞️ Build 15-min detailed clips and a short **daily timelapse summary** (timelapse speed derived from summary FPS vs detailed FPS).  
- 🔁 Robust backlog processing: missed videos/summaries are queued and created on next run.  
- 🖱️ System tray app to control / exit the recorder easily.

---

## ⚙️ Quick start
1. 🐣 Create venv & install:
   ```bash
   uv init
   .venv\Scripts\activate
   uv sync
   ```

2. 🛠️ Install **ffmpeg** and make sure it’s on your PATH.
3. ⚙️ Edit `.config.yml` (paths, fps, intervals) if needed.
4. ▶️ Run the tray app:

   ```bash
   uv run start_app.py
   ```

   or run the `start.bat`

   or build a single exe with PyInstaller and add a shortcut to `shell:startup` for autostart. ✨

---

## 📦 Minimal dependencies

* `mss`, `Pillow`, `numpy`, `opencv-python`, `pystray`
  (see `pyproject.toml`) ✅

---

## 🎯 Key design choices

* **WebP** for compact storage. 🗜️
* **dhash\_bits via OpenCV** for quick, low-false-positive change detection (mouse wiggles ignored). 🧠
* **SQLite** DB for metadata + reliable backlog processing (never lose pending processing). 💾
* **FFmpeg concat + per-image durations / fps-based timelapse** to create short, watchable daily summaries. 🎬

---

## 🧰 Use cases

* ⏱️ **Productivity tracking** — glance at a short visual timeline.
* 🎞️ **Video/Recap generation** — daily highlights in minutes.
* 💚 **Digital wellbeing** — understand app usage visually.

---

## 📝 Notes

* Runs CPU-only (no GPU required). ⚙️
* All data stays local — privacy-first. 🔒
* Want the summary always X minutes? tweak `summary_fps` in `.config.yml`. ⚙️

---

Sudharshan TK © 2025 — Built for simplicity & privacy. ❤️

---