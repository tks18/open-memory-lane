import threading
import os
import datetime
import time
import shutil

import app.helpers.config as cfg
from app.logger import logger
from app.helpers.db import archive_old_records, sync_db_to_archive
from app.helpers.copy import safe_copy_file
from app.helpers.lockfile import cleanup_stale_locks

IMAGES_DIR = cfg.IMAGES_DIR
DETAILED_DIR = cfg.DETAILED_DIR
SUMMARY_DIR = cfg.SUMMARY_DIR
BACKUP_BASE_DIR = cfg.BACKUP_BASE_DIR
BACKUP_IMAGES_DIR = cfg.BACKUP_IMAGES_DIR
BACKUP_DETAILED_DIR = cfg.BACKUP_DETAILED_DIR
BACKUP_SUMMARY_DIR = cfg.BACKUP_SUMMARY_DIR

LOCAL_RETENTION_DAYS = cfg.LOCAL_RETENTION_DAYS


class BackupWorker(threading.Thread):
    """
    Periodically moves completed items from TEMP → OneDrive:
      - images: .../images/YYYY-MM-DD/(session) when session has no 'session.lock'
      - detailed: .../timelapse/detailed/YYYY-MM-DD when day < today
      - summary: .../timelapse/summary/YYYY-MM/ files for days < today
    """

    def __init__(self, stop_event: threading.Event, thread_name: str, interval_seconds: int = 3 * 60 * 60):
        super().__init__(name=thread_name, daemon=True)
        self.thread_name = thread_name
        self.stop_event = stop_event
        self.interval_seconds = interval_seconds

    def run(self):
        logger.info("Worker started")
        while not self.stop_event.is_set():
            try:
                today = datetime.date.today().isoformat()
                current_month = today[:7]

                # 1) IMAGES: copy session folders (skip locked sessions to avoid partial files)
                for day in os.listdir(IMAGES_DIR):
                    src_day = os.path.join(IMAGES_DIR, day)
                    if not os.path.isdir(src_day):
                        continue

                    dst_day = os.path.join(BACKUP_IMAGES_DIR, day)
                    os.makedirs(dst_day, exist_ok=True)

                    # Copy session folders' contents (safe copy)
                    for session in os.listdir(src_day):
                        src_session = os.path.join(src_day, session)
                        if not os.path.isdir(src_session):
                            continue
                        # still skip active sessions if lock exists
                        if os.path.exists(os.path.join(src_session, "session.lock")):
                            continue
                        dst_session = os.path.join(dst_day, session)
                        os.makedirs(dst_session, exist_ok=True)
                        # copy all files within session folder
                        for root, _, files in os.walk(src_session):
                            rel_root = os.path.relpath(root, src_day)
                            for f in files:
                                sfile = os.path.join(root, f)
                                # dst path keeps same relative structure
                                dfile = os.path.join(dst_day, rel_root, f)
                                safe_copy_file(sfile, dfile)

                    # clean up day folder if empty (only removes empty local dirs; do not delete files here)
                    try:
                        if os.path.isdir(src_day) and not os.listdir(src_day):
                            os.rmdir(src_day)
                    except Exception:
                        pass

                # 2) DETAILED: copy whole day directories for previous days (do NOT touch today's day)
                for day in os.listdir(DETAILED_DIR):
                    src_day_dir = os.path.join(DETAILED_DIR, day)
                    if not day or not os.path.isdir(src_day_dir):
                        continue
                    if day >= today:
                        continue
                    dst_day_dir = os.path.join(BACKUP_DETAILED_DIR, day)
                    # if destination doesn't exist, copy tree; otherwise copy missing files
                    if not os.path.isdir(dst_day_dir):
                        try:
                            shutil.copytree(src_day_dir, dst_day_dir,
                                            copy_function=shutil.copy2)
                        except FileExistsError:
                            # already created by another run; fall through to sync contents
                            pass
                        except Exception:
                            logger.exception(
                                "Failed copying detailed day %s -> %s", src_day_dir, dst_day_dir)
                    else:
                        # copy any new files inside src_day_dir to dst_day_dir
                        for root, _, files in os.walk(src_day_dir):
                            rel = os.path.relpath(root, src_day_dir)
                            target_root = os.path.join(dst_day_dir, rel)
                            os.makedirs(target_root, exist_ok=True)
                            for f in files:
                                sfile = os.path.join(root, f)
                                dfile = os.path.join(target_root, f)
                                safe_copy_file(sfile, dfile)

                # 3) SUMMARY: copy past months or earlier days in current month
                for month in os.listdir(SUMMARY_DIR):
                    src_month_dir = os.path.join(SUMMARY_DIR, month)
                    if not os.path.isdir(src_month_dir):
                        continue
                    dst_month_dir = os.path.join(BACKUP_SUMMARY_DIR, month)
                    os.makedirs(dst_month_dir, exist_ok=True)

                    if month < current_month:
                        # copy entire past month folder
                        if not os.path.isdir(os.path.join(BACKUP_SUMMARY_DIR, month)):
                            try:
                                shutil.copytree(
                                    src_month_dir, dst_month_dir, copy_function=shutil.copy2)
                            except Exception:
                                logger.exception(
                                    "Failed copying summary month: %s", src_month_dir)
                        else:
                            # sync files
                            for f in os.listdir(src_month_dir):
                                src_f = os.path.join(src_month_dir, f)
                                dst_f = os.path.join(dst_month_dir, f)
                                if os.path.isfile(src_f):
                                    safe_copy_file(src_f, dst_f)
                        continue

                    if month == current_month:
                        # copy only non-today summary files to remote
                        for f in os.listdir(src_month_dir):
                            if not f.endswith("_summary.mp4"):
                                continue
                            day_prefix = f.split("_summary.mp4")[
                                0]  # YYYY-MM-DD
                            if day_prefix < today:
                                src_f = os.path.join(src_month_dir, f)
                                dst_f = os.path.join(dst_month_dir, f)
                                safe_copy_file(src_f, dst_f)

                    # clean up month folder if empty
                    try:
                        if os.path.isdir(src_month_dir) and not os.listdir(src_month_dir):
                            os.rmdir(src_month_dir)
                    except Exception:
                        pass

                # 4) SYNC DB TO ARCHIVE
                try:
                    sync_db_to_archive()  # sync incremental rows up to now
                except Exception:
                    logger.exception("Periodic DB sync to archive failed")

                # 5) Archive old records & Prune Local DB for only Retention Days
                try:
                    time.sleep(0.25)
                    archive_old_records(LOCAL_RETENTION_DAYS)
                except Exception:
                    logger.exception("Archive pass failed")

                # 5) CLEANUP OLD FILES/FOLDERS (beyond LOCAL_RETENTION_DAYS)
                try:
                    cutoff = datetime.date.today() - datetime.timedelta(days=LOCAL_RETENTION_DAYS)

                    # IMAGES: only delete local day folder if it's older and remote has that day
                    if os.path.isdir(IMAGES_DIR):
                        for day in os.listdir(IMAGES_DIR):
                            day_path = os.path.join(IMAGES_DIR, day)
                            try:
                                day_date = datetime.date.fromisoformat(day)
                            except Exception:
                                continue
                            if day_date < cutoff and os.path.isdir(day_path):
                                # confirm remote copy exists for that day before deleting
                                remote_day = os.path.join(
                                    BACKUP_IMAGES_DIR, day)
                                if os.path.isdir(remote_day) and os.listdir(remote_day):
                                    shutil.rmtree(day_path, ignore_errors=True)

                    # DETAILED: remove local detailed day folders older than cutoff only if remote copy exists
                    if os.path.isdir(DETAILED_DIR):
                        for day in os.listdir(DETAILED_DIR):
                            day_path = os.path.join(DETAILED_DIR, day)
                            try:
                                day_date = datetime.date.fromisoformat(day)
                            except Exception:
                                continue
                            if day_date < cutoff and os.path.isdir(day_path):
                                backup_day = os.path.join(
                                    BACKUP_DETAILED_DIR, day)
                                if os.path.isdir(backup_day) and os.listdir(backup_day):
                                    shutil.rmtree(day_path, ignore_errors=True)

                    # SUMMARY: remove local summary files older than cutoff only if remote copy exists
                    if os.path.isdir(SUMMARY_DIR):
                        cutoff_month = cutoff.isoformat()[:7]
                        for month in os.listdir(SUMMARY_DIR):
                            month_path = os.path.join(SUMMARY_DIR, month)
                            if month < cutoff_month:
                                remote_month = os.path.join(
                                    BACKUP_SUMMARY_DIR, month)
                                # only prune if remote month exists
                                if os.path.isdir(remote_month) and os.listdir(remote_month):
                                    shutil.rmtree(
                                        month_path, ignore_errors=True)

                    cleanup_stale_locks(IMAGES_DIR)
                except Exception:
                    logger.exception("Retention cleanup failed")

            except Exception as e:
                logger.exception("Backup to Folder Failed: %s", e)

            self.stop_event.wait(self.interval_seconds)
        logger.info("Worker Stopped")
