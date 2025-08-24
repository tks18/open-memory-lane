"""
==========================
Database - Archive Database SQL Statements
==========================

This module contains SQL statements for initializing and managing the archive database of the application.
This also gives the pragma statements for performance and concurrency optimizations in SQLite.

Features:
- Provides SQL Statements for creating tables and inserting data.
- Provides Performance and concurrency optimizations for SQLite.


Usage:
>>> from app.db import archive_db_sql_statements
>>> SQL_CREATE_TABLE_ARCHIVE_META  # Access the SQL statement for creating archive metadata table
>>> SQL_CREATE_INDEX_IMAGES_DAY_SESSION_PATH  # Access the SQL statement for creating index on images day and session path
>>> SQL_CREATE_INDEX_VIDEOS_DAY_SESSION_PATH  # Access the SQL statement for creating index on videos day and session path
>>> SQL_CREATE_INDEX_SUMMARIES_DAY_PATH  # Access the SQL statement for creating index on summaries day path
>>> SQL_CREATE_INDEX_IMAGES_CREATED_TS  # Access the SQL statement for creating index on images created timestamp
>>> SQL_CREATE_INDEX_VIDEOS_CREATED_TS  # Access the SQL statement for creating index on videos created timestamp
>>> SQL_CREATE_INDEX_SUMMARIES_CREATED_TS  # Access the SQL statement for creating index on summaries created timestamp
>>> SQL_INIT_ARCHIVE_DB_STATEMENTS  # Access the list of SQL statements to initialize the archive database

*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

from app.db.sql.common import *

# Archive Schema for long-term storage of processed data
SQL_CREATE_TABLE_ARCHIVE_META = """
        CREATE TABLE IF NOT EXISTS archive_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """

# IMPORTANT: create UNIQUE indexes to prevent duplicates (idempotent)
SQL_CREATE_INDEX_IMAGES_DAY_SESSION_PATH = "CREATE UNIQUE INDEX IF NOT EXISTS ui_images_day_session_path ON images(day, session, local_path)"
SQL_CREATE_INDEX_VIDEOS_DAY_SESSION_PATH = "CREATE UNIQUE INDEX IF NOT EXISTS ui_videos_day_session_path ON videos(day, session, local_path)"
SQL_CREATE_INDEX_SUMMARIES_DAY_PATH = "CREATE UNIQUE INDEX IF NOT EXISTS ui_summaries_day_path ON summaries(day, local_path)"

# Index on created_ts for efficient incremental queries
SQL_CREATE_INDEX_IMAGES_CREATED_TS = "CREATE INDEX IF NOT EXISTS idx_archive_images_created_ts ON images(created_ts)"
SQL_CREATE_INDEX_VIDEOS_CREATED_TS = "CREATE INDEX IF NOT EXISTS idx_archive_videos_created_ts ON videos(created_ts)"
SQL_CREATE_INDEX_SUMMARIES_CREATED_TS = "CREATE INDEX IF NOT EXISTS idx_archive_summaries_created_ts ON summaries(created_ts)"

SQL_INIT_ARCHIVE_DB_STATEMENTS = [
    SQL_PRAGMA_JOURNAL_MODE_WAL,
    SQL_PRAGMA_SYNCHRONOUS_NORMAL,

    SQL_CREATE_TABLE_IMAGE,
    SQL_CREATE_TABLE_VIDEO,
    SQL_CREATE_TABLE_SUMMARY,
    SQL_CREATE_TABLE_ARCHIVE_META,

    SQL_CREATE_INDEX_IMAGES_DAY_SESSION_PATH,
    SQL_CREATE_INDEX_VIDEOS_DAY_SESSION_PATH,
    SQL_CREATE_INDEX_SUMMARIES_DAY_PATH,

    SQL_CREATE_INDEX_IMAGES_CREATED_TS,
    SQL_CREATE_INDEX_VIDEOS_CREATED_TS,
    SQL_CREATE_INDEX_SUMMARIES_CREATED_TS
]
