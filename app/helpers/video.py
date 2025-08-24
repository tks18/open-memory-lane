import os
import subprocess
import glob
import shutil

from app.helpers.config import FFMPEG, SESSION_VIDEO_FPS, SUMMARY_VIDEO_FPS
from app.logger import logger
from app.helpers.paths import get_detailed_day_dir


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
