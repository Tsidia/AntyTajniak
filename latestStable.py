import threading
import queue
import time
import os
import re
import cv2
import numpy as np
import pytesseract
import easyocr
from paddleocr import PaddleOCR
from ultralytics import YOLO
import pyrealsense2 as rs
import customtkinter as ctk
import tkinter as tk
import json
from playsound import playsound

#####################################
# Global variables
#####################################
last_alert_time = 0.0  # track last time we played alert
ALERT_COOLDOWN = 120.0  # 120 seconds = 2 minutes
running = True

# Dictionary for multiple police cars:
#   { plate_text: {
#       "id": (canvas item ID),
#       "last_x": float,
#       "last_y": float,
#       "orientation": "front"/"back",
#   }, ... }
police_cars = {}

#####################################
# Fuzzy Matching / Levenshtein Distance
#####################################
def levenshtein_distance(s1, s2):
    """Compute the Levenshtein distance between two strings (case-insensitive)."""
    s1 = s1.upper()
    s2 = s2.upper()
    m, n = len(s1), len(s2)

    if m == 0:
        return n
    if n == 0:
        return m

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # deletion
                dp[i][j - 1] + 1,      # insertion
                dp[i - 1][j - 1] + cost   # substitution
            )
    return dp[m][n]

#####################################
# Settings Handling (JSON + Lock)
#####################################
SETTINGS_FILE = 'app_settings.json'
settings_lock = threading.Lock()

def load_settings():
    with settings_lock:
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # If missing or invalid, return defaults
            return {'mismatch_tolerance': 1, 'volume_level': 100}

def save_settings(settings):
    with settings_lock:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

#####################################
# Detection and OCR setup
#####################################
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
tesseract_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
easyocr_reader = easyocr.Reader(['en'])
paddleocr_reader = PaddleOCR(lang='en', use_angle_cls=True)

plate_model = YOLO("D:\\Users\\admin-5\\Desktop\\license_plate_detector.pt")  # Update path if needed

# Database
database_path = os.path.join(os.path.dirname(__file__), 'license_plate_database.txt')
if not os.path.exists(database_path):
    open(database_path, 'w', encoding='utf-8').close()

with open(database_path, 'r', encoding='utf-8') as f:
    database_entries = {line.strip() for line in f if line.strip()}

#####################################
# Fuzzy Match Logic
#####################################
def fuzzy_match(recognized_text, db_entries, mismatch_tolerance):
    """Return a matching db_plate if recognized_text is within mismatch_tolerance of it."""
    recognized_text = recognized_text.strip().upper()
    if not recognized_text:
        return None

    best_match = None
    best_dist = 9999
    for db_plate in db_entries:
        dist = levenshtein_distance(recognized_text, db_plate)
        if dist < best_dist:
            best_dist = dist
            best_match = db_plate

    if best_dist <= mismatch_tolerance:
        return best_match
    return None

#####################################
# Camera Config
#####################################
FRONT_CAMERA_SERIAL = "112322077965"
BACK_CAMERA_SERIAL = "109622072518"

config_front = rs.config()
config_front.enable_device(FRONT_CAMERA_SERIAL)
config_front.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
config_front.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30)

config_back = rs.config()
config_back.enable_device(BACK_CAMERA_SERIAL)
config_back.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
config_back.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30)

#####################################
# UI Setup
#####################################
app = ctk.CTk()
app.geometry("1280x720")
app.title("Anty Tajniak")

sidebar = ctk.CTkFrame(app, width=200, corner_radius=0, fg_color="#2e2e2e")
sidebar.pack(side="left", fill="y")
sidebar.grid_rowconfigure(0, weight=1)
sidebar.grid_rowconfigure(1, weight=1)
sidebar.grid_rowconfigure(2, weight=1)
sidebar.grid_rowconfigure(3, weight=1)

camera_frame = ctk.CTkFrame(app, corner_radius=0, fg_color="#121212")
camera_frame.pack(side="right", fill="both", expand=True)

camera_label = ctk.CTkLabel(camera_frame, text="Podgląd kamery tutaj", font=("Arial", 18), text_color="white")

#####################################
# Map Setup
#####################################
road_canvas = None
car_image = None
police_car_image = None
user_car_id = None
# We no longer keep a single police_car_id.

def show_map():
    global road_canvas, user_car_id, police_car_id
    for widget in camera_frame.winfo_children():
        widget.pack_forget()

    road_canvas = tk.Canvas(camera_frame, bg="#121212", highlightthickness=0)
    road_canvas.pack(expand=True, fill="both")

    road_canvas.bind('<Configure>', on_canvas_resize)
    update_map_display()

def on_canvas_resize(event):
    if hasattr(on_canvas_resize, 'after_id'):
        road_canvas.after_cancel(on_canvas_resize.after_id)
    on_canvas_resize.after_id = road_canvas.after(100, update_map_display)

def update_map_display():
    global car_image, police_car_image, user_car_id

    if not road_canvas:
        return

    w = road_canvas.winfo_width()
    h = road_canvas.winfo_height()

    # Fill entire canvas with the road
    road_canvas.delete("all")
    road_canvas.create_rectangle(0, 0, w, h, fill="gray", outline="")

    # Choose icon size
    smallest_dim = min(w, h)
    icon_size = int(smallest_dim * 0.25)

    # Load/scale images
    car_img_orig = tk.PhotoImage(file="car_icon.png")
    police_img_orig = tk.PhotoImage(file="police_car_icon.png")

    def scale_image(original, target_size):
        ow, oh = original.width(), original.height()
        if ow == 0 or oh == 0 or target_size == 0:
            return original
        return original.subsample(
            max(1, ow // target_size),
            max(1, oh // target_size)
        )

    global car_image, police_car_image
    car_image = scale_image(car_img_orig, icon_size)
    police_car_image = scale_image(police_img_orig, icon_size)

    # Place user's car in the center
    center_x = w / 2
    center_y = h / 2
    user_car_id = road_canvas.create_image(center_x, center_y, image=car_image, anchor=tk.CENTER)

    # Store dimensions for future use
    road_canvas.canvas_width = w
    road_canvas.canvas_height = h
    road_canvas.center_x = center_x
    road_canvas.center_y = center_y

#####################################
# DB Management, UI Screens, etc.
#####################################
database_entries = database_entries  # already loaded
def normalize_plate(text):
    text = text.upper()
    text = re.sub(r'[^A-Z0-9]', '', text)
    return text

def save_database():
    with open(database_path, 'w', encoding='utf-8') as f:
        for plate in sorted(database_entries):
            f.write(plate + "\n")

def show_database_screen():
    for widget in camera_frame.winfo_children():
        widget.pack_forget()
    # ... code for listing & adding/removing plates ...

def show_settings():
    for widget in camera_frame.winfo_children():
        widget.pack_forget()
    # ... code for mismatch_tolerance & volume_level sliders ...

#####################################
# Placing Multiple Police Cars
#####################################
def place_or_move_police_car(plate_text, distance, horizontal_offset, orientation):
    """Create or move a police car for 'plate_text' with a smooth transition."""
    if not road_canvas or not police_car_image:
        return

    w = road_canvas.canvas_width
    h = road_canvas.canvas_height

    # Base calculations for position
    cx = road_canvas.center_x
    cy = road_canvas.center_y

    if orientation == "front":
        # negative => up
        y_pos_new = cy - (distance * 1000)
    else:
        # positive => down
        y_pos_new = cy + (distance * 1000)
        horizontal_offset = -horizontal_offset

    x_pos_new = cx + (horizontal_offset * 10)

    # clamp
    police_w = police_car_image.width()
    police_h = police_car_image.height()
    half_w = police_w / 2
    half_h = police_h / 2

    x_pos_new = max(half_w, min(x_pos_new, w - half_w))
    y_pos_new = max(half_h, min(y_pos_new, h - half_h))

    # If this plate isn't tracked yet, create a new icon
    if plate_text not in police_cars:
        new_id = road_canvas.create_image(x_pos_new, y_pos_new, image=police_car_image, anchor=tk.CENTER)
        police_cars[plate_text] = {
            "id": new_id,
            "last_x": x_pos_new,
            "last_y": y_pos_new,
            "orientation": orientation,
        }
    else:
        # Animate existing
        car_info = police_cars[plate_text]
        car_id = car_info["id"]
        x_old, y_old = road_canvas.coords(car_id)

        animate_police_car_move(
            plate_text = plate_text,
            current_step=0,
            steps=20,
            duration=500,
            x_start=x_old,
            y_start=y_old,
            x_end=x_pos_new,
            y_end=y_pos_new
        )

def animate_police_car_move(plate_text, current_step, steps, duration, x_start, y_start, x_end, y_end):
    """Smoothly move the police car from (x_start,y_start) to (x_end,y_end)."""
    if plate_text not in police_cars:
        return  # This plate was removed or no longer valid

    car_info = police_cars[plate_text]
    car_id = car_info["id"]

    if current_step > steps:
        # final
        road_canvas.coords(car_id, x_end, y_end)
        car_info["last_x"] = x_end
        car_info["last_y"] = y_end
        return

    ratio = current_step / float(steps)
    x_mid = x_start + ratio * (x_end - x_start)
    y_mid = y_start + ratio * (y_end - y_start)

    road_canvas.coords(car_id, x_mid, y_mid)

    interval = duration // steps
    app.after(interval, animate_police_car_move,
              plate_text,
              current_step + 1, steps, duration,
              x_start, y_start, x_end, y_end)

#####################################
# Realsense Detection Threads
#####################################
detection_queue = queue.Queue()

def run_detection(pipeline, orientation, config):
    global running, last_alert_time
    align_to = rs.stream.color
    align = rs.align(align_to)

    pipeline.start(config)

    text_window_name = "Text Detection Feed (Front)" if orientation == "front" else "Text Detection Feed (Back)"
    distance_window_name = "Distance Detection Feed (Front)" if orientation == "front" else "Distance Detection Feed (Back)"

    def local_normalize_text(t):
        return re.sub(r'[^A-Z0-9]', '', t.upper())

    try:
        while running:
            frames = pipeline.wait_for_frames()
            aligned_frames = align.process(frames)
            color_frame = aligned_frames.get_color_frame()
            depth_frame = aligned_frames.get_depth_frame()
            if not color_frame or not depth_frame:
                continue

            color_image = np.asanyarray(color_frame.get_data())
            image_height, image_width, _ = color_image.shape
            image_center_x = image_width / 2

            # Debug windows
            text_detection_feed = color_image.copy()
            distance_detection_feed = color_image.copy()

            plate_results = plate_model(color_image)

            # Grab mismatch tolerance
            settings = load_settings()
            mismatch_tolerance = settings.get('mismatch_tolerance', 1)

            for plate_box in plate_results[0].boxes:
                x1_plate, y1_plate, x2_plate, y2_plate = map(int, plate_box.xyxy[0])
                plate_region = color_image[y1_plate:y2_plate, x1_plate:x2_plate]
                if plate_region.size == 0:
                    continue

                plate_gray = cv2.cvtColor(plate_region, cv2.COLOR_BGR2GRAY)
                text_tesseract = pytesseract.image_to_string(plate_gray, config=tesseract_config).strip()
                result_easyocr = easyocr_reader.readtext(plate_gray, detail=0, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
                text_easyocr = ''.join(result_easyocr).strip()

                result_paddleocr = paddleocr_reader.ocr(plate_gray, cls=True)
                text_paddleocr = ''
                if result_paddleocr and isinstance(result_paddleocr, list):
                    for line in result_paddleocr:
                        if (line 
                            and isinstance(line, list)
                            and len(line) > 1
                            and line[1]
                            and isinstance(line[1], tuple)
                            and len(line[1]) > 0
                            and line[1][0]):
                            recognized_text = line[1][0]
                            text_paddleocr += recognized_text
                text_paddleocr = text_paddleocr.strip()

                ocr_results = {
                    'Tesseract': local_normalize_text(text_tesseract),
                    'EasyOCR': local_normalize_text(text_easyocr),
                    'PaddleOCR': local_normalize_text(text_paddleocr)
                }

                bbox_center_x = (x1_plate + x2_plate) / 2
                bbox_center_y = (y1_plate + y2_plate) / 2
                depth = depth_frame.get_distance(int(bbox_center_x), int(bbox_center_y))
                distance_text = f"{depth:.2f}m"

                # Debug feed text
                text_offset_y = y2_plate + 60
                for engine_name, rec_text in ocr_results.items():
                    cv2.putText(text_detection_feed, f"{engine_name}: {rec_text}",
                                (x1_plate, text_offset_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
                    text_offset_y += 25

                # Attempt fuzzy match among the 3 OCR results
                plate_found = None
                for engine_name, recognized_text in ocr_results.items():
                    if recognized_text:
                        match = fuzzy_match(recognized_text, database_entries, mismatch_tolerance)
                        if match:
                            plate_found = match  # e.g. "ABC123"
                            break

                # Draw bounding boxes
                if plate_found:
                    cv2.rectangle(distance_detection_feed, (x1_plate, y1_plate), (x2_plate, y2_plate), (0,255,0), 2)
                    cv2.putText(distance_detection_feed, distance_text, (x1_plate, y2_plate + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)

                    # Send an event, passing plate_found so we track it separately
                    horizontal_diff = bbox_center_x - image_center_x
                    horizontal_offset = horizontal_diff / 2.0
                    detection_queue.put(('police_car', plate_found, depth, horizontal_offset, orientation))

                    now = time.time()
                    if now - last_alert_time >= ALERT_COOLDOWN:
                        last_alert_time = now
                        detection_queue.put(('play_alert', 'UWAGA TAJNIAK!'))
                else:
                    # No match
                    cv2.rectangle(distance_detection_feed, (x1_plate, y1_plate), (x2_plate, y2_plate), (255,0,0), 2)
                    cv2.putText(distance_detection_feed, f"No Match | {distance_text}",
                                (x1_plate, y2_plate + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,0,0), 2)

            # Show debug feeds
            cv2.imshow(text_window_name, text_detection_feed)
            cv2.imshow(distance_window_name, distance_detection_feed)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                running = False
                break

    finally:
        pipeline.stop()
        cv2.destroyWindow(text_window_name)
        cv2.destroyWindow(distance_window_name)

def detection_thread_front():
    pipeline_front = rs.pipeline()
    run_detection(pipeline_front, "front", config_front)

def detection_thread_back():
    pipeline_back = rs.pipeline()
    run_detection(pipeline_back, "back", config_back)

threading.Thread(target=detection_thread_front, daemon=True).start()
threading.Thread(target=detection_thread_back, daemon=True).start()

#####################################
# Playing Alerts
#####################################
def play_alert_sound(message):
    # 1. Non-blocking
    threading.Thread(target=playsound, args=("alert.wav",), daemon=True).start()
    # 2. Show label
    show_alert_label(message)

def show_alert_label(text):
    alert_label = ctk.CTkLabel(camera_frame, text=text,
                               fg_color="red", text_color="white",
                               font=("Arial", 24, "bold"))
    alert_label.pack(pady=10)

    def remove_label():
        alert_label.destroy()
    app.after(5000, remove_label)

#####################################
# Real-time UI Update
#####################################
def update_ui():
    try:
        while True:
            item = detection_queue.get_nowait()
            if item[0] == 'police_car':
                # item = ('police_car', plate_found, distance, offset, orientation)
                plate_text = item[1]
                distance = item[2]
                horizontal_offset = item[3]
                orientation = item[4]
                place_or_move_police_car(plate_text, distance, horizontal_offset, orientation)
            elif item[0] == 'play_alert':
                alert_message = item[1]
                play_alert_sound(alert_message)
    except queue.Empty:
        pass
    app.after(100, update_ui)

def report(tablica):
    print(f"Zgłoszono tablicę rejestracyjną: {tablica}")

#####################################
# UI Buttons
#####################################
def button_click(button_name):
    for widget in camera_frame.winfo_children():
        widget.pack_forget()
    if button_name == "Mapa":
        show_map()
    elif button_name == "Baza tajniaków":
        show_database_screen()
    elif button_name == "Informacje":
        version_label = ctk.CTkLabel(camera_frame, text="Wersja aplikacji: 1.0.0",
                                     font=("Arial",16), text_color="white")
        version_label.pack(pady=10)
        authors_label = ctk.CTkLabel(camera_frame,
            text="Autorzy:\nJakub Gołębiewski\nKarol Marczak\nMarcel Oczeretko\nKrystian Klisz",
            font=("Arial",16), text_color="white")
        authors_label.pack(pady=10)
    elif button_name == "Ustawienia":
        show_settings()

map_button = ctk.CTkButton(sidebar, text="Mapa", command=lambda: button_click("Mapa"), width=180, height=50)
map_button.grid(row=0, padx=20, pady=20, sticky="ew")

settings_button = ctk.CTkButton(sidebar, text="Ustawienia", command=lambda: button_click("Ustawienia"), width=180, height=50)
settings_button.grid(row=1, padx=20, pady=20, sticky="ew")

report_button = ctk.CTkButton(sidebar, text="Baza tajniaków", command=lambda: button_click("Baza tajniaków"),
                              width=180, height=50)
report_button.grid(row=2, padx=20, pady=20, sticky="ew")

info_button = ctk.CTkButton(sidebar, text="Informacje", command=lambda: button_click("Informacje"),
                            width=180, height=50)
info_button.grid(row=3, padx=20, pady=20, sticky="ew")

#####################################
# Initialize
#####################################
app.after(1000, lambda: button_click("Mapa"))
update_ui()
app.mainloop()
running = False
