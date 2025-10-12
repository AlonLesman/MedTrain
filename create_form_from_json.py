#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Create a Google Form from an MCQ JSON file, supporting **both** OAuth (user) and
Service Account (server) authentication. Default is OAuth.

Usage:
  python create_form_from_json.py mcqs.json [--auth oauth|sa] [--sa-file path] [--share-with you@gmail.com]

Requirements:
  pip install google-api-python-client google-auth google-auth-oauthlib

Before first run (depending on auth mode):

OAuth (default, creates the Form under YOUR account):
  - In Google Cloud Console, enable: Google Forms API, Google Drive API.
  - Create OAuth Client ID (Desktop) and download `client_secret.json` next to this script.

Service Account (automation / servers):
  - In Google Cloud Console, enable: Google Forms API, Google Drive API.
  - Create a Service Account and download its JSON key (e.g. `service_account.json`).
  - (Optional) Use --share-with to add your user as an editor so you can see/manage the Form.

Environment Variables:
  VERBOSITY: 0=ERROR, 1=INFO (default), 2=DEBUG
  GOOGLE_FORMS_LOG_LEVEL: Override log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  GOOGLE_FORMS_SHOW_DETAILED_LOGS: true/false - Show detailed operation logs
  GOOGLE_FORMS_SHOW_AUTH_LOGS: true/false - Show authentication details
  GOOGLE_FORMS_SHOW_API_LOGS: true/false - Show API call details
"""

import sys
import os
import json
import pickle
import logging
from dotenv import load_dotenv, find_dotenv
from typing import Optional
from datetime import datetime

from googleapiclient.discovery import build
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from pdf_to_questions import generate_mcqs_to_file
from token_utils import get_token_path, load_google_token, get_client_secret_path

import traceback
import time


def setup_logging(verbosity: int = 1):
    """
    Set up logging configuration similar to PdfToQuestions.py
    
    Args:
        verbosity: 0=ERROR, 1=INFO, 2=DEBUG
    """
    # Check for environment variable override
    env_log_level = os.getenv("GOOGLE_FORMS_LOG_LEVEL", "").upper()
    if env_log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        level = level_map[env_log_level]
    else:
        # Use verbosity parameter
        level = logging.INFO if verbosity == 1 else logging.DEBUG if verbosity == 2 else logging.ERROR
    
    # Create logger
    logger = logging.getLogger("google_forms")
    logger.setLevel(level)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Create formatter (same format as PdfToQuestions.py)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def should_show_detailed_logs() -> bool:
    """Check if detailed logs should be shown."""
    return os.getenv("GOOGLE_FORMS_SHOW_DETAILED_LOGS", "false").lower() in ("true", "1", "yes")


def should_show_auth_logs() -> bool:
    """Check if authentication details should be logged."""
    return os.getenv("GOOGLE_FORMS_SHOW_AUTH_LOGS", "false").lower() in ("true", "1", "yes")


def should_show_api_logs() -> bool:
    """Check if API call details should be logged."""
    return os.getenv("GOOGLE_FORMS_SHOW_API_LOGS", "false").lower() in ("true", "1", "yes")


def log(msg: str, level: str = "info"):
    """
    Enhanced logging function that uses proper logging system
    
    Args:
        msg: Message to log
        level: Log level (debug, info, warning, error, critical)
    """
    logger = logging.getLogger("google_forms")
    
    # Map string levels to logging methods
    level_map = {
        "debug": logger.debug,
        "info": logger.info,
        "warning": logger.warning,
        "error": logger.error,
        "critical": logger.critical
    }
    
    log_func = level_map.get(level.lower(), logger.info)
    log_func(msg)
    
    # Also print to console for compatibility
    print(f"[mcq-forms] {msg}")
    try:
        sys.stdout.flush()
    except Exception:
        pass


# Scopes: Forms body (create/edit), Forms responses (read), Drive (sharing/visibility)
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/drive",
]

# Token and client secret paths are now managed by token_utils module


def get_oauth_creds():
    """Obtain/reuse OAuth user credentials with lazy loading and Cloud Run support."""
    log("Authentication mode: OAuth (user)", "info")
    
    if should_show_auth_logs():
        log("Starting OAuth authentication process", "debug")
    
    # Try to load existing token first (lazy loading)
    creds = None
    try:
        creds = load_google_token()
        log(f"Found existing token file: {get_token_path()} — loading…", "info")
        if should_show_auth_logs():
            log("Token loaded successfully from file", "debug")
    except FileNotFoundError as e:
        log(f"Token file not found: {e}", "info")
        creds = None
    except Exception as e:
        log(f"Failed to load token file: {e}", "warning")
        creds = None
    
    if not creds or not creds.valid:
        if creds and getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
            log("Token expired; attempting refresh…", "info")
            try:
                creds.refresh(Request())
                log("Token refresh successful", "info")
                if should_show_auth_logs():
                    log("Refreshed token is valid", "debug")
            except Exception as e:
                log(f"Token refresh failed: {e}", "error")
                creds = None
        else:
            client_secret_file = get_client_secret_path()
            log(f"Launching OAuth flow using {client_secret_file}…", "info")
            if not os.path.exists(client_secret_file):
                log(f"ERROR: {client_secret_file} not found. Please download it from Google Cloud Console.", "error")
                raise FileNotFoundError(f"OAuth client secret file not found: {client_secret_file}")
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
                creds = flow.run_local_server(port=0)
                log("OAuth consent completed successfully", "info")
                if should_show_auth_logs():
                    log("OAuth flow completed, credentials obtained", "debug")
            except Exception as e:
                log(f"OAuth flow failed: {e}", "error")
                raise
        
        # Save the credentials to the appropriate location
        try:
            token_path = get_token_path()
            with open(token_path, "wb") as token:
                pickle.dump(creds, token)
                log(f"Saved credentials to {token_path}", "info")
        except Exception as e:
            log(f"Warning: Failed to save credentials: {e}", "warning")
    else:
        log("Existing token is valid", "info")
        if should_show_auth_logs():
            log("Using cached valid credentials", "debug")
    
    return creds


essential_sa_hint = (
    "Service Account auth selected but no --sa-file provided and SERVICE_ACCOUNT_FILE env var is unset.\n"
    "Provide --sa-file /path/to/key.json or set SERVICE_ACCOUNT_FILE."
)


def get_sa_creds(sa_file: Optional[str]):
    """Load Service Account credentials from file (path or $SERVICE_ACCOUNT_FILE)."""
    key_path = sa_file or os.environ.get("SERVICE_ACCOUNT_FILE")
    log(f"Authentication mode: Service Account — key path: {key_path or 'N/A'}", "info")
    
    if should_show_auth_logs():
        log("Starting Service Account authentication process", "debug")
    
    if not key_path:
        log("ERROR: No Service Account key file provided", "error")
        raise SystemExit(essential_sa_hint)
    
    if not os.path.exists(key_path):
        log(f"ERROR: Service Account key file not found: {key_path}", "error")
        raise FileNotFoundError(f"Service Account key file not found: {key_path}")
    
    try:
        creds = service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)
        log("Service Account credentials loaded successfully", "info")
        if should_show_auth_logs():
            log(f"Loaded credentials for service account from: {key_path}", "debug")
    except Exception as e:
        log(f"Failed to load Service Account credentials: {e}", "error")
        raise
    
    return creds

def create_form_from_json(json_path: str, auth_method: str = "oauth", sa_file: Optional[str] = None, share_with: Optional[str] = None):
    """Create Google Form from MCQ JSON file with comprehensive logging."""
    
    # Log startup information
    log("=" * 60, "info")
    log("GOOGLE FORMS CREATOR - Starting Processing", "info")
    log("=" * 60, "info")
    log(f"Input parameters:", "info")
    log(f"  JSON Path: {json_path}", "info")
    log(f"  Auth Method: {auth_method}", "info")
    log(f"  Share With: {share_with or 'None'}", "info")
    log(f"  Detailed Logs: {should_show_detailed_logs()}", "info")
    log(f"  Auth Logs: {should_show_auth_logs()}", "info")
    log(f"  API Logs: {should_show_api_logs()}", "info")
    
    # Validate input file
    if not os.path.exists(json_path):
        log(f"ERROR: JSON file not found: {json_path}", "error")
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    
    log(f"JSON file validation: {json_path} exists", "info")
    
    # Authentication
    log("Starting authentication process...", "info")
    start_time = time.time()
    
    try:
        # if auth_method == "sa":
        #     creds = get_sa_creds(sa_file)
        # else:
        creds = get_oauth_creds()
        
        auth_time = time.time() - start_time
        log(f"✅ Authentication completed in {auth_time:.2f} seconds", "info")
        
    except Exception as e:
        log(f"❌ Authentication failed: {e}", "error")
        if should_show_detailed_logs():
            log("Authentication error details:", "debug")
            traceback.print_exc()
        raise

    # Build Google Forms service
    log("Building Google Forms service...", "info")
    try:
        forms_service = build("forms", "v1", credentials=creds)
        log("✅ Google Forms service initialized", "info")
        if should_show_api_logs():
            log("Forms API client ready for operations", "debug")
    except Exception as e:
        log(f"❌ Failed to initialize Forms service: {e}", "error")
        raise

    # Create empty form
    log("Creating empty Google Form...", "info")
    try:
        form = forms_service.forms().create(body={
            "info": {"title": "Mission Quiz", "documentTitle": "MCQ Quiz"}
        }).execute()
        form_id = form["formId"]
        log(f"✅ Form created successfully with ID: {form_id}", "info")
        if should_show_api_logs():
            log(f"Form creation API response: {form}", "debug")
    except Exception as e:
        log(f"❌ Failed to create form: {e}", "error")
        if should_show_detailed_logs():
            traceback.print_exc()
        raise

    # Ensure the form is a quiz before setting grading
    try:
        quiz_toggle = {
            "requests": [
                {
                    "updateSettings": {
                        "settings": {
                            "quizSettings": {"isQuiz": True}
                        },
                        "updateMask": "quizSettings.isQuiz"
                    }
                }
            ]
        }
        forms_service.forms().batchUpdate(formId=form_id, body=quiz_toggle).execute()
        log("✅ Form quiz mode enabled (quizSettings.isQuiz = true)", "info")
    except Exception as e:
        log(f"⚠️  Failed to enable quiz mode automatically (will continue): {e}", "warning")

    # Load and parse JSON
    log(f"Loading MCQs from: {json_path}", "info")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        questions = data.get("questions", [])
        total_qs = len(questions)
        log(f"✅ JSON parsing completed: {total_qs} question(s) found", "info")
        
        if should_show_detailed_logs():
            log(f"JSON structure analysis:", "debug")
            log(f"  Total questions: {total_qs}", "debug")
            log(f"  Source summary: {data.get('source_summary', 'N/A')[:100]}...", "debug")
            
    except json.JSONDecodeError as e:
        log(f"❌ Invalid JSON format: {e}", "error")
        raise
    except Exception as e:
        log(f"❌ Failed to load JSON file: {e}", "error")
        raise

    # Process questions
    if not questions:
        log("⚠️  No questions found in JSON file", "warning")
        return

    log(f"Processing {total_qs} questions...", "info")
    requests = []
    processed_count = 0

    for i, q in enumerate(questions, 1):
        try:
            if should_show_detailed_logs():
                log(f"Processing question {i}/{total_qs}: {q.get('stem', 'Untitled')[:50]}...", "debug")

            options = [{"value": opt["text"]} for opt in q.get("options", [])]
            correct = (q.get("answer") or {}).get("text", "")

            if should_show_detailed_logs():
                log(f"  Question {i} details:", "debug")
                log(f"    Stem: {q.get('stem', 'Untitled')[:100]}...", "debug")
                log(f"    Options: {len(options)}", "debug")
                log(f"    Correct answer: {correct[:50]}...", "debug")
                log(f"    Rationale: {q.get('rationale', 'N/A')[:50]}...", "debug")

            # Add question
            requests.append({
                "createItem": {
                    "item": {
                        "title": q.get("stem", "Untitled question"),
                        "questionItem": {
                            "question": {
                                "required": True,
                                "choiceQuestion": {
                                    "type": "RADIO",
                                    "options": options,
                                    "shuffle": False,
                                }
                            }
                        }
                    },
                    "location": {"index": 0}
                }
            })

            # Validate 'correct' is among options before adding grading
            option_values = [o["value"] for o in options if "value" in o]
            if correct and correct not in option_values:
                log(f"⚠️  Correct answer not found among options for question {i}; skipping grading for this item.", "warning")
                continue

            # Add grading (answer key, without feedback fields)
            requests.append({
                "updateItem": {
                    "item": {
                        "title": q.get("stem", "Untitled question"),
                        "questionItem": {
                            "question": {
                                "grading": {
                                    "pointValue": 1,
                                    "correctAnswers": {"answers": [{"value": correct}]}
                                }
                            }
                        }
                    },
                    "location": {"index": 0},
                    "updateMask": "questionItem.question.grading"
                }
            })

            processed_count += 1

        except Exception as e:
            log(f"⚠️  Failed to process question {i}: {e}", "warning")
            if should_show_detailed_logs():
                log(f"Question {i} error details:", "debug")
                traceback.print_exc()
            continue

    log(f"✅ Question processing completed: {processed_count}/{total_qs} questions processed", "info")

    # Send batch update to Google Forms
    if requests:
        log(f"Sending batch update with {len(requests)} request objects to Google Forms...", "info")
        try:
            start_time = time.time()
            forms_service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()
            update_time = time.time() - start_time
            log(f"✅ Batch update completed in {update_time:.2f} seconds", "info")
            if should_show_api_logs():
                log(f"Batch update API call successful: {len(requests)} requests processed", "debug")
        except Exception as e:
            log(f"❌ Batch update failed: {e}", "error")
            if should_show_detailed_logs():
                traceback.print_exc()
            raise
    else:
        log("⚠️  No requests to send (no valid questions found)", "warning")

    # Display results
    form_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    log("=" * 60, "info")
    log("FORM CREATION COMPLETED SUCCESSFULLY", "info")
    log("=" * 60, "info")
    log(f"Form URL: {form_url}", "info")
    log("⚠️  Remember: Open the form, go to Settings → Quizzes, and enable 'Make this a quiz'", "warning")
    print(f"\nForm created: {form_url}")
    print("⚠️ Remember: open the form, go to Settings → Quizzes, and enable 'Make this a quiz'.")

    # Optional: Share form if using Service Account
    if auth_method == "sa" and share_with:
        log(f"Sharing form with {share_with} (Editor access)...", "info")
        try:
            drive_service = build("drive", "v3", credentials=creds)
            drive_service.permissions().create(
                fileId=form_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": share_with,
                },
                sendNotificationEmail=False,
            ).execute()
            log(f"✅ Form shared successfully with {share_with}", "info")
            print(f"Shared with {share_with} as Editor.")
        except Exception as e:
            log(f"⚠️  Form sharing failed: {e}", "warning")
            if should_show_detailed_logs():
                log("Sharing error details:", "debug")
                traceback.print_exc()
    
    # Return the form edit URL
    return form_url

def run_pipeline_from_env():
    """End-to-end pipeline: PDF → MCQs JSON → Google Form, driven by .env variables."""
    # Generator envs
    pdf_path = (os.getenv("PDF_PATH") or "").strip().strip('"').strip("'")
    output_dir = (os.getenv("OUTPUT_DIR") or "").strip().strip('"').strip("'")
    model = (os.getenv("MODEL") or "gpt-4.1").strip()
    try:
        num_questions = int((os.getenv("NUM_QUESTIONS") or "4").strip())
    except ValueError:
        num_questions = 4

    # Form envs
    auth_method = (os.getenv("FORMS_AUTH_METHOD") or "oauth").strip()
    sa_file = (os.getenv("SA_FILE") or "").strip().strip('"').strip("'") or None
    share_with = (os.getenv("SHARE_WITH") or "").strip().strip('"').strip("'") or None

    # Validate generator inputs
    if not pdf_path:
        log("PIPELINE: PDF_PATH is required.", "error")
        sys.exit(1)
    if not output_dir:
        log("PIPELINE: OUTPUT_DIR is required.", "error")
        sys.exit(1)

    # Step 1: PDF -> MCQs JSON
    log("PIPELINE: Generating MCQs JSON from PDF…", "info")
    combined_path = generate_mcqs_to_file(pdf_path, output_dir, model, num_questions)
    log(f"PIPELINE: MCQs JSON ready → {combined_path}", "info")

    # Step 2: JSON -> Google Form
    log("PIPELINE: Creating Google Form from MCQs JSON…", "info")
    create_form_from_json(
        json_path=combined_path,
        auth_method=auth_method,
        sa_file=sa_file,
        share_with=share_with,
    )
    log("PIPELINE: Completed.", "info")

def main():
    """Main function with environment variable support (no command line arguments)."""
    
    # Load environment variables with validation
    json_path = os.getenv("JSON_PATH", "").strip().strip('"').strip("'")
    auth_method = os.getenv("FORMS_AUTH_METHOD", "oauth").strip().lower()
    sa_file = os.getenv("SA_FILE", "").strip().strip('"').strip("'")
    share_with = os.getenv("SHARE_WITH", "").strip().strip('"').strip("'")
    
    # Parse verbosity from environment (similar to PdfToQuestions.py)
    v_raw = (os.getenv("VERBOSITY") or "1").strip().upper()
    verbosity = {"0": 0, "ERROR": 0, "1": 1, "INFO": 1, "2": 2, "DEBUG": 2}.get(v_raw, 1)
    
    # Set up logging
    logger = setup_logging(verbosity)
    
    # Log environment information
    logger.info("Google Forms Creator - Starting")
    logger.info(f"Environment variables:")
    logger.info(f"  JSON_PATH: {json_path or 'NOT SET'}")
    logger.info(f"  AUTH_METHOD: {auth_method}")
    logger.info(f"  SA_FILE: {sa_file or 'NOT SET'}")
    logger.info(f"  SHARE_WITH: {share_with or 'NOT SET'}")
    logger.info(f"  VERBOSITY: {os.getenv('VERBOSITY', 'Not set')}")
    logger.info(f"  GOOGLE_FORMS_LOG_LEVEL: {os.getenv('GOOGLE_FORMS_LOG_LEVEL', 'Not set')}")
    logger.info(f"  GOOGLE_FORMS_SHOW_DETAILED_LOGS: {os.getenv('GOOGLE_FORMS_SHOW_DETAILED_LOGS', 'Not set')}")
    logger.info(f"  GOOGLE_FORMS_SHOW_AUTH_LOGS: {os.getenv('GOOGLE_FORMS_SHOW_AUTH_LOGS', 'Not set')}")
    logger.info(f"  GOOGLE_FORMS_SHOW_API_LOGS: {os.getenv('GOOGLE_FORMS_SHOW_API_LOGS', 'Not set')}")
    
    # Pipeline mode: run PDF → MCQs → Form using .env
    if (os.getenv("PIPELINE", "false").lower() in ("true", "1", "yes")):
        log("PIPELINE mode enabled via env. Running end-to-end…", "info")
        run_pipeline_from_env()
        return

    # Validate required environment variables
    if not json_path:
        logger.error("JSON_PATH environment variable is required.")
        logger.error("Example: export JSON_PATH='mcqs.json'")
        sys.exit(1)
    
    if auth_method not in ["oauth", "sa"]:
        logger.error(f"Invalid AUTH_METHOD: {auth_method}. Must be 'oauth' or 'sa'")
        sys.exit(1)
    
    if auth_method == "sa" and not sa_file:
        logger.error("SA_FILE environment variable is required when AUTH_METHOD=sa")
        logger.error("Example: export SA_FILE='service_account.json'")
        sys.exit(1)
    
    logger.info("Starting Google Forms creation pipeline...")
    logger.info(
        f"Configuration: json_path='{json_path}', auth_method='{auth_method}', "
        f"sa_file='{sa_file or 'N/A'}', share_with='{share_with or 'N/A'}, verbosity={verbosity}"
    )

    try:
        create_form_from_json(
            json_path=json_path,
            auth_method=auth_method,
            sa_file=sa_file if sa_file else None,
            share_with=share_with if share_with else None,
        )
        log("✅ All operations completed successfully", "info")
    except FileNotFoundError as e:
        log(f"❌ File not found: {e}", "error")
        if should_show_detailed_logs():
            traceback.print_exc()
        sys.exit(2)
    except Exception as e:
        log(f"❌ Unexpected error: {e}", "error")
        if should_show_detailed_logs():
            traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    load_dotenv('/secrets/.env')
    main()