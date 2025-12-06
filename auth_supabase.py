"""
Supabase Authentication for Apple Music Dashboard

Industry-standard authentication with:
- Email/password with bcrypt hashing
- Forgot password (email reset)  
- TOTP 2FA
- Magic links (passwordless)
- Session management
- Rate limiting
- SOC2 Type II certified

Setup:
1. Create free account at https://supabase.com
2. Create a new project
3. Go to Authentication > Providers > Enable Email
4. Go to Settings > API > Copy URL and anon key
5. Add to .streamlit/secrets.toml:
   
   [supabase]
   url = "https://your-project.supabase.co"
   key = "your-anon-key"

6. Enable 2FA: Authentication > Settings > Enable TOTP

Usage:
    from auth_supabase import SupabaseAuth
    
    auth = SupabaseAuth()
    if auth.require_auth():
        # User is authenticated
        user = auth.get_user()
"""

import streamlit as st
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Try to import supabase
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


@dataclass
class User:
    """Authenticated user."""
    id: str
    email: str
    name: Optional[str] = None
    email_verified: bool = False
    mfa_enabled: bool = False


class SupabaseAuth:
    """
    Supabase-powered authentication.
    
    Features:
    - Email/password authentication
    - Forgot password (email reset link)
    - TOTP 2FA (Google Authenticator)
    - Magic links (passwordless)
    - Secure session management
    - Rate limiting (built into Supabase)
    """
    
    def __init__(self):
        self.client: Optional[Client] = None
        self._init_client()
        self._init_session_state()
    
    def _init_client(self):
        """Initialize Supabase client from secrets."""
        if not SUPABASE_AVAILABLE:
            return
        
        try:
            if "supabase" not in st.secrets:
                return
            
            url = st.secrets.supabase.get("url", "")
            key = st.secrets.supabase.get("key", "")
            
            if not url or not key:
                return
            
            self.client = create_client(url, key)
        except AttributeError:
            # st.secrets might not be available
            return
        except Exception as e:
            # Don't show error during init - will be handled in require_auth
            pass
    
    def _init_session_state(self):
        """Initialize session state."""
        if "sb_user" not in st.session_state:
            st.session_state.sb_user = None
        if "sb_session" not in st.session_state:
            st.session_state.sb_session = None
        if "auth_view" not in st.session_state:
            st.session_state.auth_view = "login"
    
    def _check_existing_session(self) -> bool:
        """Check for existing valid session."""
        if not self.client:
            return False
        
        try:
            response = self.client.auth.get_session()
            if response and response.session:
                st.session_state.sb_session = response.session
                st.session_state.sb_user = response.session.user
                return True
        except Exception:
            pass
        
        return False
    
    def require_auth(self) -> bool:
        """
        Require authentication to proceed.
        
        Returns True if user is authenticated, shows login UI otherwise.
        """
        if not SUPABASE_AVAILABLE:
            st.error("❌ Supabase not installed. Run: pip install supabase")
            st.stop()
            return False
        
        if not self.client:
            # Check if secrets exist but are invalid
            if "supabase" in st.secrets:
                url = st.secrets.supabase.get("url", "")
                key = st.secrets.supabase.get("key", "")
                if not url or not key:
                    st.error("⚠️ Supabase URL or key missing in secrets. Please configure in Streamlit Cloud settings.")
                    st.stop()
                    return False
                else:
                    st.error("⚠️ Failed to connect to Supabase. Please check your credentials.")
                    st.stop()
                    return False
            else:
                st.error("⚠️ Supabase not configured. Please add secrets in Streamlit Cloud settings.")
                st.stop()
                return False
        
        # Check existing session
        if self._check_existing_session():
            return True
        
        # Check session state
        if st.session_state.sb_user:
            return True
        
        # Show auth UI
        self._render_auth_ui()
        return False
    
    def _render_auth_ui(self):
        """Render the authentication UI."""
        st.title("🎵 Apple Music Wrapped")
        
        # Tab navigation
        view = st.session_state.auth_view
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Login", type="primary" if view == "login" else "secondary"):
                st.session_state.auth_view = "login"
                st.rerun()
        with col2:
            if st.button("Sign Up", type="primary" if view == "signup" else "secondary"):
                st.session_state.auth_view = "signup"
                st.rerun()
        with col3:
            if st.button("Forgot Password", type="primary" if view == "forgot" else "secondary"):
                st.session_state.auth_view = "forgot"
                st.rerun()
        
        st.markdown("---")
        
        if view == "login":
            self._render_login()
        elif view == "signup":
            self._render_signup()
        elif view == "forgot":
            self._render_forgot_password()
        elif view == "verify_otp":
            self._render_verify_otp()
        
        st.markdown("---")
        st.caption("🔒 Secured by Supabase (SOC2 Type II certified)")
    
    def _render_login(self):
        """Render login form."""
        st.subheader("🔐 Login")
        
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In", type="primary")
        
        if submitted and email and password:
            try:
                response = self.client.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                
                if response.session:
                    # Check if MFA is required
                    if hasattr(response, 'mfa_required') and response.mfa_required:
                        st.session_state.auth_view = "verify_otp"
                        st.session_state.mfa_email = email
                        st.rerun()
                    else:
                        st.session_state.sb_session = response.session
                        st.session_state.sb_user = response.user
                        st.success("✅ Logged in!")
                        st.rerun()
            except Exception as e:
                error_msg = str(e)
                if "Invalid login credentials" in error_msg:
                    st.error("❌ Invalid email or password")
                elif "Email not confirmed" in error_msg:
                    st.error("❌ Please verify your email first")
                else:
                    st.error(f"❌ Login failed: {error_msg}")
        
        # Magic link option
        st.markdown("---")
        st.markdown("**Or login with magic link:**")
        magic_email = st.text_input("Email for magic link", key="magic_email")
        if st.button("Send Magic Link"):
            if magic_email:
                try:
                    self.client.auth.sign_in_with_otp({"email": magic_email})
                    st.success(f"✅ Magic link sent to {magic_email}")
                except Exception as e:
                    st.error(f"❌ Failed to send: {e}")
    
    def _render_signup(self):
        """Render signup form."""
        st.subheader("📝 Create Account")
        
        with st.form("signup_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Sign Up", type="primary")
        
        if submitted:
            if not email or not password:
                st.error("❌ Please fill in all fields")
            elif password != confirm:
                st.error("❌ Passwords don't match")
            elif len(password) < 8:
                st.error("❌ Password must be at least 8 characters")
            else:
                try:
                    response = self.client.auth.sign_up({
                        "email": email,
                        "password": password
                    })
                    
                    if response.user:
                        st.success("✅ Account created! Check your email to verify.")
                        st.session_state.auth_view = "login"
                except Exception as e:
                    st.error(f"❌ Signup failed: {e}")
    
    def _render_forgot_password(self):
        """Render forgot password form."""
        st.subheader("🔑 Reset Password")
        
        email = st.text_input("Enter your email")
        
        if st.button("Send Reset Link", type="primary"):
            if email:
                try:
                    self.client.auth.reset_password_email(email)
                    st.success(f"✅ Password reset link sent to {email}")
                    st.info("Check your email and click the link to reset your password.")
                except Exception as e:
                    # Don't reveal if email exists or not (security)
                    st.success(f"✅ If an account exists for {email}, a reset link has been sent.")
    
    def _render_verify_otp(self):
        """Render 2FA verification."""
        st.subheader("📱 Two-Factor Authentication")
        st.markdown("Enter the 6-digit code from your authenticator app.")
        
        code = st.text_input("2FA Code", max_chars=6)
        
        if st.button("Verify", type="primary"):
            if code and len(code) == 6:
                try:
                    response = self.client.auth.verify_otp({
                        "email": st.session_state.get("mfa_email", ""),
                        "token": code,
                        "type": "totp"
                    })
                    
                    if response.session:
                        st.session_state.sb_session = response.session
                        st.session_state.sb_user = response.user
                        st.success("✅ Verified!")
                        st.rerun()
                except Exception as e:
                    st.error("❌ Invalid code. Please try again.")
    
    def logout(self):
        """Log out the current user."""
        if self.client:
            try:
                self.client.auth.sign_out()
            except Exception:
                pass
        
        st.session_state.sb_user = None
        st.session_state.sb_session = None
        st.session_state.auth_view = "login"
    
    def logout_button(self):
        """Show logout button in sidebar."""
        if st.session_state.sb_user:
            user = st.session_state.sb_user
            email = user.email if hasattr(user, 'email') else str(user)
            st.sidebar.markdown(f"👤 **{email}**")
            if st.sidebar.button("🚪 Logout"):
                self.logout()
                st.rerun()
    
    def get_user(self) -> Optional[User]:
        """Get the current authenticated user."""
        if not st.session_state.sb_user:
            return None
        
        user = st.session_state.sb_user
        return User(
            id=user.id,
            email=user.email,
            name=user.user_metadata.get("name") if user.user_metadata else None,
            email_verified=user.email_confirmed_at is not None,
            mfa_enabled=bool(user.factors) if hasattr(user, 'factors') else False
        )


# ============================================================================
# SETUP HELPER
# ============================================================================

def setup_instructions():
    """Print setup instructions."""
    print("""
🔐 Supabase Auth Setup Guide
=============================

1. CREATE SUPABASE PROJECT
   - Go to https://supabase.com
   - Click "Start your project" (free)
   - Create a new project

2. ENABLE EMAIL AUTH
   - Go to Authentication > Providers
   - Enable "Email" provider
   - Optionally enable "Confirm email" for verification

3. ENABLE 2FA (OPTIONAL)
   - Go to Authentication > Settings
   - Under "Multi-Factor Authentication (MFA)"
   - Enable "TOTP" (Time-based One-Time Password)

4. GET API CREDENTIALS
   - Go to Settings > API
   - Copy "Project URL" and "anon public" key

5. ADD TO SECRETS
   Create/update .streamlit/secrets.toml:
   
   [supabase]
   url = "https://your-project-id.supabase.co"
   key = "your-anon-public-key"

6. INSTALL DEPENDENCIES
   pip install supabase

7. INVITE USERS
   - Go to Authentication > Users
   - Click "Invite user"
   - Enter their email
   - They'll receive an email to set their password

SECURITY NOTES:
- Supabase handles password hashing (bcrypt)
- Rate limiting is built-in
- Sessions are JWT-based with refresh tokens
- All data encrypted at rest and in transit
- SOC2 Type II certified
""")


if __name__ == "__main__":
    setup_instructions()

