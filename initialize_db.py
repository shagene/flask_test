from main import initialize_database, update_database, download_card_images

if __name__ == "__main__":
    print("Starting database initialization...")
    initialize_database()
    update_database()
    download_card_images()
    print("Database initialization complete!")