from main import app, initialize_database
from threading import Thread

# Initialize database in background
Thread(target=initialize_database, daemon=True).start()

# Export the Flask application
application = app