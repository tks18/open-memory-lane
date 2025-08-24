"""
==========================
Database - Common SQL Statements
==========================

This module provides common SQL statements for initializing and managing the application's main and archive databases.
This also gives the pragma statements for performance and concurrency optimizations in SQLite.

Features:
- Gives SQL Statements for creating tables and inserting data.
- Gives Performance and concurrency optimizations for SQLite.


Usage:
>>> from app.db import common_sql_statements
>>> SQL_PRAGMA_JOURNAL_MODE_WAL  # Access the SQL statement for setting journal mode to WAL
>>> SQL_PRAGMA_SYNCHRONOUS_NORMAL  # Access the SQL statement for setting synchronous mode to NORMAL
>>> SQL_CREATE_TABLE_IMAGE  # Access the SQL statement for creating the images table
>>> SQL_CREATE_TABLE_VIDEO  # Access the SQL statement for creating the videos table
>>> SQL_CREATE_TABLE_SUMMARY  # Access the SQL statement for creating the summaries table
>>> SQL_INSERT_IMAGE  # Access the SQL statement for inserting an image record
>>> SQL_INSERT_VIDEO  # Access the SQL statement for inserting a video record
>>> SQL_INSERT_SUMMARY  # Access the SQL statement for inserting a summary record
>>> SQL_GET_PENDING_VIDEO_SESSIONS  # Access the SQL statement for fetching pending video sessions
>>> SQL_GET_PENDING_SUMMARY_SESSIONS  # Access the SQL statement for fetching pending summary days

*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

# Common Performance and concurrency optimizations for SQLite database operations
SQL_PRAGMA_JOURNAL_MODE_WAL = "PRAGMA journal_mode=WAL;"
SQL_PRAGMA_SYNCHRONOUS_NORMAL = "PRAGMA synchronous=NORMAL;"

# SQL Common Create Statements for Main and Archive Databases
SQL_CREATE_TABLE_IMAGE = """CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        session TEXT,      -- HHMM-HHMM
        local_path TEXT,
        backup_path TEXT,
        win_title TEXT,
        win_app TEXT,
        created_ts INTEGER, -- UNIX timestamp of when the image was captured
        processed INTEGER DEFAULT 0
    )"""

SQL_CREATE_TABLE_VIDEO = """CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        session TEXT,      -- HHMM-HHMM
        local_path TEXT,
        backup_path TEXT,
        created_ts INTEGER, -- UNIX timestamp of when the video was created
        processed INTEGER DEFAULT 1
    )"""

SQL_CREATE_TABLE_SUMMARY = """CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        local_path TEXT,
        backup_path TEXT,
        created_ts INTEGER, -- UNIX timestamp of when the summary was created
        processed INTEGER DEFAULT 1
    )"""

SQL_GET_PENDING_VIDEO_SESSIONS = """
        SELECT DISTINCT day, session
        FROM images i
        WHERE NOT EXISTS (
            SELECT 1 FROM videos v
            WHERE v.day = i.day AND v.session = i.session
        )
        ORDER BY day, session
    """

SQL_GET_PENDING_SUMMARY_SESSIONS = """
        SELECT day
        FROM videos
        WHERE NOT EXISTS (
            SELECT 1 FROM summaries s WHERE s.day = videos.day
        )
        GROUP BY day
        ORDER BY day
    """

SQL_INSERT_IMAGE = """INSERT INTO images(day, session, local_path, backup_path, win_title, win_app, created_ts)
    VALUES (?,?,?,?,?,?,?)"""

SQL_INSERT_VIDEO = """INSERT INTO videos(day, session, local_path, backup_path, created_ts, processed)
    VALUES (?,?,?,?,?,1)"""

SQL_INSERT_SUMMARY = """INSERT INTO summaries(day, path, local_path, backup_path, created_ts processed)
    VALUES (?,?,?,?,?,1)"""

SQL_TABLE_COLS = [
    {
        "tbl": "images",
        "cols_insert": "(day, session, local_path, backup_path, win_title, win_app, created_ts, processed)",
        "cols_select": "day, session, local_path, backup_path, win_title, win_app, created_ts, processed",
    },
    {
        "tbl": "videos",
        "cols_insert": "(day, session, local_path, backup_path, created_ts, processed)",
        "cols_select": "day, session, local_path, backup_path, created_ts, processed",
    },
    {
        "tbl": "summaries",
        "cols_insert": "(day, local_path, backup_path, created_ts, processed)",
        "cols_select": "day, local_path, backup_path, created_ts, processed",
    },
]
