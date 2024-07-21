# Web Server Flask

## Setup

1. Install Poetry if not already installed:

   ```bash
   python install-poetry.py
   ```
   or
      ```bash
   pip install poetry
   ```

3. Install dependencies:

   ```bash
   poetry install
   ```

4. Run the application:

   ```bash
   poetry run python app.py
   ```

5. Run Gunicorn server:

   ```bash
   poetry run gunicorn -c gunicorn_config.py app:app
   ```

6. To use Honcho for automatic server restarts:

   ```bash
   poetry run python honcho-reload.py
   ```
   or
   ```bash
   honcho start
   ```
