# settings_manager.py

import json
import threading

SETTINGS_FILE = 'app_settings.json'
settings_lock = threading.Lock()


def load_settings():
    with settings_lock:
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # Return default settings if no file found
            return {
                'mismatch_tolerance': 1,
                'volume_level': 100
            }
        except json.JSONDecodeError:
            # Return defaults if file is corrupted
            return {
                'mismatch_tolerance': 1,
                'volume_level': 100
            }


def save_settings(settings: dict):
    with settings_lock:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
