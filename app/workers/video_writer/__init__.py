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
from app.workers.video_writer.worker import *
