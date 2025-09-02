"""
==========================
Client - Flask App
==========================

This module implements a Flask web application that serves as the client interface for the Personal Memory Recorder.
It provides various API endpoints to interact with the recorded data, including searching, timeline retrieval,
image retrieval, and exporting data as CSV.

Features:
- `/api/config`: Returns configuration details for the front-end.
- `/api/search`: Searches for image records based on window title, application name, and time range.
- `/api/timeline`: Retrieves a timeline of image records with optional filtering.
- `/api/image_at`: Retrieves the image record closest to a specified timestamp.
- `/api/thumbnail`: Serves thumbnail images based on a provided path.
- `/api/export`: Exports image records as a CSV file.

Usage:
>>> from app.client.client import run_flask_app
>>> run_flask_app()

*Author: Sudharshan TK*\n
*Created: 2023-09-02*
"""

from app.client.client import run_flask_app
