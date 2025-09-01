import os
import threading
import signal
import webbrowser

from PIL import Image
import pystray
from pystray import MenuItem as Item, Menu as TrayMenu

from app.helpers.general import ensure_dirs
from app.logger import configure_logger, logger
from app.helpers.config import CLIENT_PORT, DB_PATH, LOG_FOLDER, BASE_DIR
from app.workers import DBWriter, BackupWorker, CaptureWorker, VideoWriter, run_flask_thread, graceful_workers_shutdown
from app.helpers.video import ffmpeg_exists

# =========================
# Tray Icon
# =========================


def create_tray_image():
    img = Image.open(os.path.join("__assets__", "recall_logo.png"))
    img = img.convert("RGBA")
    return img


def open_logs(_icon=None, _item=None):
    try:
        os.startfile(LOG_FOLDER)
    except Exception:
        pass


def open_root(_icon=None, _item=None):
    try:
        os.startfile(os.path.abspath(BASE_DIR))
    except Exception:
        pass


def open_browser(icon, item):
    webbrowser.open(f'http://localhost:{CLIENT_PORT}/')


def run_tray_app():
    """
    Main function to run the tray application.
    Initializes and starts all worker threads, sets up signal handlers for graceful shutdown,
    and starts the tray icon.
    """
    global worker, backup_thread

    ensure_dirs()

    configure_logger()

    stop_event = threading.Event()

    # Start DB Writer
    db_writer = DBWriter(thread_name="DBWriterThread", db_path=DB_PATH)
    db_writer.start()

    # Start Video Worker
    video_thread = VideoWriter(
        thread_name="VideoWriterThread", db_writer=db_writer, flush_interval=1 * 60)

    video_thread.start()

    # Start Main Worker
    capture_worker = CaptureWorker(stop_event=stop_event,
                                   thread_name="CaptureThread", db_writer=db_writer, video_writer=video_thread)
    capture_worker.start()

    # Start backup worker thread
    backup_thread = BackupWorker(
        stop_event=stop_event, thread_name="BackupThread", interval_seconds=3 * 60 * 60)
    backup_thread.start()

    flask_thread = run_flask_thread(stop_event=stop_event)
    logger.info("Flask thread started on port %s", CLIENT_PORT)

    main_workers = [backup_thread, capture_worker]
    writer_workers = [video_thread, db_writer]

    signal.signal(
        signal.SIGINT, lambda *a: graceful_workers_shutdown(icon,
                                                            None, stop_event, main_workers, writer_workers))
    signal.signal(signal.SIGTERM, lambda *a: graceful_workers_shutdown(icon,
                  None, stop_event, main_workers, writer_workers))

    menu = TrayMenu(
        Item("Open Folder", open_root),
        Item("Open Client", open_browser),
        Item("Open Logs", open_logs),
        Item("Exit", lambda icon, item: graceful_workers_shutdown(
            icon, item, stop_event, main_workers, writer_workers))
    )

    icon = pystray.Icon("Shan's Memory Recorder", create_tray_image(),
                        "Shan's Memory Recorder", menu)
    icon.run()


def start_app():
    """
    Entry point to start the tray application.
    Checks for ffmpeg availability and starts the tray app.
    Handles exceptions and logs fatal errors.
    """
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
