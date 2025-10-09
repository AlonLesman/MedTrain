# PDF → MCQs → Google Form Web Interface

A minimal web interface for running the PDF to Google Form pipeline.

## Quick Start

### Option 1: Easy Startup (Recommended)
```bash
# Install all dependencies
pip install -r requirements.txt

# Run the startup script (checks everything and opens browser)
python start_web_interface.py
```

### Option 2: Manual Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up your environment variables** in a `.env` file:
   ```bash
   # Required
   OPENAI_API_KEY=your_openai_api_key_here
   
   # Optional (defaults shown)
   MODEL=gpt-4.1
   NUM_QUESTIONS=6
   PIPELINE_PASSWORD=changeme
   FLASK_SECRET_KEY=dev-secret
   ```

3. **Set up Google OAuth** (first time only):
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project or select existing one
   - Enable Google Forms API and Google Drive API
   - Create OAuth Client ID (Desktop application)
   - Download `client_secret.json` to the project root

4. **Start the Flask server**:
   ```bash
   python server/app.py
   ```

5. **Open the web interface**:
   - Go to http://127.0.0.1:5050/web/index.html
   - Or visit http://127.0.0.1:5050 and click the link

## Authentication

The web interface is protected by a simple password gate:

- **Default password**: `changeme` (set via `PIPELINE_PASSWORD` environment variable)
- **Login page**: http://127.0.0.1:5050/login
- **Logout**: Click the "Logout" button in the top-right corner
- **Session management**: Uses Flask sessions with configurable secret key

## Usage

1. **Login**: Enter the password to access the form
2. **Upload a PDF**: Select a PDF file from your computer
3. **Choose number of questions**: Set how many MCQs to generate (1-50)
4. **Select language**: Choose from English, Hebrew, or Polish (currently logged for future use)
5. **Click "Generate"**: The pipeline will:
   - Extract text from your PDF
   - Generate MCQs using OpenAI
   - Create a Google Form with the questions
   - Return the form edit URL

## Features

- **Simple Interface**: Clean, minimal HTML form
- **Real-time Status**: See progress and results in the status area
- **Error Handling**: Clear error messages if something goes wrong
- **OAuth Authentication**: First run will open browser for Google OAuth
- **Temporary Files**: Uploaded PDFs are automatically cleaned up

## API Endpoints

- `GET /` - Redirects to login or form based on authentication
- `GET /login` - Login page (GET) and authentication (POST)
- `GET /form` - Main form page (requires authentication)
- `GET /logout` - Logout and clear session
- `POST /api/pipeline` - Main pipeline endpoint (requires authentication)
- `GET /health` - Health check
- `GET /web/<path:filename>` - Serve web files

## Troubleshooting

- **"Missing file 'pdf'"**: Make sure you selected a PDF file before clicking Generate
- **"Pipeline failed"**: Check your OpenAI API key and internet connection
- **OAuth issues**: Make sure you have `client_secret.json` in the project root
- **Port 5050 in use**: Change the port in `server/app.py` if needed

## File Structure

```
MedTrain/
├── web/
│   └── index.html              # Web interface (HTML/CSS/JS)
├── server/
│   ├── app.py                  # Flask server with API endpoints
│   └── requirements.txt        # Flask-specific dependencies
├── create_form_from_json.py    # Google Forms creation (modified to return URL)
├── pdf_to_questions.py         # PDF to MCQs generation
├── start_web_interface.py      # Easy startup script with checks
├── test_integration.py         # Integration test script
├── requirements.txt            # All project dependencies
├── README_WEB_INTERFACE.md     # This file
├── .env                        # Environment variables (create this)
├── client_secret.json          # Google OAuth credentials (download this)
└── token.pkl                   # OAuth token cache (auto-generated)
```

## Next Steps

- Add language support to the MCQ generation prompt
- Add Service Account authentication option
- Add form sharing functionality
- Add progress bars for long operations
