"""
==========================
Helpers - Configurations
==========================

This module provides configurations for the application, including paths for the main database, backup database, assets, and other directories.

Features:
- Loads configuration from a YAML file.
- Defines paths for the main application directories and backup directories.
- Defines constants for session management, video processing, and local retention settings.


Usage:
>>> import app.helpers.config as cfg
>>> print(cfg.APP_NAME)  # Access the application name

*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

import yaml
from pathlib import Path
import os

# =========================
# CONFIG
# =========================

# Load the ocnfiguration from a YAML file if it exists
with open(".config.yml", "r") as f:
    cfg = yaml.safe_load(f)

# App Name
APP_NAME = cfg["app"]["name"]

# Base Path
APP_BASE_DIR = Path(cfg["paths"]["base_dir"])
APP_BACKUP_BASE_DIR = Path(cfg["paths"]["backup_base_dir"])

# Main Dirs
BASE_DIR = Path(os.path.join(APP_BASE_DIR, APP_NAME))
LOG_FOLDER = Path(os.path.join(BASE_DIR, "Logs"))
DB_FOLDER = Path(os.path.join(BASE_DIR, "Database"))
ASSETS_DIR = Path(os.path.join(BASE_DIR, "Assets"))

# Backup Dirs
BACKUP_BASE_DIR = Path(os.path.join(APP_BACKUP_BASE_DIR, APP_NAME))
BACKUP_DB_FOLDER = Path(os.path.join(BACKUP_BASE_DIR, "Database"))
BACKUP_ASSETS_DIR = Path(os.path.join(BACKUP_BASE_DIR, "Assets"))

# DB Paths
DB_PATH = Path(os.path.join(DB_FOLDER, "pyrecall.db"))
BACKUP_DB_PATH = Path(os.path.join(BACKUP_DB_FOLDER, "pyrecall.db"))

# Asset Dirs
IMAGES_DIR = Path(os.path.join(ASSETS_DIR, "Images"))
TIMELAPSE_DIR = Path(os.path.join(ASSETS_DIR, "Timelapse"))
DETAILED_DIR = Path(os.path.join(TIMELAPSE_DIR, "Detailed"))
SUMMARY_DIR = Path(os.path.join(TIMELAPSE_DIR, "Summary"))

# Backup Asset Dirs
BACKUP_IMAGES_DIR = Path(os.path.join(BACKUP_ASSETS_DIR, "Images"))
BACKUP_TIMELAPSE_DIR = Path(os.path.join(BACKUP_ASSETS_DIR, "Timelapse"))
BACKUP_DETAILED_DIR = Path(os.path.join(BACKUP_TIMELAPSE_DIR, "Detailed"))
BACKUP_SUMMARY_DIR = Path(os.path.join(BACKUP_TIMELAPSE_DIR, "Summary"))

# All Paths Arrays
MAIN_PATHS = [
    APP_BASE_DIR,
    BASE_DIR, LOG_FOLDER, DB_FOLDER, ASSETS_DIR,
    IMAGES_DIR, TIMELAPSE_DIR, DETAILED_DIR, SUMMARY_DIR,
]

BACKUP_PATHS = [
    APP_BACKUP_BASE_DIR,
    BACKUP_BASE_DIR, BACKUP_DB_FOLDER, BACKUP_ASSETS_DIR,
    BACKUP_IMAGES_DIR, BACKUP_TIMELAPSE_DIR, BACKUP_DETAILED_DIR, BACKUP_SUMMARY_DIR
]

# Capture Configs
CAPTURE_INTERVAL = float(cfg["capture"]["interval"])
WEBP_QUALITY = int(cfg["capture"]["webp_quality"])
HASH_SIZE = int(cfg["capture"]["hash_size"])
HAMMING_THRESHOLD = int(cfg["capture"]["hamming_threshold"])
PERSISTENCE_FRAMES = int(cfg["capture"]["persistence_frames"])
AREA_SMALL_PXL = int(cfg["capture"]["area_small_pxl"])
AREA_SMALL = (AREA_SMALL_PXL, AREA_SMALL_PXL)
AREA_FRAC_THRESHOLD = float(cfg["capture"]["area_frac_threshold"])

# Video Configs
FFMPEG = str(cfg["video"]["ffmpeg"])
SESSION_VIDEO_FPS = int(cfg["video"]["fps"])
SUMMARY_VIDEO_FPS = int(cfg["video"]["summary_video_fps"])

# Session Configs
SESSION_MINUTES = int(cfg["session"]["minutes"])
IDLE_THRESHOLD = int(cfg["session"]["idle_threshold"])

# Local Retention & Backup Config
LOCAL_RETENTION_DAYS = int(cfg["local_retention"]["days"])
BACKUP_FREQUENCY_HOURS = int(cfg["local_retention"]["backup_freq_hrs"])

# Lock file Config
LOCK_STALE_MINUTES = int(cfg["session"]["lock_stale_minutes"])
LOCK_STALE_SECONDS = LOCK_STALE_MINUTES * 60

# Client Config
TIMELINE_LIMIT = cfg["client"]["timeline_limit"]
CLIENT_PORT = cfg["client"]["port"]
