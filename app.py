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
import io

import requests
import hmac
import hashlib
from urllib.parse import urlparse

# Optional: Twilio (for WhatsApp via Twilio)
try:
    from twilio.request_validator import RequestValidator
    from twilio.rest import Client as TwilioClient
except Exception:
    RequestValidator = None
    TwilioClient = None

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
    <title>Login - PDF → MCQs Google Form Generator</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 400px;
            margin: 100px auto;
            padding: 20px;
            line-height: 1.6;
            background: url('/BG.webp') no-repeat center center fixed;
            background-size: cover;
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
    <title>PDF → MCQs Google Form Generator</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
            background: url('/BG.webp') no-repeat center center fixed;
            background-size: cover;
        }
        .overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(255, 255, 255, 0.6); /* light translucent layer */
            z-index: 0;
        }
        .form-container {
            position: relative;
            z-index: 1;
            background: rgba(255, 255, 255, 0.85);
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            max-width: 700px;
            margin: 50px auto;
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
            position: absolute;
            top: 20px;
            right: 20px;
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
            box-sizing: border-box;
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
        .actions {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-top: 16px;
        }
        /* Ensure both buttons have identical size */
        button, .link-btn {
            padding: 12px 24px;
            font-size: 16px;
            border-radius: 4px;
            line-height: 1.2;
            min-height: 44px;
            box-sizing: border-box;
        }
        .link-btn {
            display: inline-block;
            background: #6c757d;
            color: #fff;
            text-decoration: none;
            /* sizing handled by shared rule above */
        }
        .link-btn:hover {
            background: #5a6268;
        }
    </style>
</head>
<body>
    <div class="overlay"></div>
    <div class="form-container">
        <a href="/logout" class="logout-btn">Logout</a>
        <h2>
            Takeaways Doc PDF → MCQs Google Form Generator
        </h2>
        
        <form id="f">
            <div class="form-group">
                <label for="pdf">Upload Takeaways Document PDF:</label>
                <input id="pdf" type="file" accept="application/pdf" required>
                <small style="color:#d32f2f; display:block; margin-top:4px; font-weight:500;">⚠️ Do not upload any confidential information.</small>
            </div>
            
            <div class="form-group">
                <label for="count">Choose the number of questions you want to generate:</label>
                <input id="count" type="number" min="1" max="20" value="6">
            </div>
            
            <div class="form-group">
                <label for="lang">Choose the language of the questions:</label>
                <select id="lang">
                    <option value="en" selected>English</option>
                    <option value="he">Hebrew</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="share_with">In order to get editor access to the Google Form, please enter your email here:</label>
                <input id="share_with" type="email" placeholder="you@example.com">
            </div>
            
            <button type="submit" id="submitBtn">Generate Google Form</button>
        </form>
        
        <pre id="status">Ready to generate. Select a PDF file and click Generate.</pre>

        <hr style="margin:24px 0; border:none; border-top:1px solid #ddd;" />
        <div class="form-group">
            <label for="rotate_link">Paste the current quiz Google Form link (response link, not the edit link):</label>
            <input id="rotate_link" type="url" placeholder="https://docs.google.com/forms/d/e/…/viewform">
            <small>Paste the Form response link, not the edit link.</small>
        </div>
        <div class="actions">
            <button type="button" onclick="setCurrentFormLink()">Set as current quiz</button>
            <a href="/current-responses" target="_blank" class="link-btn">Latest quiz responses</a>
        </div>
    </div>

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

        // Admin: Set current quiz link
        async function setCurrentFormLink() {
            const link = (document.getElementById('rotate_link').value || '').trim();
            if (!link) {
                status.textContent = 'Please paste a Google Form link.';
                status.className = 'error';
                return;
            }
            try {
                status.textContent = 'Updating current quiz link…';
                status.className = 'loading';
                const res = await fetch('/api/set_current_form', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ form_url: link })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    status.textContent = '✅ Current quiz link updated: ' + data.active_form_url;
                    status.className = 'success';
                    const respDiv = document.createElement('div');
                    respDiv.innerHTML = `<br><strong>Responses link:</strong> <a href="/current-responses" target="_blank">Open latest responses</a>`;
                    status.appendChild(respDiv);
                } else {
                    status.textContent = 'Error updating current quiz link: ' + (data.error || res.statusText);
                    status.className = 'error';
                }
            } catch (err) {
                status.textContent = 'Network Error: ' + err.message;
                status.className = 'error';
            }
        }
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

# -----------------------------
# WhatsApp Bot Helpers
# -----------------------------

def _parse_allowlist() -> set:
    raw = (os.getenv('WHATSAPP_ALLOWLIST') or '').strip()
    if not raw:
        return set()
    # Accept formats like: "+972501234567,+972..." or "whatsapp:+972..."
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    return set(parts)


def _is_allowed_sender(sender: str) -> bool:
    allow = _parse_allowlist()
    if not allow:
        # If no allowlist is configured, default-deny for safety
        return False
    if sender in allow:
        return True
    # Normalize Twilio WhatsApp sender format: "whatsapp:+972..."
    if sender.startswith('whatsapp:'):
        s2 = sender.replace('whatsapp:', '', 1)
        return s2 in allow
    return False


def _download_to_tmp(url: str, dst_path: str, headers: dict | None = None) -> None:
    headers = headers or {}
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dst_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def _run_pipeline_on_pdf_path(
    pdf_path: str,
    *,
    num_questions: int,
    language: str,
    model: str,
    share_with: str | None,
    tmpdir: str,
) -> dict:
    """Run the existing pipeline given a PDF on disk.

    Returns the same structure you return from /api/pipeline (where possible).
    """
    FORMS_AUTH_METHOD = os.getenv('FORMS_AUTH_METHOD', 'oauth')
    if FORMS_AUTH_METHOD == 'sa':
        # ensure service account json exists if you use that mode
        save_env_to_json('CLIENT_SECRET', 'client_secret.json')

    logger.info(f"Starting pipeline (bot/web): PDF={os.path.basename(pdf_path)}, questions={num_questions}, language={language}")

    # Step 1: PDF → MCQs JSON
    mcqs_json_path = generate_mcqs_to_file(
        pdf_path=pdf_path,
        output_dir=tmpdir,
        model=model,
        num_questions=num_questions,
        language=language,
    )

    # Safety check / truncation
    try:
        with open(mcqs_json_path, 'r', encoding='utf-8') as f:
            mcqs_data = json.load(f)
        questions = mcqs_data.get('questions', [])
        if not questions:
            raise ValueError('No questions generated from PDF')
        if len(questions) > num_questions:
            mcqs_data['questions'] = questions[:num_questions]
            with open(mcqs_json_path, 'w', encoding='utf-8') as f:
                json.dump(mcqs_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Question validation failed: {e}")

    # Step 2: JSON → Google Form
    form_edit_url = create_form_from_json(
        json_path=mcqs_json_path,
        auth_method=FORMS_AUTH_METHOD,
        sa_file=os.getenv('SA_FILE'),
        share_with=share_with if share_with else None,
    )

    # Step 3: (optional) share via Drive permissions (same logic as /api/pipeline)
    share_success = None
    drive_share_error = None
    if form_edit_url and share_with:
        import re
        m = re.search(r'/d/([a-zA-Z0-9_-]+)', form_edit_url)
        file_id = m.group(1) if m else None
        if file_id:
            try:
                creds = None
                if FORMS_AUTH_METHOD == 'sa':
                    from google.oauth2 import service_account
                    sa_file = os.getenv('SA_FILE') or 'client_secret.json'
                    creds = service_account.Credentials.from_service_account_file(
                        sa_file,
                        scopes=[
                            'https://www.googleapis.com/auth/drive',
                            'https://www.googleapis.com/auth/forms.body',
                            'https://www.googleapis.com/auth/forms.responses.readonly',
                        ],
                    )
                else:
                    import pickle
                    token_path = os.getenv('TOKEN_PATH') or '/secrets/token.pkl'
                    with open(token_path, 'rb') as token:
                        creds = pickle.load(token)

                drive_service = build('drive', 'v3', credentials=creds)
                permission = {'type': 'user', 'role': 'writer', 'emailAddress': share_with}
                drive_service.permissions().create(
                    fileId=file_id,
                    body=permission,
                    sendNotificationEmail=False,
                ).execute()
                share_success = True
            except Exception as e:
                share_success = False
                drive_share_error = str(e)

    return {
        'success': True,
        'mcqs_json_path': mcqs_json_path,
        'form_edit_url': form_edit_url,
        'pdf_filename': os.path.basename(pdf_path),
        'num_questions': num_questions,
        'language': language,
        'model': model,
        'shared_with': share_with if share_with else None,
        'share_success': share_success,
        'drive_share_error': drive_share_error,
    }


def _twilio_send_message(to_number: str, body: str) -> None:
    """Send a WhatsApp message via Twilio."""
    if TwilioClient is None:
        raise RuntimeError('Twilio SDK not installed. pip install twilio')
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_WHATSAPP_FROM')  # e.g. "whatsapp:+14155238886" or your approved number
    if not (sid and token and from_number):
        raise RuntimeError('Missing TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM env vars')
    client = TwilioClient(sid, token)
    client.messages.create(from_=from_number, to=to_number, body=body)


def _twilio_validate_request(req) -> bool:
    """Validate Twilio webhook signature (recommended for production)."""
    if RequestValidator is None:
        # If SDK missing, do not silently accept in production.
        return False
    auth_token = os.getenv('TWILIO_AUTH_TOKEN') or ''
    signature = req.headers.get('X-Twilio-Signature', '')
    # Build the full URL Twilio used (Cloud Run behind proxy may need X-Forwarded-Proto)
    proto = req.headers.get('X-Forwarded-Proto', req.scheme)
    host = req.headers.get('X-Forwarded-Host', req.host)
    url = f"{proto}://{host}{req.path}"
    validator = RequestValidator(auth_token)
    return validator.validate(url, req.form.to_dict(flat=True), signature)

# Atomic JSON writer for current form link persistence. We do NOT use env vars
# for this because environment variables are read-only at runtime on many
# platforms (e.g., Cloud Run). We persist the active link in a JSON file.
def _atomic_write_json(target_path: str, data: dict):
    directory = os.path.dirname(target_path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_current_form_", dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as tmpf:
            json.dump(data, tmpf, ensure_ascii=False, indent=2)
            tmpf.flush()
            os.fsync(tmpf.fileno())
        os.replace(tmp_path, target_path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise

def _resolve_current_form_json_path() -> str:
    """Resolve a writable path for current_form.json with no env vars required.
    Order:
      1) /secrets if it exists and is writable
      2) /tmp (Cloud Run writable tmpfs)
      3) Project directory (local dev)
    """
    secrets_dir = '/secrets'
    try:
        if os.path.isdir(secrets_dir) and os.access(secrets_dir, os.W_OK):
            return os.path.join(secrets_dir, 'current_form.json')
    except Exception:
        pass
    # Prefer /tmp for Cloud Run runtime writes
    try:
        if os.path.isdir('/tmp') and os.access('/tmp', os.W_OK):
            return os.path.join('/tmp', 'current_form.json')
    except Exception:
        pass
    # Fallback to project directory for local dev
    project_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(project_dir, 'current_form.json')

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
    """Handle PDF → MCQs Google Form Generator pipeline"""
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

            # Run core pipeline
            share_with = (request.form.get('share_with') or '').strip()
            if not share_with:
                share_with = (os.getenv('SHARE_WITH') or '').strip()

            result = _run_pipeline_on_pdf_path(
                pdf_path,
                num_questions=num_questions,
                language=language,
                model=model,
                share_with=share_with if share_with else None,
                tmpdir=tmpdir,
            )

            logger.info("Pipeline completed successfully")
            return jsonify(result)

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

@app.route('/api/set_current_form', methods=['POST'])
@require_auth
def set_current_form():
    """Set the current active Google Form (response link) atomically in JSON.
    Persists to /secrets/current_form.json under key "active_form_url".
    """
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Expected JSON body"}), 400
        payload = request.get_json(silent=True) or {}
        form_url = (payload.get('form_url') or '').strip()
        if not form_url:
            return jsonify({"success": False, "error": "form_url is required"}), 400

        # Compute responses URL based on the provided form_url
        if form_url.endswith("/viewform"):
            responses_url = form_url.replace("/viewform", "/edit#responses")
        else:
            responses_url = form_url + "#responses"

        target_path = _resolve_current_form_json_path()
        _atomic_write_json(target_path, {
            "active_form_url": form_url,
            "active_responses_url": responses_url
        })
        return jsonify({
            "success": True,
            "active_form_url": form_url,
            "active_responses_url": responses_url
        })
    except Exception as e:
        logger.error(f"set_current_form error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/current-form', methods=['GET'])
def current_form_redirect():
    """Redirect to the currently active Google Form. 404 if not set."""
    try:
        target_path = _resolve_current_form_json_path()
        if not os.path.exists(target_path):
            return jsonify({"success": False, "error": "No active form set"}), 404
        with open(target_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        url = (data.get('active_form_url') or '').strip()
        if not url:
            return jsonify({"success": False, "error": "No active form set"}), 404
        return redirect(url)
    except Exception as e:
        logger.error(f"current_form_redirect error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/current-responses', methods=['GET'])
def current_responses_redirect():
    """Redirect to the current active form's responses page."""
    try:
        target_path = _resolve_current_form_json_path()
        if not os.path.exists(target_path):
            return jsonify({"success": False, "error": "No active form set"}), 404
        with open(target_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        url = (data.get('active_responses_url') or '').strip()
        if not url:
            return jsonify({"success": False, "error": "No active responses link set"}), 404
        return redirect(url)
    except Exception as e:
        logger.error(f"current_responses_redirect error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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

@app.route('/BG.webp')
def bg_image():
    """Serve the background image from project root."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(root_dir, 'BG.webp')

if __name__ == "__main__":
    # Get port from environment variable (Cloud Run) or default to 5050 for local dev
    port = int(os.getenv('PORT', 5050))
    host = os.getenv('HOST', '127.0.0.1')
    
    logger.info("Starting Flask server...")
    logger.info(f"Open http://{host}:{port} in your browser")
    logger.info("Login with password: changeme (or set PIPELINE_PASSWORD in .env)")
    app.run(host=host, port=port, debug=True)

@app.route('/whatsapp/twilio', methods=['POST'])
def whatsapp_twilio_inbound():
    """Twilio → WhatsApp inbound webhook.

    Usage:
      - Send a PDF as media to generate a new quiz form.
      - Send: "set <google-form-response-link>" to update the current quiz link (admin action).

    Security:
      - Requires WHATSAPP_ALLOWLIST to contain the sender number.
      - Validates X-Twilio-Signature when Twilio SDK is available.
    """
    # Signature validation (recommended). If SDK missing, reject.
    if not _twilio_validate_request(request):
        return ("invalid signature", 403)

    sender = (request.form.get('From') or '').strip()  # e.g. "whatsapp:+972..."
    body = (request.form.get('Body') or '').strip()
    num_media = int(request.form.get('NumMedia') or '0')

    if not _is_allowed_sender(sender):
        try:
            _twilio_send_message(sender, "Sorry, this number is not authorized to use this bot.")
        except Exception:
            pass
        return ("forbidden", 403)

    # Admin command: set current form link
    if body.lower().startswith('set '):
        link = body[4:].strip()
        if not link:
            _twilio_send_message(sender, "Please send: set <Google Form response link>")
            return ("ok", 200)
        try:
            # Reuse existing persistence helpers
            if link.endswith('/viewform'):
                responses_url = link.replace('/viewform', '/edit#responses')
            else:
                responses_url = link + '#responses'
            target_path = _resolve_current_form_json_path()
            _atomic_write_json(target_path, {
                'active_form_url': link,
                'active_responses_url': responses_url,
            })
            _twilio_send_message(sender, f"✅ Current quiz link updated. Responses: {request.url_root.rstrip('/')}/current-responses")
        except Exception as e:
            _twilio_send_message(sender, f"❌ Failed to update: {e}")
        return ("ok", 200)

    # PDF workflow
    if num_media < 1:
        _twilio_send_message(sender, "Send me a PDF and I'll generate a Google Form quiz. Optionally add text like: q=8 lang=en")
        return ("ok", 200)

    media_url = (request.form.get('MediaUrl0') or '').strip()
    media_type = (request.form.get('MediaContentType0') or '').strip()

    if 'pdf' not in media_type.lower() and not media_url.lower().endswith('.pdf'):
        _twilio_send_message(sender, "Please attach a PDF file.")
        return ("ok", 200)

    # Parse optional parameters from body (very lightweight): q=<n> lang=<en|he>
    q = None
    lang = None
    for token in body.split():
        if token.lower().startswith('q='):
            q = token.split('=', 1)[1]
        if token.lower().startswith('lang='):
            lang = token.split('=', 1)[1]

    language = normalize_language(lang)
    num_questions = clamp_num_questions(q, default=6)
    model = (os.getenv('WHATSAPP_MODEL') or 'gpt-4.1').strip()
    share_with = (os.getenv('WHATSAPP_SHARE_WITH') or os.getenv('SHARE_WITH') or '').strip() or None

    _twilio_send_message(sender, "⏳ Got it. Processing your PDF now…")

    tmpdir = tempfile.mkdtemp(prefix='medtrain_wa_', dir='/tmp')
    pdf_path = os.path.join(tmpdir, 'input.pdf')

    try:
        # Twilio media URLs require basic auth (Account SID/Auth Token)
        sid = os.getenv('TWILIO_ACCOUNT_SID')
        token = os.getenv('TWILIO_AUTH_TOKEN')
        if not (sid and token):
            raise RuntimeError('Missing TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN for media download')

        with requests.get(media_url, auth=(sid, token), stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(pdf_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        result = _run_pipeline_on_pdf_path(
            pdf_path,
            num_questions=num_questions,
            language=language,
            model=model,
            share_with=share_with,
            tmpdir=tmpdir,
        )

        form_url = (result.get('form_edit_url') or '').strip()
        if form_url:
            _twilio_send_message(sender, f"✅ Done! Here is your Google Form (edit link): {form_url}")
        else:
            _twilio_send_message(sender, "❌ Form creation failed (no URL returned). Check logs.")

    except Exception as e:
        logger.error(f"WhatsApp Twilio pipeline error: {e}")
        logger.error(traceback.format_exc())
        try:
            _twilio_send_message(sender, f"❌ Failed: {e}")
        except Exception:
            pass

    finally:
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception:
            pass

    return ("ok", 200)