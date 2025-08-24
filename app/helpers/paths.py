import os
import datetime

from pathlib import Path

from app.helpers.config import SUMMARY_DIR, DETAILED_DIR, SESSION_MINUTES


def get_detailed_day_dir(day: str) -> str:
    # detailed videos go under .../detailed/YYYY-MM-DD/
    return os.path.join(DETAILED_DIR, day)


def get_summary_month_dir(day: str) -> str:
    # summaries go under .../summary/YYYY-MM/
    month = day[:7]
    return os.path.join(SUMMARY_DIR, month)


def to_backup_equivalent(local_path: str, local_root: Path, backup_root: Path) -> str:
    """
    Convert a local absolute path to the equivalent path under the OneDrive root.
    This only computes the path string; it does NOT move files.
    """
    try:
        local_root = Path(local_root).resolve()
        backup_root = Path(backup_root).resolve()
        p = Path(local_path).resolve()
        rel = p.relative_to(local_root)  # may raise
        dst = backup_root.joinpath(rel)
        return str(dst).replace("\\", "/")
    except Exception:
        # fallback: create a day-based path if relative fails
        return str(backup_root.joinpath(os.path.basename(local_path))).replace("\\", "/")


def new_session_labels(now: datetime.datetime):
    start_str = now.strftime("%H%M")
    end_str = (now + datetime.timedelta(minutes=SESSION_MINUTES)
               ).strftime("%H%M")
    return f"{start_str}-{end_str}"
