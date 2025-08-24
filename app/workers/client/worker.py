import threading
from app.client import run_flask_app


def run_flask_thread(stop_event: threading.Event = None):
    """
    Run Flask app in a daemon thread. Uses app.run (Werkzeug) — OK for local desktop use.
    """

    thr = threading.Thread(target=run_flask_app,
                           daemon=True, name="FlaskThread")
    thr.start()
    return thr
