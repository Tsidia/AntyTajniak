# detection.py

import cv2
import numpy as np
import os
import time
import queue
import threading
import re

import pyrealsense2 as rs
import pytesseract
import easyocr
from paddleocr import PaddleOCR
from ultralytics import YOLO

from fuzzy_match import fuzzy_match
from database_manager import database_entries
from settings_manager import load_settings

detection_queue = queue.Queue()
running = True

# --- DEBUG MODE GLOBALS ---
front_debug_mode = False
back_debug_mode = False
front_debug_image = None   # Numpy array for front camera override
back_debug_image = None    # Numpy array for back camera override

# Keep track of each camera’s *current* frame to show mini-previews in the UI
front_last_frame = None
back_last_frame = None
# --------------------------

ALERT_COOLDOWN = 120.0
last_alert_time = 0.0

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
tesseract_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

easyocr_reader = easyocr.Reader(['en'])
paddleocr_reader = PaddleOCR(lang='en', use_angle_cls=True)

# Load your YOLO plate model
plate_model = YOLO("D:\\Users\\admin-5\\Desktop\\license_plate_detector.pt")

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


def run_detection(pipeline, orientation, config):
    """
    If debug_mode is True for a camera, use the debug_image in place of RealSense frames.
    Also store the last displayed frame into front_last_frame/back_last_frame for UI previews.
    """
    global running, last_alert_time
    global front_debug_mode, back_debug_mode
    global front_debug_image, back_debug_image
    global front_last_frame, back_last_frame

    # Decide which camera’s debug variables to use
    if orientation == "front":
        debug_mode = front_debug_mode
        debug_img_ref = lambda: front_debug_image
    else:
        debug_mode = back_debug_mode
        debug_img_ref = lambda: back_debug_image

    if not debug_mode:
        align_to = rs.stream.color
        align = rs.align(align_to)
        pipeline.start(config)

    text_window_name = f"Text Detection Feed ({orientation.title()})"
    distance_window_name = f"Distance Detection Feed ({orientation.title()})"

    def local_normalize_text(text):
        text = text.upper()
        text = re.sub(r'[^A-Z0-9]', '', text)
        return text

    try:
        while running:
            # If we’re in debug mode, we skip reading RealSense frames
            if (orientation == "front" and front_debug_mode and front_debug_image is not None):
                color_image = front_debug_image.copy()
                depth_frame = None
                depth_val = 2.0  # example fixed distance
            elif (orientation == "back" and back_debug_mode and back_debug_image is not None):
                color_image = back_debug_image.copy()
                depth_frame = None
                depth_val = 2.0
            else:
                # Normal RealSense path
                frames = pipeline.wait_for_frames()
                align_to = rs.stream.color
                align = rs.align(align_to)
                aligned_frames = align.process(frames)
                color_frame = aligned_frames.get_color_frame()
                depth_frame = aligned_frames.get_depth_frame()
                if not color_frame or not depth_frame:
                    continue
                color_image = np.asanyarray(color_frame.get_data())

            image_height, image_width, _ = color_image.shape
            image_center_x = image_width / 2

            text_detection_feed = color_image.copy()
            distance_detection_feed = color_image.copy()

            plate_results = plate_model(color_image)

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
                        if (line and isinstance(line, list) and len(line) > 1 and line[1]
                            and isinstance(line[1], tuple) and len(line[1]) > 0 and line[1][0]):
                            text_paddleocr += line[1][0]
                text_paddleocr = text_paddleocr.strip()

                ocr_results = {
                    'Tesseract': local_normalize_text(text_tesseract),
                    'EasyOCR': local_normalize_text(text_easyocr),
                    'PaddleOCR': local_normalize_text(text_paddleocr)
                }

                bbox_center_x = (x1_plate + x2_plate) / 2
                bbox_center_y = (y1_plate + y2_plate) / 2
                if depth_frame is not None:
                    depth = depth_frame.get_distance(int(bbox_center_x), int(bbox_center_y))
                else:
                    depth = depth_val

                distance_text = f"{depth:.2f}m"

                # Debug overlay
                text_offset_y = y2_plate + 60
                for engine_name, rec_text in ocr_results.items():
                    cv2.putText(text_detection_feed, f"{engine_name}: {rec_text}",
                                (x1_plate, text_offset_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    text_offset_y += 25

                # Attempt fuzzy matches
                plate_found = None
                for engine_name, recognized_text in ocr_results.items():
                    if recognized_text:
                        match = fuzzy_match(recognized_text, database_entries, mismatch_tolerance)
                        if match:
                            plate_found = match
                            break

                if plate_found:
                    # matched
                    cv2.rectangle(distance_detection_feed, (x1_plate, y1_plate), (x2_plate, y2_plate), (0, 255, 0), 2)
                    cv2.putText(distance_detection_feed, distance_text,
                                (x1_plate, y2_plate + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                    horizontal_diff = bbox_center_x - image_center_x
                    horizontal_offset = horizontal_diff / 2.0
                    detection_queue.put(('police_car', plate_found, depth, horizontal_offset, orientation))

                    now = time.time()
                    if now - last_alert_time >= ALERT_COOLDOWN:
                        last_alert_time = now
                        detection_queue.put(('play_alert', 'UWAGA TAJNIAK!'))

                else:
                    # no match
                    cv2.rectangle(distance_detection_feed, (x1_plate, y1_plate), (x2_plate, y2_plate), (255, 0, 0), 2)
                    cv2.putText(distance_detection_feed, f"No Match | {distance_text}",
                                (x1_plate, y2_plate + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

            # Show debug windows
            cv2.imshow(text_window_name, text_detection_feed)
            cv2.imshow(distance_window_name, distance_detection_feed)

            # --- Update front_last_frame / back_last_frame for UI previews
            if orientation == "front":
                front_last_frame = color_image.copy()
            else:
                back_last_frame = color_image.copy()
            # ---

            if cv2.waitKey(1) & 0xFF == ord('q'):
                running = False
                break

    finally:
        if not debug_mode:
            pipeline.stop()
        cv2.destroyWindow(text_window_name)
        cv2.destroyWindow(distance_window_name)


def detection_thread_front():
    pipeline_front = rs.pipeline()
    run_detection(pipeline_front, "front", config_front)


def detection_thread_back():
    pipeline_back = rs.pipeline()
    run_detection(pipeline_back, "back", config_back)
