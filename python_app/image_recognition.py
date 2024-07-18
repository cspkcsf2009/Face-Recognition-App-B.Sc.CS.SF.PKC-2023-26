import cv2
import face_recognition
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, storage

# Initialize Firebase Admin SDK
cred = credentials.Certificate('facedetect/serviceAccountKey.json')  # Update with your service account key path
firebase_admin.initialize_app(cred, {
    'storageBucket': 'face-recognition-storage.appspot.com'  # Update with your Firebase Storage bucket name
})
bucket = storage.bucket()

# Function to dynamically fetch and load images for known people from Firebase Storage
def load_known_people_images_from_firebase():
    known_encodings = {}

    # List blobs in the Firebase Storage path for known_people
    blobs = bucket.list_blobs(prefix='known_people/')

    for blob in blobs:
        if blob.name.endswith('/') and blob.name != 'known_people/':  # Check if it's a directory and skip the root directory
            person_name = blob.name.split('/')[-2]  # Extract directory name (person's name)
            person_images = []

            print(f"Loading images for: {person_name}")

            # List files in the Firebase Storage path for the person
            person_blobs = bucket.list_blobs(prefix=f'{blob.name}')

            for person_blob in person_blobs:
                if person_blob.name.endswith('.jpg'):
                    print(f"  Recognized {person_name} from {person_blob.name}")

                    # Download image from Firebase Storage to a temporary local file
                    local_image_path = f'/tmp/{person_blob.name.split("/")[-1]}'  # Temporary local path
                    person_blob.download_to_filename(local_image_path)

                    # Load image and get face encoding
                    img = face_recognition.load_image_file(local_image_path)
                    img_encoding = face_recognition.face_encodings(img)[0]
                    person_images.append((img_encoding, person_blob.name.split("/")[-1]))  # Store encoding and filename

            known_encodings[person_name] = person_images

    return known_encodings
# Function to recognize faces in an image and display output
def recognize_faces_in_image(image_path, known_encodings):
    img = face_recognition.load_image_file(image_path)
    face_locations = face_recognition.face_locations(img)
    face_encodings = face_recognition.face_encodings(img, face_locations)

    # Convert RGB image to BGR for OpenCV display
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        best_match_name = "Unknown"
        best_match_distance = 0.6  # Set a threshold for considering a match

        for person_name, encodings in known_encodings.items():
            for known_encoding, filename in encodings:
                distance = face_recognition.face_distance([known_encoding], face_encoding)
                if distance < best_match_distance:
                    best_match_distance = distance
                    best_match_name = person_name

        # Draw rectangle and label around the face
        cv2.rectangle(img, (left, top), (right, bottom), (0, 0, 255), 2)
        cv2.putText(img, best_match_name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    # Display the image with annotations
    cv2.imshow('Recognized Image', img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

# Example usage:
if __name__ == "__main__":
    # Load known people images from Firebase Storage dynamically
    known_encodings = load_known_people_images_from_firebase()

    # Prompt user to enter image path for recognition
    image_path = input("Enter path to the image file: ").strip()

    # Call the function to recognize faces in the image
    recognize_faces_in_image(image_path, known_encodings)