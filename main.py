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
SUMMARY_VIDEO_FPS = int(cfg["video"].get("summary_fps", SESSION_VIDEO_FPS))

# =========================
# LOGGING
# =========================
os.makedirs(BASE_DIR, exist_ok=True)
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
# DB helpers (SQLite)
# =========================


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        session TEXT,      -- HHMM-HHMM
        path TEXT,
        win_title TEXT,
        win_app TEXT,
        processed INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        session TEXT,      -- HHMM-HHMM
        path TEXT,
        processed INTEGER DEFAULT 1
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,          -- YYYY-MM-DD
        path TEXT,
        processed INTEGER DEFAULT 1
    )""")
    conn.commit()
    conn.close()


def db_exec(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    conn.commit()
    conn.close()


def db_fetchall(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def add_image(day: str, session: str, path: str, win_title, win_app):
    db_exec("INSERT INTO images(day, session, path, win_title, win_app) VALUES (?,?,?,?,?)",
            (day, session, path, win_title, win_app))


def mark_video(day: str, session: str, path: str):
    db_exec("INSERT INTO videos(day, session, path, processed) VALUES (?,?,?,1)",
            (day, session, path))


def mark_summary(day: str, path: str):
    db_exec("INSERT INTO summaries(day, path, processed) VALUES (?,?,1)", (day, path))


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

    day_prefix = f"{day}_"
    mp4s = sorted(p for p in glob.glob(os.path.join(DETAILED_DIR, "*.mp4"))
                  if os.path.basename(p).startswith(day_prefix))

    if not mp4s:
        logger.warning("No detailed videos found for day: %s", day)
        return False

    # Create concat list and a temporary concatenated file
    list_file = os.path.join(DETAILED_DIR, f"{day}_concat_list.txt")
    tmp_concat = os.path.join(DETAILED_DIR, f"{day}_concat_temp.mp4")
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


def ensure_dirs():
    for d in [IMAGES_DIR, DETAILED_DIR, SUMMARY_DIR]:
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
            add_image(day, session, path, window_title, app_name)
            return pil_img

        return last_img
    except Exception as e:
        logger.exception("Screenshot capture failed: %s", e)
        return last_img

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
        self.process_backlog()

        last_img = None
        session_start_time = time.time()

        current_day = datetime.date.today().isoformat()
        day_images_dir = os.path.join(IMAGES_DIR, current_day)
        os.makedirs(day_images_dir, exist_ok=True)

        session_label = new_session_labels(datetime.datetime.now())
        session_dir = os.path.join(day_images_dir, session_label)
        os.makedirs(session_dir, exist_ok=True)

        last_backlog_sweep = time.time()

        logger.info("Recall worker started.")
        while not self.stop_event.is_set():
            today = datetime.date.today().isoformat()
            if today != current_day:
                summary_file = os.path.join(
                    SUMMARY_DIR, f"{current_day}_summary.mp4")
                if not os.path.exists(summary_file):
                    if concat_daily_videos(current_day, summary_file):
                        mark_summary(current_day, summary_file)
                current_day = today
                day_images_dir = os.path.join(IMAGES_DIR, current_day)
                os.makedirs(day_images_dir, exist_ok=True)

            # Capture
            last_img = capture_screenshot(
                last_img, session_dir, current_day, session_label)
            time.sleep(CAPTURE_INTERVAL)

            if time.time() - session_start_time >= SESSION_MINUTES * 60:
                if get_idle_time_seconds() >= IDLE_THRESHOLD:
                    out_file = os.path.join(
                        DETAILED_DIR, f"{current_day}_{session_label}.mp4")
                    if not os.path.exists(out_file):
                        if make_video_from_folder(session_dir, out_file):
                            mark_video(current_day, session_label, out_file)
                session_start_time = time.time()
                session_label = new_session_labels(datetime.datetime.now())
                session_dir = os.path.join(day_images_dir, session_label)
                os.makedirs(session_dir, exist_ok=True)

            if time.time() - last_backlog_sweep >= 5 * 60:
                if get_idle_time_seconds() >= IDLE_THRESHOLD:
                    self.process_backlog()
                last_backlog_sweep = time.time()

        logger.info("Recall worker stopping...")

    def process_backlog(self):
        for day, session in get_pending_video_sessions():
            folder = os.path.join(IMAGES_DIR, day, session)
            if not os.path.isdir(folder):
                continue
            out_file = os.path.join(DETAILED_DIR, f"{day}_{session}.mp4")
            if os.path.exists(out_file):
                continue
            logger.info(
                "[BACKLOG] Creating detailed video for %s %s", day, session)
            if make_video_from_folder(folder, out_file):
                mark_video(day, session, out_file)

        for day in get_pending_summary_days():
            out_file = os.path.join(SUMMARY_DIR, f"{day}_summary.mp4")
            if os.path.exists(out_file):
                continue
            logger.info("[BACKLOG] Creating summary for %s", day)
            if concat_daily_videos(day, out_file):
                mark_summary(day, out_file)

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
    stop_event.set()
    icon.stop()


def run_tray_app():
    stop_event = threading.Event()
    worker = RecallWorker(stop_event)
    worker.start()

    menu = TrayMenu(
        Item("Open Recall Folder", open_root),
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
