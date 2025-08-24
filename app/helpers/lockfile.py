"""
==========================
Helpers - Lock File Management
==========================

This module provides functions to manage session lock files, ensuring that only 
one instance of the application can access a session directory at a time. 
It includes functions to create, remove, and check the status of lock files,
and to clean up stale locks that may occur due to unexpected application terminations.

Functions:
- `lock_path_for`: Get the path for the session lock file.
- `create_session_lock`: Create a session lock file in the specified directory.
- `remove_session_lock`: Remove the session lock file from the specified directory.
- `read_lock_metadata`: Read metadata from the session lock file.
- `is_pid_alive`: Check if a process with the given PID is alive.
- `is_lock_stale`: Check if the session lock is stale based on PID and timestamp.
- `cleanup_stale_locks`: Cleanup stale session locks in the specified root images directory.


Usage:
>>> from app.helpers.lockfile import (
    lock_path_for, create_session_lock, remove_session_lock,
    read_lock_metadata, is_pid_alive, is_lock_stale, cleanup_stale_locks
    )
>>> session_dir = "/path/to/session"
>>> create_session_lock(session_dir)  # Create a lock file for the session
>>> metadata = read_lock_metadata(session_dir)  # Read lock metadata
>>> is_stale = is_lock_stale(session_dir)  # Check if the lock is stale
>>> if is_stale:
    remove_session_lock(session_dir)  # Remove stale lock if necessary
>>> cleanup_stale_locks("/path/to/root/images")  # Cleanup stale locks in the root images directory
>>> is_pid_alive(metadata['pid'])  # Check if the process with the lock's PID is alive

*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

import os
import datetime
import json
import psutil

from app.logger import logger
from app.helpers.config import LOCK_STALE_SECONDS


def lock_path_for(session_dir: str) -> str:
    """
    Get the path for the session lock file.

    Args:
        session_dir (str): The directory where the session is stored.

    Returns:
        str: The full path to the session lock file.
    """

    return os.path.join(session_dir, "session.lock")


def create_session_lock(session_dir: str):
    """
    Create a session lock file in the specified directory.

    Args:
        session_dir (str): The directory where the session is stored.
    """

    os.makedirs(session_dir, exist_ok=True)
    lp = lock_path_for(session_dir)
    data = {"pid": os.getpid(), "ts": datetime.datetime.now(
        datetime.UTC).isoformat()}
    tmp = lp + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, lp)
    except Exception:
        # best-effort atomic write fallback
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        try:
            with open(lp, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            logger.exception("Failed to create lock at %s", lp)


def remove_session_lock(session_dir: str):
    """
    Remove the session lock file from the specified directory.

    Args:
        session_dir (str): The directory where the session is stored.
    """

    lp = lock_path_for(session_dir)
    try:
        if os.path.exists(lp):
            os.remove(lp)
    except Exception:
        logger.exception("Failed to remove session lock: %s", lp)


def read_lock_metadata(session_dir: str):
    """
    Read the metadata from the session lock file.

    Args:
        session_dir (str): The directory where the session is stored.

    Returns:
        _type_: A dictionary containing the lock metadata, or None if the lock file is unreadable.
    """

    lp = lock_path_for(session_dir)
    try:
        with open(lp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_pid_alive(pid: int) -> bool:
    """
    Check if a process with the given PID is alive.

    Args:
        pid (int): The process ID to check.

    Returns:
        bool: True if the process is alive, False otherwise.
    """

    try:
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def is_lock_stale(session_dir: str) -> bool:
    """
    Check if the session lock is stale.

    Args:
        session_dir (str): The directory where the session is stored.

    Returns:
        bool: True if the lock is stale, False otherwise.
    """

    meta = read_lock_metadata(session_dir)
    if not meta:
        # unreadable lock -> treat stale
        return True
    pid = meta.get("pid")
    ts = meta.get("ts")
    # if pid not alive -> stale
    try:
        if pid is not None and not is_pid_alive(pid):
            return True
    except Exception:
        pass
    # check timestamp age (UTC)
    try:
        lock_time = datetime.datetime.fromisoformat(ts)
        age_sec = (datetime.datetime.now(
            datetime.UTC) - lock_time).total_seconds()
        if age_sec > LOCK_STALE_SECONDS:
            return True
    except Exception:
        # parsing problem -> treat stale
        return True
    return False


def cleanup_stale_locks(root_images_dir: str):
    """
    Cleanup stale session locks in the specified root images directory. 
    This function iterates through all session directories under the given 
    root directory and checks if their lock files are stale. 
    If a stale lock is found, it is removed.

    Args:
        root_images_dir (str): The root directory containing session directories with lock files.
    """
    try:
        if not os.path.isdir(root_images_dir):
            return
        for day in os.listdir(root_images_dir):
            day_path = os.path.join(root_images_dir, day)
            if not os.path.isdir(day_path):
                continue
            for session in os.listdir(day_path):
                session_path = os.path.join(day_path, session)
                lp = lock_path_for(session_path)
                if not os.path.exists(lp):
                    continue
                try:
                    if is_lock_stale(session_path):
                        logger.warning("Removing stale lock: %s", lp)
                        remove_session_lock(session_path)
                except Exception:
                    logger.exception(
                        "Error checking/removing stale lock: %s", lp)
    except Exception:
        logger.exception("cleanup_stale_locks failed for %s", root_images_dir)
