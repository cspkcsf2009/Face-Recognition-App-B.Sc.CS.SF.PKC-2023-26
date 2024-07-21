import multiprocessing

# Number of worker processes
workers = 1

# Use 'gevent' worker class for asynchronous workers
worker_class = 'gevent'

# Set a high timeout value to prevent workers from timing out
timeout = 86400  # 24 hours in seconds

# Keep an idle connection open for 2 seconds
keepalive = 2

# Restart workers after a certain number of requests to prevent memory leaks
max_requests = 1000

# Logging configuration
accesslog = '-'  # Log to stdout
errorlog = '-'   # Log to stderr
loglevel = 'info'  # Logging level: debug, info, warning, error, critical

# Bind to localhost on port 8000
bind = 'localhost:8000'

# Function to retrieve bind information
def get_bind():
    return bind
