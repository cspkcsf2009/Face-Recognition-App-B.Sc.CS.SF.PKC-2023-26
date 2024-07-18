import subprocess
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class WatchdogHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.is_directory:
            return
        if event.event_type == 'modified' or event.event_type == 'created':
            print(f'Restarting script due to {event.event_type} event...')
            subprocess.run([sys.executable, 'main.py'])

if __name__ == "__main__":
    event_handler = WatchdogHandler()
    observer = Observer()
    observer.schedule(event_handler, '.', recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()