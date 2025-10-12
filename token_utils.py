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

import os
import json

def save_env_to_json(env_var_name: str, output_file: str = "env_output.json"):
    """
    Reads an environment variable and saves it as a JSON file.

    Args:
        env_var_name (str): The name of the environment variable to read.
        output_file (str): The name of the JSON file to create (default: 'env_output.json').

    Raises:
        ValueError: If the environment variable is not found.
    """
    # Get the environment variable
    value = os.getenv(env_var_name)

    if value is None:
        raise ValueError(f"Environment variable '{env_var_name}' not found.")

    # Create a dictionary to store the variable
    data = {env_var_name: value}

    # Write to JSON file
    with open(output_file, "w") as f:
        json.dump(data, f, indent=4)

    print(f"✅ Saved {env_var_name} to {output_file}")


# Example usage:
# save_env_to_json("API_KEY", "config.json")