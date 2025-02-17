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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use shared memory for SQLite
DB_URI = "file:cards_db?mode=memory&cache=shared"
image_cache = {}  # Cache for card images
db_lock = Lock()  # Lock for database operations
initialized = False

app = Flask(__name__)

# Add global status tracking
db_status = {
    "state": "not_started",
    "total_cards": 0,
    "current_card": 0,
    "message": "Database not initialized",
    "progress": 0,
    "error": None,
    "last_updated": None
}

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_URI, uri=True)
    return g.db

@app.teardown_appcontext
def close_db(error):
    if 'db' in g:
        g.db.close()

def initialize_database():
    global db_status, initialized
    try:
        logger.info("Starting database initialization...")
        with db_lock:  # Use lock to prevent multiple initializations
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
            # Create an initial connection to keep the shared memory alive
            keep_alive_conn = sqlite3.connect(DB_URI, uri=True)
            conn = sqlite3.connect(DB_URI, uri=True)
            cursor = conn.cursor()
            
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
            
            # Update database with card data
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
            
            # Process cards in smaller batches for better progress updates
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
    def __init__(self, app):
        self.app = app
        self._db_initialized = False

    def __call__(self, environ, start_response):
        if not self._db_initialized:
            with app.app_context():
                initialize_database()
            self._db_initialized = True
        return self.app(environ, start_response)

app.wsgi_app = DatabaseInitMiddleware(app.wsgi_app)

@app.route('/db-status')
def get_db_status():
    return jsonify(db_status)

@app.route('/')
def index():
    return render_template("index.html", db_status=db_status)

@app.route('/search')
def search():
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
    # Get port from environment variable with fallback to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
