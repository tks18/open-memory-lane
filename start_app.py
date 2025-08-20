import subprocess
import sys
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(base_dir, ".venv", "Scripts",
                           "python.exe")  # your venv python
app_path = os.path.join(base_dir, "main.py")
client_path = os.path.join(base_dir, "client.py")


def run_hidden(script_path):
    creationflags = subprocess.CREATE_NO_WINDOW
    subprocess.Popen([venv_python, script_path],
                     stdout=open(script_path + ".log", "w"),
                     stderr=subprocess.STDOUT,
                     creationflags=creationflags)


run_hidden(app_path)
run_hidden(client_path)

print("✅ Both scripts launched in background.")
