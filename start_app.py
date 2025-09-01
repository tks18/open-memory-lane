import subprocess
import os

from app.helpers.config import LOG_FOLDER

os.makedirs(LOG_FOLDER, exist_ok=True)  # Ensure the log folder exists

LOG_PATH_APP_CLI = os.path.join(LOG_FOLDER, "recorder_cli.log")
LOG_PATH_CLIENT = os.path.join(LOG_FOLDER, "client_cli.log")

base_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(base_dir, ".venv", "Scripts",
                           "python.exe")  # your venv python
app_path = os.path.join(base_dir, "main.py")


def run_hidden(script_path, log_path):
    """
    Run a script in the background without opening a console window.

    Args:
        script_path (str): Path to the script to run.
        log_path (str): Path to the log file to capture output.
    """
    creationflags = subprocess.CREATE_NO_WINDOW
    subprocess.Popen([venv_python, script_path],
                     stdout=open(log_path, "w"),
                     stderr=subprocess.STDOUT,
                     creationflags=creationflags)


run_hidden(app_path, LOG_PATH_APP_CLI)

print("✅ Scripts launched in background.")
