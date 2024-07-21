import { useState, useRef, useEffect, useCallback } from 'react';
import axios from 'axios';
import { io } from 'socket.io-client';

const Webcam = () => {
    // State variables for managing streaming, video source, detected persons, and loading state
    const [isStreaming, setIsStreaming] = useState(false);
    const [videoSrc, setVideoSrc] = useState('');
    const [detectedPersons, setDetectedPersons] = useState(['Unknown']);
    const [isLoading, setIsLoading] = useState(false);
    const [isServerHealthy, setIsServerHealthy] = useState(true); // Health status

    // Refs for managing WebSocket connection and spoken names
    const socketRef = useRef(null);
    const spokenNames = useRef(new Set());

    // Backend host URL from environment variables or default to local
    const backendHostUrl = import.meta.env.VITE_BACKEND_HOST_URL || 'http://127.0.0.1:8000';

    // Function to check server health
    const checkServerHealth = useCallback(async () => {
        try {
            const response = await axios.get(`${backendHostUrl}/health`);
            if (response.status === 200 && response.data.status === 'healthy') {
                setIsServerHealthy(true);
            } else {
                setIsServerHealthy(false);
            }
        } catch (error) {
            console.error('Health check failed:', error);
            setIsServerHealthy(false);
        }
    }, [backendHostUrl]);

    // Health check interval
    useEffect(() => {
        const interval = setInterval(checkServerHealth, 3600000); // Check every 1 hour
        return () => clearInterval(interval); // Clean up interval on component unmount
    }, [checkServerHealth]);

    // Function to handle speaking names with greetings
    const speakNames = (names) => {
        const greetings = {
            "Unknown": " ",
            "A. Samuvel": "Congrats A. Saaamuyel",
            "Sujith": "Congrats Sujith Laaalaaso Patil",
            "S. Logith": "Congrats Logith Pandiyan",
            "M. Sakthi": "Congrats R. Sakthi Pon Raani",
            "N. Indira": "Welcome, Doctor. N. Indira, Respected Principal of this college, let's start the programme with your presidential address",
            "G. Rexin": "Welcome, Doctor. G. Rexin Thusnavis, respected Vice Principal of this college, let's inaugurate this function",
            "N. Neela mohan": "Welcome, Doctor. N. Neela mohan, Director, self financed stream of this college, let's felicitate the gathering",
            "M. S. Kavitha": "Welcome, Mrs M S Kavitha, Head of the Department. It's the time to declare the office bearers of our association DECOS.",
            "Ms Jenet": "Welcome Ms. jenet, Faculty, Feathers Software, Nagercoil. It's your time to introduce yourself and your firm",
            "Ms Saranya": "Welcome Ms. Saranya, Subject Matter Expert, Php, Feather's Software, Nagercoil. It's your timespsan of 1 hour to elaborate the PHP as easy as possible to our students",
            "V.A. Abilasha": "Welcome, Abilasha, it's your turn to welcome the gathering",
            "G. Vennila": "Welcome G. Vennila, It's your turn to thank the gathering"
        };

        const voices = speechSynthesis.getVoices();
        const selectedVoice = voices.find(voice => voice.lang === 'en-IN' && voice.name.toLowerCase().includes('male'));
        const defaultVoice = voices.find(voice => voice.lang === 'en-IN');

        names.forEach((name) => {
            if (!spokenNames.current.has(name)) {
                const message = greetings[name] || `Congrats ${name}`;
                const utterance = new SpeechSynthesisUtterance(message);

                utterance.voice = selectedVoice || defaultVoice || voices[1];
                utterance.lang = 'en-IN';
                utterance.pitch = 1;
                utterance.rate = 1;
                utterance.volume = 1;

                speechSynthesis.speak(utterance);
                spokenNames.current.add(name);
            }
        });
    };

    // Function to handle starting the video stream
    const handleStart = async () => {
        console.log('Start button clicked');
        setIsLoading(true);

        if (!isServerHealthy) {
            alert('Server is not healthy. Please try again later.');
            setIsLoading(false);
            return;
        }

        if (!socketRef.current) {
            console.log('Initializing WebSocket connection...');
            socketRef.current = io(backendHostUrl, {
                transports: ['websocket'], // Use WebSocket transport
                cors: {
                    origin: backendHostUrl,
                    methods: ["GET", "POST"],
                    credentials: true,
                },
                reconnection: true, // Enable automatic reconnection
                reconnectionAttempts: Infinity, // Unlimited reconnection attempts
                reconnectionDelay: 1000, // Delay between reconnections (in milliseconds)
                pingInterval: 25000, // Interval of 25 seconds to send ping messages to the server (matches server ping_interval)
                pingTimeout: 86400000, // Timeout of 24 hours for receiving a ping response from the server (matches server ping_timeout)
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
                alert('Failed to connect to the server. Please check your socketIO connection.');
            });

            socketRef.current.on('disconnect', () => {
                console.log('WebSocket disconnected');
            });

            socketRef.current.on('reconnect', (attemptNumber) => {
                console.log('Reconnected to server on attempt', attemptNumber);
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

    // Function to handle stopping the video stream
    const handleStop = async () => {
        console.log('Stop button clicked');
        setIsLoading(true);

        try {
            setIsStreaming(false);
            setVideoSrc('');
            console.log('Video streaming stopped');
            window.location.reload()
            const response = await axios.post(`${backendHostUrl}/stop_video_feed`);
            console.log('Received response from stop_video_feed:', response);
        } catch (error) {
            console.error('Error stopping video stream:', error);
            alert('Failed to stop video stream. Please try again.');
        } finally {
            setIsLoading(false);
        }

        if (socketRef.current) {
            socketRef.current.off();
            socketRef.current.disconnect();
            socketRef.current = null;
            console.log('WebSocket cleanup done');
        }
    };

    // Function to reset the spoken names
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
            {!isServerHealthy && (
                <p className="text-red-500 mt-4">Server health check failed. Please try again later.</p>
            )}
        </div>
    );
};

export default Webcam;
