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
from app.workers.db_writer.worker import DBWriter
from app.workers.db_writer.helpers import *
