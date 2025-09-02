import threading
import os
import datetime
import time
import shutil

import app.helpers.config as cfg
from app.logger import logger
from app.helpers.db import archive_old_records, sync_db_to_archive
from app.helpers.copy import copy_dir_contents, load_hash_manifest, save_hash_manifest, safe_copy_file
from app.helpers.lockfile import cleanup_stale_locks

IMAGES_DIR = cfg.IMAGES_DIR
DETAILED_DIR = cfg.DETAILED_DIR
SUMMARY_DIR = cfg.SUMMARY_DIR
BACKUP_BASE_DIR = cfg.BACKUP_BASE_DIR
BACKUP_IMAGES_DIR = cfg.BACKUP_IMAGES_DIR
BACKUP_DETAILED_DIR = cfg.BACKUP_DETAILED_DIR
BACKUP_SUMMARY_DIR = cfg.BACKUP_SUMMARY_DIR

LOCAL_RETENTION_DAYS = cfg.LOCAL_RETENTION_DAYS


def cleanup_old_files(retention_days: int):
    cutoff = datetime.date.today() - datetime.timedelta(days=retention_days)

    # Helper: check if folder has a manifest (non-empty backup)
    def has_backup(folder: str) -> bool:
        manifest_file = os.path.join(folder, ".hashes.json")
        return os.path.isfile(manifest_file)

    # IMAGES: delete old local day folders if remote backup exists
    if os.path.isdir(IMAGES_DIR):
        for day in os.listdir(IMAGES_DIR):
            day_path = os.path.join(IMAGES_DIR, day)
            try:
                day_date = datetime.date.fromisoformat(day)
            except Exception:
                continue
            if day_date < cutoff and os.path.isdir(day_path):
                remote_day = os.path.join(BACKUP_IMAGES_DIR, day)
                if os.path.isdir(remote_day) and has_backup(remote_day):
                    shutil.rmtree(day_path, ignore_errors=True)

    # DETAILED: remove old local detailed day folders if remote exists
    if os.path.isdir(DETAILED_DIR):
        for day in os.listdir(DETAILED_DIR):
            day_path = os.path.join(DETAILED_DIR, day)
            try:
                day_date = datetime.date.fromisoformat(day)
            except Exception:
                continue
            if day_date < cutoff and os.path.isdir(day_path):
                backup_day = os.path.join(BACKUP_DETAILED_DIR, day)
                if os.path.isdir(backup_day) and has_backup(backup_day):
                    shutil.rmtree(day_path, ignore_errors=True)

    # SUMMARY: remove local old summary months if remote exists
    if os.path.isdir(SUMMARY_DIR):
        cutoff_month = cutoff.isoformat()[:7]
        for month in os.listdir(SUMMARY_DIR):
            month_path = os.path.join(SUMMARY_DIR, month)
            if month < cutoff_month and os.path.isdir(month_path):
                remote_month = os.path.join(BACKUP_SUMMARY_DIR, month)
                if os.path.isdir(remote_month) and has_backup(remote_month):
                    shutil.rmtree(month_path, ignore_errors=True)

    # Cleanup stale locks
    cleanup_stale_locks(IMAGES_DIR)


class BackupWorker(threading.Thread):
    """
    Periodically moves completed items from TEMP → Backup:
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
                if os.path.isdir(IMAGES_DIR):
                    for day in os.listdir(IMAGES_DIR):
                        src_day = os.path.join(IMAGES_DIR, day)
                        if not os.path.isdir(src_day):
                            continue

                        dst_day = os.path.join(BACKUP_IMAGES_DIR, day)
                        os.makedirs(dst_day, exist_ok=True)

                        for session in os.listdir(src_day):
                            src_session = os.path.join(src_day, session)
                            if not os.path.isdir(src_session):
                                continue
                            if os.path.exists(os.path.join(src_session, "session.lock")):
                                continue

                            dst_session = os.path.join(dst_day, session)
                            os.makedirs(dst_session, exist_ok=True)

                            # ✅ use manifest-aware copy
                            copy_dir_contents(
                                src_session, dst_session, skip_locked_sessions=True)

                        # cleanup empty day
                        try:
                            if os.path.isdir(src_day) and not os.listdir(src_day):
                                os.rmdir(src_day)
                        except Exception:
                            pass

                # 2) DETAILED: copy whole day directories (skip today)
                if os.path.isdir(DETAILED_DIR):
                    for day in os.listdir(DETAILED_DIR):
                        src_day_dir = os.path.join(DETAILED_DIR, day)
                        if not day or not os.path.isdir(src_day_dir):
                            continue
                        if day >= today:
                            continue

                        dst_day_dir = os.path.join(BACKUP_DETAILED_DIR, day)
                        os.makedirs(dst_day_dir, exist_ok=True)

                        # ✅ use manifest-aware copy instead of manual os.walk
                        copy_dir_contents(
                            src_day_dir, dst_day_dir, skip_locked_sessions=False)

                # 3) SUMMARY: copy past months or earlier days in current month
                if os.path.isdir(SUMMARY_DIR):
                    for month in os.listdir(SUMMARY_DIR):
                        src_month_dir = os.path.join(SUMMARY_DIR, month)
                        if not os.path.isdir(src_month_dir):
                            continue

                        dst_month_dir = os.path.join(BACKUP_SUMMARY_DIR, month)
                        os.makedirs(dst_month_dir, exist_ok=True)

                        if month < current_month:
                            copy_dir_contents(
                                src_month_dir, dst_month_dir, skip_locked_sessions=False)
                            continue

                        if month == current_month:
                            cutoff_day = datetime.date.today() - datetime.timedelta(days=2)
                            # ✅ copy only non-today summaries
                            manifest = load_hash_manifest(dst_month_dir)
                            updated = False

                            for f in os.listdir(src_month_dir):
                                if not f.endswith("_summary.mp4"):
                                    continue
                                day_prefix = f.split("_summary.mp4")[0]
                                try:
                                    file_date = datetime.date.fromisoformat(
                                        day_prefix)
                                except ValueError:
                                    continue  # skip weird filenames
                                if file_date <= cutoff_day:
                                    src_f = os.path.join(src_month_dir, f)
                                    dst_f = os.path.join(dst_month_dir, f)
                                    ok, manifest = safe_copy_file(
                                        src_f, dst_f, manifest)
                                    if ok:
                                        updated = True

                            if updated:
                                save_hash_manifest(dst_month_dir, manifest)

                        # cleanup month folder if empty
                        try:
                            if os.path.isdir(src_month_dir) and not os.listdir(src_month_dir):
                                os.rmdir(src_month_dir)
                        except Exception:
                            pass

                # 4) SYNC DB TO ARCHIVE
                try:
                    sync_db_to_archive()
                except Exception:
                    logger.exception("Periodic DB sync to archive failed")

                # 5) Archive + prune local DB
                try:
                    time.sleep(0.25)
                    archive_old_records(LOCAL_RETENTION_DAYS)
                except Exception:
                    logger.exception("Archive pass failed")

                # 6) CLEANUP OLD FILES/FOLDERS (retention cutoff)
                try:
                    cleanup_old_files(LOCAL_RETENTION_DAYS)
                except Exception:
                    logger.exception("Retention cleanup failed")

            except Exception as e:
                logger.exception("Backup to Folder Failed: %s", e)

            self.stop_event.wait(self.interval_seconds)

        logger.info("Worker Stopped")
