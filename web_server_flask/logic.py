import cv2
import logging
import numpy as np
import face_recognition
from dotenv import load_dotenv
import os
from io import BytesIO
from firebase_admin import credentials, initialize_app, storage

# Load environment variables from .env
load_dotenv()

# Access environment variables
firebase_secret = os.getenv('FIREBASE_SECRET')

# Initialize Firebase Admin SDK
cred = credentials.Certificate(firebase_secret)
initialize_app(cred, {
    'storageBucket': 'face-recognition-storage.appspot.com'
})
bucket = storage.bucket()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Define the threshold as a constant
FACE_MATCH_THRESHOLD = 0.4

# Function to dynamically fetch and load images for known people from Firebase Storage
def load_known_people_images_from_firebase():
    known_encodings = {}
    blobs = bucket.list_blobs(prefix='known_people/')

    for blob in blobs:
        if blob.name.endswith('/') and blob.name != 'known_people/':
            person_name = blob.name.split('/')[-2]
            person_images = []

            logging.info(f"Loading images for: {person_name}")
            person_blobs = bucket.list_blobs(prefix=f'{blob.name}')

            for person_blob in person_blobs:
                if person_blob.name.endswith('.jpg'):
                    logging.info(f"  Recognized {person_name} from {person_blob.name}")
                    img_bytes = person_blob.download_as_bytes()
                    img = face_recognition.load_image_file(BytesIO(img_bytes))

                    if len(face_recognition.face_encodings(img)) > 0:
                        img_encoding = face_recognition.face_encodings(img)[0]
                        person_images.append((img_encoding, person_blob.name.split("/")[-1]))
                    else:
                        logging.warning(f"No face found in image: {person_blob.name}")

            known_encodings[person_name] = person_images
            logging.info(f"Loaded {len(person_images)} images for {person_name}.")

    logging.info("Finished loading known people images.")
    return known_encodings

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
        logging.error(f"Error processing frame: {e}")
        return []

# Ensure that known encodings are loaded before processing frames or images
known_encodings = load_known_people_images_from_firebase()

# Example usage:
# recognized_faces = recognize_faces_in_image('path_to_image.jpg', known_encodings)
# annotated_image_data = annotate_image(image_data, recognized_faces)
