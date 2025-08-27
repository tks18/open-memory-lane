import sqlite3
import datetime
import os
import re

from pathlib import Path
import app.helpers.config as cfg

DB_PATH = cfg.DB_PATH
IMAGES_BASE = cfg.IMAGES_DIR

BACKUP_DB_PATH = cfg.BACKUP_DB_PATH
BACKUP_IMAGES_DIR = cfg.BACKUP_IMAGES_DIR
LOCAL_RETENTION_DAYS = cfg.LOCAL_RETENTION_DAYS


def db_conn(path: Path = None):
    use_path = Path(path) if path else Path(DB_PATH)
    if not use_path.exists():
        # don't error for archive lookup — return None so callers can fallback
        raise FileNotFoundError(f"DB not found: {use_path}")
    conn = sqlite3.connect(use_path)
    conn.row_factory = sqlite3.Row
    return conn


def query_rows_from_conn(conn, win_title=None, win_app=None, start=None, end=None):
    """
    Query a given sqlite3.Connection for image rows using same selection logic.
    start/end are ISO datetimes or None. This helper uses 'day' coarse filtering
    (YYYY-MM-DD) to avoid heavy timestamp parsing in SQL.
    Returns list of sqlite3.Row
    """
    cur = conn.cursor()

    # prefer schema that includes local_path/backup_path; fallback handled below
    base_cols = "id, day, session, local_path, backup_path, win_title, win_app"

    q = f"SELECT {base_cols} FROM images WHERE 1=1"
    params = []

    if win_title:
        q += " AND win_title LIKE ?"
        params.append(f"%{win_title}%")
    if win_app:
        q += " AND win_app LIKE ?"
        params.append(f"%{win_app}%")

    # coarse day filtering if start/end provided (use only date part)
    if start:
        try:
            start_day = datetime.datetime.fromisoformat(
                start).date().isoformat()
            q += " AND day >= ?"
            params.append(start_day)
        except Exception:
            pass
    if end:
        try:
            end_day = datetime.datetime.fromisoformat(end).date().isoformat()
            q += " AND day <= ?"
            params.append(end_day)
        except Exception:
            pass

    q += " ORDER BY day DESC"

    try:
        cur.execute(q, params)
        rows = cur.fetchall()
        return rows
    except sqlite3.OperationalError:
        # older schema fallback (no local_path / onedrive_path)
        q2 = "SELECT id, day, session, path, win_title, win_app FROM images WHERE 1=1"
        params2 = []
        if win_title:
            q2 += " AND win_title LIKE ?"
            params2.append(f"%{win_title}%")
        if win_app:
            q2 += " AND win_app LIKE ?"
            params2.append(f"%{win_app}%")
        if start:
            try:
                start_day = datetime.datetime.fromisoformat(
                    start).date().isoformat()
                q2 += " AND day >= ?"
                params2.append(start_day)
            except Exception:
                pass
        if end:
            try:
                end_day = datetime.datetime.fromisoformat(
                    end).date().isoformat()
                q2 += " AND day <= ?"
                params2.append(end_day)
            except Exception:
                pass
        q2 += " ORDER BY day DESC"
        cur.execute(q2, params2)
        rows = cur.fetchall()
        return rows


# Parse timestamp from filename. Recorder uses SCREENSHOT_dd_mm_YYYY_H_M_S.webp


def parse_timestamp_from_path(path_str):
    try:
        b = os.path.basename(path_str)
        parts = b.split('_')
        if len(parts) >= 7:
            dd = parts[1]
            mm = parts[2]
            yyyy = parts[3]
            hh = parts[4]
            mi = parts[5]
            ss_and_ext = parts[6]
            ss = ss_and_ext.split('.')[0]
            dt = datetime.datetime(int(yyyy), int(
                mm), int(dd), int(hh), int(mi), int(ss))
            return dt
    except Exception:
        pass
    return None

# Safe path join to images base


def safe_image_path(p):
    p = os.path.normpath(p)
    try:
        candidate = Path(p)
        if not candidate.is_absolute():
            candidate = (Path(IMAGES_BASE) / p)
        candidate = candidate.resolve()
        base = Path(IMAGES_BASE).resolve()
        if base in candidate.parents or candidate == base:
            return str(candidate)
    except Exception:
        pass
    return None

# Generic fetch rows with optional filters


def fetch_image_rows(win_title=None, win_app=None, start=None, end=None):
    """
    Fetch rows from local DB, and when requested date-range covers older than retention,
    also fetch from archive DB (ONEDRIVE_DB_PATH) and merge results.

    Returns: list of dicts (each dict represents a row).
    """
    rows_map = {}  # key -> dict
    # 1) Query local DB (if exists)
    try:
        conn = db_conn(DB_PATH)
    except FileNotFoundError:
        conn = None

    if conn:
        try:
            local_rows = query_rows_from_conn(
                conn, win_title, win_app, start, end)
            for r in local_rows:
                # normalize row to plain dict so we can safely use .get everywhere
                try:
                    rdict = dict(r)
                except Exception:
                    # if r is already a dict-like, just copy
                    rdict = dict(r) if isinstance(r, dict) else {}
                key = (rdict.get("day"), rdict.get(
                    "session"), rdict.get("local_path"))
                rows_map[key] = rdict
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # 2) Decide whether to query archive DB:
    need_archive = False
    try:
        if BACKUP_DB_PATH and str(BACKUP_DB_PATH).strip():
            if start:
                try:
                    start_date = datetime.datetime.fromisoformat(start).date()
                    cutoff = datetime.date.today() - datetime.timedelta(days=LOCAL_RETENTION_DAYS)
                    if start_date < cutoff:
                        need_archive = True
                except Exception:
                    need_archive = True
            else:
                if not rows_map:
                    need_archive = True
    except Exception:
        need_archive = False

    if need_archive:
        try:
            aconn = db_conn(BACKUP_DB_PATH)
            try:
                arch_rows = query_rows_from_conn(
                    aconn, win_title, win_app, start, end)
                for r in arch_rows:
                    try:
                        rdict = dict(r)
                    except Exception:
                        rdict = dict(r) if isinstance(r, dict) else {}
                    key = (rdict.get("day"), rdict.get(
                        "session"), rdict.get("path"))
                    if key not in rows_map:
                        rows_map[key] = rdict
            finally:
                try:
                    aconn.close()
                except Exception:
                    pass
        except FileNotFoundError:
            # archive DB doesn't exist — that's fine
            pass

    # 3) Build list, sort by day/timestamp descending and return list of dicts
    result_rows = list(rows_map.values())

    # sort: try using timestamp-like info (day), fallback safe behavior
    def ts_key(r):
        try:
            day = r.get("day")
            if day:
                return datetime.datetime.fromisoformat(day)
            return datetime.datetime.min
        except Exception:
            return datetime.datetime.min

    result_rows.sort(key=ts_key, reverse=True)
    return result_rows

# Convert DB row into record with parsed timestamp


def row_to_record(r):
    row = dict(r)
    # compatibility: prefer explicit local_path/backup_path if present
    local_p = row.get("local_path") or ""
    backup_p = row.get("backup_path") or ""

    # parse timestamp from local path first, then fallback to filename or day/session
    ts = parse_timestamp_from_path(local_p)

    if ts is None:
        try:
            day = row.get('day')
            sess = row.get('session')
            if day and sess and '-' in sess:
                hh = int(sess.split('-')[0][:2])
                mm = int(sess.split('-')[0][2:])
                ts = datetime.datetime.fromisoformat(
                    day) + datetime.timedelta(hours=hh, minutes=mm)
        except Exception:
            ts = None

    row['timestamp'] = ts.isoformat() if ts else None
    row['ts_ms'] = int(ts.timestamp() * 1000) if ts else None
    row['local_path'] = local_p
    row['backup_path'] = backup_p
    return row

# Downsample list to roughly `limit` points by uniform sampling


def downsample(items, limit):
    n = len(items)
    if n <= limit:
        return items
    # generate 'limit' indices evenly spaced across 0..n-1
    sampled_output = [items[round(i * (n - 1) / (limit - 1))]
                      for i in range(limit)]
    return sampled_output


# other path helpers

# returns (local_candidate_str or None, backup_candidate_str or None)

def candidates_from_path_string(p):
    """
    Given a stored path or filename, return the likely local candidate and
    the corresponding backup candidate (using configured roots).
    """
    try:
        candidate = Path(p)
        # absolute path: check directly for local; derive relative to IMAGES_BASE for backup
        if candidate.is_absolute():
            local_c = str(candidate) if candidate.exists() else None
            try:
                rel = candidate.relative_to(IMAGES_BASE.resolve())
                backup_c = str(BACKUP_IMAGES_DIR.resolve() /
                               rel) if BACKUP_IMAGES_DIR else None
            except Exception:
                # not under IMAGES_BASE — attempt to map by filename into backup root
                backup_c = str(BACKUP_IMAGES_DIR.resolve() /
                               candidate.name) if BACKUP_IMAGES_DIR else None
            return local_c, backup_c
        # relative path: treat as relative to IMAGES_BASE
        local_cand = (IMAGES_BASE / p).resolve()
        local_c = str(local_cand) if local_cand.exists() else None
        # backup candidate preserves same relative structure
        backup_cand = (BACKUP_IMAGES_DIR /
                       p).resolve() if BACKUP_IMAGES_DIR else None
        backup_c = str(
            backup_cand) if backup_cand and backup_cand.exists() else None
        return local_c, backup_c
    except Exception:
        return None, None


def _day_from_timestamp_or_path(p):
    # first attempt parsing timestamp using filename pattern
    dt = parse_timestamp_from_path(p)
    if dt:
        return dt.date().isoformat()
    # try extract YYYY-MM-DD segment from path
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", str(p))
    if m:
        return m.group(1)
    return None


def resolve_serving_path(record):
    """
    Decide which path to serve given a DB record (dict with local_path & backup_path).
    Policy:
      - If record day < (today - LOCAL_RETENTION_DAYS) prefer backup_path (if exists)
      - Else prefer local_path if exists; fallback to backup_path; fallback to path
    Returns absolute path string or None.
    """
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=LOCAL_RETENTION_DAYS)

    # prefer explicit columns if present
    local_p = record.get('local_path') or ""
    backup_p = record.get('backup_path') or ""

    # compute day
    day = record.get('day') or _day_from_timestamp_or_path(
        local_p) or _day_from_timestamp_or_path(backup_p)
    try:
        if day:
            day_date = datetime.date.fromisoformat(day)
        else:
            day_date = None
    except Exception:
        day_date = None

    # if older than cutoff, prefer backup path if available
    if day_date and day_date < cutoff:
        if backup_p:
            # prefer absolute backup path if exists; otherwise attempt candidate mapping
            if os.path.isabs(backup_p) and os.path.exists(backup_p):
                return backup_p
            # attempt candidate mapping from original relative path
            _, backup_candidate = candidates_from_path_string(
                local_p or record.get('path', ''))
            if backup_candidate and os.path.exists(backup_candidate):
                return backup_candidate
        # backup not available -> try local anyway
    # not older than cutoff (or backup missing) -> prefer local
    if local_p:
        if os.path.isabs(local_p) and os.path.exists(local_p):
            return local_p
        local_candidate, backup_candidate = candidates_from_path_string(
            local_p)
        if local_candidate and os.path.exists(local_candidate):
            return local_candidate
        # fallback to backup candidate
        if backup_candidate and os.path.exists(backup_candidate):
            return backup_candidate

    # final fallback: try direct backup_p absolute
    if backup_p and os.path.isabs(backup_p) and os.path.exists(backup_p):
        return backup_p

    return None
