# ui.py

import tkinter as tk
import customtkinter as ctk
import threading
import time
import queue

from settings_manager import load_settings, save_settings
from database_manager import (
    database_entries,
    refresh_database_list,
    add_plate_entry,
    remove_selected_plate
)
import map_display
from detection import detection_queue, running

def show_database_screen(camera_frame):
    # Clear parent frame
    for widget in camera_frame.winfo_children():
        widget.pack_forget()

    title_label = ctk.CTkLabel(camera_frame, text="Baza tajniaków", font=("Arial", 20), text_color="white")
    title_label.pack(pady=10)

    list_frame = ctk.CTkFrame(camera_frame, corner_radius=10, fg_color="#2e2e2e")
    list_frame.pack(pady=20, fill="both", expand=True)

    scrollbar = tk.Scrollbar(list_frame, orient="vertical")
    plate_listbox = tk.Listbox(
        list_frame, 
        yscrollcommand=scrollbar.set,
        font=("Arial", 14),
        bg="#121212",
        fg="white",
        selectbackground="#333333",
        highlightthickness=0,
        selectforeground="white"
    )
    scrollbar.config(command=plate_listbox.yview)
    scrollbar.pack(side="right", fill="y")
    plate_listbox.pack(side="left", fill="both", expand=True)

    refresh_database_list(plate_listbox)

    control_frame = ctk.CTkFrame(camera_frame, corner_radius=10, fg_color="#2e2e2e")
    control_frame.pack(pady=20)

    add_label = ctk.CTkLabel(control_frame, text="Dodaj tablicę rejestracyjną:", 
                             font=("Arial", 14), text_color="white")
    add_label.grid(row=0, column=0, padx=10, pady=10)

    add_entry = ctk.CTkEntry(control_frame, font=("Arial", 14), width=200)
    add_entry.grid(row=0, column=1, padx=10, pady=10)

    add_button = ctk.CTkButton(control_frame, text="Dodaj", width=100,
                               command=lambda: add_plate_entry(add_entry, plate_listbox))
    add_button.grid(row=0, column=2, padx=10, pady=10)

    remove_button = ctk.CTkButton(control_frame, text="Usuń zaznaczoną", width=100,
                                  command=lambda: remove_selected_plate(plate_listbox))
    remove_button.grid(row=0, column=3, padx=10, pady=10)


def show_settings_screen(camera_frame):
    # Clear parent frame
    for widget in camera_frame.winfo_children():
        widget.pack_forget()

    settings = load_settings()

    title_label = ctk.CTkLabel(camera_frame, text="Ustawienia", font=("Arial", 24, "bold"), text_color="white")
    title_label.pack(pady=20)

    settings_frame = ctk.CTkFrame(camera_frame)
    settings_frame.pack(pady=20, padx=20, fill="x")

    # --- Mismatch Tolerance ---
    mismatch_frame = ctk.CTkFrame(settings_frame)
    mismatch_frame.pack(pady=10, padx=10, fill="x")

    mismatch_label = ctk.CTkLabel(mismatch_frame,
                                  text="Dopuszczalna liczba błędnych znaków (0–5)",
                                  font=("Arial", 16),
                                  text_color="black")
    mismatch_label.pack(pady=5)

    mismatch_value_label = ctk.CTkLabel(mismatch_frame,
                                        text=f"Obecna wartość: {settings.get('mismatch_tolerance', 1)}",
                                        font=("Arial", 14),
                                        text_color="black")
    mismatch_value_label.pack(pady=5)

    def update_mismatch_tolerance(value):
        val = int(float(value))
        mismatch_value_label.configure(text=f"Obecna wartość: {val}")
        settings['mismatch_tolerance'] = val
        save_settings(settings)

    mismatch_slider = ctk.CTkSlider(mismatch_frame, from_=0, to=5,
                                    number_of_steps=5,
                                    command=update_mismatch_tolerance)
    mismatch_slider.set(settings.get('mismatch_tolerance', 1))
    mismatch_slider.pack(pady=10, padx=20, fill="x")

    desc_text = (
        "Określa liczbę znaków w tablicy rejestracyjnej,\n"
        "które mogą się nie zgadzać, a mimo to\n"
        "uznamy wykryty tekst za trafienie w bazie."
    )
    desc_label = ctk.CTkLabel(mismatch_frame, text=desc_text,
                              font=("Arial", 12), text_color="black", justify="left")
    desc_label.pack(pady=10)

    # --- Volume Level ---
    volume_frame = ctk.CTkFrame(settings_frame)
    volume_frame.pack(pady=10, padx=10, fill="x")

    volume_label = ctk.CTkLabel(volume_frame, text="Głośność powiadomień (0–100)",
                                font=("Arial", 16),
                                text_color="black")
    volume_label.pack(pady=5)

    volume_value_label = ctk.CTkLabel(volume_frame,
                                      text=f"Obecna wartość: {settings.get('volume_level', 100)}%",
                                      font=("Arial", 14),
                                      text_color="black")
    volume_value_label.pack(pady=5)

    def update_volume_level(value):
        val = int(float(value))
        val = max(0, min(val, 100))
        volume_value_label.configure(text=f"Obecna wartość: {val}%")
        settings['volume_level'] = val
        save_settings(settings)

    volume_slider = ctk.CTkSlider(volume_frame, from_=0, to=100,
                                  number_of_steps=100,
                                  command=update_volume_level)
    volume_slider.set(settings.get('volume_level', 100))
    volume_slider.pack(pady=10, padx=20, fill="x")


def show_info_screen(camera_frame):
    # Clear parent frame
    for widget in camera_frame.winfo_children():
        widget.pack_forget()

    version_label = ctk.CTkLabel(camera_frame,
                                 text="Wersja aplikacji: 1.0.0",
                                 font=("Arial", 16), text_color="white")
    version_label.pack(pady=10)

    authors_label = ctk.CTkLabel(camera_frame,
        text="Autorzy:\nJakub Gołębiewski\nKarol Marczak\nMarcel Oczeretko\nKrystian Klisz",
        font=("Arial", 16), text_color="white")
    authors_label.pack(pady=10)


def button_click(button_name, camera_frame):
    """
    Decides which screen to display based on button_name.
    """
    if button_name == "Mapa":
        # Clear and show map
        for widget in camera_frame.winfo_children():
            widget.pack_forget()
        map_display.show_map(camera_frame)

    elif button_name == "Baza tajniaków":
        show_database_screen(camera_frame)

    elif button_name == "Ustawienia":
        show_settings_screen(camera_frame)

    elif button_name == "Informacje":
        show_info_screen(camera_frame)


def play_alert_sound(alert_message, camera_frame):
    """
    Plays alert sound asynchronously and shows an on-screen label.
    """
    import threading
    from playsound import playsound

    # 1) play alert sound in separate thread
    threading.Thread(target=playsound, args=("alert.wav",), daemon=True).start()

    # 2) show a label
    alert_label = ctk.CTkLabel(camera_frame,
                               text=alert_message,
                               fg_color="red",
                               text_color="white",
                               font=("Arial", 24, "bold"))
    alert_label.pack(pady=10)

    # remove label after 5 seconds
    camera_frame.after(5000, alert_label.destroy)


def update_ui(camera_frame):
    """
    Periodically checks the detection_queue for events 
    (police_car or play_alert) and updates the map accordingly.
    Also removes expired police cars from the map if not detected again.
    """
    import time
    from detection import detection_queue
    from map_display import police_cars, place_or_move_police_car, road_canvas
    DETECTION_TIMEOUT = 5.0  # seconds

    # Process new queue items
    try:
        while True:
            item = detection_queue.get_nowait()
            if item[0] == 'police_car':
                # item = ('police_car', plate, depth, horiz_offset, orientation)
                _, plate, distance, horizontal_offset, orientation = item
                place_or_move_police_car(plate, distance, horizontal_offset, orientation)

            elif item[0] == 'play_alert':
                alert_message = item[1]
                play_alert_sound(alert_message, camera_frame)

    except queue.Empty:
        pass

    # Clean up old police cars
    now = time.time()
    to_remove = []
    for plate, info in police_cars.items():
        if now - info['last_detection_time'] >= DETECTION_TIMEOUT:
            # remove from canvas
            if road_canvas:
                road_canvas.delete(info['canvas_id'])
            to_remove.append(plate)
    for plate in to_remove:
        del police_cars[plate]

    # schedule next check
    camera_frame.after(100, update_ui, camera_frame)


def create_app():
    """
    Create and return the main CustomTkinter application.
    """
    app = ctk.CTk()
    app.geometry("1280x720")
    app.title("Anty Tajniak")

    # Layout: a sidebar + main camera_frame
    sidebar = ctk.CTkFrame(app, width=200, corner_radius=0, fg_color="#2e2e2e")
    sidebar.pack(side="left", fill="y")

    camera_frame = ctk.CTkFrame(app, corner_radius=0, fg_color="#121212")
    camera_frame.pack(side="right", fill="both", expand=True)

    # Sidebar Buttons
    sidebar.grid_rowconfigure(0, weight=1)
    sidebar.grid_rowconfigure(1, weight=1)
    sidebar.grid_rowconfigure(2, weight=1)
    sidebar.grid_rowconfigure(3, weight=1)

    map_btn = ctk.CTkButton(sidebar, text="Mapa",
        command=lambda: button_click("Mapa", camera_frame), width=180, height=50)
    map_btn.grid(row=0, padx=20, pady=20, sticky="ew")

    settings_btn = ctk.CTkButton(sidebar, text="Ustawienia",
        command=lambda: button_click("Ustawienia", camera_frame), width=180, height=50)
    settings_btn.grid(row=1, padx=20, pady=20, sticky="ew")

    database_btn = ctk.CTkButton(sidebar, text="Baza tajniaków",
        command=lambda: button_click("Baza tajniaków", camera_frame), width=180, height=50)
    database_btn.grid(row=2, padx=20, pady=20, sticky="ew")

    info_btn = ctk.CTkButton(sidebar, text="Informacje",
        command=lambda: button_click("Informacje", camera_frame), width=180, height=50)
    info_btn.grid(row=3, padx=20, pady=20, sticky="ew")

    # After the UI is loaded, we start with the "Mapa" view:
    app.after(1000, lambda: button_click("Mapa", camera_frame))

    # Start periodic UI update checks
    update_ui(camera_frame)

    return app
