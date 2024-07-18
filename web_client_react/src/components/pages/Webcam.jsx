import { useState, useRef } from 'react';
import axios from 'axios';
import { io } from 'socket.io-client';

const Webcam = () => {
    const [isStreaming, setIsStreaming] = useState(false);
    const [videoSrc, setVideoSrc] = useState('');
    const [detectedPersons, setDetectedPersons] = useState(['Unknown']);
    const [isLoading, setIsLoading] = useState(false);
    const socketRef = useRef(null);
    const spokenNames = useRef(new Set());

    const backendHostUrl = import.meta.env.VITE_BACKEND_HOST_URL || 'http://127.0.0.1:8000';

    const speakNames = (names) => {
        const greetings = {
            "Samuvel": "Good Morning Samuvel",
            "Akash": "Good Evening Akash",
            "Unknown": " "
        };

        const voices = speechSynthesis.getVoices();
        const femaleVoice = voices.find(voice => voice.name.toLowerCase().includes('female'));

        names.forEach((name) => {
            if (!spokenNames.current.has(name)) {
                const message = greetings[name] || `Hello ${name}`;
                const utterance = new SpeechSynthesisUtterance(message);

                utterance.voice = femaleVoice || voices[0];
                utterance.lang = 'en-US';
                utterance.pitch = 1;
                utterance.rate = 1;
                utterance.volume = 1;

                speechSynthesis.speak(utterance);
                spokenNames.current.add(name);
            }
        });
    };

    const handleStart = async () => {
        console.log('Start button clicked');
        setIsLoading(true);

        // Initialize WebSocket connection when start button is clicked
        if (!socketRef.current) {
            console.log('Initializing WebSocket connection...');
            socketRef.current = io(backendHostUrl, {
                transports: ['websocket'],
                cors: {
                    origin: backendHostUrl,
                    methods: ["GET", "POST"],
                    credentials: true,
                },
                autoConnect: false,
            });

            socketRef.current.connect();
            console.log('Socket connection attempt...');

            socketRef.current.on('connect', () => {
                console.log('Connected to WebSocket');
            });

            socketRef.current.on('persons_recognized', (data) => {
                console.log('Received "persons_recognized" event:', data);
                if (data && Array.isArray(data.names)) {
                    setDetectedPersons(data.names);
                    console.log('Detected persons updated:', data.names);
                    speakNames(data.names);
                } else {
                    console.warn('Invalid data format for persons_recognized:', data);
                }
            });

            socketRef.current.on('connect_error', (error) => {
                console.error('Socket connection error:', error);
                alert('Failed to connect to the server. Please check your connection.');
            });

            socketRef.current.on('disconnect', () => {
                console.log('WebSocket disconnected');
            });
        }

        try {
            const response = await axios.post(`${backendHostUrl}/start_video_feed`);
            console.log('Received response from start_video_feed:', response);

            if (response.status === 200) {
                setIsStreaming(true);
                setVideoSrc(`${backendHostUrl}/video_feed?_=${new Date().getTime()}`);
                console.log('Video streaming started');
            } else {
                console.warn('Unexpected response status on start:', response.status);
            }
        } catch (error) {
            console.error('Error starting video stream:', error);
            alert('Failed to start video stream. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleStop = async () => {
        console.log('Stop button clicked');
        setIsLoading(true);
        try {
            setIsStreaming(false);
            setVideoSrc('');
            console.log('Video streaming stopped');
            const response = await axios.post(`${backendHostUrl}/stop_video_feed`);
            console.log('Received response from stop_video_feed:', response);
        } catch (error) {
            console.error('Error stopping video stream:', error);
            alert('Failed to stop video stream. Please try again.');
        } finally {
            setIsLoading(false);
        }

        // Disconnect WebSocket when stop button is clicked
        if (socketRef.current) {
            socketRef.current.off();
            socketRef.current.disconnect();
            socketRef.current = null;
            console.log('WebSocket cleanup done');
        }
    };

    const handleResetSpokenNames = () => {
        spokenNames.current.clear();
        console.log('Spoken names reset');
    };

    return (
        <div className="flex flex-col items-center p-4">
            <h2 className="text-2xl font-bold mb-4">Webcam Streaming</h2>
            <div className="mb-4">
                <button
                    onClick={handleStart}
                    disabled={isStreaming || isLoading}
                    className={`px-4 py-2 rounded ${isLoading && !isStreaming ? 'bg-gray-300' : 'bg-blue-500 text-white'}`}
                >
                    {isLoading && !isStreaming ? 'Starting...' : 'Start'}
                </button>
                <button
                    onClick={handleStop}
                    disabled={!isStreaming || isLoading}
                    className={`ml-2 px-4 py-2 rounded ${isLoading && isStreaming ? 'bg-gray-300' : 'bg-red-500 text-white'}`}
                >
                    {isLoading && isStreaming ? 'Stopping...' : 'Stop'}
                </button>
                <button
                    onClick={handleResetSpokenNames}
                    className="ml-2 px-4 py-2 rounded bg-yellow-500 text-white"
                >
                    Reset Spoken Names
                </button>
            </div>
            {isStreaming && (
                <div>
                    <img src={videoSrc} width="840" height="680" alt="Webcam feed" className="rounded shadow-md" />
                    <h3 className="text-xl font-semibold mt-4">Detected Persons:</h3>
                    <ul className="list-disc list-inside">
                        {detectedPersons.map((name, index) => (
                            <li key={index}>{name}</li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
};

export default Webcam;
