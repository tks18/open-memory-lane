"""
===========================
APP: Personal Memory Recorder
===========================

What it does: 
- Records periodic screenshots and webcam images, stores them in a local database.
- Provides a web interface for browsing and searching through the recorded memories.
- Supports Archiving of data at a regular interval.
- Uses a system tray application for easy access and control.
- Designed for Windows OS.

Author: Sudharshan TK \n
Github: https://github.com/tks18/open-memory-lane \n
License: GPLv3
"""
from app import start_app


if __name__ == "__main__":
    start_app()
