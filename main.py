# main.py

import threading

from detection import detection_thread_front, detection_thread_back, running
from ui import create_app


def main():
    # Start the two RealSense detection threads in daemon mode
    front_thread = threading.Thread(target=detection_thread_front, daemon=True)
    back_thread = threading.Thread(target=detection_thread_back, daemon=True)
    front_thread.start()
    back_thread.start()

    # Build and run the UI
    app = create_app()
    try:
        app.mainloop()
    finally:
        # When the UI is closed, signal detection loops to stop
        global running
        running = False


if __name__ == "__main__":
    main()
