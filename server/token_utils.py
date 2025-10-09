#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Token utilities for Google OAuth authentication with Cloud Run secret mounting support.
"""

import os
import pathlib
import pickle
from typing import Optional


# Token paths for different environments
TOKEN_DEFAULT = "token.pkl"          # for local dev
TOKEN_CLOUD   = "/secrets/token.pkl" # mounted path in Cloud Run


def get_token_path() -> str:
    """
    Determine the correct token path based on environment.
    
    Returns:
        str: Path to the token file (Cloud Run secret mount or local dev)
    """
    return TOKEN_CLOUD if pathlib.Path(TOKEN_CLOUD).exists() else TOKEN_DEFAULT


def load_google_token():
    """
    Load Google OAuth token with lazy loading and Cloud Run support.
    
    Returns:
        Google OAuth credentials object
        
    Raises:
        FileNotFoundError: If token file is not found at either location
    """
    path = get_token_path()
    if not pathlib.Path(path).exists():
        # Be graceful: raise a clear error that surfaces in logs
        raise FileNotFoundError(
            f"Google token not found at {path}. "
            f"Provide local {TOKEN_DEFAULT} or mount secret to {TOKEN_CLOUD}."
        )
    
    with open(path, "rb") as f:
        return pickle.load(f)


def get_client_secret_path() -> str:
    """
    Get the path to the client secret file.
    
    Returns:
        str: Path to client_secret.json
    """
    return "client_secret.json"
