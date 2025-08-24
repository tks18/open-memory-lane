
import os
import datetime
import numpy as np
import cv2
from typing import Optional, Tuple
from mss import mss
from PIL import Image

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
    gray = cv2.cvtColor(cv_img_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (hash_size + 1, hash_size),
                       interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    return diff.astype(np.uint8).flatten()


def hamming_distance_bits(b1: Optional[np.ndarray], b2: Optional[np.ndarray]) -> int:
    if b1 is None or b2 is None:
        return int(1e9)
    return int(np.count_nonzero(b1 != b2))


def changed_area_fraction(cv_img1_bgr: Optional[np.ndarray], cv_img2_bgr: Optional[np.ndarray], small_size: Tuple[int, int] = AREA_SMALL) -> float:
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
            pil_img.save(path, "WEBP", quality=WEBP_QUALITY)

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
