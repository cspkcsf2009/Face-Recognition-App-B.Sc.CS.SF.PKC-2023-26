import os
import subprocess
import time
import psutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from gunicorn_config import get_bind  # Import function to retrieve bind information

class ChangeHandler(FileSystemEventHandler):
    def __init__(self, process):
        self.process = process

    def on_any_event(self, event):
        print(f"File change detected: {event.src_path}")  # Debugging line
        self.process.terminate()
        self.process.wait()  # Wait for the process to terminate completely
        self.process = start_gunicorn()

def kill_process_using_port(port):
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in proc.net_connections(kind='inet'):
                if conn.laddr.port == port:
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def start_gunicorn():
    bind_info = get_bind()
    print(f"Bind info: {bind_info}")  # Debugging line

    # Dynamic Port Extraction
    try:
        _, port = bind_info.split(':')  # Extract port from bind info
        port = int(port.strip())
    except ValueError:
        port = 8000  # Default port number if extraction fails

    # Kill existing processes using the dynamically retrieved port
    kill_process_using_port(port)

    return subprocess.Popen(['gunicorn', '-c', 'gunicorn_config.py', 'app:app'])

if __name__ == "__main__":
    # Start Gunicorn initially
    process = start_gunicorn()

    # Set up file change monitoring
    event_handler = ChangeHandler(process)
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()
    process.terminate()
