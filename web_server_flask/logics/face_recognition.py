import cv2
import numpy as np
import face_recognition
from logger_config import setup_logger
from logics.firebase import load_known_people_images_from_firebase

# Colorful logger Configuration
logger = setup_logger()

# Define the threshold as a constant
FACE_MATCH_THRESHOLD = 0.5

# Function to recognize faces in an image and annotate it
def recognize_faces_in_image(image_data, known_encodings):
    # Convert image data to a numpy array and decode it
    np_img = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)
    
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # Convert image to RGB (for face_recognition)

    # Find all face locations and encodings in the image
    face_locations = face_recognition.face_locations(rgb_img)
    face_encodings = face_recognition.face_encodings(rgb_img, face_locations)

    recognized_faces = []

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        best_match_name = "Unknown"
        best_match_distance = FACE_MATCH_THRESHOLD  # Use the constant threshold

        for person_name, encodings in known_encodings.items():
            for known_encoding, filename in encodings:
                distance = face_recognition.face_distance([known_encoding], face_encoding)
                if distance < best_match_distance:
                    best_match_distance = distance
                    best_match_name = person_name

        # Collect recognized face data
        recognized_faces.append((top, right, bottom, left, best_match_name))

    return recognized_faces

# Function to annotate the image with recognized faces without saving temporary files
def annotate_image(image_data, recognized_faces):
    # Convert image data to a numpy array and decode it
    np_img = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

    for (top, right, bottom, left, name) in recognized_faces:
        # Draw rectangle and label around the face
        cv2.rectangle(img, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.putText(img, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    # Encode annotated image to bytes
    _, annotated_img = cv2.imencode('.jpg', img)
    return annotated_img.tobytes()

# Function to process a single frame
def process_frame(frame, known_encodings):
    try:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # Convert image to RGB (for face_recognition)
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        results = []

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            best_match_name = "Unknown"
            best_match_distance = FACE_MATCH_THRESHOLD  # Use the constant threshold

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
