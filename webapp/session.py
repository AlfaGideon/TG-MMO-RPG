"""Кто сейчас в панели: владелец или админ, вошедший через /admin-login.

Страница входа (admin-login.html) кладёт в localStorage ключ
`shadowlands_session`. Здесь мы его читаем и превращаем в объект Player,
чтобы права проверялись теми же engine.permissions, что и в боте.
"""
import json

KEY = "shadowlands_session"
MAX_AGE_MS = 12 * 60 * 60 * 1000            # 12 часов


def _raw():
    try:
        from js import window
        return window.localStorage.getItem(KEY)
    except Exception:                                    # вне браузера
        return None


def _drop():
    try:
        from js import window
        window.localStorage.removeItem(KEY)
    except Exception:
        pass


def _asked_logout():
    """index.html?logout=1 — выход, на который уводит /admin-logout."""
    try:
        from js import URLSearchParams, window
        return URLSearchParams.new(window.location.search).get("logout") == "1"
    except Exception:
        return False


def load(store):
    """Возвращает Player-админа либо None (владелец панели)."""
    if _asked_logout():
        _drop()
        return None
    raw = _raw()
    if not raw:
        return None
    try:
        blob = json.loads(str(raw))
        uid = int(blob.get("uid") or 0)
        at = int(blob.get("at") or 0)
    except Exception:
        _drop()
        return None
    if not uid:
        _drop()
        return None

    try:
        from js import Date
        if at and Date.now() - at > MAX_AGE_MS:
            _drop()
            return None
    except Exception:
        pass

    p = store.players.get(uid)
    if p is None or not getattr(p, "is_web_admin", False):
        _drop()
        return None
    return p


def logout():
    _drop()


def label(actor):
    from engine import permissions
    if actor is None:
        return "Владелец панели"
    return f"{actor.name} · {permissions.rank_title(actor.web_admin_role)}"
