"""
==========================
Database - Main Database SQL Statements
==========================

This module contains SQL statements for initializing and managing the main database of the application.
This also gives the pragma statements for performance and concurrency optimizations in SQLite.

Features:
- Provides SQL Statements for creating tables and inserting data.
- Provides Performance and concurrency optimizations for SQLite.


Usage:
>>> from app.db import main_db_sql_statements
>>> SQL_PRAGMA_TEMP_STORE_MEMORY  # Access the SQL statement for setting temp store to MEMORY
>>> SQL_CREATE_INDEX_IMAGES_CREATED_TS  # Access the SQL statement for creating index on images created timestamp
>>> SQL_CREATE_INDEX_IMAGES_DAY  # Access the SQL statement for creating index on images day
>>> SQL_CREATE_INDEX_VIDEOS_DAY  # Access the SQL statement for creating index on videos day
>>> SQL_CREATE_INDEX_SUMMARIES_DAY  # Access the SQL statement for creating index on summaries day
>>> SQL_INIT_DB_STATEMENTS  # Access the list of SQL statements to initialize the main database

*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

from app.db.sql.common import *

# Performance and concurrency tuning for Main Database
SQL_PRAGMA_TEMP_STORE_MEMORY = "PRAGMA temp_store=MEMORY;"

SQL_CREATE_INDEX_IMAGES_CREATED_TS = "CREATE INDEX IF NOT EXISTS idx_images_created_ts ON images(created_ts)"
SQL_CREATE_INDEX_IMAGES_DAY = "CREATE INDEX IF NOT EXISTS idx_images_day ON images(day)"
SQL_CREATE_INDEX_VIDEOS_DAY = "CREATE INDEX IF NOT EXISTS idx_videos_day ON videos(day)"
SQL_CREATE_INDEX_SUMMARIES_DAY = "CREATE INDEX IF NOT EXISTS idx_summaries_day ON summaries(day)"

SQL_INIT_DB_STATEMENTS = [
    SQL_PRAGMA_JOURNAL_MODE_WAL,
    SQL_PRAGMA_SYNCHRONOUS_NORMAL,
    SQL_PRAGMA_TEMP_STORE_MEMORY,

    SQL_CREATE_TABLE_IMAGE,
    SQL_CREATE_TABLE_VIDEO,
    SQL_CREATE_TABLE_SUMMARY,

    SQL_CREATE_INDEX_IMAGES_CREATED_TS,
    SQL_CREATE_INDEX_IMAGES_DAY,
    SQL_CREATE_INDEX_VIDEOS_DAY,
    SQL_CREATE_INDEX_SUMMARIES_DAY
]
