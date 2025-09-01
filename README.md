[![Commitizen friendly](https://img.shields.io/badge/commitizen-friendly-brightgreen.svg)](http://commitizen.github.io/cz-cli/) [![semantic-release](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg)](https://github.com/semantic-release/semantic-release)

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

## 🖥️ Client-side features

- 📜 **Scrollable Timeline View**
  - Navigate through your day visually with a smooth, zoomable timeline.
  - Jump to exact sessions (15-min detailed clips or daily summaries).
  - Filter by **app name**, **window title**, or **time range**.

- 🔎 **Query the Database**
  - Built-in query console to search the SQLite metadata:
    - Example: _“Show all Chrome windows between 2–4 PM”_
    - Example: _“List apps I used more than 30 mins today”_
  - Fast results with indexed lookups.

- 📤 **Export Data as CSV**
  - Export metadata (timestamp, app name, window title, etc.) into a clean CSV.
  - Perfect for analytics in Excel / Power BI / Python notebooks.
  - Optional: include file paths to screenshots for external use.

---

## 🧩 End-to-end workflow

1. **Capture**: lightweight background screenshots + metadata storage.
2. **Process**: timelapse clips auto-generated daily.
3. **Explore**: open the timeline view, scroll through your day.
4. **Query**: filter/search by apps, titles, or times.
5. **Export**: save your activity log to CSV for analysis or sharing.

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

- `mss`, `Pillow`, `numpy`, `opencv-python`, `pystray`
  (see `pyproject.toml`) ✅

---

## 🎯 Key design choices

- **WebP** for compact storage. 🗜️
- **dhash_bits via OpenCV** for quick, low-false-positive change detection (mouse wiggles ignored). 🧠
- **SQLite** DB for metadata + reliable backlog processing (never lose pending processing). 💾
- **FFmpeg concat + per-image durations / fps-based timelapse** to create short, watchable daily summaries. 🎬

---

## 🧰 Use cases

- ⏱️ **Productivity tracking** — glance at a short visual timeline.
- 🎞️ **Video/Recap generation** — daily highlights in minutes.
- 💚 **Digital wellbeing** — understand app usage visually.

---

## 📝 Notes

- Runs CPU-only (no GPU required). ⚙️
- All data stays local — privacy-first. 🔒
- Want the summary always X minutes? tweak `summary_fps` in `.config.yml`. ⚙️
- Want to change the capture interval? tweak `capture_interval` in `.config.yml`. ⚙️
- Want to change the WebP quality? tweak `webp_quality` in `.config.yml`. ⚙️

---

Sudharshan TK © 2025 — Built for simplicity & privacy. ❤️

[![GitHub](https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white)](https://github.com/sudharshan-tk/open-memory-lane)

---
