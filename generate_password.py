#!/usr/bin/env python3
"""
Password Hash Generator for Apple Music Dashboard

Generates bcrypt hashes for use in .streamlit/secrets.toml

Usage:
    python generate_password.py
    
    # Or with a specific password:
    python generate_password.py "my-password"

Security:
    - Uses bcrypt with work factor 12 (industry standard)
    - Each hash is unique due to random salt
    - Same password produces different hashes (this is correct!)
"""

import sys
import secrets


def generate_hash(password: str) -> str:
    """Generate a bcrypt hash for a password."""
    try:
        # Try streamlit-authenticator's Hasher (v0.4+)
        import streamlit_authenticator as stauth
        hasher = stauth.Hasher()
        return hasher.hash_pw(password)
    except (ImportError, AttributeError):
        pass
    
    try:
        # Fall back to bcrypt directly
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    except ImportError:
        pass
    
    print("❌ Neither streamlit-authenticator nor bcrypt is installed.")
    print("   Install with: pip install streamlit-authenticator bcrypt")
    sys.exit(1)


def main():
    if len(sys.argv) > 1:
        # Password provided as argument
        password = sys.argv[1]
    else:
        # Interactive mode
        print("🔐 Password Hash Generator")
        print("=" * 40)
        print()
        import getpass
        password = getpass.getpass("Enter password to hash: ")
        confirm = getpass.getpass("Confirm password: ")
        
        if password != confirm:
            print("❌ Passwords don't match!")
            sys.exit(1)
    
    # Generate hash
    hashed = generate_hash(password)
    
    print()
    print("✅ Bcrypt hash generated!")
    print()
    print("Copy this into your .streamlit/secrets.toml:")
    print("-" * 50)
    print(f'password = "{hashed}"')
    print("-" * 50)
    print()
    print("📝 Note: Each run generates a different hash (due to random salt).")
    print("   This is correct and secure!")
    
    # Also generate a cookie key if needed
    print()
    print("🍪 Cookie key (if you need one):")
    cookie_key = secrets.token_hex(16)
    print(f'cookie_key = "{cookie_key}"')


if __name__ == "__main__":
    main()
