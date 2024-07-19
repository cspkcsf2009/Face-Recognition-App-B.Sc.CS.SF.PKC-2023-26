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
import colorlog

# Path Configuration
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'logic')))
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

# Flask Configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'default_secret!')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

# CORS Configuration
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# SocketIO Configuration
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Colorful Logging Configuration
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(levelname)s:%(name)s:%(message)s',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
))
logger = colorlog.getLogger()
logger.addHandler(handler)
# logger.setLevel(logging.DEBUG)

# Logging and Warning Configuration
warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL 1.1.1+.*")

# Global Variables
known_encodings = {}
loaded_images = False
streaming = False
video_capture = None
detected_names = set()
uploaded_videos = {}
lock = gevent.lock.Semaphore()

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def load_known_encodings():
    """
    Load known face encodings from Firebase Storage. This function is called
    once on server startup to cache known face encodings in memory.
    """
    global known_encodings, loaded_images
    if loaded_images:
        return
    with lock:
        if not loaded_images:
            try:
                known_encodings.update(load_known_people_images_from_firebase())
                loaded_images = True
                logger.info("Loaded known encodings successfully in app.py.")
            except Exception as e:
                logger.error(f"Error loading known encodings: {e}")

# Load known encodings on startup
load_known_encodings()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    """
    Handle a new client connection to the SocketIO server.
    """
    logger.info(f'Client connected: {request.sid}')
    socketio.emit('response', {'message': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    """
    Handle client disconnection from the SocketIO server.
    """
    logger.info(f'Client disconnected: {request.sid}')

@app.route('/favicon.ico')
def favicon():
    return send_file(os.path.join(app.root_path, 'static', 'favicon.ico'))

@app.route('/upload_image', methods=['POST'])
def upload_image():
    """
    Handle image upload, perform face recognition, and return the annotated image.
    """
    if 'imageFile' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['imageFile']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        image_data = file.read()
        recognized_faces = recognize_faces_in_image(image_data, known_encodings)
        annotated_image_data = annotate_image(image_data, recognized_faces)
        return Response(annotated_image_data, mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        return jsonify({'error': 'Error processing image', 'details': str(e)}), 500

@app.route('/upload_video', methods=['POST'])
def upload_video():
    """
    Handle video upload, save it to the server, and return the URL for streaming.
    """
    if 'videoFile' not in request.files:
        logger.error('No file part in request')
        return jsonify({'error': 'No file part'}), 400

    file = request.files['videoFile']
    if file.filename == '':
        logger.error('No selected file')
        return jsonify({'error': 'No selected file'}), 400

    video_path = os.path.join(UPLOAD_FOLDER, file.filename)
    logger.info(f"Saving uploaded video to {video_path}")

    try:
        file.save(video_path)
        uploaded_videos[video_path] = datetime.now()
        logger.info(f"Uploaded video: {video_path}")
        return jsonify({'video_url': f"/stream_video/{file.filename}"})
    except Exception as e:
        logger.error(f"Error saving video: {e}")
        return jsonify({'error': 'Error saving video', 'details': str(e)}), 500

@app.route('/stream_video/<video_name>')
def stream_video(video_name):
    """
    Stream an uploaded video with face recognition annotations.
    """
    video_path = os.path.join(UPLOAD_FOLDER, video_name)
    if not os.path.exists(video_path):
        return jsonify({'error': 'Video not found'}), 404
    return Response(stream_annotated_video(video_path, known_encodings), mimetype='multipart/x-mixed-replace; boundary=frame')

def stream_annotated_video(video_path, known_encodings):
    """
    Generator function to stream video frames with face recognition annotations.
    """
    try:
        if video_path not in uploaded_videos:
            raise ValueError("Video not found or expired.")

        if datetime.now() - uploaded_videos[video_path] > timedelta(hours=1):
            os.remove(video_path)
            del uploaded_videos[video_path]
            logger.info(f"Video {video_path} has expired and has been deleted.")
            return

        video_capture = cv2.VideoCapture(video_path)
        if not video_capture.isOpened():
            raise ValueError("Error opening video stream")

        while True:
            ret, frame = video_capture.read()
            if not ret:
                break

            recognized_faces = process_frame(frame, known_encodings)
            frame = annotate_frame(frame, recognized_faces)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

            gc.collect()
    except ValueError as ve:
        logger.error(f"ValueError: {ve}")
    except Exception as e:
        logger.error(f"Error processing video: {e}")
    finally:
        if video_capture:
            video_capture.release()
        gc.collect()

def annotate_frame(frame, recognized_faces):
    """
    Annotate video frame with rectangles and labels for recognized faces.
    """
    for (top, right, bottom, left, name) in recognized_faces:
        rectangle_color, text_color = ((0, 0, 255), (255, 255, 255)) if name == 'Unknown' else ((0, 255, 0), (255, 255, 255))
        cv2.rectangle(frame, (left, top), (right, bottom), rectangle_color, 2)
        text_size, _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        rect_bottom_left, rect_top_right = (left, bottom - 35), (right, bottom)
        cv2.rectangle(frame, rect_bottom_left, rect_top_right, rectangle_color, cv2.FILLED)
        text_position = (left + 6, bottom - 6)
        if text_position[0] + text_size[0] > right:
            text_position = (right - text_size[0] - 6, bottom - 6)
        cv2.putText(frame, name, text_position, cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
    ret, buffer = cv2.imencode('.jpg', frame)
    return buffer.tobytes()

@app.route('/video_feed')
def video_feed():
    """
    Endpoint to stream real-time video feed from the webcam with face recognition annotations.
    """
    if streaming:
        return Response(process_video(), mimetype='multipart/x-mixed-replace; boundary=frame')
    return jsonify({'error': 'Streaming not available'}), 503

def process_video():
    """
    Process real-time video frames from the webcam and perform face recognition.
    """
    global streaming, video_capture, previous_names
    previous_names = set()
    try:
        video_capture = cv2.VideoCapture(0)
        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        frame_counter = 0
        gc_interval = 30

        while streaming:
            ret, frame = video_capture.read()
            if not ret:
                logger.warning("Frame not retrieved, stopping video stream.")
                break

            recognized_faces = process_frame(frame, known_encodings)
            detected_names = {name for (_, _, _, _, name) in recognized_faces}

            if detected_names != previous_names:
                previous_names = detected_names
                logger.info(f"Recognized faces: {detected_names}")
                socketio.emit('persons_recognized', {'names': list(previous_names)})
                gevent.sleep(0.1)

            frame = annotate_frame(frame, recognized_faces)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

            # Collect garbage periodically to free up memory
            frame_counter += 1
            if frame_counter % gc_interval == 0:
                gc.collect()
    except Exception as e:
        logger.error(f"Error processing video: {e}")
    finally:
        if video_capture:
            video_capture.release()
        gc.collect()

@app.route('/start_video_feed', methods=['POST'])
def start_video_feed():
    """
    Start the real-time video feed from the webcam.
    """
    global streaming
    streaming = True
    logger.info("Started video feed.")
    return jsonify({'status': 'started'})

@app.route('/stop_video_feed', methods=['POST'])
def stop_video_feed():
    """
    Stop the real-time video feed from the webcam.
    """
    global streaming
    streaming = False
    if video_capture:
        video_capture.release()
    logger.info("Stopped video feed.")
    return jsonify({'status': 'stopped'})

@app.route('/health')
def health_check():
    """
    Health check endpoint to verify the service status.
    """
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000)
