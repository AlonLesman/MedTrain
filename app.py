#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Flask server for PDF → MCQs → Google Form pipeline
"""

from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string, g
import os
import tempfile
import logging
import json
import traceback
from dotenv import load_dotenv, find_dotenv

# For Google Drive API sharing
from googleapiclient.discovery import build

# Import our existing pipeline components
from pdf_to_questions import generate_mcqs_to_file
from create_form_from_json import create_form_from_json
from token_utils import save_env_to_json

load_dotenv('/secrets/.env')

app = Flask(__name__)

# Set secret key for sessions
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret')

# Import new validation functions
from pdf_to_questions import normalize_language, clamp_num_questions, resolve_token_path

# Helper functions for request parameter validation
def _get_language():
    """Extract and normalize language parameter from request."""
    raw = (request.form.get('language') or request.args.get('language') or (request.json.get('language') if request.is_json else None))
    return normalize_language(raw)

def _get_num_questions(default=6):
    """Extract and validate number of questions parameter from request."""
    raw = (request.form.get('num_questions') or request.args.get('num_questions') or (request.json.get('num_questions') if request.is_json else None))
    return clamp_num_questions(raw, default=default)

# HTML Templates
LOGIN_TEMPLATE = '''
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>Login - PDF → MCQs → Google Form</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 400px;
            margin: 100px auto;
            padding: 20px;
            line-height: 1.6;
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 16px;
            box-sizing: border-box;
        }
        button {
            width: 100%;
            background: #007acc;
            color: white;
            border: none;
            padding: 12px;
            border-radius: 4px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #005a9e;
        }
        .error {
            color: #d32f2f;
            background: #ffebee;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 20px;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1>🔐 Login Required</h1>
    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}
    <form method="POST">
        <div class="form-group">
            <label for="password">Password:</label>
            <input type="password" id="password" name="password" required autofocus>
        </div>
        <button type="submit">Login</button>
    </form>
</body>
</html>
'''

FORM_TEMPLATE = '''
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>PDF → MCQs → Google Form</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #007acc;
            padding-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logout-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            text-decoration: none;
            font-size: 14px;
        }
        .logout-btn:hover {
            background: #c82333;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
        }
        input, select {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        input[type="file"] {
            padding: 4px;
        }
        button {
            background: #007acc;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 4px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #005a9e;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        #status {
            background: #f5f5f5;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin-top: 20px;
            white-space: pre-wrap;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 12px;
            max-height: 400px;
            overflow-y: auto;
        }
        .error {
            color: #d32f2f;
        }
        .success {
            color: #2e7d32;
        }
        .loading {
            color: #1976d2;
        }
    </style>
</head>
<body>
    <h1>
        PDF → MCQs → Google Form
        <a href="/logout" class="logout-btn">Logout</a>
    </h1>
    
    <form id="f">
        <div class="form-group">
            <label for="pdf">PDF File:</label>
            <input id="pdf" type="file" accept="application/pdf" required>
        </div>
        
        <div class="form-group">
            <label for="count">Number of Questions:</label>
            <input id="count" type="number" min="1" max="20" value="6">
        </div>
        
        <div class="form-group">
            <label for="lang">Language:</label>
            <select id="lang">
                <option value="en" selected>English</option>
                <option value="he">Hebrew</option>
                <option value="pl">Polish</option>
            </select>
        </div>
        
        <div class="form-group">
            <label for="share_with">Share with (email, optional):</label>
            <input id="share_with" type="email" placeholder="you@example.com">
        </div>
        
        <button type="submit" id="submitBtn">Generate Google Form</button>
    </form>
    
    <pre id="status">Ready to generate. Select a PDF file and click Generate.</pre>

    <script>
        const form = document.getElementById('f');
        const status = document.getElementById('status');
        const submitBtn = document.getElementById('submitBtn');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Disable button and show loading
            submitBtn.disabled = true;
            submitBtn.textContent = 'Generating...';
            status.textContent = 'Working… Please wait, this may take a few minutes.';
            status.className = 'loading';
            
            const fd = new FormData();
            const pdf = document.getElementById('pdf').files[0];
            const count = document.getElementById('count').value;
            const lang = document.getElementById('lang').value;
            const shareWith = (document.getElementById('share_with').value || '').trim();
            
            fd.append('pdf', pdf);
            fd.append('num_questions', count);
            fd.append('language', lang);
            fd.append('share_with', shareWith);

            try {
                const res = await fetch('/api/pipeline', { 
                    method: 'POST', 
                    body: fd 
                });
                
                const data = await res.json();
                
                if (data.success) {
                    status.textContent = JSON.stringify(data, null, 2);
                    status.className = 'success';
                    
                    // Show form URL prominently
                    if (data.form_edit_url) {
                        const urlDiv = document.createElement('div');
                        urlDiv.innerHTML = `<br><strong>🎉 Google Form Created!</strong><br><a href="${data.form_edit_url}" target="_blank">${data.form_edit_url}</a>`;
                        status.appendChild(urlDiv);
                    }
                } else {
                    status.textContent = 'Error: ' + data.error;
                    status.className = 'error';
                }
            } catch (err) {
                status.textContent = 'Network Error: ' + err.message;
                status.className = 'error';
            } finally {
                // Re-enable button
                submitBtn.disabled = false;
                submitBtn.textContent = 'Generate Google Form';
            }
        });
    </script>
</body>
</html>
'''

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Authentication helpers
def is_logged_in():
    """Check if user is logged in"""
    return session.get('logged_in', False)

def require_auth(f):
    """Decorator to require authentication"""
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return jsonify({"success": False, "error": "Authentication required"}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        correct_password = os.getenv('PIPELINE_PASSWORD', 'changeme')
        
        if password == correct_password:
            session['logged_in'] = True
            logger.info("User logged in successfully")
            return redirect('/form')
        else:
            logger.warning("Invalid login attempt")
            return render_template_string(LOGIN_TEMPLATE, error="Invalid password")
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    logger.info("User logged out")
    return redirect(url_for('login'))

@app.route('/form')
def form():
    """Main form page - requires authentication"""
    if not is_logged_in():
        return redirect(url_for('login'))
    return render_template_string(FORM_TEMPLATE)

@app.route('/api/pipeline', methods=['POST'])
@require_auth
def pipeline():
    """Handle PDF → MCQs → Google Form pipeline"""
    FORMS_AUTH_METHOD = os.getenv('FORMS_AUTH_METHOD', 'oauth')
    if FORMS_AUTH_METHOD == 'sa':
        save_env_to_json('CLIENT_SECRET', 'client_secret.json')
    try:
        # Validate required fields
        if 'pdf' not in request.files:
            return jsonify({"success": False, "error": "Missing file 'pdf'"}), 400
        
        f = request.files['pdf']
        if f.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        # Store filename early to avoid issues later
        pdf_filename = f.filename
        
        # Get form parameters with validation
        language = _get_language()
        num_questions = _get_num_questions()
        model = request.form.get('model', 'gpt-4.1').strip()
        
        # Debug breadcrumbs
        print(json.dumps({
            "evt": "pipeline.inputs",
            "req_id": getattr(g, "req_id", None),
            "language": language,
            "num_questions": num_questions,
            "model": model,
            "token_exists": os.path.exists("/secrets/token.pkl"),
            "key_present": bool(os.getenv("OPENAI_API_KEY")),
        }), flush=True)
        
        logger.info(f"Starting pipeline: PDF={pdf_filename}, questions={num_questions}, language={language}")
        
        # Create temporary directory for processing (use /tmp for Cloud Run)
        tmpdir = tempfile.mkdtemp(prefix="medtrain_", dir="/tmp")
        pdf_path = os.path.join(tmpdir, pdf_filename)
        
        try:
            # Save uploaded PDF
            f.save(pdf_path)
            logger.info(f"PDF saved to: {pdf_path}")
            
            # Step 1: PDF → MCQs JSON
            logger.info("Step 1: Generating MCQs from PDF...")
            mcqs_json_path = generate_mcqs_to_file(
                pdf_path=pdf_path, 
                output_dir=tmpdir,
                model=model, 
                num_questions=num_questions,
                language=language
            )
            logger.info(f"MCQs JSON generated: {mcqs_json_path}")
            
            # Safety check: Ensure we don't exceed the requested number of questions
            try:
                with open(mcqs_json_path, 'r', encoding='utf-8') as f:
                    mcqs_data = json.load(f)
                
                questions = mcqs_data.get('questions', [])
                logger.info(f"📊 Found {len(questions)} questions in generated JSON")
                
                if len(questions) == 0:
                    logger.error(f"❌ No questions found in generated JSON!")
                    logger.error(f"📄 JSON content: {json.dumps(mcqs_data, indent=2)[:500]}...")
                    return jsonify({
                        "success": False,
                        "error": "No questions generated from PDF. Please check the PDF content and try again.",
                        "req_id": getattr(g, "req_id", None)
                    }), 400
                
                if len(questions) > num_questions:
                    logger.warning(f"⚠️ Generated {len(questions)} questions, truncating to {num_questions}")
                    mcqs_data['questions'] = questions[:num_questions]
                    
                    # Save the truncated version
                    with open(mcqs_json_path, 'w', encoding='utf-8') as f:
                        json.dump(mcqs_data, f, ensure_ascii=False, indent=2)
                        
            except Exception as e:
                logger.error(f"❌ Could not validate question count: {e}")
                logger.error(f"📄 Validation error traceback: {traceback.format_exc()}")
            
            logger.info(f"Requested language: {language}")
            
            # Step 2: JSON → Google Form
            logger.info("Step 2: Creating Google Form from MCQs JSON...")
            try:
                share_with = (request.form.get('share_with') or '').strip()
                if not share_with:
                    share_with = (os.getenv('SHARE_WITH') or '').strip()
                form_edit_url = create_form_from_json(
                    json_path=mcqs_json_path,
                    auth_method=FORMS_AUTH_METHOD,
                    sa_file=os.getenv('SA_FILE'),
                    share_with=share_with if share_with else None
                )
                if form_edit_url:
                    logger.info(f"✅ Google Form created successfully: {form_edit_url}")
                else:
                    logger.error(f"❌ Google Form creation failed: No URL returned")
            except Exception as e:
                logger.error(f"❌ Google Form creation failed with exception: {e}")
                logger.error(f"📄 Google Form error traceback: {traceback.format_exc()}")
                form_edit_url = None

            # Step 3: Share Google Form if requested
            share_success = None
            drive_share_error = None
            drive_response = None
            file_id = None
            if form_edit_url and share_with:
                # Try to extract the file ID from the form_edit_url
                import re
                m = re.search(r'/d/([a-zA-Z0-9_-]+)', form_edit_url)
                if m:
                    file_id = m.group(1)
                    logger.info(f"Extracted Google Form file ID: {file_id}")
                else:
                    logger.error(f"Could not extract file ID from form_edit_url: {form_edit_url}")
                if file_id:
                    try:
                        # Reuse credentials from the Forms flow if possible
                        creds = None
                        if FORMS_AUTH_METHOD == 'sa':
                            # Use service account credentials
                            from google.oauth2 import service_account
                            sa_file = os.getenv('SA_FILE') or 'client_secret.json'
                            creds = service_account.Credentials.from_service_account_file(
                                sa_file,
                                scopes=[
                                    'https://www.googleapis.com/auth/drive',
                                    'https://www.googleapis.com/auth/forms.body',
                                    'https://www.googleapis.com/auth/forms.responses.readonly'
                                ]
                            )
                        else:
                            # Use pickled OAuth user credentials (token.pkl)
                            import pickle
                            token_path = os.getenv('TOKEN_PATH') or '/secrets/token.pkl'
                            with open(token_path, 'rb') as token:
                                creds = pickle.load(token)
                        drive_service = build('drive', 'v3', credentials=creds)
                        permission = {
                            'type': 'user',
                            'role': 'writer',
                            'emailAddress': share_with
                        }
                        drive_response = drive_service.permissions().create(
                            fileId=file_id,
                            body=permission,
                            sendNotificationEmail=False
                        ).execute()
                        import json as _jsonmod
                        logger.info(f"Drive API response: {_jsonmod.dumps(drive_response, indent=2)}")
                        logger.info(f"✅ Shared Google Form with {share_with} via Drive API")
                        share_success = True
                    except Exception as e:
                        logger.error(f"❌ Failed to share Google Form with {share_with}: {e}")
                        logger.error(f"Drive API error traceback: {traceback.format_exc()}")
                        share_success = False
                        drive_share_error = str(e)
            
            # Return success response
            response_data = {
                "success": True,
                "mcqs_json_path": mcqs_json_path,
                "form_edit_url": form_edit_url,
                "pdf_filename": pdf_filename,
                "num_questions": num_questions,
                "language": language,
                "model": model,
                "shared_with": share_with if share_with else None,
                "share_success": share_success,
                "drive_share_error": drive_share_error
            }

            logger.info("Pipeline completed successfully")
            return jsonify(response_data)
            
        except Exception as e:
            logger.error(f"Pipeline error: {str(e)}")
            return jsonify({
                "success": False, 
                "error": f"Pipeline failed: {str(e)}"
            }), 500
            
        finally:
            # Clean up temporary files (optional - you might want to keep them for debugging)
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                logger.info("Temporary files cleaned up")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary files: {e}")
                
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({
            "success": False, 
            "error": f"Server error: {str(e)}"
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "PDF to Google Form Pipeline"})

@app.route('/healthz', methods=['GET'])
def healthz():
    """Health check endpoint (Cloud Run standard)"""
    return {"status": "ok"}

@app.route('/web/<path:filename>')
def web_files(filename):
    """Serve web interface files"""
    web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web')
    return send_from_directory(web_dir, filename)

@app.route('/', methods=['GET'])
def index():
    """Redirect to login or form based on authentication status"""
    if is_logged_in():
        return redirect(url_for('form'))
    else:
        return redirect(url_for('login'))

if __name__ == "__main__":
    # Get port from environment variable (Cloud Run) or default to 5050 for local dev
    port = int(os.getenv('PORT', 5050))
    host = os.getenv('HOST', '127.0.0.1')
    
    logger.info("Starting Flask server...")
    logger.info(f"Open http://{host}:{port} in your browser")
    logger.info("Login with password: changeme (or set PIPELINE_PASSWORD in .env)")
    app.run(host=host, port=port, debug=True)
