"""
==========================
Screenshot Capture Worker Module
==========================

This module provides a background worker for capturing screenshots and creating videos.
It uses a queue to collect jobs, which are then executed in batches to optimize performance and reduce contention.
(Configure the `CAPTURE_INTERVAL` and `IDLE_THRESHOLD` settings in `.config.yml` to adjust the frequency and threshold for capturing screenshots.)


Features:
- Implements a `CaptureWorker` class that extends `threading.Thread`.
- Collects jobs in a queue.
- Processes jobs one by one in the background.
- Provides methods to enqueue jobs and stop the worker gracefully.

Usage:
>>> from app.workers.capture import CaptureWorker
>>> capture_worker = CaptureWorker(stop_event, thread_name="CaptureWorker", db_writer, video_writer)
>>> capture_worker.start()  # Start the background worker thread


*Author: Sudharshan TK*\n
*Created: 2025-08-31*
"""
from app.workers.capture.worker import *
