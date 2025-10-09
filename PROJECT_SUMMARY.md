# MedTrain - PDF to Google Forms Pipeline

## Project Overview

MedTrain is a Flask-based web application that converts PDF documents into interactive Google Forms with multiple-choice questions (MCQs). The application uses AI (OpenAI GPT) to extract content from PDFs, generate educational questions, and automatically create Google Forms with proper quiz settings.

## Core Functionality

1. **PDF Processing**: Extracts text content from uploaded PDF files
2. **AI Question Generation**: Uses OpenAI GPT to generate educational MCQs from PDF content
3. **Google Forms Integration**: Automatically creates Google Forms with quiz settings
4. **Web Interface**: User-friendly web UI with authentication
5. **Cloud Run Ready**: Production-ready deployment with secret management

## Project Structure

```
MedTrain/
├── Procfile                          # Cloud Run deployment configuration
├── requirements.txt                   # Python dependencies
├── .gitignore                        # Git ignore patterns (excludes secrets)
├── PROJECT_SUMMARY.md                # This file
│
├── server/                           # Main Flask application
│   ├── app.py                       # Flask app with web interface & API
│   └── requirements.txt             # Server-specific dependencies
│
├── web/                             # Static web files
│   └── index.html                   # Web interface HTML
│
├── token_utils.py                   # Token management utilities
├── create_form_from_json.py         # Google Forms creation logic
├── pdf_to_questions.py              # PDF processing & AI integration
├── start_web_interface.py           # Local development startup script
│
├── app.py                           # Alternative Flask app (simpler version)
├── admin_pafe.html                  # Admin interface
├── create_form_from_json.py         # Form creation utilities
├── mcqs.json                        # Sample MCQ data
├── pdf_to_questions.py              # PDF processing utilities
│
└── Sample PDFs/                     # Test documents
    ├── TakeAways_June_2025.pdf
    └── TakeAways_June_2025_en.pdf
```

## Key Components

### 1. Flask Application (`server/app.py`)
- **Main Entry Point**: Production Flask app with full web interface
- **Authentication**: Password-protected access
- **API Endpoints**:
  - `POST /api/pipeline` - Main processing pipeline
  - `GET /health` - Health check
  - `GET /healthz` - Cloud Run health check
  - `GET /login` - Authentication page
  - `GET /form` - Main web interface

### 2. Token Management (`token_utils.py`)
- **Cloud Run Support**: Handles secret mounting at `/secrets/token.pkl`
- **Local Development**: Falls back to `token.pkl` for local dev
- **Lazy Loading**: Tokens loaded only when needed (not at import time)

### 3. Google Forms Integration (`create_form_from_json.py`)
- **OAuth Authentication**: User-based Google authentication
- **Service Account Support**: Server-based authentication option
- **Quiz Creation**: Automatically configures forms as quizzes
- **Batch Processing**: Efficiently processes multiple questions

### 4. PDF Processing (`pdf_to_questions.py`)
- **Text Extraction**: Uses pdfplumber for PDF text extraction
- **AI Integration**: OpenAI GPT for question generation
- **Multi-language Support**: English, Hebrew, Polish
- **Configurable**: Adjustable number of questions

## Dependencies

### Core Dependencies (`requirements.txt`)
```
# PDF Processing
pdfplumber>=0.11.0
tenacity>=9.0.0

# AI Integration
openai>=1.0.0

# Environment Management
python-dotenv>=0.19.0

# Google APIs
google-api-python-client>=2.180.0
google-auth>=2.40.0
google-auth-oauthlib>=1.2.0

# Web Framework
flask>=2.0.0
gunicorn
```

## Environment Variables

### Required
- `OPENAI_API_KEY` - OpenAI API key for question generation
- `PIPELINE_PASSWORD` - Web interface password (default: "changeme")
- `FLASK_SECRET_KEY` - Flask session secret (default: "dev-secret")

### Optional
- `MODEL` - OpenAI model to use (default: "gpt-4.1")
- `NUM_QUESTIONS` - Default number of questions (default: 6)
- `VERBOSITY` - Logging level (0=ERROR, 1=INFO, 2=DEBUG)

## Google Cloud Setup

### Required APIs
1. **Google Forms API** - For creating forms
2. **Google Drive API** - For file management and sharing

### Authentication Setup
1. **OAuth Client ID** (Desktop Application)
   - Download `client_secret.json` to project root
   - Used for user-based authentication

2. **Service Account** (Optional)
   - For server-to-server authentication
   - Download service account JSON key

## Deployment Architecture

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env  # Edit with your API keys

# Run locally
python start_web_interface.py
# OR
python server/app.py
```

### Cloud Run Deployment
```bash
# Deploy to Cloud Run
gcloud run deploy medtrain \
  --source . \
  --set-secrets /secrets/token.pkl=medtrain-token-pkl:latest \
  --port 8080 \
  --allow-unauthenticated
```

### Secret Management
- **Local**: Uses `token.pkl` and `client_secret.json`
- **Cloud Run**: Mounts secrets at `/secrets/token.pkl`
- **Security**: All secrets excluded from Git via `.gitignore`

## API Usage

### Main Pipeline Endpoint
```bash
POST /api/pipeline
Content-Type: multipart/form-data

Parameters:
- pdf: PDF file (required)
- num_questions: Number of questions (default: 6)
- language: Language code (en/he/pl, default: en)
- model: OpenAI model (default: gpt-4.1)
```

### Response Format
```json
{
  "success": true,
  "mcqs_json_path": "/tmp/mcqs.json",
  "form_edit_url": "https://docs.google.com/forms/d/...",
  "pdf_filename": "document.pdf",
  "num_questions": 6,
  "language": "en",
  "model": "gpt-4.1"
}
```

## Security Features

1. **Authentication**: Password-protected web interface
2. **Secret Management**: No secrets in code or Git
3. **Environment Isolation**: Separate configs for dev/prod
4. **Error Handling**: Graceful failure without exposing internals
5. **Input Validation**: File type and parameter validation

## Monitoring & Health Checks

- **`/health`** - Detailed health status
- **`/healthz`** - Cloud Run standard health check
- **Logging**: Comprehensive logging with configurable levels
- **Error Tracking**: Detailed error messages for debugging

## Development Workflow

1. **Local Development**: Use `start_web_interface.py` for full setup
2. **Testing**: Upload PDFs via web interface
3. **Debugging**: Set `VERBOSITY=2` for detailed logs
4. **Deployment**: Use `gcloud run deploy` with secret mounting

## Troubleshooting

### Common Issues
1. **Missing Token**: App starts but Google Forms creation fails
2. **API Limits**: OpenAI rate limiting for large documents
3. **File Permissions**: Ensure proper Cloud Run secret mounting
4. **Memory Limits**: Large PDFs may require increased Cloud Run memory

### Debug Mode
```bash
# Enable detailed logging
export VERBOSITY=2
export GOOGLE_FORMS_SHOW_DETAILED_LOGS=true
export GOOGLE_FORMS_SHOW_AUTH_LOGS=true
```

## Production Considerations

1. **Scaling**: Gunicorn with 2 workers (configurable)
2. **Timeouts**: 180-second timeout for long PDF processing
3. **Memory**: May need increased memory for large PDFs
4. **Secrets**: Use Google Secret Manager for production
5. **Monitoring**: Set up Cloud Run monitoring and alerting

This project is production-ready for Cloud Run deployment with proper secret management and scalable architecture.
