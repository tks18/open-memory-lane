"""
==========================
File / Folder Copy Helper Functions
==========================

This module provides helper functions for copying files and directories with optimizations
for large datasets, including hash-based change detection and manifest management.

Features:
- `file_hash`: Compute SHA256 hash of a file.
- `load_hash_manifest`: Load a JSON manifest of file hashes for a directory.
- `save_hash_manifest`: Save a JSON manifest atomically, handling cloud storage locks.
- `safe_copy_file`: Copy a file safely with hash checks and manifest updates.
- `copy_dir_contents`: Copy all contents from one directory to another with optimizations.


Usage:
>>> from app.helpers.copy import copy_dir_contents
>>> copied, failed = copy_dir_contents('/path/to/src', '/path/to/dst')
>>> saved, manifest = safe_copy_file('/path/to/src/file.txt', '/path/to/dst/file.txt')

*Author: Sudharshan TK*\n
*Created: 2025-09-02*
"""

import time
import tempfile
import os
import shutil
import hashlib
import json
from datetime import datetime, UTC

from app.logger import logger
from app.helpers.lockfile import lock_path_for, is_lock_stale, remove_session_lock


def file_hash(path: str, chunk_size: int = 8192) -> str:
    """
    Compute SHA256 hash of a file.

    Args:
        path (str): Path to the file.
        chunk_size (int, optional): Chunk size for reading the file. Defaults to 8192.

    Returns:
        str: Hexadecimal SHA256 hash of the file.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hash_manifest(folder: str) -> dict:
    """
    Load hash manifest from .hashes.json in the given folder.
    Returns an empty dict if the manifest does not exist.

    Args:
        folder (str): Folder path to load the manifest from.

    Returns:
        dict: Manifest data mapping filenames to their hash info. {"filename": {"size": size, "mtime": mtime, "hash": hash, "last_backup": isotime}, ...}
    """
    manifest_path = os.path.join(folder, ".hashes.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.warning("Corrupt manifest, recreating: %s", manifest_path)
    return {}


def save_hash_manifest(folder: str, manifest: dict):
    """
    Save hash manifest to .hashes.json in the given folder atomically.
    Handles cloud storage locking issues with retries and fallbacks.

    Implementation:
    1. Write manifest to a temporary file in the same directory.
    2. Attempt to atomically replace the target manifest file with the temp file.
    3. If atomic replace fails (e.g., due to PermissionError from cloud storage locks), retry a few times.
    4. If still failing, fallback to overwriting the manifest file directly (non-atomic) with retries.
    5. Clean up temporary files and ensure durability with fsync where possible.

    Args:
        folder (str): Folder path to save the manifest in.
        manifest (dict): Manifest data to save.
    """

    manifest_path = os.path.join(folder, ".hashes.json")
    tmp_file = None
    tmp_path = None

    # Ensure target folder exists
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        logger.exception("Failed ensuring manifest folder exists: %s", folder)
        # Continue — the NamedTemporaryFile will likely fail next and be caught.

    try:
        # Create a temp file in the same directory so moves are atomic within same FS
        dirpath = os.path.dirname(manifest_path) or "."
        tmp = tempfile.NamedTemporaryFile(
            "w", delete=False, dir=dirpath, suffix=".part", encoding="utf-8")
        tmp_file = tmp
        tmp_path = tmp.name

        # Write JSON to temp file
        json.dump(manifest, tmp, indent=2, sort_keys=True)
        tmp.flush()

        # Ensure data hits disk (durability)
        try:
            os.fsync(tmp.fileno())
        except Exception:
            # fsync may fail on some platforms or file systems; best-effort
            logger.debug(
                "fsync temp manifest failed or not supported; continuing")

        tmp.close()
        tmp_file = None  # closed, safe to remove reference

        # Try atomic replace, with retries in case cloud storage briefly locks file
        replace_retries = 4
        replace_backoff = 0.25
        replaced = False
        for attempt in range(replace_retries):
            try:
                os.replace(tmp_path, manifest_path)
                replaced = True
                break
            except PermissionError:
                # PermissionError likely from cloud storage/antivirus locking the file.
                logger.debug("os.replace PermissionError on attempt %d for %s -> %s",
                             attempt + 1, tmp_path, manifest_path)
                if attempt < replace_retries - 1:
                    # small backoff
                    time.sleep(replace_backoff * (1 + attempt))
                    continue
                else:
                    # final attempt failed, will fallback below
                    logger.warning(
                        "Atomic replace failed due to PermissionError after %d attempts: %s", replace_retries, manifest_path)
            except Exception:
                # Some other unexpected error — re-raise to outer handler
                logger.exception(
                    "Unexpected error doing os.replace(%s, %s)", tmp_path, manifest_path)
                raise

        if not replaced:
            # Fallback: overwrite-in-place (non-atomic) with retries
            overwrite_retries = 3
            overwrite_backoff = 0.25
            written = False
            for attempt in range(overwrite_retries):
                try:
                    # Write directly to manifest_path (will create or truncate)
                    with open(manifest_path, "w", encoding="utf-8") as mf:
                        json.dump(manifest, mf, indent=2, sort_keys=True)
                        mf.flush()
                        try:
                            os.fsync(mf.fileno())
                        except Exception:
                            logger.debug(
                                "fsync manifest fallback failed or not supported; continuing")
                    written = True
                    break
                except PermissionError:
                    logger.debug(
                        "Fallback overwrite PermissionError attempt %d for %s", attempt + 1, manifest_path)
                    if attempt < overwrite_retries - 1:
                        time.sleep(overwrite_backoff * (1 + attempt))
                        continue
                    else:
                        logger.exception(
                            "Failed to overwrite manifest after retries: %s", manifest_path)
                except Exception:
                    logger.exception(
                        "Unexpected error while overwriting manifest: %s", manifest_path)
                    break

            # If fallback wrote the manifest, remove tmp_path if it still exists
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                logger.debug(
                    "Failed to remove tmp manifest after fallback: %s", tmp_path)

    except Exception:
        logger.exception("save_hash_manifest failed for folder: %s", folder)
        # Cleanup tmp file if present
        try:
            if tmp_file is not None:
                # if tmp_file still open, close it then remove
                try:
                    tmp_file.close()
                except Exception:
                    pass
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            logger.debug("Failed to cleanup tmp manifest file: %s", tmp_path)
        return

    # Best-effort: fsync parent directory so rename is durable (some OSes benefit)
    try:
        dir_fd = None
        try:
            dir_fd = os.open(dirpath, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            except Exception:
                logger.debug(
                    "fsync directory not supported or failed; continuing")
        finally:
            if dir_fd is not None:
                os.close(dir_fd)
    except Exception:
        logger.debug("Failed to fsync manifest directory: %s", dirpath)

    logger.debug("Manifest saved: %s", manifest_path)


def safe_copy_file(src: str, dst: str, manifest: dict | None = None) -> tuple[bool, dict]:
    """
    Copy a file from src to dst safely, using hash checks and updating the manifest.
    If the file already exists at dst with the same hash, it is not copied again.

    Args:
        src (str): Source file path.
        dst (str): Destination file path.
        manifest (dict | None, optional): Manifest dictionary. Defaults to None.

    Returns:
        tuple[bool, dict]: (True, updated_manifest) if copy succeeded or was unnecessary, (False, manifest) on failure.
    """
    tmp_dst = None
    try:
        dst_dir = os.path.dirname(dst)
        os.makedirs(dst_dir, exist_ok=True)

        # Load manifest if not provided
        if manifest is None:
            manifest = load_hash_manifest(dst_dir)

        rel_name = os.path.basename(dst)

        src_stat = os.stat(src)
        src_size = src_stat.st_size
        src_mtime = int(src_stat.st_mtime)

        entry = manifest.get(rel_name)

        # Quick check
        if entry and entry["size"] == src_size and entry["mtime"] == src_mtime:
            return True, manifest

        # Hash check
        src_hash = file_hash(src)
        if entry and entry["hash"] == src_hash:
            entry.update({
                "size": src_size,
                "mtime": src_mtime,
                "hash": src_hash,
                "last_backup": datetime.now(UTC).isoformat()
            })
            return True, manifest

        # Actual copy
        tmp_dst = dst + ".part"
        shutil.copy2(src, tmp_dst)
        os.replace(tmp_dst, dst)

        # Update manifest
        manifest[rel_name] = {
            "size": src_size,
            "mtime": src_mtime,
            "hash": src_hash,
            "last_backup": datetime.now(UTC).isoformat()
        }

        return True, manifest

    except Exception:
        logger.exception("safe_copy_file failed: %s -> %s", src, dst)
        try:
            if tmp_dst and os.path.exists(tmp_dst):
                os.remove(tmp_dst)
        except Exception:
            pass
        return False, manifest or {}


def copy_dir_contents(src_dir: str, dst_dir: str, skip_locked_sessions=True):
    """
    Copy all contents from src_dir to dst_dir, optimizing with hash manifests.
    Skips directories with active session locks if skip_locked_sessions is True.

    Args:
        src_dir (str): Source directory path.
        dst_dir (str): Destination directory path.
        skip_locked_sessions (bool, optional): Skip directories with active locks. Defaults to True.

    Returns:
        tuple[int, int]: Number of files copied, number of failures.
    """
    copied = 0
    failed = 0

    try:
        os.makedirs(dst_dir, exist_ok=True)

        for name in os.listdir(src_dir):
            src_path = os.path.join(src_dir, name)
            dst_path = os.path.join(dst_dir, name)

            if os.path.isdir(src_path):
                # Handle session locking
                lp = lock_path_for(src_path)
                if skip_locked_sessions and os.path.exists(lp):
                    try:
                        if is_lock_stale(src_path):
                            logger.warning(
                                "Found stale lock (auto-removing): %s", lp)
                            remove_session_lock(src_path)
                        else:
                            continue  # active session -> skip
                    except Exception:
                        logger.exception("Error checking lock: %s", lp)
                        continue

                os.makedirs(dst_path, exist_ok=True)

                # --- manifest optimization ---
                manifest = load_hash_manifest(dst_path)
                updated = False

                for root, _, files in os.walk(src_path):
                    # relative to current subfolder
                    rel_root = os.path.relpath(root, src_path)
                    dst_subdir = os.path.join(dst_path, rel_root)
                    os.makedirs(dst_subdir, exist_ok=True)

                    for f in files:
                        sfile = os.path.join(root, f)
                        dfile = os.path.join(dst_subdir, f)

                        ok, manifest = safe_copy_file(
                            sfile, dfile, manifest=manifest
                        )
                        if ok:
                            copied += 1
                            updated = True
                        else:
                            failed += 1

                if updated:
                    save_hash_manifest(dst_path, manifest)

            elif os.path.isfile(src_path):
                # Handle single file in root (rare for your structure)
                manifest = load_hash_manifest(dst_dir)
                ok, manifest = safe_copy_file(
                    src_path, dst_path, manifest=manifest)
                if ok:
                    copied += 1
                    save_hash_manifest(dst_dir, manifest)
                else:
                    failed += 1

    except Exception:
        logger.exception(
            "copy_dir_contents failed for %s -> %s", src_dir, dst_dir)

    return copied, failed


def ensure_remote_exists_for_day(local_day: str, local_root: str, remote_root: str) -> bool:
    """
    Check if the remote directory for a given day exists and is non-empty.

    Args:
        local_day (str): Day string in 'YYYY-MM-DD' format.
        local_root (str): Local root directory path.
        remote_root (str): Remote root directory path.

    Returns:
        bool: True if the remote directory exists and is non-empty, False otherwise.
    """
    try:
        # If detailed/day exists remotely, consider it safe.
        remote_day = os.path.join(remote_root, local_day)
        return os.path.isdir(remote_day) and bool(os.listdir(remote_day))
    except Exception:
        return False
