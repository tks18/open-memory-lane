import os
import datetime
import time
import threading

import app.helpers.config as cfg
from app.logger import logger
from app.helpers.db import init_db, get_pending_video_sessions, get_pending_summary_days
from app.helpers.win import get_idle_time_seconds
from app.helpers.general import is_today
from app.workers.db_writer import DBWriter, mark_summary, mark_video
from app.workers.video_writer import VideoWriter
from app.helpers.paths import get_detailed_day_dir, new_session_labels, get_summary_month_dir, to_backup_equivalent
from app.helpers.lockfile import create_session_lock, cleanup_stale_locks, remove_session_lock
from app.helpers.screenshot import capture_screenshot
from app.helpers.video import make_video_from_folder, concat_daily_videos


IMAGES_DIR = cfg.IMAGES_DIR
DETAILED_DIR = cfg.DETAILED_DIR
SUMMARY_DIR = cfg.SUMMARY_DIR

BACKUP_DETAILED_DIR = cfg.BACKUP_DETAILED_DIR
BACKUP_SUMMARY_DIR = cfg.BACKUP_SUMMARY_DIR

SESSION_MINUTES = cfg.SESSION_MINUTES
CAPTURE_INTERVAL = cfg.CAPTURE_INTERVAL
IDLE_THRESHOLD = cfg.IDLE_THRESHOLD


class CaptureWorker(threading.Thread):
    """
    Background worker for capturing screenshots and creating videos.
    This class extends `threading.Thread` and uses a queue to collect jobs.
    uses db_writer and video_writer to write to the database and create videos.
    Configure the `CAPTURE_INTERVAL` and `IDLE_THRESHOLD` settings in `.config.yml` to adjust the frequency and threshold for capturing screenshots.
    """

    def __init__(self, stop_event: threading.Event, thread_name: str, db_writer: DBWriter, video_writer: VideoWriter):
        """
        Args:
            stop_event (threading.Event): stop event to signal the thread to stop
            thread_name (str): name of the thread
            db_writer (DBWriter): Db Writer Worker
            video_writer (VideoWriter): Video Writer Worker
        """
        super().__init__(name=thread_name, daemon=True)
        self.thread_name = thread_name
        self.stop_event = stop_event
        self.db_writer = db_writer
        self.video_writer = video_writer

    def run(self):
        """
        Main worker loop — captures screenshots and creates videos.
        Runs until `stop_event` is set, then flushes remaining jobs.
        """
        init_db()
        cleanup_stale_locks(IMAGES_DIR)
        self.process_backlog()

        last_img = None
        session_start_time = time.time()

        current_day = datetime.date.today().isoformat()
        day_images_dir = os.path.join(IMAGES_DIR, current_day)
        os.makedirs(day_images_dir, exist_ok=True)

        session_label = new_session_labels(datetime.datetime.now())
        session_dir = os.path.join(day_images_dir, session_label)
        os.makedirs(session_dir, exist_ok=True)

        create_session_lock(session_dir)

        last_backlog_sweep = time.time()

        self.process_backlog()

        logger.info("Worker started")
        while not self.stop_event.is_set():
            today = datetime.date.today().isoformat()
            if today != current_day:
                summary_dir = get_summary_month_dir(current_day)
                os.makedirs(summary_dir, exist_ok=True)
                summary_file = os.path.join(
                    summary_dir, f"{current_day}_summary.mp4")
                backup_summary = to_backup_equivalent(
                    summary_dir, SUMMARY_DIR, BACKUP_SUMMARY_DIR)
                if not os.path.exists(summary_file):
                    self.video_writer.enqueue_summary_video(
                        current_day, summary_file, summary_file, backup_summary)
                current_day = today
                day_images_dir = os.path.join(IMAGES_DIR, current_day)
                os.makedirs(day_images_dir, exist_ok=True)

            # Capture
            last_img = capture_screenshot(
                self.db_writer, last_img, session_dir, current_day, session_label)
            time.sleep(CAPTURE_INTERVAL)

            if time.time() - session_start_time >= SESSION_MINUTES * 60:
                day_dir = get_detailed_day_dir(current_day)
                os.makedirs(day_dir, exist_ok=True)
                out_file = os.path.join(
                    day_dir, f"{current_day}_{session_label}.mp4")
                if not os.path.exists(out_file):
                    backup_out = to_backup_equivalent(
                        out_file, DETAILED_DIR, BACKUP_DETAILED_DIR)
                    self.video_writer.enqueue_detailed_video(session_dir, out_file, current_day, session_label,
                                                             out_file, backup_out)

                remove_session_lock(session_dir)

                session_start_time = time.time()
                session_label = new_session_labels(datetime.datetime.now())
                session_dir = os.path.join(day_images_dir, session_label)
                os.makedirs(session_dir, exist_ok=True)
                create_session_lock(session_dir)

            if time.time() - last_backlog_sweep >= 5 * 60:
                if get_idle_time_seconds() >= IDLE_THRESHOLD:
                    self.process_backlog(current_session=(
                        current_day, session_label))
                last_backlog_sweep = time.time()

        logger.info("Worker stopped")

    def process_backlog(self, current_session=None):
        """
        Process backlog of Detailed & Summary videos.
        This method is called periodically to check for new videos to process.
        It checks the DB for pending videos and processes them one by one.

        Args:
            current_session (tuple, optional): Current session tuple (day, session_label). Defaults to None.
        """
        logger.info("Processing Backlogs")
        for day, session in get_pending_video_sessions():
            if current_session and (day, session) == current_session:
                continue

            folder = os.path.join(IMAGES_DIR, day, session)
            if not os.path.isdir(folder):
                continue

            if os.path.exists(os.path.join(folder, "session.lock")):
                continue

            day_dir = get_detailed_day_dir(day)
            os.makedirs(day_dir, exist_ok=True)
            out_file = os.path.join(day_dir, f"{day}_{session}.mp4")
            backup_out = to_backup_equivalent(
                out_file, DETAILED_DIR, BACKUP_DETAILED_DIR)
            logger.info(
                "Backlog - Creating detailed video for %s %s", day, session)
            self.video_writer.enqueue_detailed_video(
                folder, out_file, day, session, out_file, backup_out)

        for day in get_pending_summary_days():
            if is_today(day):
                continue

            month_dir = get_summary_month_dir(day)
            os.makedirs(month_dir, exist_ok=True)
            out_file = os.path.join(month_dir, f"{day}_summary.mp4")
            backup_summary = to_backup_equivalent(
                out_file, SUMMARY_DIR, BACKUP_SUMMARY_DIR)
            logger.info("Backlog - Creating summary for %s", day)
            self.video_writer.enqueue_summary_video(
                day, out_file, out_file, backup_summary)
