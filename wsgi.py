from main import app, initialize_database, update_database, download_card_images

# Initialize the database when the WSGI application starts
print("Starting database initialization...")
initialize_database()
update_database()
download_card_images()
print("Database initialization complete!")

# Export the Flask application
application = app