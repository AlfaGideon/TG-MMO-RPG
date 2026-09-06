"""Настройки вестей: серверный реэкспорт общих правил.

Правила — в `engine/notify.py` (единственный источник правды). Здесь
только серверные удобства поверх JSON-поля `Character.prefs`.
"""
from engine.notify import (  # noqa: F401
    CHANNELS,
    DEFAULTS,
    enabled,
    in_quiet_hours,
    normalized,
    of,
    set_pref,
    toggle,
)


def prefs_of(character: "object") -> dict:
    """Настройки серверного героя (поле `prefs` — JSON-текст или dict)."""
    raw = getattr(character, "prefs", None)
    if isinstance(raw, str):
        import json
        try:
            return normalized(json.loads(raw or "{}"))
        except Exception:
            return normalized({})
    return normalized(raw)


def set_pref_on(character: "object", key: str, value) -> dict:
    """Записать одну настройку серверного героя (поля — JSON-текст)."""
    import json
    prefs = prefs_of(character)
    if key in DEFAULTS:
        if key in ("quiet_start", "quiet_end"):
            if isinstance(value, str) and len(value) == 5 and value[2] == ":":
                prefs[key] = value
        else:
            prefs[key] = bool(value)
    character.prefs = json.dumps(prefs, ensure_ascii=False)
    return prefs
