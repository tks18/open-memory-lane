import threading
import queue
import time
from app.logger import logger
from app.helpers.video import make_video_from_folder, concat_daily_videos
from app.workers.db_writer import DBWriter
from app.workers.db_writer.helpers import mark_summary, mark_video


class VideoWriter(threading.Thread):
    """
    Background worker for creating videos asynchronously.
    Jobs are enqueued via `enqueue_make` or `enqueue_concat`.
    The worker runs in a separate thread and executes ffmpeg jobs sequentially.
    """

    def __init__(self, thread_name: str, db_writer: DBWriter, flush_interval: float = 30 * 60):
        """
        Args:
            thread_name (str): Name of the worker thread.
            flush_interval (float): Time in seconds to wait for jobs before looping. Defaults to 2.0s.
        """
        super().__init__(name=thread_name, daemon=True)
        self.thread_name = thread_name
        self.flush_interval = flush_interval
        self.q = queue.Queue()
        self.db_writer = db_writer
        self.stop_event = threading.Event()

    def enqueue_detailed_video(self, folder: str, out_file: str, day: str, session: str, local_path: str, backup_path: str = None):
        """
        Queue a job to create a detailed video from a folder of images.
        This method adds a tuple to the queue with the following elements:
        - job type ("make")

        Args:
            folder (str): Folder containing the images to be processed.
            out_file (str): Output file name for the video.
            day (str): The day of the video (YYYY-MM-DD).
            session (str): The session name.
            local_path (str): The local path to the folder.
            backup_path (str, optional): The backup path to the folder. Defaults to None.
        """
        self.q.put(("make", folder, out_file, day,
                   session, local_path, backup_path))

    def enqueue_summary_video(self, day: str, out_file: str, local_path: str, backup_path: str = None):
        """
        Queue a job to concatenate daily videos into a summary video.
        This method adds a tuple to the queue with the following elements:
        - job type ("concat")

        Args:
            day (str): The day of the video (YYYY-MM-DD).
            out_file (str): The output file name for the summary video.
            local_path (str): The local path to the folder containing the daily videos.
            backup_path (str, optional): The backup path to the folder. Defaults to None.
        """
        self.q.put(("concat", day, out_file, local_path, backup_path))

    def run(self):
        """
        Main worker loop — pulls jobs from the queue and processes them asynchronously.
        Runs until `stop_event` is set, then flushes remaining jobs.
        This method is called in a separate thread and continuously checks the queue for jobs.
        """
        logger.info("Worker Started")
        while not self.stop_event.is_set():
            try:
                job = None
                try:
                    job = self.q.get(timeout=self.flush_interval)
                except queue.Empty:
                    continue  # no jobs, just loop again

                if not job:
                    continue

                job_type = job[0]
                if job_type == "make":
                    _, folder, out_file, day, session, local_path, backup_path = job
                    logger.info(
                        "Processing Detailed Video: %s -> %s", folder, out_file)
                    if make_video_from_folder(folder, out_file):
                        mark_video(self.db_writer, day, session,
                                   local_path, backup_path)
                elif job_type == "concat":
                    _, day, out_file, local_path, backup_path = job
                    logger.info(
                        "Processing Summary Video: day=%s -> %s", day, out_file)
                    if concat_daily_videos(day, out_file):
                        mark_summary(self.db_writer, day,
                                     local_path, backup_path)
                else:
                    logger.warning("Unknown job type: %s", job_type)

                self.q.task_done()
            except Exception:
                logger.exception(
                    "Worker loop exception")
                time.sleep(1)

        # Final flush
        self._flush_remaining()
        logger.info("Worker Stopped")

    def _flush_remaining(self):
        """
        Flush remaining jobs synchronously on stop.
        This method is called when the worker is stopped, and it flushes any remaining jobs in the queue.
        It is used to ensure that the worker thread exits cleanly.
        """
        logger.info("Flushing remaining jobs...")
        while not self.q.empty():
            try:
                job = self.q.get_nowait()
                job_type = job[0]
                if job_type == "make":
                    _, folder, out_file, day, session, local_path, backup_path = job
                    logger.info("Processing Detailed Video: %s -> %s",
                                folder, out_file)
                    if make_video_from_folder(folder, out_file):
                        mark_video(self.db_writer, day, session,
                                   local_path, backup_path)
                elif job_type == "concat":
                    _, day, out_file, local_path, backup_path = job
                    logger.info(
                        "Processing Summary Video: day=%s -> %s", day, out_file)
                    if concat_daily_videos(day, out_file):
                        mark_summary(self.db_writer, day,
                                     local_path, backup_path)
                self.q.task_done()
            except Exception:
                logger.exception("Error flushing job")

    def stop(self):
        """
        Stop the worker gracefully, flushing remaining jobs.
        This method is called when the application is shutting down to ensure that the worker thread exits cleanly.
        """
        self.stop_event.set()
        self.join()
        logger.info("Worker Stopped")
