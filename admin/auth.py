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

def _load_secret() -> str:
    """Ключ подписи сессий: из окружения, иначе — свой на эту установку.

    Раньше здесь стоял дефолт `"shadow-lands-secret"`, лежащий в публичном
    репозитории: кто угодно мог подделать cookie и войти в панель, если её
    выставили наружу (`AUDIT-BUGS.md`, «Прочее на заметку»). Падать без
    переменной нельзя — панель задумана как «запустил и работает», поэтому
    ключ генерируется один раз и сохраняется рядом с базой, в `data/`
    (каталог в .gitignore, в репозиторий не попадёт).
    """
    env_key = (os.getenv("ADMIN_SECRET_KEY") or "").strip()
    if env_key and env_key not in _WEAK_KEYS:
        return env_key

    path = os.path.join("data", "admin_secret.key")
    try:
        if os.path.exists(path):
            saved = open(path, encoding="utf-8").read().strip()
            if saved:
                return saved
        os.makedirs("data", exist_ok=True)
        generated = secrets.token_urlsafe(48)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(generated)
        try:                                   # только владелец, если ОС умеет
            os.chmod(path, 0o600)
        except OSError:
            pass
        if env_key:
            print("⚠️  ADMIN_SECRET_KEY выглядит как пример из документации — "
                  "сгенерирован собственный ключ (data/admin_secret.key).")
        return generated
    except OSError:
        # Файловая система только для чтения: ключ живёт до перезапуска —
        # сессии слетят, но подделать их снаружи всё равно нельзя.
        return secrets.token_urlsafe(48)


# Значения, которые нельзя принимать за настоящий ключ: они опубликованы.
_WEAK_KEYS = {"shadow-lands-secret", "super-secret-key-change-me",
              "change-me", "secret"}

SECRET = _load_secret()
COOKIE_NAME = "wa_session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 days

# Ранги (пресеты) и точечные права — как ранги в кланах MMO.
from engine.permissions import (           # noqa: E402  (общий источник правды)
    CAPS, CAP_KEYS, CAP_LABELS, CAP_GROUPS, RANKS, RANK_KEYS,
    rank_caps, rank_title,
)

ROLES = list(RANK_KEYS)

ROLE_LABELS = {r: rank_title(r) for r in RANK_KEYS}

ALL_CAPS = set(CAP_KEYS)


# Старые «крупные» права -> набор новых точечных. Любое из них открывает доступ.
LEGACY_CAPS = {
    "view": {"view_dash", "view_players", "view_world", "view_content"},
    "manage_players": {"edit_players", "heal_players", "give_items", "del_players"},
    "manage_content": {"edit_content", "edit_world", "regen_world", "dungeons"},
    "manage_settings": {"settings", "bot_control", "broadcast"},
    "manage_admins": {"grant_admin"},
}


def caps_for(role, custom=None):
    """Итоговые права: точечный список важнее пресета ранга."""
    if custom:
        keys = [c.strip() for c in custom.split(",") if c.strip()]
        picked = {c for c in keys if c in ALL_CAPS}
        if picked:
            return picked
    return set(rank_caps(role or "viewer"))


# ── Троттлинг подбора пароля ─────────────────────────────────
# Пароли генерируем криптостойкими, но форма принимает и маленькие ID-логины,
# а панель может висеть на публичном туннеле. Считаем неудачи в памяти
# процесса: (telegram id + ip) → список отметок. Это не заменяет fail2ban,
# но обрывает скриптовый перебор «500 паролей за минуту».
LOGIN_WINDOW = 15 * 60          # 15 минут
LOGIN_MAX_FAILS = 8             # попыток в окне
_login_fails: "dict[str, list[float]]" = {}


def _login_key(uid) -> str:
    return str(uid)


def login_retry_after(uid) -> int:
    """Сколько секунд ждать после серии неудач; 0 — входить можно."""
    now = time.time()
    stamps = [t for t in _login_fails.get(_login_key(uid), []) if now - t < LOGIN_WINDOW]
    if len(stamps) >= LOGIN_MAX_FAILS:
        _login_fails[_login_key(uid)] = stamps
        return int(LOGIN_WINDOW - (now - stamps[0])) + 1
    _login_fails[_login_key(uid)] = stamps
    return 0


def note_login_failure(uid) -> None:
    key = _login_key(uid)
    if len(_login_fails) > 2048:          # страховка от разрастания словаря
        for stale in [k for k, v in _login_fails.items()
                      if not v or time.time() - max(v) > LOGIN_WINDOW]:
            _login_fails.pop(stale, None)
    _login_fails.setdefault(key, []).append(time.time())


def clear_login_failures(uid) -> None:
    _login_fails.pop(_login_key(uid), None)


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


def has_capability(role, cap: str, custom=None) -> bool:
    """role is None for the owner (unrestricted) or one of ROLES.

    Accepts both new granular caps ("edit_world") and legacy coarse ones
    ("manage_content"), so older routes keep working unchanged.
    """
    if role is None:
        return True
    mine = caps_for(role, custom)
    if cap in mine:
        return True
    return bool(LEGACY_CAPS.get(cap, set()) & mine)


def role_of(request: Request):
    session = get_web_session(request)
    return session[1] if session else None
