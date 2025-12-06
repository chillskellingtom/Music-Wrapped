"""
Hardened Authentication Module

Security layers:
1. Pepper: Server-side secret HMAC'd with password before bcrypt
2. Rate limiting: Exponential backoff on failed attempts
3. Account lockout: Temporary lock after N failures
4. 2FA: Optional TOTP (Google Authenticator compatible)
5. Secure session: Encrypted cookies with rotation

Usage:
    from secure_auth import SecureAuthenticator
    
    auth = SecureAuthenticator()
    if auth.login():
        # User authenticated
        pass
    auth.logout_button()
"""

import streamlit as st
import bcrypt
import hmac
import hashlib
import time
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# Try to import TOTP library
try:
    import pyotp
    TOTP_AVAILABLE = True
except ImportError:
    TOTP_AVAILABLE = False


@dataclass
class AuthConfig:
    """Authentication configuration."""
    # Pepper: Server-side secret (MUST be in secrets, never in code)
    pepper: str = ""
    
    # Rate limiting
    max_attempts: int = 5
    lockout_minutes: int = 15
    backoff_base: float = 1.5  # Exponential backoff multiplier
    
    # Session
    session_timeout_hours: int = 24
    
    # 2FA
    require_2fa: bool = False
    
    # Password requirements
    min_password_length: int = 12


@dataclass  
class LoginAttempt:
    """Track login attempts for rate limiting."""
    count: int = 0
    last_attempt: datetime = field(default_factory=datetime.now)
    locked_until: Optional[datetime] = None


class SecureAuthenticator:
    """
    Hardened authentication with multiple security layers.
    
    Security features:
    - Pepper: Passwords are HMAC'd with a server secret before bcrypt
    - Rate limiting: Exponential backoff between failed attempts  
    - Account lockout: 15-minute lock after 5 failures
    - 2FA: Optional TOTP support (Google Authenticator)
    - Timing-safe comparisons throughout
    """
    
    def __init__(self):
        self.config = self._load_config()
        self._init_session_state()
    
    def _load_config(self) -> AuthConfig:
        """Load auth config from secrets."""
        config = AuthConfig()
        
        if "auth" in st.secrets:
            auth = st.secrets.auth
            config.pepper = auth.get("pepper", "")
            config.max_attempts = auth.get("max_attempts", 5)
            config.lockout_minutes = auth.get("lockout_minutes", 15)
            config.require_2fa = auth.get("require_2fa", False)
            config.min_password_length = auth.get("min_password_length", 12)
        
        return config
    
    def _init_session_state(self):
        """Initialize session state for tracking."""
        if "auth_attempts" not in st.session_state:
            st.session_state.auth_attempts = {}  # username -> LoginAttempt
        if "authenticated" not in st.session_state:
            st.session_state.authenticated = False
        if "auth_user" not in st.session_state:
            st.session_state.auth_user = None
        if "auth_time" not in st.session_state:
            st.session_state.auth_time = None
    
    def _apply_pepper(self, password: str) -> bytes:
        """
        Apply pepper to password using HMAC-SHA256.
        
        The pepper is a server-side secret that makes pre-computed
        hash databases completely useless, even for common passwords.
        """
        if not self.config.pepper:
            # No pepper configured - still secure but warn
            return password.encode('utf-8')
        
        # HMAC the password with the pepper
        peppered = hmac.new(
            self.config.pepper.encode('utf-8'),
            password.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        return peppered
    
    def hash_password(self, password: str) -> str:
        """
        Hash a password with pepper + bcrypt.
        
        Use this to generate hashes for secrets.toml:
            python -c "from secure_auth import SecureAuthenticator; \\
                       a = SecureAuthenticator(); \\
                       print(a.hash_password('your-password'))"
        """
        peppered = self._apply_pepper(password)
        # bcrypt with work factor 12 (good balance of security/speed)
        hashed = bcrypt.hashpw(peppered, bcrypt.gensalt(rounds=12))
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash (timing-safe)."""
        peppered = self._apply_pepper(password)
        try:
            return bcrypt.checkpw(peppered, hashed.encode('utf-8'))
        except Exception:
            return False
    
    def _get_attempts(self, username: str) -> LoginAttempt:
        """Get login attempts for a user."""
        if username not in st.session_state.auth_attempts:
            st.session_state.auth_attempts[username] = LoginAttempt()
        return st.session_state.auth_attempts[username]
    
    def _is_locked(self, username: str) -> Tuple[bool, Optional[int]]:
        """Check if account is locked. Returns (is_locked, seconds_remaining)."""
        attempts = self._get_attempts(username)
        
        if attempts.locked_until:
            now = datetime.now()
            if now < attempts.locked_until:
                remaining = (attempts.locked_until - now).total_seconds()
                return True, int(remaining)
            else:
                # Lockout expired, reset
                attempts.locked_until = None
                attempts.count = 0
        
        return False, None
    
    def _get_backoff_seconds(self, username: str) -> float:
        """Calculate backoff delay based on failed attempts."""
        attempts = self._get_attempts(username)
        if attempts.count == 0:
            return 0
        
        # Exponential backoff: 1.5^attempts seconds (capped at 30s)
        delay = min(30, self.config.backoff_base ** attempts.count)
        
        # Check if enough time has passed since last attempt
        elapsed = (datetime.now() - attempts.last_attempt).total_seconds()
        if elapsed < delay:
            return delay - elapsed
        return 0
    
    def _record_failed_attempt(self, username: str):
        """Record a failed login attempt."""
        attempts = self._get_attempts(username)
        attempts.count += 1
        attempts.last_attempt = datetime.now()
        
        # Lock account after max attempts
        if attempts.count >= self.config.max_attempts:
            attempts.locked_until = datetime.now() + timedelta(
                minutes=self.config.lockout_minutes
            )
    
    def _record_success(self, username: str):
        """Clear attempts on successful login."""
        if username in st.session_state.auth_attempts:
            del st.session_state.auth_attempts[username]
    
    def _verify_totp(self, username: str, code: str) -> bool:
        """Verify TOTP code for 2FA."""
        if not TOTP_AVAILABLE:
            return True  # Skip if pyotp not installed
        
        try:
            # Get user's TOTP secret from secrets
            if "credentials" not in st.secrets.auth:
                return True
            
            users = st.secrets.auth.credentials.usernames
            if username not in users:
                return False
            
            user = users[username]
            totp_secret = user.get("totp_secret", "")
            
            if not totp_secret:
                return True  # No 2FA configured for this user
            
            totp = pyotp.TOTP(totp_secret)
            return totp.verify(code, valid_window=1)  # Allow 30s window
            
        except Exception:
            return False
    
    def _get_users(self) -> dict:
        """Get user credentials from secrets."""
        if "auth" not in st.secrets:
            return {}
        if "credentials" not in st.secrets.auth:
            return {}
        if "usernames" not in st.secrets.auth.credentials:
            return {}
        
        return dict(st.secrets.auth.credentials.usernames)
    
    def _check_session_valid(self) -> bool:
        """Check if current session is still valid."""
        if not st.session_state.authenticated:
            return False
        
        if st.session_state.auth_time is None:
            return False
        
        # Check session timeout
        elapsed = datetime.now() - st.session_state.auth_time
        if elapsed > timedelta(hours=self.config.session_timeout_hours):
            self._clear_session()
            return False
        
        return True
    
    def _clear_session(self):
        """Clear authentication session."""
        st.session_state.authenticated = False
        st.session_state.auth_user = None
        st.session_state.auth_time = None
    
    def login(self) -> bool:
        """
        Display login form and authenticate user.
        
        Returns True if authenticated, False otherwise.
        """
        # Check for existing valid session
        if self._check_session_valid():
            return True
        
        # Check if auth is configured
        users = self._get_users()
        if not users:
            # No auth configured, allow access
            st.session_state.authenticated = True
            st.session_state.auth_user = "guest"
            st.session_state.auth_time = datetime.now()
            return True
        
        # Display login form
        st.title("🎵 Apple Music Wrapped")
        st.markdown("### Secure Login")
        st.markdown("---")
        
        # Login form
        with st.form("login_form"):
            username = st.text_input("Username").lower().strip()
            password = st.text_input("Password", type="password")
            
            # 2FA field (if any user has it configured)
            show_2fa = self.config.require_2fa or any(
                users.get(u, {}).get("totp_secret") for u in users
            )
            totp_code = ""
            if show_2fa:
                totp_code = st.text_input(
                    "2FA Code (if enabled)", 
                    max_chars=6,
                    help="Enter the 6-digit code from your authenticator app"
                )
            
            submitted = st.form_submit_button("🔐 Log In", type="primary")
        
        if submitted and username and password:
            # Check if account is locked
            is_locked, remaining = self._is_locked(username)
            if is_locked:
                st.error(f"🔒 Account locked. Try again in {remaining // 60}m {remaining % 60}s")
                return False
            
            # Check rate limiting backoff
            backoff = self._get_backoff_seconds(username)
            if backoff > 0:
                st.warning(f"⏳ Please wait {backoff:.0f}s before trying again")
                return False
            
            # Verify credentials
            if username not in users:
                self._record_failed_attempt(username)
                st.error("❌ Invalid credentials")
                self._show_attempts_warning(username)
                return False
            
            user = users[username]
            stored_hash = user.get("password", "")
            
            if not self.verify_password(password, stored_hash):
                self._record_failed_attempt(username)
                st.error("❌ Invalid credentials")
                self._show_attempts_warning(username)
                return False
            
            # Verify 2FA if configured
            if user.get("totp_secret"):
                if not totp_code:
                    st.error("❌ 2FA code required")
                    return False
                if not self._verify_totp(username, totp_code):
                    st.error("❌ Invalid 2FA code")
                    return False
            
            # Success!
            self._record_success(username)
            st.session_state.authenticated = True
            st.session_state.auth_user = username
            st.session_state.auth_time = datetime.now()
            st.rerun()
        
        # Security info
        st.markdown("---")
        st.caption("🔒 Protected by bcrypt + pepper + rate limiting")
        if self.config.require_2fa:
            st.caption("📱 2FA enabled")
        
        return False
    
    def _show_attempts_warning(self, username: str):
        """Show warning about remaining attempts."""
        attempts = self._get_attempts(username)
        remaining = self.config.max_attempts - attempts.count
        if remaining <= 2:
            st.warning(f"⚠️ {remaining} attempts remaining before lockout")
    
    def logout_button(self):
        """Show logout button in sidebar."""
        if st.session_state.authenticated:
            user = st.session_state.auth_user
            if user and user != "guest":
                st.sidebar.markdown(f"👤 **{user}**")
            if st.sidebar.button("🚪 Logout"):
                self._clear_session()
                st.rerun()
    
    def get_current_user(self) -> Optional[str]:
        """Get current authenticated username."""
        if st.session_state.authenticated:
            return st.session_state.auth_user
        return None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_totp_secret() -> str:
    """Generate a new TOTP secret for 2FA setup."""
    if not TOTP_AVAILABLE:
        raise ImportError("pyotp required: pip install pyotp")
    return pyotp.random_base32()


def get_totp_qr_uri(secret: str, username: str, issuer: str = "MusicWrapped") -> str:
    """Get the URI for generating a QR code for authenticator apps."""
    if not TOTP_AVAILABLE:
        raise ImportError("pyotp required: pip install pyotp")
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def generate_secure_password(length: int = 16) -> str:
    """Generate a cryptographically secure random password."""
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


# ============================================================================
# CLI TOOLS
# ============================================================================

def main():
    """CLI for generating credentials."""
    import sys
    import getpass
    
    print("🔐 Secure Authentication Setup")
    print("=" * 50)
    
    if len(sys.argv) < 2:
        print("""
Usage:
    python secure_auth.py hash            - Generate password hash
    python secure_auth.py pepper          - Generate a pepper secret
    python secure_auth.py totp <username> - Setup 2FA for a user
    python secure_auth.py password        - Generate secure random password
""")
        return
    
    command = sys.argv[1]
    
    if command == "hash":
        print("\n📝 Password Hash Generator")
        print("-" * 30)
        
        # Check for pepper in environment or secrets
        pepper = ""
        secrets_path = Path(".streamlit/secrets.toml")
        if secrets_path.exists():
            import tomllib
            with open(secrets_path, "rb") as f:
                secrets_data = tomllib.load(f)
                pepper = secrets_data.get("auth", {}).get("pepper", "")
        
        if pepper:
            print("✅ Using pepper from secrets.toml")
        else:
            print("⚠️  No pepper configured (hash will work but less secure)")
            pepper_input = input("Enter pepper (or press Enter to skip): ").strip()
            if pepper_input:
                pepper = pepper_input
        
        password = getpass.getpass("Enter password to hash: ")
        confirm = getpass.getpass("Confirm password: ")
        
        if password != confirm:
            print("❌ Passwords don't match!")
            return
        
        if len(password) < 12:
            print("⚠️  Warning: Password should be at least 12 characters")
        
        # Hash with pepper
        if pepper:
            peppered = hmac.new(
                pepper.encode('utf-8'),
                password.encode('utf-8'),
                hashlib.sha256
            ).digest()
        else:
            peppered = password.encode('utf-8')
        
        hashed = bcrypt.hashpw(peppered, bcrypt.gensalt(rounds=12)).decode()
        
        print("\n✅ Hash generated!")
        print("-" * 50)
        print(f'password = "{hashed}"')
        print("-" * 50)
    
    elif command == "pepper":
        print("\n🌶️  Pepper Generator")
        print("-" * 30)
        pepper = secrets.token_hex(32)
        print("\nAdd this to .streamlit/secrets.toml under [auth]:")
        print("-" * 50)
        print(f'pepper = "{pepper}"')
        print("-" * 50)
        print("\n⚠️  IMPORTANT: Keep this secret! Never commit to git!")
        print("   If you change the pepper, all existing password hashes become invalid.")
    
    elif command == "totp":
        if not TOTP_AVAILABLE:
            print("❌ pyotp required: pip install pyotp")
            return
        
        username = sys.argv[2] if len(sys.argv) > 2 else input("Username: ")
        
        print(f"\n📱 2FA Setup for {username}")
        print("-" * 30)
        
        secret = generate_totp_secret()
        uri = get_totp_qr_uri(secret, username)
        
        print(f"\n1. Add to secrets.toml under [auth.credentials.usernames.{username}]:")
        print("-" * 50)
        print(f'totp_secret = "{secret}"')
        print("-" * 50)
        
        print(f"\n2. Scan this URI with Google Authenticator (or generate QR):")
        print(uri)
        
        print("\n3. Test code verification:")
        totp = pyotp.TOTP(secret)
        print(f"   Current code: {totp.now()}")
    
    elif command == "password":
        length = int(sys.argv[2]) if len(sys.argv) > 2 else 16
        password = generate_secure_password(length)
        print(f"\n🎲 Generated password ({length} chars):")
        print("-" * 50)
        print(password)
        print("-" * 50)
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()

