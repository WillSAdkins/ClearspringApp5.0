"""Member authentication.

Passwords are hashed with PBKDF2 via werkzeug (bundled with Flask), so no extra
dependency is needed. Magic-link tokens are random, single-use and short-lived.

Nothing here logs or stores a password in plain text at any point.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash, check_password_hash

# Magic links expire quickly — they arrive by email, which isn't a secure channel.
MAGIC_LINK_MINUTES = 20

# How long a signed-in session lasts before needing to sign in again.
SESSION_DAYS = 90

MIN_PASSWORD_LENGTH = 10

# A short list of the passwords people actually pick. Not exhaustive — just
# enough to stop the worst choices without being obstructive.
COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789",
    "1234567890", "qwertyuiop", "letmein123", "welcome123", "admin123",
    "iloveyou1", "sunshine1", "princess1", "football1", "jesuschrist",
    "godisgood", "christian", "hallelujah", "changeme123",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email):
    return bool(email and EMAIL_RE.match(email.strip()))


def normalise_email(email):
    """Lower-case and trim so the same address doesn't create two accounts."""
    return (email or "").strip().lower()


def password_problem(password, email=None, name=None):
    """Return a human explanation if the password is too weak, else None."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"Please use at least {MIN_PASSWORD_LENGTH} characters."
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return "That password is too easy to guess. Please choose another."
    if email and lowered == normalise_email(email):
        return "Your password shouldn't be your email address."
    if name and len(name) > 3 and name.lower() in lowered:
        return "Please don't use your name as your password."
    if len(set(password)) < 4:
        return "Please use a few more different characters."
    return None


def hash_password(password):
    return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)


def verify_password(stored_hash, password):
    if not stored_hash or not password:
        return False
    try:
        return check_password_hash(stored_hash, password)
    except Exception:
        return False


def new_token():
    """A random token for magic links and email verification."""
    return secrets.token_urlsafe(32)


def hash_token(token):
    """Tokens are stored hashed, so a database leak doesn't hand out logins."""
    return hashlib.sha256(token.encode("utf8")).hexdigest()


def tokens_match(stored_hash, token):
    if not stored_hash or not token:
        return False
    return hmac.compare_digest(stored_hash, hash_token(token))


def token_expiry(minutes=MAGIC_LINK_MINUTES):
    return (datetime.now() + timedelta(minutes=minutes)).isoformat()


def token_expired(expires_at):
    if not expires_at:
        return True
    try:
        return datetime.fromisoformat(expires_at) < datetime.now()
    except (ValueError, TypeError):
        return True
