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
    else:
        # Let ffmpeg stream images directly from disk (much lower RAM usage)
        cmd = [
            FFMPEG, "-y",
            "-framerate", str(images_per_second),
            "-pattern_type", "glob",
            "-i", os.path.join(folder, "*.webp"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            out_file
        ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        logger.info("Created video: %s (images=%d, %.3fs/image => %.2f images/sec)",
                    out_file, len(images), per_image, images_per_second)
        return True
    except subprocess.CalledProcessError as e:
        logger.exception("ffmpeg failed for %s: %s", folder, e)
        return False


def concat_daily_videos(day: str, out_file: str) -> bool:
    """
    Create a TIMELAPSE daily summary for `day` by:
      - streaming all detailed mp4s in lexicographic order
      - determining detailed fps (via ffprobe if available)
      - applying a speed-up filter to match SUMMARY_VIDEO_FPS
    """
    if not ffmpeg_exists():
        logger.error("ffmpeg not found in PATH. Skipping summary creation.")
        return False

    day_dir = get_detailed_day_dir(day)
    mp4s = sorted(glob.glob(os.path.join(day_dir, "*.mp4")))

    if not mp4s:
        logger.warning("No detailed videos found for day: %s", day)
        return False

    # Stream all MP4s with glob instead of building concat list
    input_pattern = os.path.join(day_dir, "*.mp4")

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
                    "-of", "default=noprint_wrappers=1:nokey=1", mp4s[0]],
                capture_output=True, text=True, check=True
            )
            fps_str = (res.stdout or "").strip()
            detailed_fps = _parse_frac(fps_str)
        except Exception:
            logger.exception(
                "ffprobe failed to read avg_frame_rate for %s", mp4s[0])

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

    # speed_factor = summary_fps / detailed_fps, ensure >= 1.0 so we don't accidentally slow the day down
    speed_factor = summary_fps_local / detailed_fps if detailed_fps > 0 else 1.0
    if speed_factor < 1.0:
        speed_factor = 1.0

    logger.info("Daily concat: detailed_fps=%.3f, summary_fps=%.3f, speed_factor=%.3f",
                detailed_fps, summary_fps_local, speed_factor)

    # Build ffmpeg command
    cmd = [
        FFMPEG, "-y",
        "-pattern_type", "glob",
        "-i", input_pattern,
        "-filter:v", f"setpts=PTS/{speed_factor}",
        "-r", str(int(summary_fps_local)),
        "-an",
        out_file
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        logger.info("Created daily timelapse summary: %s", out_file)
        return True
    except subprocess.CalledProcessError as e:
        logger.exception("ffmpeg timelapse failed for %s: %s", day, e)
        return False
