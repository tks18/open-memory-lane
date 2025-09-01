import os
import shutil
import hashlib

from app.logger import logger
from app.helpers.lockfile import lock_path_for, is_lock_stale, remove_session_lock


import os
import shutil
import hashlib
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def file_hash(path: str, chunk_size: int = 8192) -> str:
    """Return SHA256 hash of a file (streamed)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hash_manifest(folder: str) -> dict:
    """Load hash manifest for a folder, return dict {filename: {size, mtime, hash}}."""
    manifest_path = os.path.join(folder, ".hashes.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.warning("Corrupt manifest, recreating: %s", manifest_path)
    return {}


def save_hash_manifest(folder: str, manifest: dict):
    """Save hash manifest back to file (atomic)."""
    manifest_path = os.path.join(folder, ".hashes.json")
    tmp_path = manifest_path + ".part"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp_path, manifest_path)


def safe_copy_file(src: str, dst: str, manifest: dict | None = None) -> tuple[bool, dict]:
    """
    Copy src -> dst safely, using provided manifest if given.
    Returns (success, manifest).
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
                "last_backup": datetime.utcnow().isoformat()
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
            "last_backup": datetime.utcnow().isoformat()
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
    Copy everything inside src_dir into dst_dir.
    Optimized to use per-folder manifests for change detection.
    Returns (copied_count, failed_count).
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
    Quick existence check: are the expected remote paths present for a given day?
    Used to avoid deleting local content unless remote copy is present.
    """
    try:
        # If detailed/day exists remotely, consider it safe.
        remote_day = os.path.join(remote_root, local_day)
        return os.path.isdir(remote_day) and bool(os.listdir(remote_day))
    except Exception:
        return False
