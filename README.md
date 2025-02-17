  # YuGiOh Card Database and Search Application

A modern web application that provides fast and efficient searching of YuGiOh cards. Built with Flask and SQLite, optimized for cloud deployment.

## Features

- **Real-time Card Search**: Search cards by name or description
- **Card Image Display**: View high-quality card images with automatic caching
- **Progress Tracking**: Visual feedback during database initialization
- **Multi-worker Support**: Uses SQLite shared memory for production deployment
- **Error Handling**: Robust error handling with detailed status reporting
- **Modern UI**: Clean and responsive user interface

## Technical Architecture

- **Backend**: Python Flask application
- **Database**: SQLite in shared memory mode
- **Data Source**: YGOPRODeck API
- **Deployment**: Optimized for cloud platforms (e.g., Render)
- **Workers**: Supports multiple Gunicorn workers

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/YGOSpreadSheetMaker.git
   cd YGOSpreadSheetMaker
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running Locally

1. Start the development server:
   ```bash
   python main.py
   ```

2. Visit `http://localhost:5000` in your browser

## Production Deployment

The application is optimized for deployment on cloud platforms like Render:

1. The application uses SQLite in shared memory mode for multi-worker support
2. Database initialization is handled automatically on first request
3. Progress tracking is available through the `/db-status` endpoint
4. Images are cached in memory for better performance

### Environment Variables

- `PORT`: The port to run the application on (default: 5000)

## API Endpoints

- `GET /`: Main search interface
- `GET /search?query=<term>`: Search for cards
- `GET /card/<card_id>`: Get card image
- `GET /db-status`: Get database initialization status

## How It Works

1. **Database Initialization**:
   - On first request, the application fetches card data from YGOPRODeck API
   - Data is stored in a shared memory SQLite database
   - Progress is tracked and displayed to users

2. **Search Functionality**:
   - Cards can be searched by name or description
   - Results are returned in real-time
   - Full card data is stored as JSON for flexibility

3. **Image Handling**:
   - Card images are fetched from YGOPRODeck
   - Images are cached in memory after first request
   - Efficient delivery through Flask's send_file

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is open source and available under the MIT License.

## Credits

- Card data provided by [YGOPRODeck API](https://db.ygoprodeck.com/api-guide/)
- Built with Flask and SQLite