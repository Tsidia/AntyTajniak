# database_manager.py

import os
import re

# Adjust the path as needed. Here we assume database file is in the same directory.
database_path = os.path.join(os.path.dirname(__file__), 'license_plate_database.txt')

# A global set that holds all known database entries
database_entries = set()

# Load the database on module import
if not os.path.exists(database_path):
    open(database_path, 'w', encoding='utf-8').close()

with open(database_path, 'r', encoding='utf-8') as f:
    # Each line is one plate
    database_entries = {line.strip() for line in f if line.strip()}


def normalize_plate(text: str) -> str:
    text = text.upper()
    text = re.sub(r'[^A-Z0-9]', '', text)
    return text


def save_database():
    with open(database_path, 'w', encoding='utf-8') as f:
        for plate in sorted(database_entries):
            f.write(plate + "\n")


def refresh_database_list(listbox):
    """
    Clear and repopulate the Tkinter listbox with the current `database_entries`.
    """
    listbox.delete(0, "end")
    for plate in sorted(database_entries):
        listbox.insert("end", plate)


def add_plate_entry(entry_widget, listbox):
    """
    Add a new plate from the entry widget to the database and refresh the listbox.
    """
    new_plate = entry_widget.get().strip()
    new_plate = normalize_plate(new_plate)
    if new_plate and new_plate not in database_entries:
        database_entries.add(new_plate)
        save_database()
        refresh_database_list(listbox)
        entry_widget.delete(0, "end")


def remove_selected_plate(listbox):
    """
    Remove the currently selected plate in the listbox from the database.
    """
    selection = listbox.curselection()
    if selection:
        plate_to_remove = listbox.get(selection[0])
        if plate_to_remove in database_entries:
            database_entries.remove(plate_to_remove)
            save_database()
            refresh_database_list(listbox)
