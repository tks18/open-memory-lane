"""
==========================
Logger Module
==========================

This module provides a logging setup for the application using Python's built-in logging library.
It supports both file and console logging, with options for rotating log files and using a queue for thread-safe logging.
It also includes a listener to process log records from the queue and write them to the appropriate handlers.

Features:
- Uses `QueueHandler` to send log records to a queue.
- Uses `QueueListener` to listen for log records and write them to file and console.
- Configurable log file size and backup count.
- Formats log messages with timestamp, level, thread name, and message.

Usage:
>>> import logging
>>> from app.logger import logger, log_queue, listener
>>> logger.info("This is an info message.")
>>> logger.error("This is an error message.")
>>> listener.stop()  # Important to stop the listener when done.

*Author: Sudharshan TK*\n
*Created: 2025-08-23*
"""

import logging
import logging.handlers
import os
import queue as std_queue
from typing import Optional

from app.helpers import config as default_config

# Public logger object other modules import
logger = logging.getLogger("myApp")
logger.setLevel(logging.INFO)

# If nothing configures logging, fall back to console so imports can safely log.
if not logger.handlers:
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s"))
    logger.addHandler(console)

# Internal state
_configured = False
_queue: Optional[std_queue.Queue] = None
_listener: Optional[logging.handlers.QueueListener] = None


def configure_client_logger():
    """
    Logger for Flask client only.
    Writes only to a file, no console output.
    """
    client_logger = logging.getLogger("client")
    client_logger.setLevel(logging.INFO)

    # Avoid adding multiple handlers if called multiple times
    if client_logger.handlers:
        return client_logger

    log_folder = default_config.LOG_FOLDER
    log_file = os.path.join(log_folder, "client.log")

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s"
    )

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    client_logger.addHandler(file_handler)

    return client_logger


def configure_logger():
    """
    Configure the logger with file and console handlers.
    This sets up a rotating file handler and a console handler.
    If `use_queue` is True, it uses QueueHandler and QueueListener for thread safety.
    This allows log messages to be processed in a thread-safe manner, especially useful
    in multi-threaded applications.

    Args:
        cfg: Configuration object containing settings like LOG_FILE.
        use_queue: If True, uses QueueHandler and QueueListener for thread-safe logging.
    """
    global _configured, _queue, _listener

    if _configured:
        return

    log_folder = default_config.LOG_FOLDER
    max_bytes = 5 * 1024 * 1024
    backup_count = 5
    level = logging.INFO

    log_file = os.path.join(log_folder, "workers.log")

    logger.setLevel(level)

    # Remove any lightweight/default handlers we added on import so they don't duplicate output
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s")

    # Create queue and a QueueHandler on the public logger
    _queue = std_queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(_queue)
    logger.addHandler(queue_handler)

    # Create real handlers that the listener will own

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    _listener = logging.handlers.QueueListener(
        _queue, file_handler, console_handler)
    _listener.start()

    _configured = True


def shutdown_logger():
    """
    Shutdown the logger by stopping the listener and closing all handlers.
    This function ensures that all log messages are flushed and handlers are closed properly.
    """
    global _listener

    if _listener:
        try:
            _listener.stop()
        except Exception:
            pass
        _listener = None

    handlers = list(logger.handlers)
    for h in handlers:
        try:
            h.flush()
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)
