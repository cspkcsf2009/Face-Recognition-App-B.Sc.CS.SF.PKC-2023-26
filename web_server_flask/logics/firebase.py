import os
from io import BytesIO
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, storage
import face_recognition
from logger_config import setup_logger
import requests  # For handling network-related errors

# Initialize logger with colorful output and file logging
logger = setup_logger()

# Load environment variables from .env file
load_dotenv()

# Access Firebase secret key from environment variables
firebase_secret = os.getenv('FIREBASE_SECRET_KEY')

# Validate that the FIREBASE_SECRET_KEY environment variable is set
if not firebase_secret:
    logger.error("FIREBASE_SECRET_KEY not found in environment variables.")
    raise ValueError("FIREBASE_SECRET_KEY environment variable not set")

# Initialize Firebase Admin SDK
try:
    # Load Firebase credentials from the service account key file
    cred = credentials.Certificate(firebase_secret)
    # Initialize Firebase with the credentials and set the storage bucket
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'face-recognition-storage.appspot.com'
    })
    bucket = storage.bucket()  # Get a reference to the storage bucket
    logger.info("Firebase Admin SDK initialized successfully.")
except FileNotFoundError as e:
    logger.error(f"Firebase credentials file not found: {e}")
    raise
except requests.exceptions.RequestException as e:
    logger.error(f"Network error during Firebase initialization: {e}")
    raise
except Exception as e:
    logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
    raise

def load_known_people_images_from_firebase():
    """
    Fetch and load images for known people from Firebase Storage.
    Create face encodings from these images for face recognition purposes.
    
    Returns:
        dict: A dictionary with names as keys and lists of face encodings as values.
    """
    known_encodings = {}  # Dictionary to store face encodings for each known person
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}  # Supported image formats

    try:
        # List all blobs (files) under the 'known_people/' directory in Firebase Storage
        blobs = bucket.list_blobs(prefix='known_people/')

        for blob in blobs:
            # Process only files (skip directories)
            if blob.name.endswith('/') and blob.name != 'known_people/':
                person_name = blob.name.split('/')[-2]  # Extract the person's name from the blob path
                person_images = []  # List to store encodings for images of the current person

                logger.info(f"Loading images for: {person_name}")
                # List all blobs for the current person
                person_blobs = bucket.list_blobs(prefix=f'{blob.name}')

                for person_blob in person_blobs:
                    # Check if the file has an allowed image extension
                    file_extension = os.path.splitext(person_blob.name)[1].lower()
                    if file_extension in allowed_extensions:
                        try:
                            logger.info(f"  Recognized {person_name} from {person_blob.name}")
                            img_bytes = person_blob.download_as_bytes()  # Download the image as bytes
                            img = face_recognition.load_image_file(BytesIO(img_bytes))  # Load the image

                            # Get face encodings from the image
                            encodings = face_recognition.face_encodings(img)
                            if encodings:
                                img_encoding = encodings[0]  # Use the first face encoding found
                                person_images.append((img_encoding, person_blob.name.split("/")[-1]))
                            else:
                                logger.warning(f"No face found in image: {person_blob.name}")
                        except (ValueError, TypeError) as e:
                            logger.error(f"Error processing image {person_blob.name}: {e}")
                        except Exception as e:
                            logger.error(f"Unexpected error with image {person_blob.name}: {e}")

                # Add the collected encodings for the current person to the dictionary
                known_encodings[person_name] = person_images
                logger.info(f"Loaded {len(person_images)} images for {person_name}.")

        logger.info("Finished loading known people images.")
        return known_encodings

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during image loading: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error loading known people images: {e}")
        return {}
