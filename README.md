# AntyTajniak
AI detection tool for recognizing unmarked police cars on the road in real time

How it works:

Step 1: Capture real time footage from the front and back of the car using cameras and feed the video streams into the program

Step 2: State of the art neural networks analyze the footage searching for license plates

Step 3: If a license plate has been detected in the footage it is cropped out of the video, enchanced and processed using OCR tools and text matching algorithms to read the license plate text

Step 4: The detected license plate text is compared to a database of known hidden police car license plates

Step 5: If there is a match, the system pinpoints the car's location and places it on a map, relative to the vehicle they're currently driving

Step 6: The system alerts and warns the user
