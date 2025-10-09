#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Startup script for the PDF → MCQs → Google Form web interface

Local dev only. Cloud Run uses Gunicorn per Procfile.
"""

import os
import sys
import webbrowser
from pathlib import Path

def check_requirements():
    """Check if all required packages are installed"""
    required_packages = [
        'flask', 'pdfplumber', 'openai', 'googleapiclient', 
        'google_auth_oauthlib', 'dotenv'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print("❌ Missing required packages:")
        for package in missing:
            print(f"   - {package}")
        print("\nInstall them with:")
        print("   pip install -r requirements.txt")
        return False
    
    return True

def check_env_file():
    """Check if .env file exists and has required variables"""
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  .env file not found. Creating template...")
        with open(".env", "w") as f:
            f.write("# PDF → MCQs → Google Form Pipeline Configuration\n")
            f.write("OPENAI_API_KEY=your_openai_api_key_here\n")
            f.write("MODEL=gpt-4.1\n")
            f.write("NUM_QUESTIONS=6\n")
            f.write("PIPELINE_PASSWORD=changeme\n")
            f.write("FLASK_SECRET_KEY=dev-secret\n")
        print("✅ Created .env template. Please edit it with your API key.")
        return False
    
    # Check if OPENAI_API_KEY is set
    with open(".env", "r") as f:
        content = f.read()
        if "your_openai_api_key_here" in content:
            print("⚠️  Please set your OPENAI_API_KEY in the .env file")
            return False
    
    # Check if PIPELINE_PASSWORD is set (optional)
    if "PIPELINE_PASSWORD" not in content:
        print("ℹ️  PIPELINE_PASSWORD not set - using default 'changeme'")
        print("   Set PIPELINE_PASSWORD=your_secure_password in .env for security")
    
    return True

def check_google_oauth():
    """Check if Google OAuth is set up"""
    oauth_file = Path("client_secret.json")
    if not oauth_file.exists():
        print("⚠️  client_secret.json not found.")
        print("   To set up Google OAuth:")
        print("   1. Go to https://console.cloud.google.com/")
        print("   2. Create a project or select existing one")
        print("   3. Enable Google Forms API and Google Drive API")
        print("   4. Create OAuth Client ID (Desktop application)")
        print("   5. Download client_secret.json to this directory")
        return False
    
    return True

def main():
    """Main startup function"""
    print("🚀 Starting PDF → MCQs → Google Form Web Interface")
    print("=" * 60)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    print("✅ All required packages installed")
    
    # Check environment file
    if not check_env_file():
        print("Please configure your .env file and try again.")
        sys.exit(1)
    print("✅ Environment configuration found")
    
    # Check Google OAuth (warning only)
    if not check_google_oauth():
        print("⚠️  Google OAuth not set up - you'll need to set it up on first use")
    else:
        print("✅ Google OAuth configured")
    
    print("\n🎉 Starting Flask server...")
    print("📱 Web interface will open at: http://127.0.0.1:5050")
    print("🔐 Login with password: changeme (or set PIPELINE_PASSWORD in .env)")
    print("🛑 Press Ctrl+C to stop the server")
    print("=" * 60)
    
    # Start the Flask server
    try:
        from server.app import app
        # Open browser after a short delay
        import threading
        import time
        
        def open_browser():
            time.sleep(2)
            webbrowser.open("http://127.0.0.1:5050")
        
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        app.run(host="127.0.0.1", port=5050, debug=True)
        
    except KeyboardInterrupt:
        print("\n👋 Server stopped. Goodbye!")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
