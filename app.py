#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main app entry point for Cloud Run deployment
"""

import os
import sys
import json
import traceback
import uuid
from flask import Flask, request, g, jsonify

# Import the main app from server module
from server.app import app as server_app

# Use the server app directly with minimal modifications
app = server_app

# Add request ID middleware
@app.before_request
def _inject_request_id():
    g.req_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    # minimal breadcrumb
    print(json.dumps({
        "evt": "request.start",
        "req_id": g.req_id,
        "method": request.method,
        "path": request.path,
        "remote": request.headers.get("X-Forwarded-For") or request.remote_addr,
    }), flush=True)

@app.after_request
def _log_after(resp):
    print(json.dumps({
        "evt": "request.end",
        "req_id": getattr(g, "req_id", None),
        "status": resp.status_code,
    }), flush=True)
    return resp

# Global error handler (don't sys.exit; log and return JSON)
@app.errorhandler(Exception)
def handle_exception(e):
    print("UNHANDLED_EXCEPTION", repr(e), flush=True)
    traceback.print_exc()
    return jsonify({
        "error": "internal_error",
        "message": "Unexpected error",
        "req_id": getattr(g, "req_id", None)
    }), 500

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)