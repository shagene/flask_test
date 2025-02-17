"""
WSGI Entry Point for the YuGiOh Card Database Application

This file serves as the entry point for WSGI servers (e.g., Gunicorn) to run the application.
The database initialization is handled by the DatabaseInitMiddleware in main.py, which ensures
that the database is properly initialized even with multiple workers.

Usage:
    gunicorn wsgi:application
"""

from main import app

# The application instance that will be used by the WSGI server
# Database initialization is handled by the middleware in main.py
application = app