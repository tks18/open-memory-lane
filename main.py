import os
import shutil
import time
import glob
import sqlite3
import logging
import threading
import subprocess
import datetime
import yaml
import json
import queue
import signal
from pathlib import Path
from win32 import win32gui, win32process
from ctypes import Structure, windll, c_uint, sizeof, byref

from mss import mss
from PIL import Image
import numpy as np
import psutil
from skimage.metrics import structural_similarity as ssim
import pystray
from pystray import MenuItem as Item, Menu as TrayMenu

# =========================
# CONFIG
# =========================

# Load the ocnfiguration from a YAML file if it exists
with open(".config.yml", "r") as f:
    cfg = yaml.safe_load(f)

BASE_DIR = Path(cfg["paths"]["base_dir"])
IMAGES_DIR = Path(cfg["paths"]["images_dir"])
TIMELAPSE_DIR = Path(cfg["paths"]["timelapse_dir"])
DETAILED_DIR = Path(cfg["paths"]["detailed_dir"])
SUMMARY_DIR = Path(cfg["paths"]["summary_dir"])
DB_PATH = Path(cfg["paths"]["db_path"])
LOG_FOLDER = Path(cfg["paths"]["log_folder"])
LOG_PATH = os.path.join(LOG_FOLDER, "recorder.log")

# backup paths
BACKUP_BASE_DIR = Path(cfg["paths"]["backup_base_dir"])
BACKUP_DB_PATH = Path(cfg["paths"]["backup_db_path"])
BACKUP_IMAGES_DIR = Path(cfg["paths"]["backup_images_dir"])
BACKUP_DETAILED_DIR = Path(cfg["paths"]["backup_detailed_dir"])
BACKUP_SUMMARY_DIR = Path(cfg["paths"]["backup_summary_dir"])

# Backup Config
LOCAL_RETENTION_DAYS = int(cfg["local_retention"]["days"])
BACKUP_FREQUENCY_HOURS = int(cfg["local_retention"]["backup_frequency_hrs"])

# lock file stale seconds
LOCK_STALE_MINUTES = int(cfg["session"]["lock_stale_minutes"])
LOCK_STALE_SECONDS = LOCK_STALE_MINUTES * 60

# length of each chunk
SESSION_MINUTES = int(cfg["session"]["minutes"])
# seconds of idle to allow video processing
IDLE_THRESHOLD = int(cfg["session"]["idle_threshold"])
# seconds between screenshots
CAPTURE_INTERVAL = float(cfg["session"]["capture_interval"])
# 0-100 lossy quality
WEBP_QUALITY = int(cfg["video"]["webp_quality"])
# rely on PATH. If needed, set absolute path.
FFMPEG = str(cfg["video"]["ffmpeg"])
# lower → more sensitive, higher → stricter
SSIM_THRESHOLD = float(cfg["video"]["ssim_threshold"])

# Video FPS
SESSION_VIDEO_FPS = int(cfg["video"]["fps"])
SUMMARY_VIDEO_FPS = int(cfg["video"]["summary_video_fps"])

# =========================
# LOGGING
# =========================
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(BACKUP_BASE_DIR, exist_ok=True)

logging.basicConfig(
    filename=LOG_PATH,
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("recall")

# =========================
# Windows Idle Detection
# =========================


class LASTINPUTINFO(Structure):
    _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]


def get_idle_time_seconds() -> float:
    """Returns seconds since last user input (Windows)."""
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = sizeof(lii)
        windll.user32.GetLastInputInfo(byref(lii))
        millis = windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    except Exception as e:
        logger.exception("Idle detection failed; assuming not idle. %s", e)
        return 0.0

# =========================
# Lock file Helpers
# =========================


def lock_path_for(session_dir: str) -> str:
    return os.path.join(session_dir, "session.lock")


def create_session_lock(session_dir: str):
    """Create lock JSON with pid + UTC timestamp (atomic write)."""
    os.makedirs(session_dir, exist_ok=True)
    lp = lock_path_for(session_dir)
    data = {"pid": os.getpid(), "ts": datetime.datetime.now(
        datetime.UTC).isoformat()}
    tmp = lp + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, lp)
    except Exception:
        # best-effort atomic write fallback
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        try:
            with open(lp, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            logger.exception("Failed to create lock at %s", lp)


def remove_session_lock(session_dir: str):
    lp = lock_path_for(session_dir)
    try:
        if os.path.exists(lp):
            os.remove(lp)
    except Exception:
        logger.exception("Failed to remove session lock: %s", lp)


def read_lock_metadata(session_dir: str):
    lp = lock_path_for(session_dir)
    try:
        with open(lp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_pid_alive(pid: int) -> bool:
    try:
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def is_lock_stale(session_dir: str) -> bool:
    """
    Return True if lock is stale (pid dead or timestamp older than threshold).
    """
    meta = read_lock_metadata(session_dir)
    if not meta:
        # unreadable lock -> treat stale
        return True
    pid = meta.get("pid")
    ts = meta.get("ts")
    # if pid not alive -> stale
    try:
        if pid is not None and not is_pid_alive(pid):
            return True
    except Exception:
        pass
    # check timestamp age (UTC)
    try:
        lock_time = datetime.datetime.fromisoformat(ts)
        age_sec = (datetime.datetime.utcnow() - lock_time).total_seconds()
        if age_sec > LOCK_STALE_SECONDS:
            return True
    except Exception:
        # parsing problem -> treat stale
        return True
    return False


def cleanup_stale_locks(root_images_dir: str):
    """
    Walk the images dir and remove stale lock files (so backlog can run).
    Call at startup and periodically.
    """
    try:
        if not os.path.isdir(root_images_dir):
            return
        for day in os.listdir(root_images_dir):
            day_path = os.path.join(root_images_dir, day)
            if not os.path.isdir(day_path):
                continue
            for session in os.listdir(day_path):
                session_path = os.path.join(day_path, session)
                lp = lock_path_for(session_path)
                if not os.path.exists(lp):
                    continue
                try:
                    if is_lock_stale(session_path):
                        logger.warning("Removing stale lock: %s", lp)
                        remove_session_lock(session_path)
                except Exception:
                    logger.exception(
                        "Error checking/removing stale lock: %s", lp)
    except Exception:
        logger.exception("cleanup_stale_locks failed for %s", root_images_dir)


# ============================
# DB Writer Worker
# ============================


class DBWriter(threading.Thread):
    """
    Background DB writer: collects jobs (SQL, params) and writes in a single transaction batch.
    Use writer.enqueue(sql, params) to queue writes from capture thread.
    """

    def __init__(self, db_path: Path, batch_size: int = 200, flush_interval: float = 2.0):
        super().__init__(daemon=True)
        self.db_path = str(db_path)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.q = queue.Queue()
        self.stop_event = threading.Event()

    def enqueue(self, sql, params=()):
        self.q.put((sql, params))

    def run(self):
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


# Start DB writer
db_writer = DBWriter(DB_PATH)
db_writer.start()

# =========================
# DB helpers (SQLite)
# =========================


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # performance and concurrency tuning
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA temp_store=MEMORY;")

    cur.execute("""CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        session TEXT,      -- HHMM-HHMM
        local_path TEXT,
        backup_path TEXT,
        win_title TEXT,
        win_app TEXT,
        processed INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        session TEXT,      -- HHMM-HHMM
        local_path TEXT,
        backup_path TEXT,
        processed INTEGER DEFAULT 1
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        local_path TEXT,
        backup_path TEXT,
        processed INTEGER DEFAULT 1
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_images_day ON images(day)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_videos_day ON videos(day)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_summaries_day ON summaries(day)")
    conn.commit()
    conn.close()

    ensure_archive_schema()


def ensure_archive_schema():
    try:
        # create directory for BACKUP_DB_PATH
        os.makedirs(Path(BACKUP_DB_PATH).parent, exist_ok=True)
        aconn = sqlite3.connect(BACKUP_DB_PATH, timeout=30)
        acur = aconn.cursor()
        acur.execute("PRAGMA journal_mode=WAL;")
        acur.execute("PRAGMA synchronous=NORMAL;")
        # same schemas as live
        acur.execute("""CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT,
            session TEXT,
            local_path TEXT,
            backup_path TEXT,
            win_title TEXT,
            win_app TEXT,
            processed INTEGER DEFAULT 0
        )""")
        acur.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT,
            session TEXT,
            local_path TEXT,
            backup_path TEXT,
            processed INTEGER DEFAULT 1
        )""")
        acur.execute("""CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT,
            local_path TEXT,
            backup_path TEXT,
            processed INTEGER DEFAULT 1
        )""")

        # IMPORTANT: create UNIQUE indexes to prevent duplicates (idempotent)
        acur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ui_images_day_session_path ON images(day, session, local_path)")
        acur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ui_videos_day_session_path ON videos(day, session, local_path)")
        acur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ui_summaries_day_path ON summaries(day, local_path)")

        aconn.commit()
        aconn.close()
    except Exception as e:
        logger.exception("Failed to ensure archive schema: %s", e)


def db_exec(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    conn.close()


def db_exec_async(sql, params=()):
    """
    Enqueue a write to the DBWriter (non-blocking).
    """
    try:
        db_writer.enqueue(sql, params)
    except Exception:
        # fallback to synchronous write if queueing fails
        db_exec(sql, params)


def db_fetchall(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def add_image(day: str, session: str, local_path: str, win_title, win_app, backup_path: str = None):
    """
    Store both local and backup paths into DB. For backwards compatibility,
    'path' will be set to local_path.
    """
    query = """INSERT INTO images(day, session, local_path, backup_path, win_title, win_app)
               VALUES (?,?,?,?,?,?)"""
    db_exec_async(query, (day, session, local_path,
                          backup_path or "", win_title, win_app))


def mark_video(day: str, session: str, local_path: str, backup_path: str = None):
    query = """INSERT INTO videos(day, session, local_path, backup_path, processed)
               VALUES (?,?,?,?,1)"""
    db_exec_async(query, (day, session, local_path, backup_path or ""))


def mark_summary(day: str, local_path: str, backup_path: str = None):
    query = """INSERT INTO summaries(day, path, local_path, backup_path, processed)
               VALUES (?,?,?,?,1)"""
    db_exec_async(query, (day, local_path, backup_path or ""))


def get_pending_video_sessions():
    return db_fetchall("""
        SELECT DISTINCT day, session
        FROM images i
        WHERE NOT EXISTS (
            SELECT 1 FROM videos v
            WHERE v.day = i.day AND v.session = i.session
        )
        ORDER BY day, session
    """)


def get_pending_summary_days():
    today = datetime.date.today().isoformat()
    return [d for (d,) in db_fetchall("""
        SELECT day
        FROM videos
        WHERE NOT EXISTS (
            SELECT 1 FROM summaries s WHERE s.day = videos.day
        )
        GROUP BY day
        ORDER BY day
    """) if d != today]

# =========================
# Video Helpers (ffmpeg)
# =========================


def _ffconcat_line(p: str) -> str:
    safe = os.path.abspath(p).replace("\\", "/")
    safe = safe.replace("'", r"\'")
    return f"file '{safe}'\n"


def ffmpeg_exists() -> bool:
    try:
        subprocess.run([FFMPEG, "-version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def make_video_from_folder(folder: str, out_file: str, images_per_second: int = SESSION_VIDEO_FPS) -> bool:
    """
    Create a video from still images in `folder` where each image is shown
    at `images_per_second` rate (default 2 -> each image 0.5s).

    Returns True on success, False on failure.
    """
    if not ffmpeg_exists():
        logger.error("ffmpeg not found in PATH. Skipping video creation.")
        return False

    # collect webp/jpg/png images in lexicographic order
    images = sorted(
        p for p in os.listdir(folder)
        if p.lower().endswith((".webp", ".png", ".jpg", ".jpeg"))
    )

    if not images:
        logger.warning("No images in folder: %s", folder)
        return False

    per_image = 1.0 / float(images_per_second)

    # Single-image edge case: loop that one image for per_image seconds
    if len(images) == 1:
        img_path = os.path.abspath(os.path.join(
            folder, images[0])).replace("\\", "/")
        cmd = [
            FFMPEG, "-y",
            "-loop", "1",
            "-i", img_path,
            "-t", f"{per_image:.6f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            out_file
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
            logger.info("Created video (single image): %s", out_file)
            return True
        except subprocess.CalledProcessError as e:
            logger.exception(
                "ffmpeg failed (single image) for %s: %s", folder, e)
            return False

    # Multiple images: build an ffconcat list with per-image duration (ffmpeg-friendly)
    list_file = os.path.join(folder, "ffconcat_list.txt")
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            f.write("ffconcat version 1.0\n")
            for i, img in enumerate(images):
                abs_path = os.path.abspath(
                    os.path.join(folder, img)).replace("\\", "/")
                abs_path = abs_path.replace("'", r"\'")  # escape single quotes
                f.write(f"file '{abs_path}'\n")
                # add duration for all but the last entry (ffmpeg quirk)
                if i < len(images) - 1:
                    f.write(f"duration {per_image:.6f}\n")

        cmd = [
            FFMPEG, "-y",
            "-safe", "0",
            "-f", "concat",
            "-i", list_file,
            "-vsync", "vfr",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            out_file
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        logger.info("Created video: %s (images=%d, %.3fs/image => %.2f images/sec)",
                    out_file, len(images), per_image, images_per_second)
        return True
    except subprocess.CalledProcessError as e:
        logger.exception("ffmpeg concat failed for %s: %s", folder, e)
        return False
    finally:
        try:
            if os.path.exists(list_file):
                os.remove(list_file)
        except Exception:
            pass


def concat_daily_videos(day: str, out_file: str) -> bool:
    """
    Create a TIMELAPSE daily summary for `day` by:
      1. concatenating all detailed mp4s into a temp concat file
      2. probing the concatenated file for its fps (detailed_fps)
      3. computing speed_factor = max(1.0, SUMMARY_VIDEO_FPS / detailed_fps)
      4. applying setpts=PTS/<speed_factor> and writing output at SUMMARY_VIDEO_FPS
    """
    if not ffmpeg_exists():
        logger.error("ffmpeg not found in PATH. Skipping summary creation.")
        return False

    day_dir = get_detailed_day_dir(day)
    mp4s = sorted(glob.glob(os.path.join(day_dir, "*.mp4")))

    if not mp4s:
        logger.warning("No detailed videos found for day: %s", day)
        return False

    # Create concat list and a temporary concatenated file
    list_file = os.path.join(day_dir, f"{day}_concat_list.txt")
    tmp_concat = os.path.join(day_dir, f"{day}_concat_temp.mp4")
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in mp4s:
                f.write(_ffconcat_line(p))

        # First produce a raw concatenated file (copy codec to avoid re-encoding)
        concat_cmd = [FFMPEG, "-y", "-f", "concat", "-safe",
                      "0", "-i", list_file, "-c", "copy", tmp_concat]
        try:
            subprocess.run(concat_cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError as e:
            logger.exception("ffmpeg concat (raw) failed for %s: %s", day, e)
            return False

        # Helper to parse fraction like "30000/1001" or "25/1" -> float
        def _parse_frac(s):
            try:
                s = s.strip()
                if "/" in s:
                    n, d = s.split("/")
                    n, d = float(n), float(d)
                    return n / d if d != 0 else None
                return float(s)
            except Exception:
                return None

        # Probe for detailed fps (try ffprobe)
        detailed_fps = None
        if shutil.which("ffprobe") is not None:
            try:
                # avg_frame_rate is typically "30000/1001" etc.
                res = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=avg_frame_rate",
                     "-of", "default=noprint_wrappers=1:nokey=1", tmp_concat],
                    capture_output=True, text=True, check=True
                )
                fps_str = (res.stdout or "").strip()
                detailed_fps = _parse_frac(fps_str)
            except Exception:
                logger.exception(
                    "ffprobe failed to read avg_frame_rate for %s", tmp_concat)

        # Fallback to SESSION_VIDEO_FPS if probing failed
        if not detailed_fps or detailed_fps <= 0:
            logger.warning(
                "Couldn't determine detailed_fps via ffprobe, falling back to SESSION_VIDEO_FPS=%s", SESSION_VIDEO_FPS)
            detailed_fps = float(SESSION_VIDEO_FPS)

        # compute speed factor from fps ratio
        try:
            summary_fps_local = float(SUMMARY_VIDEO_FPS)
        except Exception:
            summary_fps_local = float(SESSION_VIDEO_FPS)

        # speed_factor = summary_fps / detailed_fps
        # ensure >= 1.0 so we don't accidentally slow the day down
        if detailed_fps <= 0:
            speed_factor = 1.0
        else:
            speed_factor = summary_fps_local / detailed_fps
            if speed_factor < 1.0:
                speed_factor = 1.0

        logger.info("Daily concat: detailed_fps=%.3f, summary_fps=%.3f, speed_factor=%.3f",
                    detailed_fps, summary_fps_local, speed_factor)

        # Apply timelapse (speed-up) filter and write out at summary fps, drop audio
        timelapse_cmd = [
            FFMPEG, "-y",
            "-i", tmp_concat,
            "-filter:v", f"setpts=PTS/{speed_factor}",
            "-r", str(int(summary_fps_local)),
            "-an",
            out_file
        ]
        subprocess.run(timelapse_cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        logger.info(
            "Created daily timelapse summary: %s (speed_factor=%.3f)", out_file, speed_factor)
        return True

    except subprocess.CalledProcessError as e:
        logger.exception("ffmpeg timelapse creation failed for %s: %s", day, e)
        return False
    finally:
        # cleanup
        try:
            if os.path.exists(list_file):
                os.remove(list_file)
        except Exception:
            pass
        try:
            if os.path.exists(tmp_concat):
                os.remove(tmp_concat)
        except Exception:
            pass

# =========================
# Screenshot & Session Logic
# =========================


def get_detailed_day_dir(day: str) -> str:
    # detailed videos go under .../detailed/YYYY-MM-DD/
    return os.path.join(DETAILED_DIR, day)


def get_summary_month_dir(day: str) -> str:
    # summaries go under .../summary/YYYY-MM/
    month = day[:7]
    return os.path.join(SUMMARY_DIR, month)


def is_today(day: str) -> bool:
    return day == datetime.date.today().isoformat()


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


def ensure_dirs():
    for d in [IMAGES_DIR, DETAILED_DIR, SUMMARY_DIR, BACKUP_IMAGES_DIR, BACKUP_DETAILED_DIR, BACKUP_SUMMARY_DIR]:
        os.makedirs(d, exist_ok=True)


def new_session_labels(now: datetime.datetime):
    start_str = now.strftime("%H%M")
    end_str = (now + datetime.timedelta(minutes=SESSION_MINUTES)
               ).strftime("%H%M")
    return f"{start_str}-{end_str}"

# --- Function to get app name from window ---


def get_active_window_info():
    """Get the active window title and process (app) name."""
    hwnd = win32gui.GetForegroundWindow()
    window_title = win32gui.GetWindowText(hwnd)

    try:
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        app_name = psutil.Process(pid).name()
    except Exception:
        app_name = "UnknownApp"

    return window_title, app_name


def capture_screenshot(last_img: Image.Image, save_dir: str, day: str, session: str):
    try:
        with mss() as sct:
            raw = sct.grab(sct.monitors[0])   # full primary screen
            window_title, app_name = get_active_window_info()
            pil_img = Image.frombytes("RGB", raw.size, raw.rgb)

        should_save = False

        if last_img is None:
            should_save = True
        else:
            # Resize both images to smaller (e.g., 400px width) for faster SSIM
            target_w = 400
            w, h = pil_img.size
            aspect = h / w
            new_size = (target_w, int(target_w * aspect))

            img1 = last_img.resize(new_size).convert("L")
            img2 = pil_img.resize(new_size).convert("L")

            arr1 = np.array(img1)
            arr2 = np.array(img2)

            score, _ = ssim(arr1, arr2, full=True)
            if score < SSIM_THRESHOLD:
                should_save = True

        if should_save:
            now = datetime.datetime.now()
            fname = now.strftime("SCREENSHOT_%d_%m_%Y_%H_%M_%S.webp")
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, fname)
            pil_img.save(path, "WEBP", quality=WEBP_QUALITY)
            try:
                backup_equiv = to_backup_equivalent(
                    path, IMAGES_DIR, BACKUP_IMAGES_DIR)
            except Exception:
                backup_equiv = ""
            add_image(day, session, path, window_title,
                      app_name, backup_equiv)
            return pil_img

        return last_img
    except Exception as e:
        logger.exception("Screenshot capture failed: %s", e)
        return last_img

# ===========================
# BACKUP WORKER
# ===========================

# safe copy helpers


def safe_copy_file(src: str, dst: str):
    """
    Copy src -> dst safely:
      - write to dst + '.part' then os.replace to be atomic.
      - preserves metadata via copy2.
    Returns True on success, False on failure.
    """
    try:
        dst_dir = os.path.dirname(dst)
        os.makedirs(dst_dir, exist_ok=True)
        tmp_dst = dst + ".part"
        # copy2 to tmp location
        shutil.copy2(src, tmp_dst)
        # atomic replace
        os.replace(tmp_dst, dst)
        return True
    except Exception:
        logger.exception("safe_copy_file failed: %s -> %s", src, dst)
        # cleanup tmp if exists
        try:
            if os.path.exists(tmp_dst):
                os.remove(tmp_dst)
        except Exception:
            pass
        return False


def copy_dir_contents(src_dir: str, dst_dir: str, skip_locked_sessions=True):
    """
    Copy everything inside src_dir into dst_dir (non-recursive expectation: day/session structure).
    Returns (copied_count, failed_count)
    """
    copied = 0
    failed = 0
    try:
        os.makedirs(dst_dir, exist_ok=True)
        for name in os.listdir(src_dir):
            src_path = os.path.join(src_dir, name)
            dst_path = os.path.join(dst_dir, name)
            if os.path.isdir(src_path):
                # if skipping locked sessions, check for lock
                lp = lock_path_for(src_path)
                if skip_locked_sessions:
                    if os.path.exists(lp):
                        try:
                            if is_lock_stale(src_path):
                                logger.warning(
                                    "Found stale lock (auto-removing): %s", lp)
                                remove_session_lock(src_path)
                            else:
                                # active session -> skip processing this session for now
                                continue
                        except Exception:
                            logger.exception("Error checking lock: %s", lp)
                            continue
                # ensure dst folder exists
                os.makedirs(dst_path, exist_ok=True)
                # copy all files inside that session folder
                for root, _, files in os.walk(src_path):
                    rel_root = os.path.relpath(root, src_dir)
                    for f in files:
                        sfile = os.path.join(root, f)
                        dfile = os.path.join(dst_dir, rel_root, f)
                        if safe_copy_file(sfile, dfile):
                            copied += 1
                        else:
                            failed += 1
            elif os.path.isfile(src_path):
                # single file (not expected for session structure) - copy directly
                if safe_copy_file(src_path, dst_path):
                    copied += 1
                else:
                    failed += 1
    except Exception:
        logger.exception(
            "copy_dir_contents failed for %s -> %s", src_dir, dst_dir)
    return copied, failed


def ensure_remote_exists_for_day(local_day: str, local_root: str, remote_root: str) -> bool:
    """
    Quick existence check: are the expected remote paths present for a given day?
    Used to avoid deleting local content unless remote copy is present.
    """
    try:
        # If detailed/day exists remotely, consider it safe.
        remote_day = os.path.join(remote_root, local_day)
        return os.path.isdir(remote_day) and bool(os.listdir(remote_day))
    except Exception:
        return False


def archive_old_records(retention_days: int = LOCAL_RETENTION_DAYS):
    """
    Move rows older than retention_days from local DB -> archive DB (OneDrive).
    Uses INSERT OR IGNORE + delete-where-exists to ensure only incremental new rows
    are removed from the live DB. Idempotent.

    Fixed: avoid parentheses around SELECT column-list (which caused "row value misused").
    """
    try:
        cutoff = (datetime.date.today() -
                  datetime.timedelta(days=retention_days)).isoformat()
        conn = sqlite3.connect(DB_PATH, timeout=60)
        cur = conn.cursor()

        # Attach archive DB (on Backup) as 'archive'
        cur.execute("ATTACH DATABASE ? AS archive", (str(BACKUP_DB_PATH),))

        tables = [
            {
                "tbl": "images",
                # columns to insert (parentheses used for INSERT target), and select list (no parentheses)
                "cols_insert": "(day, session, local_path, backup_path, win_title, win_app, processed)",
                "cols_select": "day, session, local_path, backup_path, win_title, win_app, processed",
            },
            {
                "tbl": "videos",
                "cols_insert": "(day, session, local_path, backup_path, processed)",
                "cols_select": "day, session, local_path, backup_path, processed",
            },
            {
                "tbl": "summaries",
                "cols_insert": "(day, local_path, backup_path, processed)",
                "cols_select": "day, local_path, backup_path, processed",
            },
        ]

        for t in tables:
            tbl = t["tbl"]
            cols_insert = t["cols_insert"]
            cols_select = t["cols_select"]

            try:
                # 1) Insert into archive (ignore duplicates due to unique index)
                cur.execute("BEGIN")
                insert_sql = f"""
                    INSERT OR IGNORE INTO archive.{tbl} {cols_insert}
                    SELECT {cols_select} FROM {tbl}
                    WHERE day < ?
                """
                cur.execute(insert_sql, (cutoff,))

                try:
                    cur.execute(
                        f"SELECT COUNT(*) FROM archive.{tbl} WHERE day < ?", (cutoff,))
                    archive_count_after = cur.fetchone()[0]
                except Exception:
                    archive_count_after = None

                # 2) Delete only rows that now exist in archive (safe-delete)
                if tbl == "summaries":
                    del_sql = f"""
                        DELETE FROM {tbl}
                        WHERE day < ?
                          AND EXISTS (
                              SELECT 1 FROM archive.{tbl} a
                              WHERE a.day = {tbl}.day AND a.local_path = {tbl}.local_path
                          )
                    """
                else:
                    del_sql = f"""
                        DELETE FROM {tbl}
                        WHERE day < ?
                          AND EXISTS (
                              SELECT 1 FROM archive.{tbl} a
                              WHERE a.day = {tbl}.day
                                AND a.session = {tbl}.session
                                AND a.local_path = {tbl}.local_path
                          )
                    """
                cur.execute(del_sql, (cutoff,))
                cur.execute("COMMIT")
                logger.info("Archived & pruned table %s for cutoff %s (archive_count=%s)",
                            tbl, cutoff, archive_count_after)
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


def backup_worker(stop_event: threading.Event, interval_seconds: int = 3 * 60 * 60):
    """
    Periodically moves completed items from TEMP → OneDrive:
      - images: .../images/YYYY-MM-DD/(session) when session has no 'session.lock'
      - detailed: .../timelapse/detailed/YYYY-MM-DD when day < today
      - summary: .../timelapse/summary/YYYY-MM/ files for days < today
    """
    os.makedirs(BACKUP_BASE_DIR, exist_ok=True)
    os.makedirs(BACKUP_IMAGES_DIR, exist_ok=True)
    os.makedirs(BACKUP_DETAILED_DIR, exist_ok=True)
    os.makedirs(BACKUP_SUMMARY_DIR, exist_ok=True)

    while not stop_event.is_set():
        try:
            today = datetime.date.today().isoformat()
            current_month = today[:7]

            # 1) IMAGES: copy session folders (skip locked sessions to avoid partial files)
            for day in os.listdir(IMAGES_DIR):
                src_day = os.path.join(IMAGES_DIR, day)
                if not os.path.isdir(src_day):
                    continue

                dst_day = os.path.join(BACKUP_IMAGES_DIR, day)
                os.makedirs(dst_day, exist_ok=True)

                # Copy session folders' contents (safe copy)
                for session in os.listdir(src_day):
                    src_session = os.path.join(src_day, session)
                    if not os.path.isdir(src_session):
                        continue
                    # still skip active sessions if lock exists
                    if os.path.exists(os.path.join(src_session, "session.lock")):
                        continue
                    dst_session = os.path.join(dst_day, session)
                    os.makedirs(dst_session, exist_ok=True)
                    # copy all files within session folder
                    for root, _, files in os.walk(src_session):
                        rel_root = os.path.relpath(root, src_day)
                        for f in files:
                            sfile = os.path.join(root, f)
                            # dst path keeps same relative structure
                            dfile = os.path.join(dst_day, rel_root, f)
                            safe_copy_file(sfile, dfile)

                # clean up day folder if empty (only removes empty local dirs; do not delete files here)
                try:
                    if os.path.isdir(src_day) and not os.listdir(src_day):
                        os.rmdir(src_day)
                except Exception:
                    pass

            # 2) DETAILED: copy whole day directories for previous days (do NOT touch today's day)
            for day in os.listdir(DETAILED_DIR):
                src_day_dir = os.path.join(DETAILED_DIR, day)
                if not day or not os.path.isdir(src_day_dir):
                    continue
                if day >= today:
                    continue
                dst_day_dir = os.path.join(BACKUP_DETAILED_DIR, day)
                # if destination doesn't exist, copy tree; otherwise copy missing files
                if not os.path.isdir(dst_day_dir):
                    try:
                        shutil.copytree(src_day_dir, dst_day_dir,
                                        copy_function=shutil.copy2)
                    except FileExistsError:
                        # already created by another run; fall through to sync contents
                        pass
                    except Exception:
                        logger.exception(
                            "Failed copying detailed day %s -> %s", src_day_dir, dst_day_dir)
                else:
                    # copy any new files inside src_day_dir to dst_day_dir
                    for root, _, files in os.walk(src_day_dir):
                        rel = os.path.relpath(root, src_day_dir)
                        target_root = os.path.join(dst_day_dir, rel)
                        os.makedirs(target_root, exist_ok=True)
                        for f in files:
                            sfile = os.path.join(root, f)
                            dfile = os.path.join(target_root, f)
                            safe_copy_file(sfile, dfile)

            # 3) SUMMARY: copy past months or earlier days in current month
            for month in os.listdir(SUMMARY_DIR):
                src_month_dir = os.path.join(SUMMARY_DIR, month)
                if not os.path.isdir(src_month_dir):
                    continue
                dst_month_dir = os.path.join(BACKUP_SUMMARY_DIR, month)
                os.makedirs(dst_month_dir, exist_ok=True)

                if month < current_month:
                    # copy entire past month folder
                    if not os.path.isdir(os.path.join(BACKUP_SUMMARY_DIR, month)):
                        try:
                            shutil.copytree(
                                src_month_dir, dst_month_dir, copy_function=shutil.copy2)
                        except Exception:
                            logger.exception(
                                "Failed copying summary month: %s", src_month_dir)
                    else:
                        # sync files
                        for f in os.listdir(src_month_dir):
                            src_f = os.path.join(src_month_dir, f)
                            dst_f = os.path.join(dst_month_dir, f)
                            if os.path.isfile(src_f):
                                safe_copy_file(src_f, dst_f)
                    continue

                if month == current_month:
                    # copy only non-today summary files to remote
                    for f in os.listdir(src_month_dir):
                        if not f.endswith("_summary.mp4"):
                            continue
                        day_prefix = f.split("_summary.mp4")[0]  # YYYY-MM-DD
                        if day_prefix < today:
                            src_f = os.path.join(src_month_dir, f)
                            dst_f = os.path.join(dst_month_dir, f)
                            safe_copy_file(src_f, dst_f)

                # clean up month folder if empty
                try:
                    if os.path.isdir(src_month_dir) and not os.listdir(src_month_dir):
                        os.rmdir(src_month_dir)
                except Exception:
                    pass

            # 4) Archive old records in DB
            try:
                # give db_writer a chance to flush enqueued writes
                if 'db_writer' in globals():
                    # tiny pause; optional: implement db_writer.queue.join() semantics if needed
                    time.sleep(0.25)
                archive_old_records(LOCAL_RETENTION_DAYS)
            except Exception:
                logger.exception("Archive pass failed")

            # 5) CLEANUP OLD FILES/FOLDERS (beyond LOCAL_RETENTION_DAYS)
            try:
                cutoff = datetime.date.today() - datetime.timedelta(days=LOCAL_RETENTION_DAYS)

                # IMAGES: only delete local day folder if it's older and remote has that day
                if os.path.isdir(IMAGES_DIR):
                    for day in os.listdir(IMAGES_DIR):
                        day_path = os.path.join(IMAGES_DIR, day)
                        try:
                            day_date = datetime.date.fromisoformat(day)
                        except Exception:
                            continue
                        if day_date < cutoff and os.path.isdir(day_path):
                            # confirm remote copy exists for that day before deleting
                            remote_day = os.path.join(BACKUP_IMAGES_DIR, day)
                            if os.path.isdir(remote_day) and os.listdir(remote_day):
                                shutil.rmtree(day_path, ignore_errors=True)

                # DETAILED: remove local detailed day folders older than cutoff only if remote copy exists
                if os.path.isdir(DETAILED_DIR):
                    for day in os.listdir(DETAILED_DIR):
                        day_path = os.path.join(DETAILED_DIR, day)
                        try:
                            day_date = datetime.date.fromisoformat(day)
                        except Exception:
                            continue
                        if day_date < cutoff and os.path.isdir(day_path):
                            backup_day = os.path.join(
                                BACKUP_DETAILED_DIR, day)
                            if os.path.isdir(backup_day) and os.listdir(backup_day):
                                shutil.rmtree(day_path, ignore_errors=True)

                # SUMMARY: remove local summary files older than cutoff only if remote copy exists
                if os.path.isdir(SUMMARY_DIR):
                    cutoff_month = cutoff.isoformat()[:7]
                    for month in os.listdir(SUMMARY_DIR):
                        month_path = os.path.join(SUMMARY_DIR, month)
                        if month < cutoff_month:
                            remote_month = os.path.join(
                                BACKUP_SUMMARY_DIR, month)
                            # only prune if remote month exists
                            if os.path.isdir(remote_month) and os.listdir(remote_month):
                                shutil.rmtree(month_path, ignore_errors=True)

                cleanup_stale_locks(IMAGES_DIR)
            except Exception:
                logger.exception("Retention cleanup failed")

        except Exception as e:
            logger.exception("Backup to Folder Failed: %s", e)

        stop_event.wait(interval_seconds)

# =========================
# Worker Thread
# =========================


class RecallWorker(threading.Thread):
    def __init__(self, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.stop_event = stop_event

    def run(self):
        ensure_dirs()
        init_db()
        cleanup_stale_locks(IMAGES_DIR)
        self.process_backlog()

        last_img = None
        session_start_time = time.time()

        current_day = datetime.date.today().isoformat()
        day_images_dir = os.path.join(IMAGES_DIR, current_day)
        os.makedirs(day_images_dir, exist_ok=True)

        session_label = new_session_labels(datetime.datetime.now())
        session_dir = os.path.join(day_images_dir, session_label)
        os.makedirs(session_dir, exist_ok=True)

        create_session_lock(session_dir)

        last_backlog_sweep = time.time()

        self.process_backlog()

        logger.info("Recall worker started.")
        while not self.stop_event.is_set():
            today = datetime.date.today().isoformat()
            if today != current_day:
                summary_dir = get_summary_month_dir(current_day)
                os.makedirs(summary_dir, exist_ok=True)
                summary_file = os.path.join(
                    summary_dir, f"{current_day}_summary.mp4")
                backup_summary = to_backup_equivalent(
                    summary_dir, SUMMARY_DIR, BACKUP_SUMMARY_DIR)
                if not os.path.exists(summary_file):
                    if concat_daily_videos(current_day, summary_file):
                        mark_summary(current_day, summary_file,
                                     backup_summary)
                current_day = today
                day_images_dir = os.path.join(IMAGES_DIR, current_day)
                os.makedirs(day_images_dir, exist_ok=True)

            # Capture
            last_img = capture_screenshot(
                last_img, session_dir, current_day, session_label)
            time.sleep(CAPTURE_INTERVAL)

            if time.time() - session_start_time >= SESSION_MINUTES * 60:
                day_dir = get_detailed_day_dir(current_day)
                os.makedirs(day_dir, exist_ok=True)
                out_file = os.path.join(
                    day_dir, f"{current_day}_{session_label}.mp4")
                if not os.path.exists(out_file):
                    backup_out = to_backup_equivalent(
                        out_file, DETAILED_DIR, BACKUP_DETAILED_DIR)
                    if make_video_from_folder(session_dir, out_file):
                        mark_video(current_day, session_label,
                                   out_file, backup_out)

                remove_session_lock(session_dir)

                session_start_time = time.time()
                session_label = new_session_labels(datetime.datetime.now())
                session_dir = os.path.join(day_images_dir, session_label)
                os.makedirs(session_dir, exist_ok=True)
                create_session_lock(session_dir)

            if time.time() - last_backlog_sweep >= 5 * 60:
                if get_idle_time_seconds() >= IDLE_THRESHOLD:
                    self.process_backlog(current_session=(
                        current_day, session_label))
                last_backlog_sweep = time.time()

        logger.info("Recall worker stopping...")

    def process_backlog(self, current_session=None):
        for day, session in get_pending_video_sessions():
            if current_session and (day, session) == current_session:
                continue

            folder = os.path.join(IMAGES_DIR, day, session)
            if not os.path.isdir(folder):
                continue

            if os.path.exists(os.path.join(folder, "session.lock")):
                continue

            day_dir = get_detailed_day_dir(day)
            os.makedirs(day_dir, exist_ok=True)
            out_file = os.path.join(day_dir, f"{day}_{session}.mp4")
            backup_out = to_backup_equivalent(
                out_file, DETAILED_DIR, BACKUP_DETAILED_DIR)
            logger.info(
                "[BACKLOG] Creating detailed video for %s %s", day, session)
            if make_video_from_folder(folder, out_file):
                mark_video(day, session, out_file, backup_out)

        for day in get_pending_summary_days():
            if is_today(day):
                continue

            month_dir = get_summary_month_dir(day)
            os.makedirs(month_dir, exist_ok=True)
            out_file = os.path.join(month_dir, f"{day}_summary.mp4")
            backup_summary = to_backup_equivalent(
                out_file, SUMMARY_DIR, BACKUP_SUMMARY_DIR)
            logger.info("[BACKLOG] Creating summary for %s", day)
            if concat_daily_videos(day, out_file):
                mark_summary(day, out_file, backup_summary)

# =========================
# Tray Icon
# =========================


def create_tray_image():
    img = Image.open(os.path.join("__assets__", "recall_logo.png"))
    img = img.convert("RGBA")
    return img


def open_logs(_icon=None, _item=None):
    try:
        os.startfile(LOG_PATH)
    except Exception:
        pass


def open_root(_icon=None, _item=None):
    try:
        os.startfile(os.path.abspath(BASE_DIR))
    except Exception:
        pass


def on_exit(icon, item, stop_event: threading.Event):
    """
    Graceful shutdown sequence:
      1. signal workers to stop (stop_event)
      2. give workers a short time to finish
      3. stop+join db_writer (flushes pending DB writes)
      4. join other background threads if available (worker, backup_thread)
      5. stop the tray icon
    """
    logger.info("Shutdown requested via tray. Beginning graceful shutdown...")

    try:
        # 1) Signal threads to stop (producers/consumers should watch this)
        try:
            stop_event.set()
        except Exception:
            logger.exception("Failed to set stop_event")

        # 2) small pause to let producers stop enqueuing quickly
        time.sleep(0.25)

        # 3) Join known worker threads (best-effort — they may be local variables)
        # If you stored references globally, join them. Example names: worker, backup_thread
        for candidate in ("worker", "backup_thread", "recall_worker"):
            thr = globals().get(candidate)
            if isinstance(thr, threading.Thread):
                logger.info("Waiting for thread %s to stop...", candidate)
                try:
                    thr.join(timeout=5.0)
                    if thr.is_alive():
                        logger.warning(
                            "Thread %s still alive after timeout", candidate)
                except Exception:
                    logger.exception("Error joining thread %s", candidate)

        # 4) Stop DB writer (flush pending writes) then join it
        dbw = globals().get("db_writer")
        if dbw is not None:
            try:
                logger.info("Stopping DB writer...")
                # db_writer.stop() flushes remaining queue synchronously per earlier implementation
                dbw.stop()
                # join the thread to ensure it has exited
                if isinstance(dbw, threading.Thread):
                    dbw.join(timeout=5.0)
                    if dbw.is_alive():
                        logger.warning(
                            "db_writer still alive after join timeout")
            except Exception:
                logger.exception("Failed stopping/joining db_writer")

    except Exception:
        logger.exception("Unexpected error during on_exit")

    finally:
        # Always attempt to stop the tray icon (UI exit)
        try:
            icon.stop()
        except Exception:
            # last resort — log and ignore
            logger.exception("Failed to stop tray icon")


def run_tray_app():
    stop_event = threading.Event()

    # Start Main Worker
    worker = RecallWorker(stop_event)
    worker.start()

    # Start backup worker thread
    backup_thread = threading.Thread(
        target=backup_worker, args=(stop_event, 3 * 60 * 60), daemon=True
    )
    backup_thread.start()

    signal.signal(signal.SIGINT, lambda *a: on_exit(icon, None, stop_event))
    signal.signal(signal.SIGTERM, lambda *a: on_exit(icon, None, stop_event))

    menu = TrayMenu(
        Item("Open Memories", open_root),
        Item("Open Log", open_logs),
        Item("Exit", lambda icon, item: on_exit(icon, item, stop_event))
    )

    icon = pystray.Icon("Shan's Memory Recorder", create_tray_image(),
                        "Shan's Memory Recorder", menu)
    icon.run()


if __name__ == "__main__":
    if not ffmpeg_exists():
        logger.warning(
            "ffmpeg not found in PATH. Videos will be queued until ffmpeg is available.")

    try:
        run_tray_app()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.exception("Fatal error in tray app: %s", e)
        raise
