"""
==========================
DB & File Backup Worker Module
==========================

This module provides a background worker for copying completed items from the local machine to a remote storage location.
It uses a queue to collect jobs, which are then executed in batches to optimize performance and reduce contention.
(Configure the `LOCAL_RETENTION_DAYS` setting in `.config.yml` to adjust the number of days to retain locally.)

Features:
- Implements a `BackupWorker` class that extends `threading.Thread`.
- Periodically moves completed items from TEMP → Backup Location
- Syncs DB to Archive
- Archives old records
- Prunes local DB for only Retention Days
- Cleans up stale lock files

Usage:
>>> backup_worker = BackupWorker(stop_event, thread_name="BackupWorker", interval_seconds=60 * 60)
>>> backup_worker.start()

*Author: Sudharshan TK*\n
*Created: 2025-08-31*
"""
from app.workers.backup.worker import *
