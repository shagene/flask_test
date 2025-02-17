import sqlite3
import os
import requests
from tqdm import tqdm
from flask import Flask, render_template, request, jsonify
import json
from threading import Thread

DB_PATH = "yugioh_cards.db"
IMAGES_DIR = "static/card_images"
app = Flask(__name__)

# Add global status tracking
db_status = {
    "state": "not_started",  # not_started, initializing, updating, downloading, ready
    "total_images": 0,
    "current_image": 0,
    "message": "Database not initialized"
}

os.makedirs(IMAGES_DIR, exist_ok=True)

def initialize_database():
    global db_status
    db_status["state"] = "initializing"
    db_status["message"] = "Initializing database..."
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY,
            name TEXT,
            type TEXT,
            desc TEXT,
            card_data TEXT
        )
    ''')
    conn.commit()
    conn.close()

def update_database():
    global db_status
    db_status["state"] = "updating"
    db_status["message"] = "Updating card database..."
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    response = requests.get('https://db.ygoprodeck.com/api/v7/cardinfo.php')
    if response.status_code == 200:
        cards = response.json().get('data', [])
        for card in tqdm(cards, desc="Updating Database", unit="card"):
            cursor.execute("SELECT id FROM cards WHERE id=?", (card['id'],))
            if cursor.fetchone() is None:
                card_data = json.dumps(card)
                cursor.execute('''
                    INSERT INTO cards (id, name, type, desc, card_data)
                    VALUES (?, ?, ?, ?, ?)
                ''', (card['id'], card['name'], card['type'], card['desc'], card_data))
        conn.commit()
        conn.close()

def download_card_images():
    global db_status
    db_status["state"] = "downloading"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, card_data FROM cards")
    cards = cursor.fetchall()
    conn.close()

    missing_images = [
        (card_id, json.loads(card_data)['card_images'][0]['image_url'])
        for card_id, card_data in cards
        if not os.path.exists(f"{IMAGES_DIR}/{card_id}.jpg")
    ]

    db_status["total_images"] = len(missing_images)
    db_status["current_image"] = 0
    
    for card_id, image_url in missing_images:
        image_path = os.path.join(IMAGES_DIR, f"{card_id}.jpg")
        response = requests.get(image_url)
        with open(image_path, 'wb') as f:
            f.write(response.content)
        db_status["current_image"] += 1
        db_status["message"] = f"Downloading images ({db_status['current_image']}/{db_status['total_images']})"

    db_status["state"] = "ready"
    db_status["message"] = "Database ready"

def init_db_async():
    initialize_database()
    update_database()
    download_card_images()

@app.route('/db-status')
def get_db_status():
    return jsonify(db_status)

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/search')
def search():
    if db_status["state"] != "ready":
        return jsonify({"error": "Database not ready"}), 503
    
    query = request.args.get('query')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT name, id
        FROM cards 
        WHERE name LIKE ? OR desc LIKE ?
    """, ('%' + query + '%', '%' + query + '%'))
    cards = cursor.fetchall()
    conn.close()
    return jsonify([{"name": card[0], "id": card[1]} for card in cards])

@app.route('/card/<int:card_id>')
def get_card_image(card_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT card_data FROM cards WHERE id = ?", (card_id,))
    card = cursor.fetchone()
    conn.close()
    if card:
        card_data = json.loads(card[0])
        image_url = f"/{IMAGES_DIR}/{card_data['id']}.jpg"
        return jsonify({"image_url": image_url})
    else:
        return jsonify({"error": "Card not found"}), 404

if __name__ == "__main__":
    # Start database initialization in background
    Thread(target=init_db_async, daemon=True).start()
    
    # Get port from environment variable with fallback to 10000
    port = int(os.environ.get("PORT", 10000))
    # Explicitly bind to 0.0.0.0 to accept all incoming connections
    app.run(host='0.0.0.0', port=port)
