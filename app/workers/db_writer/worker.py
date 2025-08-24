"""
==========================
Database Writer Worker Module
==========================

This module provides a background worker for writing to the main database in a batched and asynchronous manner.
It uses a queue to collect SQL commands and parameters, which are then executed in batches to optimize performance and reduce contention.


Features:
- Implements a `DBWriter` class that extends `threading.Thread`.
- Collects SQL commands and parameters in a queue.
- Executes the queued commands in batches with a configurable batch size and flush interval.
- Provides methods to enqueue SQL commands and stop the worker gracefully.


Usage:
>>> from app.workers.db_writer import DBWriter
>>> db_writer = DBWriter(db_path="path/to/database.db")
>>> db_writer.start()  # Start the background writer thread
>>> db_writer.enqueue("INSERT INTO table_name (column1, column2) VALUES (?, ?)", (value1, value2))  # Enqueue a write operation


*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

import threading
import queue
import sqlite3
import time
from pathlib import Path

from app.logger import logger


class DBWriter(threading.Thread):
    """
    Background worker for writing to the main database in batches.
    This class extends `threading.Thread` and uses a queue to collect SQL commands
    and parameters, which are then executed in batches to optimize performance and reduce contention.
    Features:
    - Collects SQL commands and parameters in a queue.
    - Executes the queued commands in batches with a configurable batch size and flush interval.
    - Provides methods to enqueue SQL commands and stop the worker gracefully.
    Usage:
    >>> from app.workers.db_writer import DBWriter
    >>> db_writer = DBWriter(db_path=Path("path/to/database.db"))
    >>> db_writer.start()  # Start the background writer thread
    >>> db_writer.enqueue("INSERT INTO table_name (column1, column2) VALUES (?, ?)", (value1, value2))  # Enqueue a write operation
    """

    def __init__(self, thread_name: str, db_path: Path, batch_size: int = 200, flush_interval: float = 2.0):
        """
        Initialize the DBWriter worker.
        This constructor sets up the database path, batch size, flush interval,
        and initializes the queue for collecting SQL commands.

        Args:
            db_path (Path): Path to the SQLite database file.
            batch_size (int, optional): Number of SQL commands to batch together before executing. Defaults to 200.
            flush_interval (float, optional): Time in seconds to wait before flushing the queue if no new items are added. Defaults to 2.0 seconds.
        """
        super().__init__(name=thread_name, daemon=True)
        self.thread_name = thread_name
        self.db_path = str(db_path)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.q = queue.Queue()
        self.stop_event = threading.Event()

    def enqueue(self, sql: str, params=()):
        """
        Enqueue a SQL command and its parameters for batch execution.
        This method adds a tuple of SQL command and parameters to the internal queue.

        Args:
            sql (str): The SQL command to execute.
            params (tuple, optional): The parameters to bind to the SQL command. Defaults to an empty tuple.
        """
        self.q.put((sql, params))

    def run(self):
        """
        The main loop of the DBWriter worker.
        This method runs in a separate thread and continuously checks the queue for SQL commands.
        It collects commands in batches and executes them against the SQLite database.
        It will run until the `stop_event` is set, at which point it will flush any remaining items in the queue.
        """
        logger.info("[%s] DBWriter started", self.thread_name)
        while not self.stop_event.is_set():
            items = []
            try:
                # block for up to flush_interval waiting for first item
                try:
                    item = self.q.get(timeout=self.flush_interval)
                    items.append(item)
                except queue.Empty:
                    # nothing to flush; continue loop
                    continue

                # drain up to batch_size
                while len(items) < self.batch_size:
                    try:
                        items.append(self.q.get_nowait())
                    except queue.Empty:
                        break

                # perform batched transaction
                conn = sqlite3.connect(self.db_path, timeout=30)
                cur = conn.cursor()
                try:
                    cur.execute("BEGIN")
                    for sql, params in items:
                        cur.execute(sql, params)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    logger.exception("DBWriter transaction failed")
                finally:
                    conn.close()
            except Exception:
                logger.exception("DBWriter run loop exception")
                # slight sleep to avoid tight loop on repeated failures
                time.sleep(1)

    def stop(self):
        self.stop_event.set()
        # flush remaining items synchronously
        remaining = []
        while not self.q.empty():
            remaining.append(self.q.get_nowait())
        if remaining:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cur = conn.cursor()
            try:
                cur.execute("BEGIN")
                for sql, params in remaining:
                    cur.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("DBWriter final flush failed")
            finally:
                conn.close()
