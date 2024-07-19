import cv2
import logging
import numpy as np
import face_recognition
import os
import gc
import time
import sys
from io import BytesIO
from firebase_admin import credentials, initialize_app, storage
from gtts import gTTS
from google.auth.exceptions import GoogleAuthError
from retrying import retry
import colorlog

# Configure colorful logging
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S'
))

logger = colorlog.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Constants
FACE_MATCH_THRESHOLD = 0.5
GC_INTERVAL = 30
MAX_RETRIES = 3
RETRY_WAIT = 2000  # in milliseconds

# Initialize Firebase Admin SDK
def initialize_firebase():
    try:
        logger.info("Initializing Firebase Admin SDK...")
        cred = credentials.Certificate('serviceAccountKey.json')
        initialize_app(cred, {
            'storageBucket': 'face-recognition-storage.appspot.com'
        })
        bucket = storage.bucket()
        logger.info("Firebase Admin SDK initialized.")
        return bucket
    except FileNotFoundError:
        logger.critical("Service account key file not found. Ensure 'serviceAccountKey.json' is in the directory.")
        sys.exit(1)
    except GoogleAuthError as e:
        logger.critical(f"Error initializing Firebase Admin SDK: {e}")
        sys.exit(1)

bucket = initialize_firebase()

# Function to check if external command exists
def check_command(command):
    from shutil import which
    return which(command) is not None

# Check for external dependencies based on OS
def check_dependencies():
    if os.name == 'posix':
        if not check_command('afplay'):
            logger.warning("afplay not found. Audio playback will not work on macOS.")
    elif os.name == 'nt':
        if not check_command('start'):
            logger.warning("start command not found. Audio playback will not work on Windows.")
    elif os.name == 'posix':
        if not check_command('mpg123'):
            logger.warning("mpg123 not found. Audio playback will not work on Linux.")

check_dependencies()

# Function to retry loading images for known people from Firebase Storage
@retry(stop_max_attempt_number=MAX_RETRIES, wait_fixed=RETRY_WAIT)
def load_known_people_images_from_firebase():
    known_encodings = {}
    blobs = bucket.list_blobs(prefix='known_people/')

    for blob in blobs:
        if blob.name.endswith('/') and blob.name != 'known_people/':
            person_name = blob.name.split('/')[-2]
            person_images = []

            logger.info(f"Loading images for: {person_name}")
            person_blobs = bucket.list_blobs(prefix=f'{blob.name}')

            for person_blob in person_blobs:
                if person_blob.name.endswith('.jpg'):
                    logger.info(f"  Recognized {person_name} from {person_blob.name}")
                    img_bytes = person_blob.download_as_bytes()
                    img = face_recognition.load_image_file(BytesIO(img_bytes))

                    if len(face_recognition.face_encodings(img)) > 0:
                        img_encoding = face_recognition.face_encodings(img)[0]
                        person_images.append((img_encoding, person_blob.name.split("/")[-1]))
                    else:
                        logger.warning(f"No face found in image: {person_blob.name}")

            known_encodings[person_name] = person_images
            logger.info(f"Loaded {len(person_images)} images for {person_name}.")

    logger.info("Finished loading known people images.")
    return known_encodings

# Function to process a single frame and recognize faces
def process_frame(frame, known_encodings):
    try:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        results = []

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            best_match_name = "Unknown"
            best_match_distance = FACE_MATCH_THRESHOLD

            for person_name, encodings in known_encodings.items():
                for known_encoding, filename in encodings:
                    distance = face_recognition.face_distance([known_encoding], face_encoding)
                    if distance < best_match_distance:
                        best_match_distance = distance
                        best_match_name = person_name

            results.append((top, right, bottom, left, best_match_name))

        return results

    except Exception as e:
        logger.error(f"Error processing frame: {e}")
        return []

# Set to track spoken names
spoken_names = set()

# Function to speak the recognized name
def speak_name(name):
    try:
        if name in spoken_names:
            logger.info(f"{name} has already been spoken. Skipping.")
            return

        greetings = {
            "Samuvel": "Good Morning Samuvel",
            "Akash": "Good Evening Akash"
        }

        if name not in greetings:
            logger.info(f"Name '{name}' not recognized. No greeting will be spoken.")
            return

        message = greetings[name]
        logger.info(f"Speaking name: {name}")
        spoken_names.add(name)

        # Generate speech
        tts = gTTS(text=message, lang='en')
        filename = f"{name}.mp3"
        tts.save(filename)

        if os.name == 'posix':
            if check_command('afplay'):
                logger.info("Operating System: macOS")
                os.system(f"afplay {filename}")
            else:
                logger.warning("afplay not found. Audio playback will not work on macOS.")
        elif os.name == 'nt':
            logger.info("Operating System: Windows")
            os.system(f"start {filename}")
        else:
            if check_command('mpg123'):
                logger.info("Operating System: Linux")
                os.system(f"mpg123 {filename}")
            else:
                logger.warning("mpg123 not found. Audio playback will not work on Linux.")

        logger.info(f"Played greeting for {name}.")

        # Clean up the audio file after playing
        if os.path.exists(filename):
            os.remove(filename)
            logger.info(f"Deleted temporary audio file: {filename}")

    except Exception as e:
        logger.error(f"Error speaking name: {e}")

# Function to retry initializing the webcam
@retry(stop_max_attempt_number=MAX_RETRIES, wait_fixed=RETRY_WAIT)
def initialize_webcam():
    logger.info("Initializing webcam...")
    video_capture = cv2.VideoCapture(0)
    video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    if not video_capture.isOpened():
        raise IOError("Webcam could not be opened.")
    
    logger.info("Webcam initialized.")
    return video_capture

# Function to process video frames
def process_video(video_capture):
    previous_names = set()

    try:
        if not video_capture.isOpened():
            logger.error("Failed to open video capture.")
            return
        
        frame_counter = 0
        logger.info("Starting video processing...")

        while True:
            ret, frame = video_capture.read()
            if not ret:
                logger.warning("Frame not retrieved, stopping video stream.")
                break

            recognized_faces = process_frame(frame, known_encodings)
            detected_names = {name for (_, _, _, _, name) in recognized_faces}

            if detected_names and detected_names != previous_names:
                previous_names = detected_names
                for name in detected_names:
                    speak_name(name)

            # Display recognized faces and names
            for (top, right, bottom, left, name) in recognized_faces:
                # Draw rectangle around the face
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
    
                # Draw a filled rectangle below the face for the name
                text_size, _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                text_width = text_size[0]
                text_height = text_size[1]
    
                # Ensure the filled rectangle is large enough for the text
                rect_bottom_left = (left, bottom - 35)
                rect_top_right = (right, bottom)
                cv2.rectangle(frame, rect_bottom_left, rect_top_right, (0, 0, 255), cv2.FILLED)
    
                # Put text with name, ensuring it fits within the rectangle
                text_position = (left + 6, bottom - 6)
                if text_position[0] + text_width > right:
                    # Adjust text position to keep it within the rectangle
                    text_position = (right - text_width - 6, bottom - 6)
    
                cv2.putText(frame, name, text_position, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # Display the frame
            cv2.imshow("Recognized Faces", frame)

            # Check for key press to reset spoken names or stop video
            key = cv2.waitKey(1) & 0xFF
            if key == ord('r'):
                spoken_names.clear()
                logger.info("Reset spoken names.")
            elif key == ord('q'):
                logger.info("Stopping video stream on 'q' press.")
                break

            frame_counter += 1
            if frame_counter % GC_INTERVAL == 0:
                gc.collect()
                logger.info("Garbage collection performed.")

    except Exception as e:
        logger.error(f"Error processing video: {e}")

    finally:
        video_capture.release()
        cv2.destroyAllWindows()
        logger.info("Video capture released.")
        gc.collect()

if __name__ == "__main__":
    logger.info("Starting face recognition system...")
    try:
        known_encodings = load_known_people_images_from_firebase()
        video_capture = initialize_webcam()
        process_video(video_capture)
    except Exception as e:
        logger.critical(f"Critical error in main function: {e}")
    finally:
        cv2.destroyAllWindows()
        logger.info("Face recognition system stopped.")
