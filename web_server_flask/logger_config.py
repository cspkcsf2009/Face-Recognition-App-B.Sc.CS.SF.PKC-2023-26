import logging
from logging.handlers import RotatingFileHandler
import colorlog
import os

def setup_logger():
    """
    Setup a logger with colorful console output and file logging.
    """
    # Check if the logger is already set up
    if logging.getLogger().hasHandlers():
        return logging.getLogger()

    # Create a logger
    logger = colorlog.getLogger()

    # Create a directory for log files if it doesn't exist
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    # Create a stream handler with color formatting
    stream_handler = colorlog.StreamHandler()
    stream_handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(levelname)s:%(name)s:%(message)s:%(filename)s:%(lineno)d',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    ))

    # Add the stream handler to the logger
    logger.addHandler(stream_handler)

    # Create a rotating file handler with detailed formatting
    log_file_path = os.path.join(log_dir, 'app.log')
    file_handler = RotatingFileHandler(log_file_path, maxBytes=1_000_000, backupCount=5)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'  # User-friendly timestamp format
    ))
    logger.addHandler(file_handler)

    # Set the logging level for your application
    logger.setLevel(logging.DEBUG)

    # Suppress debug logs from urllib3
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    return logger
