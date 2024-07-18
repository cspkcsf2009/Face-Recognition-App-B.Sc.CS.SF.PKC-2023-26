import gevent
from gevent import monkey
monkey.patch_all()

import logging
import os
import sys
import gc
import cv2
import warnings
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_file, render_template, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from logic import load_known_people_images_from_firebase, recognize_faces_in_image, annotate_image, process_frame
from io import BytesIO

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'logic')))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# Initialize CORS for the Flask app
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Initialize SocketIO with CORS settings
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL 1.1.1+.*")
logging.basicConfig(level=logging.WARNING)

# Load known people encodings from Firebase Storage
known_encodings = {}
loaded_images = False
streaming = False
video_capture = None
detected_names = set()

uploaded_videos = {}
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

lock = gevent.lock.Semaphore()

def load_known_encodings():
    global known_encodings, loaded_images
    if loaded_images:
        return
    with lock:
        if not loaded_images:
            try:
                known_encodings.update(load_known_people_images_from_firebase())
                loaded_images = True
                logging.info("Loaded known encodings successfully.")
            except Exception as e:
                logging.error(f"Error loading known encodings: {e}")

# Load known encodings on startup
load_known_encodings()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    logging.info(f'Client connected: {request.sid}')
    socketio.emit('response', {'message': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    logging.info(f'Client disconnected: {request.sid}')

@app.route('/favicon.ico')
def favicon():
    return send_file(os.path.join(app.root_path, 'static', 'favicon.ico'))

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'imageFile' not in request.files:
        return jsonify({'error': 'No file part'})

    file = request.files['imageFile']
    if file.filename == '':
        return jsonify({'error': 'No selected file'})

    try:
        image_data = file.read()
        recognized_faces = recognize_faces_in_image(image_data, known_encodings)
        annotated_image_data = annotate_image(image_data, recognized_faces)

        return Response(annotated_image_data, mimetype='image/jpeg')

    except Exception as e:
        logging.error(f"Error processing image: {e}")
        return jsonify({'error': 'Error processing image', 'details': str(e)})

@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'videoFile' not in request.files:
        logging.error('No file part in request')
        return jsonify({'error': 'No file part'})

    file = request.files['videoFile']
    if file.filename == '':
        logging.error('No selected file')
        return jsonify({'error': 'No selected file'})

    video_path = os.path.join(UPLOAD_FOLDER, file.filename)
    logging.info(f"Saving uploaded video to {video_path}")

    try:
        file.save(video_path)
        uploaded_videos[video_path] = datetime.now()
        logging.info(f"Uploaded video: {video_path}")
        return jsonify({'video_url': f"/stream_video/{file.filename}"})
    except Exception as e:
        logging.error(f"Error saving video: {e}")
        return jsonify({'error': 'Error saving video', 'details': str(e)})

@app.route('/stream_video/<video_name>')
def stream_video(video_name):
    video_path = os.path.join(UPLOAD_FOLDER, video_name)
    if not os.path.exists(video_path):
        return jsonify({'error': 'Video not found'}), 404
    return Response(stream_annotated_video(video_path, known_encodings), mimetype='multipart/x-mixed-replace; boundary=frame')

def stream_annotated_video(video_path, known_encodings):
    video_capture = None
    try:
        if video_path not in uploaded_videos:
            raise ValueError("Video not found or expired.")

        if datetime.now() - uploaded_videos[video_path] > timedelta(hours=1):
            os.remove(video_path)
            del uploaded_videos[video_path]
            logging.info(f"Video {video_path} has expired and has been deleted.")
            return

        video_capture = cv2.VideoCapture(video_path)
        if not video_capture.isOpened():
            raise ValueError("Error opening video stream")

        while True:
            ret, frame = video_capture.read()
            if not ret:
                break

            recognized_faces = process_frame(frame, known_encodings)
            for (top, right, bottom, left, name) in recognized_faces:
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 1)

            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

            gc.collect()

    except Exception as e:
        logging.error(f"Error processing video: {e}")
    
    finally:
        if video_capture is not None:
            video_capture.release()
        gc.collect()

@app.route('/video_feed')
def video_feed():
    global streaming
    if streaming:
        return Response(process_video(), mimetype='multipart/x-mixed-replace; boundary=frame')
    else:
        return Response(status=404)

@app.route('/start_video_feed', methods=['POST'])
def start_video_feed():
    global streaming
    if not streaming:
        streaming = True
        return jsonify({'status': 'started'})
    return jsonify({'status': 'already started'})

@app.route('/stop_video_feed', methods=['POST'])
def stop_video_feed():
    global streaming, video_capture
    if streaming:
        streaming = False
        if video_capture:
            video_capture.release()
            video_capture = None
        return jsonify({'status': 'stopped'})
    return jsonify({'status': 'already stopped'})

def process_video():
    global video_capture, detected_names
    previous_names = set()

    try:
        video_capture = cv2.VideoCapture(0)
        if not video_capture.isOpened():
            logging.error("Failed to open video capture.")
            return
        
        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        frame_counter = 0
        gc_interval = 30

        while streaming:
            ret, frame = video_capture.read()
            if not ret:
                logging.warning("Frame not retrieved, stopping video stream.")
                break

            recognized_faces = process_frame(frame, known_encodings)
            detected_names = {name for (_, _, _, _, name) in recognized_faces}

            for (top, right, bottom, left, name) in recognized_faces:
                if name == 'Unknown':
                    # Display unknown faces as "Unknown"
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
                    cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 0, 255), cv2.FILLED)
                    cv2.putText(frame, 'Unknown', (left + 6, bottom - 6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                else:
                    # Display recognized faces with their names
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
                    cv2.putText(frame, name, (left + 6, bottom - 6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            # Emit recognized names only if they have changed
            if detected_names != previous_names:
                previous_names = detected_names
                logging.info(f"Emitting persons_recognized event with names: {list(detected_names)}")
                socketio.emit('persons_recognized', {'names': list(detected_names)})
                gevent.sleep(0.1)

            # Convert frame to JPEG format for streaming
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

            frame_counter += 1
            if frame_counter % gc_interval == 0:
                gc.collect()

    except Exception as e:
        logging.error(f"Error processing video: {e}")

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)
