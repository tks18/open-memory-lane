import os
import shutil

from app.logger import logger
from app.helpers.lockfile import lock_path_for, is_lock_stale, remove_session_lock


def safe_copy_file(src: str, dst: str):
    """
    Copy src -> dst safely:
      - write to dst + '.part' then os.replace to be atomic.
      - preserves metadata via copy2.
    Returns True on success, False on failure.
    """
    try:
        dst_dir = os.path.dirname(dst)
        os.makedirs(dst_dir, exist_ok=True)
        tmp_dst = dst + ".part"
        # copy2 to tmp location
        shutil.copy2(src, tmp_dst)
        # atomic replace
        os.replace(tmp_dst, dst)
        return True
    except Exception:
        logger.exception("safe_copy_file failed: %s -> %s", src, dst)
        # cleanup tmp if exists
        try:
            if os.path.exists(tmp_dst):
                os.remove(tmp_dst)
        except Exception:
            pass
        return False


def copy_dir_contents(src_dir: str, dst_dir: str, skip_locked_sessions=True):
    """
    Copy everything inside src_dir into dst_dir (non-recursive expectation: day/session structure).
    Returns (copied_count, failed_count)
    """
    copied = 0
    failed = 0
    try:
        os.makedirs(dst_dir, exist_ok=True)
        for name in os.listdir(src_dir):
            src_path = os.path.join(src_dir, name)
            dst_path = os.path.join(dst_dir, name)
            if os.path.isdir(src_path):
                # if skipping locked sessions, check for lock
                lp = lock_path_for(src_path)
                if skip_locked_sessions:
                    if os.path.exists(lp):
                        try:
                            if is_lock_stale(src_path):
                                logger.warning(
                                    "Found stale lock (auto-removing): %s", lp)
                                remove_session_lock(src_path)
                            else:
                                # active session -> skip processing this session for now
                                continue
                        except Exception:
                            logger.exception("Error checking lock: %s", lp)
                            continue
                # ensure dst folder exists
                os.makedirs(dst_path, exist_ok=True)
                # copy all files inside that session folder
                for root, _, files in os.walk(src_path):
                    rel_root = os.path.relpath(root, src_dir)
                    for f in files:
                        sfile = os.path.join(root, f)
                        dfile = os.path.join(dst_dir, rel_root, f)
                        if safe_copy_file(sfile, dfile):
                            copied += 1
                        else:
                            failed += 1
            elif os.path.isfile(src_path):
                # single file (not expected for session structure) - copy directly
                if safe_copy_file(src_path, dst_path):
                    copied += 1
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
