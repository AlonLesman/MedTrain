#!/bin/bash
# Local development runner for MedTrain

set -e

echo "🏠 Starting MedTrain locally..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8 or higher."
    exit 1
fi

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate
# Install/update dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating template..."
    cat > .env << EOF
# PDF → MCQs → Google Form Pipeline Configuration
OPENAI_API_KEY=your_openai_api_key_here
MODEL=gpt-4.1
NUM_QUESTIONS=6
PIPELINE_PASSWORD=changeme
FLASK_SECRET_KEY=dev-secret
EOF
    echo "✅ Created .env template. Please edit it with your API key."
    echo "   Then run this script again."
    exit 1
fi

# Check if Google OAuth is set up
if [ ! -f "client_secret.json" ]; then
    echo "⚠️  client_secret.json not found."
    echo "   To set up Google OAuth:"
    echo "   1. Go to https://console.cloud.google.com/"
    echo "   2. Create a project or select existing one"
    echo "   3. Enable Google Forms API and Google Drive API"
    echo "   4. Create OAuth Client ID (Desktop application)"
    echo "   5. Download client_secret.json to this directory"
    echo ""
    echo "   For now, continuing without OAuth setup..."
fi

# Start the application
echo "🚀 Starting MedTrain web interface..."
echo "📱 Web interface will be available at: http://127.0.0.1:5050"
echo "🔐 Login with password: changeme (or set PIPELINE_PASSWORD in .env)"
echo "🛑 Press Ctrl+C to stop the server"
echo "=" * 60


python3 start_local_web_interface.py
