from app.helpers.db import db_exec, common_sql_statements
from app.workers.db_writer.worker import DBWriter
from app.helpers.general import now_ms


def db_exec_async(writer: DBWriter, sql, params=()):
    """
    Execute a SQL command asynchronously using the DBWriter's queue.
    If the queueing fails, it falls back to synchronous execution.

    :param writer (DBWriter): Writer instance to handle database operations.
    :param sql (str): The SQL command to execute.
    :param params (tuple): The parameters to bind to the SQL command.
    """
    try:
        writer.enqueue(sql, params)
    except Exception:
        # fallback to synchronous write if queueing fails
        db_exec(sql, params)


def add_image(writer: DBWriter, day: str, session: str, local_path: str, win_title, win_app, backup_path: str = None):
    """
    Mark an image as captured in the database.
    This function inserts a new record into the images table with the provided details.

    Args:
        writer (DBWriter): Writer instance to handle database operations.
        day (str): day of the image in YYYY-MM-DD format.
        session (str): session identifier in HHMM-HHMM format.
        local_path (str): local file path where the image is stored.
        win_title (str): window title of the application where the image was captured.
        win_app (str): application name where the image was captured.
        backup_path (str, optional): backup file path for the image. Defaults to None.

    Returns:
        None
    """
    ts = now_ms()
    db_exec_async(writer, common_sql_statements.SQL_INSERT_IMAGE, (day, session, local_path,
                                                                   backup_path or "", win_title, win_app, ts))


def mark_video(writer: DBWriter, day: str, session: str, local_path: str, backup_path: str = None):
    """
    Mark a video as processed in the database.
    This function inserts a new record into the videos table with the provided details.

    Args:
        writer (DBWriter): Writer instance to handle database operations.
        day (str): day of the video in YYYY-MM-DD format.
        session (str): session identifier in HHMM-HHMM format.
        local_path (str): local file path where the video is stored.
        backup_path (str, optional): backup file path for the video. Defaults to None.

    Returns:
        None
    """
    ts = now_ms()
    db_exec_async(writer, common_sql_statements.SQL_INSERT_VIDEO, (day, session,
                  local_path, backup_path or "", ts))


def mark_summary(writer: DBWriter, day: str, local_path: str, backup_path: str = None):
    """
    Mark a summary as processed in the database.
    This function inserts a new record into the summaries table with the provided details.

    Args:
        writer (DBWriter): Writer instance to handle database operations.
        day (str): day of the summary in YYYY-MM-DD format.
        local_path (str): local file path where the summary is stored.
        backup_path (str, optional): backup file path for the summary. Defaults to None.

    Returns:
        None
    """
    ts = now_ms()
    db_exec_async(writer, common_sql_statements.SQL_INSERT_SUMMARY,
                  (day, local_path, backup_path or "", ts))
