"""
==========================
Database Initialization and Management Module
==========================

This module provides functions to initialize and manage the application's main and archive databases.
It ensures that the necessary database schemas are created and provides utility functions for executing SQL commands and fetching data.


Features:
- Initializes the main database with required tables and indexes.
- Ensures the archive schema is created in the backup database.
- Provides functions to execute SQL commands and fetch data from the main database.
- Provides functions to retrieve pending video sessions and summary days.

Usage:
>>> from app.helpers.db import init_db, db_exec, db_fetchall, get_pending_video_sessions, get_pending_summary_days
>>> init_db()  # Initializes the main database and archive schema
>>> db_exec("INSERT INTO table_name (column1, column2) VALUES (?, ?)", (value1, value2))  # Executes a SQL command
>>> data = db_fetchall("SELECT * FROM table_name WHERE condition = ?", (value,))  # Fetches all rows matching the query
>>> pending_videos = get_pending_video_sessions()  # Retrieves pending video sessions
>>> pending_summaries = get_pending_summary_days()  # Retrieves pending summary days

*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

import time
import os
import sqlite3
import datetime

from pathlib import Path

from app.logger import logger
from app.helpers.config import DB_PATH, BACKUP_DB_PATH, LOCAL_RETENTION_DAYS

from app.db import archive_db_sql_statements, main_db_sql_statements, common_sql_statements


def ensure_archive_schema():
    """
    Ensure the archive schema is created in the backup database.
    This function connects to the backup database and executes the necessary
    SQL statements to create the required tables and indexes for archiving data.
    If the database file does not exist, it will be created.

    Returns:
        None
    """
    try:
        # create directory for BACKUP_DB_PATH
        aconn = sqlite3.connect(BACKUP_DB_PATH, timeout=30)
        acur = aconn.cursor()

        for stmt in archive_db_sql_statements.SQL_INIT_ARCHIVE_DB_STATEMENTS:
            try:
                acur.execute(stmt)
            except sqlite3.OperationalError as e:
                logger.error(
                    "Failed to execute archive statement: %s\nError: %s", stmt, e)

        aconn.commit()
        aconn.close()
    except Exception as e:
        logger.exception("Failed to ensure archive schema: %s", e)


def init_db():
    """
    Initialize the main database by executing the SQL statements defined in
    SQL_INIT_DB_STATEMENTS. This function connects to the database, executes
    each statement, and commits the changes. If the database file does not exist,
    it will be created automatically by SQLite.

    Returns:
        None
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for stmt in main_db_sql_statements.SQL_INIT_DB_STATEMENTS:
        try:
            cur.execute(stmt)
        except sqlite3.OperationalError as e:
            logger.error("Failed to execute statement: %s\nError: %s", stmt, e)

    conn.commit()
    conn.close()

    ensure_archive_schema()


def db_exec(query: str, params=()):
    """
    Execute a SQL command on the main database.
    This function connects to the database, executes the provided query with
    the given parameters, and commits the changes. It closes the connection
    after execution.

    Args:
        query (str): _description_
        params (tuple, optional): _description_. Defaults to ().

    Returns:
        None
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    conn.close()


def db_fetchall(query: str, params=()):
    """
    Fetch all rows from the main database that match the given query.
    This function connects to the database, executes the provided query with
    the given parameters, and retrieves all matching rows. It closes the connection
    after fetching the data.

    Args:
        query (str): SQL query to execute.
        params (tuple, optional): Parameters to bind to the SQL query. Defaults to ().

    Returns:
        list[Any]: A list of tuples containing the rows fetched from the database.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def get_pending_video_sessions():
    """
    Retrieve all pending video sessions from the main database.
    This function executes a predefined SQL statement to fetch all video sessions
    that are pending processing. It returns a list of tuples containing the session details.
    The SQL statement used is defined in common_sql_statements.SQL_GET_PENDING_VIDEO_SESSIONS.

    Returns:
        list[Any]: A list of tuples containing the pending video sessions.
    """
    return db_fetchall(common_sql_statements.SQL_GET_PENDING_VIDEO_SESSIONS)


def get_pending_summary_days():
    """
    Retrieve all pending summary days from the main database.
    This function executes a predefined SQL statement to fetch all summary days
    that are pending processing. It returns a list of days in ISO format, excluding today's date.
    The SQL statement used is defined in common_sql_statements.SQL_GET_PENDING_SUMMARY_SESSIONS.
    It filters out today's date to avoid processing summaries for the current day.

    Returns:
        list[Any]: A list of days in ISO format that are pending summaries, excluding today's date.
    """
    today = datetime.date.today().isoformat()
    return [d for (d,) in db_fetchall(common_sql_statements.SQL_GET_PENDING_SUMMARY_SESSIONS) if d != today]


def get_last_archived_ts() -> int:
    """
    Return last archived timestamp (epoch ms) stored in archive_meta or 0.
    """
    try:
        if not os.path.exists(BACKUP_DB_PATH):
            return 0
        aconn = sqlite3.connect(BACKUP_DB_PATH, timeout=30)
        acur = aconn.cursor()
        acur.execute(
            "CREATE TABLE IF NOT EXISTS archive_meta (key TEXT PRIMARY KEY, value TEXT)")
        acur.execute(
            "SELECT value FROM archive_meta WHERE key = 'last_archived_ts'")
        row = acur.fetchone()
        aconn.close()
        if row and row[0]:
            return int(row[0])
    except Exception:
        logger.exception("get_last_archived_ts failed")
    return 0


def set_last_archived_ts(ts_ms: int):
    """
    Upsert last_archived_ts into archive_meta (archive DB).
    """
    try:
        os.makedirs(Path(BACKUP_DB_PATH).parent, exist_ok=True)
        aconn = sqlite3.connect(BACKUP_DB_PATH, timeout=30)
        acur = aconn.cursor()
        acur.execute(
            "CREATE TABLE IF NOT EXISTS archive_meta (key TEXT PRIMARY KEY, value TEXT)")
        acur.execute("INSERT OR REPLACE INTO archive_meta (key, value) VALUES (?, ?)",
                     ("last_archived_ts", str(int(ts_ms))))
        aconn.commit()
        aconn.close()
    except Exception:
        logger.exception("set_last_archived_ts failed for %s", ts_ms)


def sync_db_to_archive(up_to_ts_ms: int | None = None):
    """
    Incrementally copy local DB rows into archive DB up to `up_to_ts_ms` (inclusive).
    If up_to_ts_ms is None, uses now (epoch ms).
    Works using created_ts column and last_archived_ts metadata.
    """
    try:
        if not BACKUP_DB_PATH:
            logger.debug("No ONEDRIVE_DB_PATH configured; skipping DB sync.")
            return

        ensure_archive_schema()

        if up_to_ts_ms is None:
            up_to_ts_ms = int(time.time() * 1000)

        last_ts = get_last_archived_ts()
        if last_ts >= up_to_ts_ms:
            logger.debug(
                "Archive DB already up-to-date (last_ts=%s, up_to=%s)", last_ts, up_to_ts_ms)
            return

        # give DB writer a moment to flush
        try:
            if 'db_writer' in globals():
                time.sleep(0.25)
        except Exception:
            pass

        conn = sqlite3.connect(DB_PATH, timeout=60)
        cur = conn.cursor()
        cur.execute("ATTACH DATABASE ? AS archive", (str(BACKUP_DB_PATH),))

        for t in common_sql_statements.SQL_TABLE_COLS:
            tbl = t["tbl"]
            cols_insert = t["cols_insert"]
            cols_select = t["cols_select"]
            try:
                cur.execute("BEGIN")
                sql = f"""
                    INSERT OR IGNORE INTO archive.{tbl} {cols_insert}
                    SELECT {cols_select} FROM {tbl}
                    WHERE created_ts > ? AND created_ts <= ?
                """
                cur.execute(sql, (last_ts, up_to_ts_ms))
                cur.execute("COMMIT")
                logger.info("Synced table %s window (%s, %s]",
                            tbl, last_ts, up_to_ts_ms)
            except Exception:
                cur.execute("ROLLBACK")
                logger.exception(
                    "Failed syncing table %s in window (%s, %s]", tbl, last_ts, up_to_ts_ms)

        try:
            cur.execute("DETACH DATABASE archive")
        except Exception:
            pass
        conn.close()

        # update progress only after successful sync
        set_last_archived_ts(up_to_ts_ms)

    except Exception:
        logger.exception("sync_db_to_archive failed")


def archive_old_records(retention_days: int = LOCAL_RETENTION_DAYS):
    """
    Move rows older than retention_days from local DB -> archive DB (OneDrive).
    Uses INSERT OR IGNORE + delete-where-exists to ensure only incremental new rows
    are removed from the live DB. Idempotent.
    """
    try:
        cutoff_ts_ms = int((datetime.datetime.now(
            datetime.UTC) - datetime.timedelta(days=LOCAL_RETENTION_DAYS)).timestamp() * 1000)
        conn = sqlite3.connect(DB_PATH, timeout=60)
        cur = conn.cursor()

        # Attach archive DB (on Backup) as 'archive'
        cur.execute("ATTACH DATABASE ? AS archive", (str(BACKUP_DB_PATH),))

        for t in common_sql_statements.SQL_TABLE_COLS:
            tbl = t["tbl"]
            cols_insert = t["cols_insert"]
            cols_select = t["cols_select"]

            try:
                # 1) Insert into archive (ignore duplicates due to unique index)
                cur.execute("BEGIN")
                insert_sql = f"""
                    INSERT OR IGNORE INTO archive.{tbl} {cols_insert}
                    SELECT {cols_select} FROM {tbl}
                    WHERE created_ts < ?
                """
                cur.execute(insert_sql, (cutoff_ts_ms,))

                try:
                    cur.execute(
                        f"SELECT COUNT(*) FROM archive.{tbl} WHERE created_ts < ?", (cutoff_ts_ms,))
                    archive_count_after = cur.fetchone()[0]
                except Exception:
                    archive_count_after = None

                # 2) Delete only rows that now exist in archive (safe-delete)
                if tbl == "summaries":
                    del_sql = f"""
                        DELETE FROM {tbl}
                        WHERE created_ts < ?
                          AND EXISTS (
                              SELECT 1 FROM archive.{tbl} a
                              WHERE a.day = {tbl}.day AND a.local_path = {tbl}.local_path
                          )
                    """
                else:
                    del_sql = f"""
                        DELETE FROM {tbl}
                        WHERE created_ts < ?
                          AND EXISTS (
                              SELECT 1 FROM archive.{tbl} a
                              WHERE a.day = {tbl}.day
                                AND a.session = {tbl}.session
                                AND a.local_path = {tbl}.local_path
                          )
                    """
                cur.execute(del_sql, (cutoff_ts_ms,))
                cur.execute("COMMIT")
                logger.info("Archived & pruned table %s for cutoff %s (archive_count=%s)",
                            tbl, cutoff_ts_ms, archive_count_after)
            except Exception:
                cur.execute("ROLLBACK")
                logger.exception("Failed archiving table %s", tbl)

        # detach archive
        try:
            cur.execute("DETACH DATABASE archive")
        except Exception:
            pass

        conn.close()

        # Compact local DB to reclaim space (do this sparingly; it's safe here for small DB)
        try:
            conn2 = sqlite3.connect(DB_PATH, timeout=60)
            conn2.execute("VACUUM")
            conn2.close()
        except Exception:
            logger.exception("VACUUM failed on local DB")
    except Exception:
        logger.exception("archive_old_records failed")
