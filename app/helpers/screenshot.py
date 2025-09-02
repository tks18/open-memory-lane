"""
==========================
Screenshot Helper Module
==========================

This module provides helper functions for capturing screenshots and writing them to the database.
It implements mss library to capture the screen and PIL library to process and save the captured image.
Also we capture only meaninful changes of the capture. It uses Dhash and Hamming distance to detect changes and only capture if its greater than a threshold.


Features:
- Implements a `capture_screenshot` function that captures a screenshot and writes it to the database.
- uses mss library to capture the screen
- uses PIL library to process and save the captured image
- uses Dhash and Hamming distance to detect changes
- uses db_writer to write to the database
- uses video_writer to create videos

Usage:
>>> from app.helpers.screenshot import capture_screenshot
>>> capture_screenshot(db_writer, last_img, save_dir, day, session) -> Current Image / Previous Image


*Author: Sudharshan TK*\n
*Created: 2025-08-31*
"""

import os
import datetime
import numpy as np
import cv2
from typing import Optional, Tuple
from mss import mss
from PIL import Image, ImageDraw, ImageFont

from app.logger import logger
from app.helpers.win import get_active_window_info
from app.helpers.paths import to_backup_equivalent
from app.workers.db_writer import add_image, DBWriter

import app.helpers.config as cfg

# Dirs
IMAGES_DIR = cfg.IMAGES_DIR
BACKUP_IMAGES_DIR = cfg.BACKUP_IMAGES_DIR

# Tuning params
WEBP_QUALITY = cfg.WEBP_QUALITY
HASH_SIZE = cfg.HASH_SIZE
HAMMING_THRESHOLD = cfg.HAMMING_THRESHOLD
PERSISTENCE_FRAMES = cfg.PERSISTENCE_FRAMES
AREA_SMALL = cfg.AREA_SMALL
AREA_FRAC_THRESHOLD = cfg.AREA_FRAC_THRESHOLD

# Internal state
last_hash: Optional[np.ndarray] = None
last_frame_cv: Optional[np.ndarray] = None
consec_diff = 0
last_window: Optional[Tuple[str, str]] = None


def dhash_bits(cv_img_bgr: np.ndarray, hash_size: int = HASH_SIZE) -> np.ndarray:
    """
    Function to compute the difference hash of an image

    Args:
        cv_img_bgr (np.ndarray): Numpy array of the image
        hash_size (int, optional): hash size. Defaults to HASH_SIZE.

    Returns:
        np.ndarray: The difference hash
    """
    gray = cv2.cvtColor(cv_img_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (hash_size + 1, hash_size),
                       interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    return diff.astype(np.uint8).flatten()


def hamming_distance_bits(b1: Optional[np.ndarray], b2: Optional[np.ndarray]) -> int:
    """
    Function to compute the hamming distance between two difference hashes

    Args:
        b1 (Optional[np.ndarray]): Numpy array of the first difference hash
        b2 (Optional[np.ndarray]): Numpy array of the second difference hash

    Returns:
        int: The hamming distance
    """
    if b1 is None or b2 is None:
        return int(1e9)
    return int(np.count_nonzero(b1 != b2))


def changed_area_fraction(cv_img1_bgr: Optional[np.ndarray], cv_img2_bgr: Optional[np.ndarray], small_size: Tuple[int, int] = AREA_SMALL) -> float:
    """
    Function to compute the changed area fraction between two images

    Args:
        cv_img1_bgr (Optional[np.ndarray]): Numpy array of the first image
        cv_img2_bgr (Optional[np.ndarray]): Numpy array of the second image
        small_size (Tuple[int, int], optional): The size of the small image. Defaults to AREA_SMALL.

    Returns:
        float: The changed area fraction
    """
    if cv_img1_bgr is None or cv_img2_bgr is None:
        return 1.0
    a = cv2.resize(cv_img1_bgr, small_size, interpolation=cv2.INTER_AREA)
    b = cv2.resize(cv_img2_bgr, small_size, interpolation=cv2.INTER_AREA)
    a_gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    b_gray = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(a_gray, b_gray)
    _, th = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
    return int(np.count_nonzero(th)) / th.size if th.size > 0 else 0.0


def capture_screenshot(db_writer: DBWriter, last_img: Optional[Image.Image], save_dir: str, day: str, session: str) -> Optional[Image.Image]:
    """
    Function to capture a screenshot.

    Implementation:
    1. Capture the screen using mss library.
    2. Get the active window title and application name.
    3. Convert the captured image to a PIL Image.
    4. Determine if the screenshot should be saved based on changes detected using Dhash and Hamming distance.
    5. If it should be saved, save the image as a WEBP file with a timestamp overlay.
    6. Write the image details to the database using db_writer.
    7. Update internal state variables for future comparisons.

    Args:
        db_writer (DBWriter): DB Writer Worker
        last_img (Optional[Image.Image]): Last captured image
        save_dir (str): Directory to save the image
        day (str): Day in YYYY-MM-DD format
        session (str): Session in HHMM-HHMM format

    Returns:
        Optional[Image.Image]: The current frame or previous frame if no change is detected
    """
    global last_hash, last_frame_cv, consec_diff, last_window

    try:
        with mss() as sct:
            raw = sct.grab(sct.monitors[0])
            window_title, app_name = get_active_window_info()
            pil_img = Image.frombytes("RGB", raw.size, raw.rgb)

        should_save = False
        window_tuple = (window_title, app_name)
        curr_cv = cv2.cvtColor(np.asarray(pil_img), cv2.COLOR_RGB2BGR)

        # Always save if first frame or window changed
        if last_hash is None or last_img is None or window_tuple != last_window:
            should_save = True
        else:
            # Check if there is a change
            # Compute difference hash
            # Compute hamming distance (Hamming Distance is the number of bits that are different between the two difference hashes)
            curr_hash = dhash_bits(curr_cv)
            dist = hamming_distance_bits(curr_hash, last_hash)

            if dist >= HAMMING_THRESHOLD:
                area_frac = changed_area_fraction(last_frame_cv, curr_cv)
                if area_frac >= AREA_FRAC_THRESHOLD:
                    should_save = True
                else:
                    consec_diff += 1
            elif dist > (HAMMING_THRESHOLD // 2):
                area_frac = changed_area_fraction(last_frame_cv, curr_cv)
                if area_frac >= AREA_FRAC_THRESHOLD:
                    consec_diff += 1
                else:
                    consec_diff = 0
            else:
                consec_diff = 0

            if consec_diff >= PERSISTENCE_FRAMES:
                should_save = True

        if should_save:
            now_dt = datetime.datetime.now()
            fname = now_dt.strftime("SCREENSHOT_%d_%m_%Y_%H_%M_%S.webp")
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, fname)

            # Prepare timestamp
            timestamp = now_dt.strftime(
                f"{app_name} | {window_title} | %Y-%m-%d %H:%M:%S")

            # Create a small overlay to draw text with alpha and composite it.
            # Using full-size overlay is simple and memory-light for typical screens.
            overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Load font (fallback to default if truetype not available)
            try:
                font = ImageFont.truetype("arial.ttf", 15)
            except Exception:
                font = ImageFont.load_default(15)

            # Measure text size robustly:
            try:
                # Newer Pillow: textbbox gives exact bbox (left,top,right,bottom)
                bbox = draw.textbbox((0, 0), timestamp, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except Exception:
                # Fallback for older Pillow versions
                try:
                    text_width, text_height = font.getsize(timestamp)
                except Exception:
                    # Super-defensive fallback
                    text_width, text_height = (len(timestamp) * 7, 14)

            # Position: Bottom-center with margin
            margin = 8
            x = (pil_img.width - text_width) // 2  # Center horizontally
            y = pil_img.height - text_height - margin  # Bottom with margin

            # Draw semi-transparent rounded-ish rectangle behind text (slightly larger than text)
            rect_padding = 10
            rect_x0 = x - rect_padding
            rect_y0 = y - rect_padding
            rect_x1 = x + text_width + rect_padding
            rect_y1 = y + text_height + rect_padding

            # Semi-transparent black background
            draw.rectangle(
                [(rect_x0, rect_y0), (rect_x1, rect_y1)], fill=(0, 0, 0, 255))

            # Draw the timestamp (white, fully opaque)
            draw.text((x, y), timestamp, font=font, fill=(255, 255, 255, 255))

            # Composite overlay onto original image
            # Convert base image to RGBA, paste overlay, then convert back to RGB before saving
            base_rgba = pil_img.convert("RGBA")
            composited = Image.alpha_composite(
                base_rgba, overlay).convert("RGB")
            composited.save(path, "WEBP", quality=WEBP_QUALITY)

            # Encourage GC on ephemeral images
            try:
                overlay.close()
                base_rgba.close()
                composited.close()
            except Exception:
                pass

            backup_equiv = ""
            try:
                backup_equiv = to_backup_equivalent(
                    path, IMAGES_DIR, BACKUP_IMAGES_DIR)
            except Exception:
                backup_equiv = ""

            try:
                add_image(db_writer, day, session, path,
                          window_title, app_name, backup_equiv)
            except Exception as e:
                logger.exception("add_image/db write failed: %s", e)

            last_hash = dhash_bits(curr_cv)
            last_frame_cv = curr_cv
            consec_diff = 0
            last_window = window_tuple

            return pil_img

        # no save -> just update internal state
        last_hash = dhash_bits(curr_cv)
        last_frame_cv = curr_cv
        last_window = window_tuple
        return last_img

    except Exception as e:
        logger.exception("Screenshot capture failed: %s", e)
        return last_img
