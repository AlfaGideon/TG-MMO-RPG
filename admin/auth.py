"""
Lightweight role-based access for the admin web panel.

The panel's original owner opens it directly (no login) and always has full
access — this preserves existing behavior for local/Replit/Render deploys.

Players granted "web admin" access by the owner get a scoped role
(viewer / moderator / admin) and log in via a small password form. Their
session is a signed cookie; no extra dependencies are used (hmac + hashlib).
"""
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Request

SECRET = os.getenv("ADMIN_SECRET_KEY", "shadow-lands-secret")
COOKIE_NAME = "wa_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 days

ROLES = ["viewer", "moderator", "admin"]

ROLE_LABELS = {
    "viewer": "👁 Наблюдатель (только просмотр)",
    "moderator": "🛠 Модератор (управление игроками)",
    "admin": "👑 Администратор (полный доступ)",
}

# Capabilities granted to each role. `None` (no cookie / direct owner access)
# always has every capability.
CAPS_BY_ROLE = {
    "viewer": {"view"},
    "moderator": {"view", "manage_players"},
    "admin": {"view", "manage_players", "manage_content", "manage_settings", "manage_admins"},
}

ALL_CAPS = {"view", "manage_players", "manage_content", "manage_settings", "manage_admins"}


def generate_password(length: int = 10) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    salt, digest = stored_hash.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(check, digest)


def _sign(payload: str) -> str:
    return hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_token(user_id: int, role: str) -> str:
    issued = int(time.time())
    payload = f"{user_id}:{role}:{issued}"
    sig = _sign(payload)
    return f"{payload}:{sig}"


def parse_session_token(token: str):
    try:
        user_id_s, role, issued_s, sig = token.split(":")
        payload = f"{user_id_s}:{role}:{issued_s}"
        if not hmac.compare_digest(_sign(payload), sig):
            return None
        issued = int(issued_s)
        if time.time() - issued > SESSION_MAX_AGE:
            return None
        if role not in ROLES:
            return None
        return int(user_id_s), role
    except Exception:
        return None


def get_web_session(request: Request):
    """Returns (user_id, role) if the request carries a valid granted-access
    cookie, otherwise None (meaning: direct/owner access, full rights)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return parse_session_token(token)


def has_capability(role, cap: str) -> bool:
    """role is None for the owner (unrestricted) or one of ROLES."""
    if role is None:
        return True
    return cap in CAPS_BY_ROLE.get(role, set())


def role_of(request: Request):
    session = get_web_session(request)
    return session[1] if session else None
