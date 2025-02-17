import sqlite3
import os
import requests
from tqdm import tqdm
from flask import Flask, render_template, request, jsonify, send_file
import json
from threading import Thread
from io import BytesIO

# Use in-memory database for free tier
DB_PATH = ":memory:"
image_cache = {}  # Cache for card images

app = Flask(__name__)

# Add global status tracking
db_status = {
    "state": "not_started",  # not_started, initializing, updating, ready
    "total_cards": 0,
    "current_card": 0,
    "message": "Database not initialized"
}

def initialize_database():
    global db_status
    db_status["state"] = "initializing"
    db_status["message"] = "Initializing database..."
    
    # Create in-memory database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    db_status["state"] = "updating"
    db_status["message"] = "Fetching card data..."
    
    response = requests.get('https://db.ygoprodeck.com/api/v7/cardinfo.php')
    if response.status_code == 200:
        cards = response.json().get('data', [])
        db_status["total_cards"] = len(cards)
        
        for card in cards:
            db_status["current_card"] += 1
            db_status["message"] = f"Processing cards ({db_status['current_card']}/{db_status['total_cards']})"
            
            card_data = json.dumps(card)
            image_url = card['card_images'][0]['image_url']
            
            cursor.execute('''
                INSERT INTO cards (id, name, type, desc, card_data, image_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (card['id'], card['name'], card['type'], card['desc'], card_data, image_url))
            
        conn.commit()
    
    conn.close()
    db_status["state"] = "ready"
    db_status["message"] = "Database ready"

@app.route('/db-status')
def get_db_status():
    return jsonify(db_status)

@app.route('/')
def index():
    return render_template("index.html")

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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT card_data FROM cards 
        WHERE name LIKE ? OR desc LIKE ?
    """, (f'%{query}%', f'%{query}%'))
    
    results = cursor.fetchall()
    conn.close()
    
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT image_url FROM cards WHERE id=?", (card_id,))
    result = cursor.fetchone()
    conn.close()
    
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
    # Start database initialization in background
    Thread(target=initialize_database, daemon=True).start()
    
    # Get port from environment variable with fallback to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
