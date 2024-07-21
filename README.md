# Web Server Flask

## Setup

1. Install Poetry if not already installed:

   ```bash
   python install-poetry.py
   ```

2. Install dependencies:

   ```bash
   poetry install
   ```

3. Run the application:

   ```bash
   poetry run python app.py
   ```

4. Run Gunicorn server:

   ```bash
   poetry run gunicorn -c gunicorn_config.py app:app
   ```

5. To use Honcho for automatic server restarts:

   ```bash
   poetry run python honcho-reload.py
   ```
