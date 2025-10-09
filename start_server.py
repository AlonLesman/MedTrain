#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cloud Run startup script for MedTrain
"""

import os
import sys
import subprocess

if __name__ == "__main__":
    # Get port from Cloud Run environment variable
    port = os.getenv('PORT', '8080')
    
    print(f"Starting MedTrain server on port {port}")
    print(f"Environment: {os.getenv('ENVIRONMENT', 'production')}")
    
    # Start gunicorn with proper configuration
    cmd = [
        'gunicorn',
        'server.app:app',
        '--bind', f'0.0.0.0:{port}',
        '--workers', '2',
        '--timeout', '180',
        '--access-logfile', '-',
        '--error-logfile', '-',
        '--log-level', 'info'
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    
    # Start the server
    subprocess.run(cmd)
