"""
==========================
Video Writer Worker Module
==========================

This module provides a background worker for creating videos from images
and concatenating daily summaries in an asynchronous, non-blocking way.

Features:
- Implements a `VideoWriter` class that extends `threading.Thread`.
- Collects video jobs in a queue (make or concat).
- Processes jobs one by one in the background.
- Provides methods to enqueue jobs and stop the worker gracefully.

Usage:
>>> video_writer = VideoWriter("VideoWorker")
>>> video_writer.start()
>>> video_writer.enqueue_make("captures/20250824_10", "videos/20250824_10.mp4")
>>> video_writer.enqueue_concat("20250824", "videos/summary_20250824.mp4")
>>> video_writer.stop()

*Author: Sudharshan TK*
*Created: 2025-08-24*
"""

import threading
import queue
import time
from app.logger import logger
from app.helpers.video import make_video_from_folder, concat_daily_videos
from app.workers.db_writer import DBWriter
from app.workers.db_writer.helpers import mark_summary, mark_video


class VideoWriter(threading.Thread):
    """
    Background worker for creating videos asynchronously.
    Jobs are enqueued via `enqueue_make` or `enqueue_concat`.
    The worker runs in a separate thread and executes ffmpeg jobs sequentially.
    """

    def __init__(self, thread_name: str, db_writer: DBWriter, flush_interval: float = 30 * 60):
        """
        Args:
            thread_name (str): Name of the worker thread.
            flush_interval (float): Time in seconds to wait for jobs before looping. Defaults to 2.0s.
        """
        super().__init__(name=thread_name, daemon=True)
        self.thread_name = thread_name
        self.flush_interval = flush_interval
        self.q = queue.Queue()
        self.db_writer = db_writer
        self.stop_event = threading.Event()

    def enqueue_detailed_video(self, folder: str, out_file: str, day: str, session: str, local_path: str, backup_path: str = None):
        """
        Enqueue a job to make a video from a folder of images.
        """
        self.q.put(("make", folder, out_file, day,
                   session, local_path, backup_path))

    def enqueue_summary_video(self, day: str, out_file: str, local_path: str, backup_path: str = None):
        """
        Enqueue a job to concatenate daily videos into a summary.
        """
        self.q.put(("concat", day, out_file, local_path, backup_path))

    def run(self):
        """
        Main worker loop — pulls jobs from the queue and processes them.
        Runs until stop_event is set, then flushes remaining jobs.
        """
        logger.info("Worker Started")
        while not self.stop_event.is_set():
            try:
                job = None
                try:
                    job = self.q.get(timeout=self.flush_interval)
                except queue.Empty:
                    continue  # no jobs, just loop again

                if not job:
                    continue

                job_type = job[0]
                if job_type == "make":
                    _, folder, out_file, day, session, local_path, backup_path = job
                    logger.info(
                        "Processing Detailed Video: %s -> %s", folder, out_file)
                    if make_video_from_folder(folder, out_file):
                        mark_video(self.db_writer, day, session,
                                   local_path, backup_path)
                elif job_type == "concat":
                    _, day, out_file, local_path, backup_path = job
                    logger.info(
                        "Processing Summary Video: day=%s -> %s", day, out_file)
                    if concat_daily_videos(day, out_file):
                        mark_summary(self.db_writer, day,
                                     local_path, backup_path)
                else:
                    logger.warning("Unknown job type: %s", job_type)

                self.q.task_done()
            except Exception:
                logger.exception(
                    "Worker loop exception")
                time.sleep(1)

        # Final flush
        self._flush_remaining()
        logger.info("Worker Stopped")

    def _flush_remaining(self):
        """Flush remaining jobs synchronously on stop."""
        logger.info("Flushing remaining jobs...")
        while not self.q.empty():
            try:
                job = self.q.get_nowait()
                job_type = job[0]
                if job_type == "make":
                    _, folder, out_file, day, session, local_path, backup_path = job
                    logger.info("Processing Detailed Video: %s -> %s",
                                folder, out_file)
                    if make_video_from_folder(folder, out_file):
                        mark_video(self.db_writer, day, session,
                                   local_path, backup_path)
                elif job_type == "concat":
                    _, day, out_file, local_path, backup_path = job
                    logger.info(
                        "Processing Summary Video: day=%s -> %s", day, out_file)
                    if concat_daily_videos(day, out_file):
                        mark_summary(self.db_writer, day,
                                     local_path, backup_path)
                self.q.task_done()
            except Exception:
                logger.exception("Error flushing job")

    def stop(self):
        """Stop the worker gracefully, flushing remaining jobs."""
        self.stop_event.set()
        self.join()
        logger.info("Worker Stopped")
