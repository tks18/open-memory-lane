"""
==========================
Worker Management Module
==========================

This module provides a set of worker threads for different tasks, including CaptureWorker, DBWriter, BackupWorker, and VideoWriter.
It also includes a function for gracefully shutting down all the workers.

Features:
- Implements a `CaptureWorker` class that extends `threading.Thread`.
- Collects jobs in a queue.
- Processes jobs one by one in the background.
- Provides methods to enqueue jobs and stop the worker gracefully.

- Implements a `DBWriter` class that extends `threading.Thread`.
- Collects SQL commands and parameters in a queue.
- Executes the queued commands in batches with a configurable batch size and flush interval.
- Provides methods to enqueue SQL commands and stop the worker gracefully.

- Implements a `BackupWorker` class that extends `threading.Thread`.
- Periodically moves completed items from TEMP → Backup Location
- Syncs DB to Archive
- Archives old records
- Prunes local DB for only Retention Days
- Cleans up stale lock files

- Implements a `VideoWriter` class that extends `threading.Thread`.
- Collects video jobs in a queue (make or concat).
- Processes jobs one by one in the background.
- Provides methods to enqueue jobs and stop the worker gracefully.


Usage:
>>> capture_worker = CaptureWorker(stop_event, thread_name="CaptureWorker", db_writer, video_writer)
>>> capture_worker.start()  # Start the background worker thread
>>> db_writer = DBWriter(thread_name="DBWriterThread", db_path=DB_PATH)
>>> db_writer.start()  # Start the background writer thread
>>> backup_thread = BackupWorker(thread_name="BackupThread", interval_seconds=3 * 60 * 60)
>>> backup_thread.start()  # Start the backup worker thread
>>> video_thread = VideoWriter(thread_name="VideoWriterThread", db_writer=db_writer, flush_interval=1 * 60)
>>> video_thread.start()  # Start the video writer worker thread
>>> graceful_workers_shutdown(icon, item, stop_event, workers, writer_workers)

*Author: Sudharshan TK*\n
*Created: 2025-08-31*
"""

import os
import sys
import threading
import time

from app.workers.capture import CaptureWorker
from app.workers.db_writer import DBWriter
from app.workers.backup import BackupWorker
from app.workers.video_writer import VideoWriter
from app.workers.client import run_flask_thread

from app.logger import logger, shutdown_logger


def graceful_workers_shutdown(icon, item, stop_event: threading.Event, workers: list[threading.Thread], writer_workers: list[threading.Thread]):
    """
    Graceful shutdown sequence:
      1. signal workers to stop (stop_event)
      2. give workers a short time to finish
      3. stop+join db_writer (flushes pending DB writes)
      4. join other background threads if available (worker, backup_thread)
      5. stop the tray icon
    """
    logger.info("Beginning graceful shutdown...")

    try:
        # 1) Signal threads to stop (producers/consumers should watch this)
        try:
            stop_event.set()
        except Exception:
            logger.exception("Failed to set stop_event")

        # 2) small pause to let producers stop enqueuing quickly
        time.sleep(0.25)

        # 3) Join Main worker threads (best-effort — they may be local variables)
        for thr in workers:
            logger.info("Waiting for thread %s to stop...", thr.name)
            try:
                thr.join(timeout=5.0)
                if thr.is_alive():
                    logger.warning(
                        "Thread %s still alive after timeout", thr.name)
            except Exception:
                logger.exception("Error joining thread %s", thr.name)

        # 4) Stop Writer Workers (flush pending writes) then join it
        for thr in writer_workers:
            if thr is not None:
                try:
                    logger.info("Trying to Stop Thread %s...", thr.name)
                    # db_writer.stop() flushes remaining queue synchronously per earlier implementation
                    thr.stop()
                    # join the thread to ensure it has exited
                    thr.join(timeout=5.0)
                    if thr.is_alive():
                        logger.warning(
                            "%s still alive after join timeout", thr.name)
                except Exception:
                    logger.exception("Failed stopping/joining db_writer")

        logger.info("Stopping Logger Queue...")
        shutdown_logger()  # stop the listener thread if it exists

    except Exception:
        logger.exception("Unexpected error during on_exit")

    finally:
        # Always attempt to stop the tray icon (UI exit)
        try:
            icon.stop()
            try:
                sys.exit(0)
            except SystemExit:
                os._exit(0)

        except Exception:
            # last resort — log and ignore
            logger.exception("Failed to stop tray icon")
