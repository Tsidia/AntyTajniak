# detection.py

import time
import queue
import threading
import re
import os

import cv2
import numpy as np
import pyrealsense2 as rs
import pytesseract
import easyocr
from paddleocr import PaddleOCR
from ultralytics import YOLO

from fuzzy_match import fuzzy_match
from database_manager import database_entries
from settings_manager import load_settings

# A global Queue for detection events (plate found, or play_alert, etc.)
detection_queue = queue.Queue()

# This variable can be toggled by main/UI to stop detection gracefully
running = True

# Constants
ALERT_COOLDOWN = 120.0  # seconds
last_alert_time = 0.0

# Tesseract config
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
tesseract_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

# Initialize OCR engines
easyocr_reader = easyocr.Reader(['en'])
paddleocr_reader = PaddleOCR(lang='en', use_angle_cls=True)

# Load your YOLO plate model (adjust path)
plate_model = YOLO("D:\\Users\\admin-5\\Desktop\\license_plate_detector.pt")  # update your path if needed

# Configure your two cameras (front & back) by serial
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
    Main detection loop for either front or back camera.
    """
    global running, last_alert_time

    align_to = rs.stream.color
    align = rs.align(align_to)
    pipeline.start(config)

    # For debugging
    text_window_name = f"Text Detection Feed ({orientation.title()})"
    distance_window_name = f"Distance Detection Feed ({orientation.title()})"

    def local_normalize_text(text):
        text = text.upper()
        text = re.sub(r'[^A-Z0-9]', '', text)
        return text

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

            text_detection_feed = color_image.copy()
            distance_detection_feed = color_image.copy()

            # YOLO detection
            plate_results = plate_model(color_image)

            # Load mismatch tolerance from user settings
            settings = load_settings()
            mismatch_tolerance = settings.get('mismatch_tolerance', 1)

            for plate_box in plate_results[0].boxes:
                x1_plate, y1_plate, x2_plate, y2_plate = map(int, plate_box.xyxy[0])
                plate_region = color_image[y1_plate:y2_plate, x1_plate:x2_plate]
                if plate_region.size == 0:
                    continue

                plate_gray = cv2.cvtColor(plate_region, cv2.COLOR_BGR2GRAY)
                # Attempt Tesseract
                text_tesseract = pytesseract.image_to_string(plate_gray, config=tesseract_config).strip()
                # Attempt EasyOCR
                result_easyocr = easyocr_reader.readtext(plate_gray, detail=0, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
                text_easyocr = ''.join(result_easyocr).strip()
                # Attempt PaddleOCR
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
                            text_paddleocr += line[1][0]
                text_paddleocr = text_paddleocr.strip()

                # Normalize
                ocr_results = {
                    'Tesseract': local_normalize_text(text_tesseract),
                    'EasyOCR': local_normalize_text(text_easyocr),
                    'PaddleOCR': local_normalize_text(text_paddleocr)
                }

                # Estimate distance
                bbox_center_x = (x1_plate + x2_plate) / 2
                bbox_center_y = (y1_plate + y2_plate) / 2
                depth = depth_frame.get_distance(int(bbox_center_x), int(bbox_center_y))
                distance_text = f"{depth:.2f}m"

                # Debug display of OCR text
                text_offset_y = y2_plate + 60
                for engine_name, rec_text in ocr_results.items():
                    cv2.putText(text_detection_feed, f"{engine_name}: {rec_text}",
                                (x1_plate, text_offset_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    text_offset_y += 25

                # Check for a match with any OCR result
                plate_found = None
                for engine_name, recognized_text in ocr_results.items():
                    if recognized_text:
                        match = fuzzy_match(recognized_text, database_entries, mismatch_tolerance)
                        if match:
                            plate_found = match
                            break

                # Draw bounding boxes
                if plate_found:
                    cv2.rectangle(distance_detection_feed, (x1_plate, y1_plate), (x2_plate, y2_plate), (0, 255, 0), 2)
                    cv2.putText(distance_detection_feed, distance_text,
                                (x1_plate, y2_plate + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                    # Notify main/UI
                    horizontal_diff = bbox_center_x - image_center_x
                    horizontal_offset = horizontal_diff / 2.0

                    detection_queue.put(('police_car', plate_found, depth, horizontal_offset, orientation))

                    now = time.time()
                    if now - last_alert_time >= ALERT_COOLDOWN:
                        last_alert_time = now
                        detection_queue.put(('play_alert', 'UWAGA TAJNIAK!'))

                else:
                    cv2.rectangle(distance_detection_feed, (x1_plate, y1_plate), (x2_plate, y2_plate), (255, 0, 0), 2)
                    cv2.putText(distance_detection_feed, f"No Match | {distance_text}",
                                (x1_plate, y2_plate + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

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
    """
    Spawns front camera detection loop in a separate thread.
    """
    pipeline_front = rs.pipeline()
    run_detection(pipeline_front, "front", config_front)


def detection_thread_back():
    """
    Spawns back camera detection loop in a separate thread.
    """
    pipeline_back = rs.pipeline()
    run_detection(pipeline_back, "back", config_back)
