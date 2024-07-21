import gevent
from gevent import monkey
monkey.patch_all()

import os
import sys
import gc
import time
import cv2
import warnings
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_file, render_template, Response
from flask_cors import CORS
from flask_socketio import SocketIO
from logics.face_recognition import load_known_people_images_from_firebase, recognize_faces_in_image, annotate_image, process_frame
from io import BytesIO
from logger_config import setup_logger

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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', ping_interval=25, ping_timeout=86400)

# Colorful Logging Configuration
logger = setup_logger()

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
        logger.info("Known encodings already loaded.")
        return
    with lock:
        if not loaded_images:
            logger.info("Loading known encodings...")
            try:
                known_encodings.update(load_known_people_images_from_firebase())
                loaded_images = True
                logger.info("Loaded known encodings successfully.")
            except Exception as e:
                logger.error(f"Error loading known encodings: {e}")

# Load known encodings on startup
load_known_encodings()

@app.route('/')
def index():
    """
    Render the main HTML page.
    """
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    """
    Handle new client connections.
    """
    logger.info(f'Client connected: {request.sid}')
    socketio.emit('response', {'message': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    """
    Handle client disconnections.
    """
    logger.info(f'Client disconnected: {request.sid}')

@app.route('/favicon.ico')
def favicon():
    """
    Serve the favicon icon.
    """
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
    return Response(stream_annotated_video(video_path), mimetype='multipart/x-mixed-replace; boundary=frame')

def stream_annotated_video(video_path):
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
        # Define colors based on the recognized name
        rectangle_color, text_color = ((0, 0, 255), (255, 255, 255)) if name == 'Unknown' else ((0, 255, 0), (255, 255, 255))
        
        # Draw the rectangle around the face
        cv2.rectangle(frame, (left, top), (right, bottom), rectangle_color, 2)
        
        # Calculate text size and position
        text_scale = 0.5
        text_thickness = 2
        text_size, _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, text_scale, text_thickness)
        rect_bottom_left = (left, bottom - 35)
        rect_top_right = (right, bottom)
        
        # Draw background rectangle for text
        cv2.rectangle(frame, rect_bottom_left, rect_top_right, rectangle_color, cv2.FILLED)
        
        # Adjust text position if it overflows the rectangle
        text_position = (left + 6, bottom - 6)
        if text_position[0] + text_size[0] > right:
            text_position = (right - text_size[0] - 6, bottom - 6)
        
        # Put the text on the frame
        cv2.putText(frame, name, text_position, cv2.FONT_HERSHEY_SIMPLEX, text_scale, text_color, text_thickness)
        
        # Logging for each annotated face
        # logger.debug(f"Annotated face: {name} at position: ({left}, {top}), ({right}, {bottom})")
    
    try:
        # Encode the frame to JPEG format
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            raise ValueError("Frame encoding failed")
        
        # logger.info("Frame successfully encoded to JPEG format")
        return buffer.tobytes()
    except Exception as e:
        logger.error(f"Error annotating frame: {e}")
        return None


@app.route('/video_feed')
def video_feed():
    """
    Endpoint to stream real-time video feed from the webcam with face recognition annotations.
    """
    if not streaming:
        logger.warning('Streaming not available. Returning 503 response.')
        return jsonify({'error': 'Streaming not available'}), 503
    
    try:
        logger.info('Starting video feed stream.')
        response = Response(process_video(), mimetype='multipart/x-mixed-replace; boundary=frame')
        logger.info('Video feed stream started successfully.')
        return response
    except Exception as e:
        logger.error(f"Error starting video feed stream: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def process_video():
    """
    Process real-time video frames from the webcam and perform face recognition.
    """
    global streaming, video_capture, previous_names
    previous_names = set()
    video_capture = None

    try:
        video_capture = cv2.VideoCapture(0)
        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not video_capture.isOpened():
            logger.error("Failed to open video capture device.")
            return

        frame_counter = 0
        gc_interval = 30
        frame_rate = 30  # Target frame rate (frames per second)
        frame_time = 1.0 / frame_rate

        logger.info("Video capture started.")
        
        while streaming:
            start_time = time.time()
            ret, frame = video_capture.read()
            if not ret:
                logger.warning("Frame not retrieved, stopping video stream.")
                break

            recognized_faces = process_frame(frame, known_encodings)
            detected_names = {name for (_, _, _, _, name) in recognized_faces}

            if detected_names:
                if detected_names != previous_names:
                    # logger.info(f"Detected names changed. Previous: {previous_names}, Current: {detected_names}")
                    previous_names = detected_names
                    socketio.emit('persons_recognized', {'names': list(previous_names)})
                    gevent.sleep(0.1)
            #     else:
            #         logger.debug(f"Detected names unchanged: {detected_names}")
            # else:
            #     logger.debug("No faces detected.")

            frame = annotate_frame(frame, recognized_faces)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

            frame_counter += 1
            if frame_counter % gc_interval == 0:
                gc.collect()
                # logger.debug("Garbage collection performed.")

            elapsed_time = time.time() - start_time
            sleep_time = max(0, frame_time - elapsed_time)
            time.sleep(sleep_time)
    
    except cv2.error as e:
        logger.error(f"OpenCV error: {e}")
    except Exception as e:
        logger.error(f"Error processing video: {e}")
    finally:
        if video_capture:
            video_capture.release()
            logger.info("Video capture released.")
        gc.collect()
        logger.debug("Garbage collection performed in finally block.")

@app.route('/start_video_feed', methods=['POST'])
def start_video_feed():
    """
    Start the real-time video feed from the webcam.
    """
    global streaming, video_capture
    
    if streaming:
        logger.warning("Video feed is already running.")
        return jsonify({'status': 'already_started'}), 400

    try:
        video_capture = cv2.VideoCapture(0)
        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        streaming = True
        logger.info("Started video feed.")
        return jsonify({'status': 'started'})
    except Exception as e:
        logger.error(f"Error starting video feed: {e}")
        return jsonify({'error': 'Failed to start video feed'}), 500

@app.route('/stop_video_feed', methods=['POST'])
def stop_video_feed():
    """
    Stop the real-time video feed from the webcam.
    """
    global streaming, video_capture

    if not streaming:
        logger.warning("Video feed is not running.")
        return jsonify({'status': 'already_stopped'}), 400

    try:
        streaming = False
        if video_capture:
            video_capture.release()
            video_capture = None
        logger.info("Stopped video feed.")
        return jsonify({'status': 'stopped'})
    except Exception as e:
        logger.error(f"Error stopping video feed: {e}")
        return jsonify({'error': 'Failed to stop video feed'}), 500

@app.route('/health')
def health_check():
    """
    Health check endpoint to verify the service status.
    """
    try:
        status = 'healthy' if streaming else 'unhealthy'
        response = {
            'status': status,
            'timestamp': datetime.utcnow().isoformat()
        }
        logger.info("Health check successful.")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return jsonify({'error': 'Failed to perform health check'}), 500

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)
