"""
==========================
Helpers - Windows Idle Detection
==========================

This module provides helpers for Windows-specific functionality related to idle time detection.
It includes a function to get the idle time in seconds since the last user input.

Functions:
- `get_idle_time_seconds`: Returns the idle time in seconds since the last user input.
  It uses the Windows API to retrieve the last input time and calculates the idle time.
  If an error occurs, it logs the exception and returns 0.0, assuming the system is not idle.

Usage:
>>> from app.helpers.win import get_idle_time_seconds
>>> idle_time = get_idle_time_seconds()

*Author: Sudharshan TK*\n
*Created: 2025-08-23*
"""

import psutil
from ctypes import Structure, windll, c_uint, sizeof, byref
from win32 import win32gui, win32process

from app.logger import logger


class LASTINPUTINFO(Structure):
    """
    Structure to hold information about the last input event.
    """
    _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]


def get_idle_time_seconds() -> float:
    """
    Get the idle time in seconds since the last user input.
    This function uses the Windows API to retrieve the last input time
    and calculates the idle time in seconds.
    If an error occurs, it logs the exception and returns 0.0,
    assuming the system is not idle.

    Returns:
        float: Idle time in seconds since the last user input.
    """
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = sizeof(lii)
        windll.user32.GetLastInputInfo(byref(lii))
        millis = windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    except Exception as e:
        logger.exception("Idle detection failed; assuming not idle. %s", e)
        return 0.0


def get_active_window_info():
    """
    Get the Active Window Info such as title & app_name

    Returns:
        tuple(window_title, app_name): Tuple returning window_title & app_name
    """
    hwnd = win32gui.GetForegroundWindow()
    window_title = win32gui.GetWindowText(hwnd)

    try:
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        app_name = psutil.Process(pid).name()
    except Exception:
        app_name = "UnknownApp"

    return window_title, app_name
