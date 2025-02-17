"""
YuGiOh Card Database and Search Application

This application provides a web interface to search and view YuGiOh cards. It fetches card data
from the YGOPRODeck API (https://db.ygoprodeck.com/api/v7/cardinfo.php) and stores it in an
in-memory SQLite database for fast searching. The application is designed to work with multiple
workers in a production environment (e.g., Gunicorn) by using SQLite's shared memory mode.

Key Features:
- Real-time card search with name and description matching
- Card image viewing and caching
- Progress tracking during database initialization
- Error handling and status reporting
- Multi-worker support using SQLite shared memory

Dependencies:
- Flask: Web framework
- SQLite3: Database backend (in shared memory mode)
- Requests: For API calls
- Threading: For thread-safe operations
"""

import sqlite3
import os
import requests
from tqdm import tqdm
from flask import Flask, render_template, request, jsonify, send_file, g
import json
from threading import Thread, Lock
from io import BytesIO
from datetime import datetime
import logging

# Configure logging to track application behavior and errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use shared memory SQLite for multi-worker support
# This allows all Gunicorn workers to access the same database
DB_URI = "file:cards_db?mode=memory&cache=shared"
image_cache = {}  # In-memory cache for card images
db_lock = Lock()  # Thread-safe lock for database operations
initialized = False  # Flag to track if database has been initialized

app = Flask(__name__)

# Global status tracking for database initialization
# This helps provide feedback to users during the initialization process
db_status = {
    "state": "not_started",  # States: not_started, initializing, updating, ready, error
    "total_cards": 0,        # Total number of cards to process
    "current_card": 0,       # Number of cards processed
    "message": "Database not initialized",  # User-friendly status message
    "progress": 0,           # Progress percentage (0-100)
    "error": None,           # Error message if something goes wrong
    "last_updated": None     # Timestamp of last update
}

def get_db():
    """
    Get a database connection for the current request.
    Uses Flask's application context to ensure each request gets its own connection.
    Connections are automatically closed when the request ends.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(DB_URI, uri=True)
    return g.db

@app.teardown_appcontext
def close_db(error):
    """
    Close the database connection when the request ends.
    This prevents connection leaks and ensures proper cleanup.
    """
    if 'db' in g:
        g.db.close()

def initialize_database():
    """
    Initialize the SQLite database and populate it with card data from the YGOPRODeck API.
    This function:
    1. Creates the cards table if it doesn't exist
    2. Fetches card data from the API
    3. Processes cards in batches for better performance
    4. Updates status and progress for the frontend
    
    The function is thread-safe and will only initialize once, even with multiple workers.
    """
    global db_status, initialized
    try:
        logger.info("Starting database initialization...")
        with db_lock:  # Ensure only one worker initializes the database
            if initialized:
                logger.info("Database already initialized")
                return
                
            db_status.update({
                "state": "initializing",
                "message": "Initializing database...",
                "progress": 0,
                "error": None
            })
            
            # Create shared memory database connection
            logger.info("Creating database connection...")
            # Keep-alive connection prevents the shared memory from being cleared
            keep_alive_conn = sqlite3.connect(DB_URI, uri=True)
            conn = sqlite3.connect(DB_URI, uri=True)
            cursor = conn.cursor()
            
            # Create the cards table with all necessary fields
            logger.info("Creating tables...")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    type TEXT,
                    desc TEXT,
                    card_data TEXT,
                    image_url TEXT
                )
            ''')
            conn.commit()
            
            # Fetch card data from the YGOPRODeck API
            logger.info("Fetching card data from API...")
            db_status.update({
                "state": "updating",
                "message": "Fetching card data from API...",
                "progress": 10
            })
            
            response = requests.get('https://db.ygoprodeck.com/api/v7/cardinfo.php', timeout=30)
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
                
            cards = response.json().get('data', [])
            if not cards:
                raise Exception("No card data received from API")
                
            logger.info(f"Received {len(cards)} cards from API")
            db_status.update({
                "total_cards": len(cards),
                "message": f"Processing {len(cards)} cards...",
                "progress": 20
            })
            
            # Process cards in batches for better performance and progress updates
            batch_size = 100
            for i in range(0, len(cards), batch_size):
                batch = cards[i:i+batch_size]
                for card in batch:
                    db_status["current_card"] += 1
                    progress = min(90, 20 + (70 * db_status["current_card"] // len(cards)))
                    db_status.update({
                        "message": f"Processing cards ({db_status['current_card']}/{db_status['total_cards']})",
                        "progress": progress
                    })
                    
                    # Store complete card data as JSON for flexibility
                    card_data = json.dumps(card)
                    image_url = card['card_images'][0]['image_url']
                    
                    cursor.execute('''
                        INSERT INTO cards (id, name, type, desc, card_data, image_url)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (card['id'], card['name'], card['type'], card['desc'], card_data, image_url))
                
                conn.commit()
                logger.info(f"Processed batch of {len(batch)} cards. Total progress: {progress}%")
            
            initialized = True
            logger.info("Database initialization completed successfully")
            db_status.update({
                "state": "ready",
                "message": f"Database ready with {db_status['total_cards']} cards",
                "progress": 100,
                "last_updated": datetime.now().isoformat()
            })
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during initialization: {error_msg}", exc_info=True)
        db_status.update({
            "state": "error",
            "message": "Failed to initialize database",
            "error": error_msg
        })

class DatabaseInitMiddleware:
    """
    WSGI middleware that ensures the database is initialized before handling any requests.
    This replaces the deprecated @app.before_first_request decorator and works with multiple workers.
    """
    def __init__(self, app):
        self.app = app
        self._db_initialized = False

    def __call__(self, environ, start_response):
        if not self._db_initialized:
            with app.app_context():
                initialize_database()
            self._db_initialized = True
        return self.app(environ, start_response)

# Apply the database initialization middleware
app.wsgi_app = DatabaseInitMiddleware(app.wsgi_app)

@app.route('/db-status')
def get_db_status():
    """Return the current database initialization status."""
    return jsonify(db_status)

@app.route('/')
def index():
    """Render the main page with the current database status."""
    return render_template("index.html", db_status=db_status)

@app.route('/search')
def search():
    """
    Search for cards by name or description.
    Returns a JSON array of matching cards.
    
    Query Parameters:
    - query: The search term to look for in card names and descriptions
    
    Returns:
    - 503: If the database is not ready
    - 200: JSON array of matching cards
    """
    if db_status["state"] != "ready":
        return jsonify({
            "error": "Database is not ready yet",
            "status": db_status["state"],
            "message": db_status["message"]
        }), 503
        
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify([])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT card_data FROM cards 
        WHERE name LIKE ? OR desc LIKE ?
    """, (f'%{query}%', f'%{query}%'))
    
    results = cursor.fetchall()
    cards = [json.loads(row[0]) for row in results]
    return jsonify(cards)

@app.route('/card/<int:card_id>')
def get_card_image(card_id):
    """
    Retrieve a card's image by its ID.
    Images are cached in memory after first request.
    
    Parameters:
    - card_id: The ID of the card to retrieve
    
    Returns:
    - 503: If the database is not ready
    - 404: If the card or image is not found
    - 200: The card image file
    """
    if db_status["state"] != "ready":
        return jsonify({"error": "Database not ready"}), 503
        
    # Check if image is in cache
    if card_id in image_cache:
        return send_file(
            BytesIO(image_cache[card_id]),
            mimetype='image/jpeg'
        )
    
    # Get image URL from database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT image_url FROM cards WHERE id=?", (card_id,))
    result = cursor.fetchone()
    
    if not result:
        return "Card not found", 404
        
    # Download and cache image
    response = requests.get(result[0])
    if response.status_code == 200:
        image_cache[card_id] = response.content
        return send_file(
            BytesIO(response.content),
            mimetype='image/jpeg'
        )
    
    return "Image not found", 404

if __name__ == "__main__":
    # When running directly (not through Gunicorn)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
