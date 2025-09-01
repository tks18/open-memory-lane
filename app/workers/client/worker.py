import threading
from app.client import run_flask_app


def run_flask_thread(stop_event: threading.Event = None):
    """
    Start the flask app in a thread.
    This is used to run the flask app in a separate thread so that the main
    thread can continue to run other tasks.

    Args:
        stop_event (threading.Event, optional): threading event to stop the thread. Defaults to None.

    Returns:
        threading.Thread: thread object
    """

    thr = threading.Thread(target=run_flask_app,
                           daemon=True, name="FlaskThread")
    thr.start()
    return thr
