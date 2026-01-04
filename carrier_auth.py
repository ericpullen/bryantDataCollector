#!/usr/bin/env python3
"""
Carrier/Bryant Authentication Module

Handles OAuth 2.0 authentication for Carrier Infinity systems.
"""

import json
import os
import requests
from typing import Optional, Tuple
from datetime import datetime


# Carrier/Bryant OAuth Configuration
OKTA_BASE_URL = "https://sso.carrier.com"
OKTA_AUTH_SERVER = "default"
OKTA_CLIENT_ID = "0oa1ce7hwjuZbfOMB4x7"


def load_credentials(config_file: str = "config.json") -> Tuple[Optional[str], Optional[str]]:
    """
    Load credentials from JSON config file.
    
    Expected config.json format:
    {
        "username": "your_email@example.com",
        "password": "your_password"
    }
    
    Returns:
        Tuple of (username, password) or (None, None) if not found
    """
    # First try config file
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
            username = config.get("username")
            password = config.get("password")
            if username and password:
                return username, password
            else:
                print(f"Warning: {config_file} found but missing 'username' or 'password' keys")
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_file}: {e}")
    except Exception as e:
        print(f"Error reading {config_file}: {e}")
    
    # Fall back to environment variables
    username = os.environ.get("CARRIER_USERNAME")
    password = os.environ.get("CARRIER_PASSWORD")
    
    if username and password:
        return username, password
    
    return None, None


class CarrierAuth:
    """Handle Carrier/Bryant SSO Authentication (Synchronous)"""
    
    def __init__(self):
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.id_token: Optional[str] = None
    
    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate using username and password.
        
        Uses Resource Owner Password Grant (the method that works).
        
        Returns:
            True if authentication successful, False otherwise
        """
        url = f"{OKTA_BASE_URL}/oauth2/{OKTA_AUTH_SERVER}/v1/token"
        
        data = {
            "grant_type": "password",
            "client_id": OKTA_CLIENT_ID,
            "username": username,
            "password": password,
            "scope": "openid offline_access",
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        
        try:
            resp = self.session.post(url, data=data, headers=headers)
            
            if resp.status_code == 200:
                result = resp.json()
                self.access_token = result.get("access_token")
                self.refresh_token = result.get("refresh_token")
                self.id_token = result.get("id_token")
                return True
            else:
                print(f"Authentication failed: {resp.status_code}")
                try:
                    error = resp.json()
                    print(f"Error: {error.get('error_description', error.get('error', resp.text[:200]))}")
                except:
                    print(f"Response: {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"Authentication error: {e}")
            return False
    
    def refresh_access_token(self) -> bool:
        """Refresh the access token using the refresh token"""
        if not self.refresh_token:
            print("No refresh token available")
            return False
        
        url = f"{OKTA_BASE_URL}/oauth2/{OKTA_AUTH_SERVER}/v1/token"
        
        data = {
            "grant_type": "refresh_token",
            "client_id": OKTA_CLIENT_ID,
            "refresh_token": self.refresh_token,
            "scope": "openid offline_access",
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        
        try:
            resp = self.session.post(url, data=data, headers=headers)
            
            if resp.status_code == 200:
                result = resp.json()
                self.access_token = result.get("access_token")
                self.refresh_token = result.get("refresh_token", self.refresh_token)
                self.id_token = result.get("id_token")
                return True
            else:
                print(f"Token refresh failed: {resp.status_code}")
                return False
        except Exception as e:
            print(f"Token refresh error: {e}")
            return False
    
    def get_access_token(self) -> Optional[str]:
        """Get the current access token"""
        return self.access_token
    
    def save_tokens(self, filepath: str = "carrier_tokens.json"):
        """Save tokens to a file for reuse"""
        data = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "saved_at": datetime.now().isoformat(),
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def load_tokens(self, filepath: str = "carrier_tokens.json") -> bool:
        """Load tokens from a file"""
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
            self.id_token = data.get("id_token")
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"Error loading tokens: {e}")
            return False

