# map_display.py

import tkinter as tk

# We'll store references here so detection/UI can manipulate the map
road_canvas = None
car_image = None
police_car_image = None

# Dictionary of known police cars on map: {plate: {...}}
police_cars = {}  

def handle_window_resize(event):
    """
    Handle window resize by updating the map display with a small delay
    to avoid frequent re-renders.
    """
    canvas = event.widget
    if hasattr(handle_window_resize, 'after_id'):
        canvas.after_cancel(handle_window_resize.after_id)
    handle_window_resize.after_id = canvas.after(100, update_map_display)


def show_map(parent_frame):
    """
    Create the road canvas in the given parent frame and set up event bindings.
    """
    global road_canvas
    road_canvas = tk.Canvas(parent_frame, bg="#121212", highlightthickness=0)
    road_canvas.pack(expand=True, fill="both")
    road_canvas.bind('<Configure>', handle_window_resize)
    update_map_display()


def update_map_display():
    """
    Clears and re-draws the map canvas with the user car in the center.
    """
    global road_canvas, car_image, police_car_image

    if not road_canvas:
        return
    
    # Clear existing
    road_canvas.delete("all")

    # Dimensions
    canvas_width = road_canvas.winfo_width()
    canvas_height = road_canvas.winfo_height()

    # Draw the background "road" as a big rectangle
    road_canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill="gray", outline="")

    # Load user car & police car icons here or pass them in
    # For demonstration, we assume you have .png images in the same folder
    user_car_image_original = tk.PhotoImage(file="car_icon.png")
    police_car_image_original = tk.PhotoImage(file="police_car_icon.png")

    # Choose an icon size
    smallest_dim = min(canvas_width, canvas_height)
    icon_size = int(smallest_dim * 0.25) if smallest_dim else 1

    # Simple "subsample" scaling approach
    def scale_image(original, target_size):
        w, h = original.width(), original.height()
        if w == 0 or h == 0 or target_size == 0:
            return original
        return original.subsample(max(1, w // target_size),
                                  max(1, h // target_size))

    car_image = scale_image(user_car_image_original, icon_size)
    police_car_image = scale_image(police_car_image_original, icon_size)

    # Place user's car at center
    center_x = canvas_width / 2
    center_y = canvas_height / 2
    road_canvas.create_image(center_x, center_y, image=car_image, anchor=tk.CENTER)

    # Store some helpful references
    road_canvas.canvas_width = canvas_width
    road_canvas.canvas_height = canvas_height
    road_canvas.center_x = center_x
    road_canvas.center_y = center_y

    # Re-draw any existing police cars that were saved in `police_cars`
    for plate, car_info in police_cars.items():
        # Recreate or place them at their last known location
        x_old, y_old = car_info.get('x'), car_info.get('y')
        canvas_id = road_canvas.create_image(x_old, y_old, image=police_car_image, anchor=tk.CENTER)
        car_info['canvas_id'] = canvas_id


def place_or_move_police_car(plate: str, distance: float, horizontal_offset: float, orientation: str):
    """
    Create or update a police car on the map for the given `plate`, 
    based on distance from user's car and orientation (front/back).
    """
    from time import time
    global police_cars, police_car_image, road_canvas

    if not road_canvas or not police_car_image:
        return

    now = time()

    w = road_canvas.canvas_width
    h = road_canvas.canvas_height
    center_x = road_canvas.center_x
    center_y = road_canvas.center_y

    # Convert distance into some scaling, e.g. multiply by 1000 px for demonstration
    if orientation == "front":
        y_pos_new = center_y - (distance * 1000)
    else:
        y_pos_new = center_y + (distance * 1000)
        horizontal_offset = -horizontal_offset  # flip side if behind

    x_pos_new = center_x + (horizontal_offset * 10)

    # Make sure it doesn’t go out of the canvas
    half_w = police_car_image.width() / 2
    half_h = police_car_image.height() / 2
    x_pos_new = max(half_w, min(x_pos_new, w - half_w))
    y_pos_new = max(half_h, min(y_pos_new, h - half_h))

    if plate not in police_cars:
        # Create new police car
        canvas_id = road_canvas.create_image(x_pos_new, y_pos_new, image=police_car_image, anchor=tk.CENTER)
        police_cars[plate] = {
            'canvas_id': canvas_id,
            'last_detection_time': now,
            'x': x_pos_new,
            'y': y_pos_new
        }
    else:
        car_info = police_cars[plate]
        car_info['last_detection_time'] = now
        x_old, y_old = car_info['x'], car_info['y']
        car_info['x'] = x_pos_new
        car_info['y'] = y_pos_new

        # Animate from old to new
        animate_police_car_move(
            current_step=0,
            steps=20,
            duration=500,
            x_start=x_old,
            y_start=y_old,
            x_end=x_pos_new,
            y_end=y_pos_new,
            canvas_id=car_info['canvas_id'],
            plate=plate
        )


def animate_police_car_move(current_step, steps, duration, x_start, y_start,
                            x_end, y_end, canvas_id, plate):
    """
    Smoothly move the police car from (x_start, y_start) to (x_end, y_end).
    """
    from time import time
    if plate not in police_cars:
        return

    if current_step > steps:
        road_canvas.coords(canvas_id, x_end, y_end)
        return

    ratio = current_step / float(steps)
    x_mid = x_start + ratio * (x_end - x_start)
    y_mid = y_start + ratio * (y_end - y_start)

    road_canvas.coords(canvas_id, x_mid, y_mid)

    interval = int(duration / steps)
    road_canvas.after(interval, animate_police_car_move, 
                      current_step + 1, steps, duration,
                      x_start, y_start, x_end, y_end, canvas_id, plate)
