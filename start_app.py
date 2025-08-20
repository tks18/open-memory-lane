import subprocess
import sys
import os
from pathlib import Path
import yaml

# Load the ocnfiguration from a YAML file if it exists
with open(".config.yml", "r") as f:
    cfg = yaml.safe_load(f)

LOG_FOLDER = Path(cfg["paths"]["log_folder"])
LOG_PATH_APP_CLI = os.path.join(LOG_FOLDER, "recorder_cli.log")
LOG_PATH_CLIENT = os.path.join(LOG_FOLDER, "client.log")

base_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(base_dir, ".venv", "Scripts",
                           "python.exe")  # your venv python
app_path = os.path.join(base_dir, "main.py")
client_path = os.path.join(base_dir, "client.py")


def run_hidden(script_path, log_path):
    creationflags = subprocess.CREATE_NO_WINDOW
    subprocess.Popen([venv_python, script_path],
                     stdout=open(log_path, "w"),
                     stderr=subprocess.STDOUT,
                     creationflags=creationflags)


run_hidden(app_path, LOG_PATH_APP_CLI)
run_hidden(client_path, LOG_PATH_CLIENT)

print("✅ Both scripts launched in background.")
