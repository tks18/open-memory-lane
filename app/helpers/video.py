"""
==========================
Video Helper Module
==========================

This module provides helper functions for creating videos from images
and concatenating daily summaries.


Features:
- `make_video`: Creates a video from a set of images.
- `concat_videos`: Concatenates a set of videos into a single video.

Usage:
>>> from app.helpers.video import make_video, concat_videos
>>> make_video("captures/20250824_10", "videos/20250824_10.mp4")
>>> concat_videos("20250824", "videos/summary_20250824.mp4")


*Author: Sudharshan TK*\n
*Created: 2025-08-24*
"""

import os
import subprocess
import glob
import shutil
import tempfile

from app.helpers.config import FFMPEG, SESSION_VIDEO_FPS, SUMMARY_VIDEO_FPS
from app.logger import logger
from app.helpers.paths import get_detailed_day_dir


def _ffconcat_line(p: str) -> str:
    safe = os.path.abspath(p).replace("\\", "/")
    safe = safe.replace("'", r"\'")
    return f"file '{safe}'\n"


def ffmpeg_exists() -> bool:
    """
    Check if ffmpeg is available.

    Returns:
        bool: True if ffmpeg is available, False otherwise.
    """
    try:
        subprocess.run([FFMPEG, "-version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def _run_and_log(cmd):
    """
    Run a subprocess command and log errors if it fails.

    Args:
        cmd (list): Command and arguments to run.

    Returns:
        bool: True if command succeeded, False otherwise.
    """
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True)
        return True
    except subprocess.CalledProcessError as e:
        # decode stderr if possible and log for debugging
        err = (e.stderr.decode("utf-8", errors="replace")
               if getattr(e, "stderr", None) else str(e))
        logger.exception(
            "ffmpeg failed: %s\ncmd: %s\nstderr: %s", e, " ".join(cmd), err)
        return False
    except Exception as e:
        logger.exception(
            "Unexpected error running ffmpeg: %s (cmd=%s)", e, " ".join(cmd))
        return False


def make_video_from_folder(folder: str, out_file: str, images_per_second: int = SESSION_VIDEO_FPS) -> bool:
    """
    Create a video from a folder of images using ffmpeg.

    Implementation:
    1. Check if ffmpeg is available.
    2. List and sort all .webp images in the folder.
    3. If no images, log a warning and return False.
    4. If only one image, create a video by looping that image for the required duration.
    5. If multiple images, create a temporary directory and populate it with sequentially named hardlinks to the images.
       This ensures ffmpeg can read them in order.
    6. Use ffmpeg to create the video from the sequential images.
    7. Clean up the temporary directory.

    Args:
        folder (str): Path to the folder containing images.
        out_file (str): Path to the output video file.
        images_per_second (int, optional): Images per second. Defaults to SESSION_VIDEO_FPS.

    Returns:
        bool: True if video creation succeeded, False otherwise.
    """
    if not ffmpeg_exists():
        logger.error("ffmpeg not found in PATH. Skipping video creation.")
        return False

    images = sorted(
        p for p in os.listdir(folder)
        if p.lower().endswith(".webp")
    )

    if not images:
        logger.warning("No images in folder: %s", folder)
        return False

    per_image = 1.0 / float(images_per_second)

    # Edge case: single image -> loop that one for the required duration
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
        return _run_and_log(cmd)

    # Create temporary dir and populate sequential hardlinks (frame_000001.webp ...)
    tmp_dir = tempfile.mkdtemp(prefix="pr_frames_")
    try:
        for i, img in enumerate(images, start=1):
            src = os.path.join(folder, img)
            dst = os.path.join(tmp_dir, f"{i:06d}.webp")
            try:
                # attempt a hardlink (cheap & quick)
                os.link(src, dst)
            except Exception:
                # fallback to copy if linking is not possible
                shutil.copy2(src, dst)

        seq_pattern = os.path.join(tmp_dir, "%06d.webp").replace("\\", "/")
        cmd = [
            FFMPEG, "-y",
            "-framerate", str(images_per_second),
            "-i", seq_pattern,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            out_file
        ]
        ok = _run_and_log(cmd)
        if ok:
            logger.info("Created video: %s (images=%d, %.3fs/image => %.2f images/sec)",
                        out_file, len(images), per_image, images_per_second)
        return ok
    finally:
        # cleanup temp dir
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            logger.exception("Failed to remove temp frames dir: %s", tmp_dir)


def concat_daily_videos(day: str, out_file: str) -> bool:
    """
    Concatenate all detailed videos for a given day into a single summary video.

    Implementation:
    1. Check if ffmpeg is available.
    2. List and sort all .mp4 files in the detailed day directory.
    3. If no videos found, log a warning and return False.
    4. Create a temporary concat list file with paths to each video.
    5. Probe the fps of the first video using ffprobe (if available) to determine speed factor.
    6. Use ffmpeg with the concat demuxer and a setpts filter to create a timelapse summary video.
    7. Clean up the temporary concat list file.

    Args:
        day (str): Day in ISO format (YYYY-MM-DD).
        out_file (str): Path to the output summary video file.

    Returns:
        bool: True if summary creation succeeded, False otherwise.
    """
    if not ffmpeg_exists():
        logger.error("ffmpeg not found in PATH. Skipping summary creation.")
        return False

    day_dir = get_detailed_day_dir(day)
    mp4s = sorted(glob.glob(os.path.join(day_dir, "*.mp4")))

    if not mp4s:
        logger.warning("No detailed videos found for day: %s", day)
        return False

    # Create concat list file (platform-agnostic)
    list_file = os.path.join(day_dir, f"{day}_concat_list.txt")
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in mp4s:
                f.write(_ffconcat_line(p))

        # Probe fps from first file (if ffprobe available)
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

        detailed_fps = None
        if shutil.which("ffprobe") is not None:
            try:
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

        if not detailed_fps or detailed_fps <= 0:
            logger.warning(
                "Couldn't determine detailed_fps via ffprobe, falling back to SESSION_VIDEO_FPS=%s", SESSION_VIDEO_FPS)
            detailed_fps = float(SESSION_VIDEO_FPS)

        try:
            summary_fps_local = float(SUMMARY_VIDEO_FPS)
        except Exception:
            summary_fps_local = float(SESSION_VIDEO_FPS)

        speed_factor = summary_fps_local / detailed_fps if detailed_fps > 0 else 1.0
        if speed_factor < 1.0:
            speed_factor = 1.0

        logger.info("Daily concat: detailed_fps=%.3f, summary_fps=%.3f, speed_factor=%.3f",
                    detailed_fps, summary_fps_local, speed_factor)

        # Use concat demuxer as ffmpeg input and apply timelapse filter on-the-fly (no tmp file)
        cmd = [
            FFMPEG, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-filter:v", f"setpts=PTS/{speed_factor}",
            "-r", str(int(summary_fps_local)),
            "-an",
            out_file
        ]
        ok = _run_and_log(cmd)
        if ok:
            logger.info(
                "Created daily timelapse summary: %s (speed_factor=%.3f)", out_file, speed_factor)
        return ok

    finally:
        # cleanup concat list
        try:
            if os.path.exists(list_file):
                os.remove(list_file)
        except Exception:
            logger.exception("Failed to remove concat list: %s", list_file)
