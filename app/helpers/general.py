"""
==========================
Helpers - General Operations
==========================

This module provides general helper functions for the application, including directory management and time utilities.

Features:
- `now_ms`: Get the current time in milliseconds since the epoch.
- `ensure_dirs`: Ensure all necessary directories exist by creating them if they do not.


Usage:
>>> from app.helpers.general import now_ms, ensure_dirs
>>> current_time = now_ms()  # Get current time in milliseconds
>>> ensure_dirs()  # Ensure all necessary directories exist

*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

import os
import datetime
import time

import app.helpers.config as cfg


def now_ms() -> int:
    """
    Get the current time in milliseconds since the epoch.

    Returns:
        int: Current time in milliseconds.
    """
    return int(time.time() * 1000)


def ensure_dirs() -> None:
    """
    Ensure all necessary directories exist by creating them if they do not.
    This function checks both main and backup paths defined in the configuration
    and creates them as needed.

    Returns:
        None
    """
    for d in cfg.MAIN_PATHS + cfg.BACKUP_PATHS:
        os.makedirs(d, exist_ok=True)


def is_today(day: str) -> bool:
    return day == datetime.date.today().isoformat()
