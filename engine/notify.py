"""🔕 Настройки вестей: что игроку присылать, а что — нет.

Идея 1.5 из IDEAS-new-2026.md. Правила — единственный источник правды для
обоих стеков (как у осад и домашнего сундука): `core/notify.py`
реэкспортирует их, поэтому бот и браузерный движок не разъедутся.

Сейчас напоминания в игре три (bot/reminders.py): аукцион, портал и вызов
на дуэль. Здесь — каналы под них плюс «тихие часы» (не слать в окно без
дайджеста). Дайджест-копилку намеренно не заводим в первой итерации:
честнее выключить шум, чем обещать накопление сообщений.
"""
import time

# Каналы, которые можно выключить отдельно.
CHANNELS = (
    ("auction", "⏳ Аукцион"),
    ("portal", "🌀 Портал"),
    ("duel", "⚔️ Дуэли"),
)

DEFAULTS = {
    "auction": True,
    "portal": True,
    "duel": True,
    "quiet_enabled": False,
    "quiet_start": "22:00",
    "quiet_end": "08:00",
}


def _valid_time(text) -> bool:
    if not isinstance(text, str) or len(text) != 5 or text[2] != ":":
        return False
    try:
        h, m = text.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except ValueError:
        return False


def normalized(raw=None) -> dict:
    """Слить пользовательские настройки с дефолтами (битые значения — прочь)."""
    raw = raw or {}
    if not isinstance(raw, dict):
        raw = {}
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        val = raw.get(key)
        if key in ("quiet_start", "quiet_end"):
            if _valid_time(val):
                out[key] = val
        elif isinstance(val, bool):
            out[key] = val
    return out


def enabled(raw, channel: str) -> bool:
    """Включён ли канал. Незнакомый канал считаем выключенным."""
    if channel not in DEFAULTS:
        return False
    return bool(normalized(raw).get(channel, True))


# ── тихие часы ──────────────────────────────────────────────
def _minutes(text: str) -> int:
    h, m = (text or "00:00").split(":")
    return (int(h) * 60 + int(m)) % (24 * 60)


def in_quiet_hours(raw=None, ts=None) -> bool:
    """True — сейчас окно, в которое личные вести лучше не слать.

    Границы хранятся минутами от полуночи; окно может переходить через
    полночь (22:00 → 08:00). По умолчанию выключено — поведение игры не
    меняется, пока игрок сам не включит тихие часы.
    """
    prefs = normalized(raw)
    if not prefs.get("quiet_enabled", False):
        return False
    now_min = (time.localtime(ts if ts is not None else time.time())[3] * 60
               + time.localtime(ts if ts is not None else time.time())[4])
    start = _minutes(prefs["quiet_start"])
    end = _minutes(prefs["quiet_end"])
    if start <= end:
        return start <= now_min < end
    return now_min >= start or now_min < end


def toggle(raw=None, key: str = "") -> tuple[bool, dict]:
    """Переключить булев канал (или тихие часы). Возвращает (новое, prefs)."""
    prefs = normalized(raw)
    if key in DEFAULTS:
        prefs[key] = not prefs.get(key, False)
    return bool(prefs.get(key, False)), prefs


# ── работа с игровым объектом (Player / Character) ─────────
def of(player) -> dict:
    return normalized(getattr(player, "prefs", None))


def save(player, store=None) -> None:
    """Записать настройки в хранилище (браузерный движок)."""
    if store is not None:
        store.save_player(player)


def set_pref(player, key: str, value) -> dict:
    prefs = of(player)
    if key in DEFAULTS:
        if key in ("quiet_start", "quiet_end"):
            if _valid_time(value):
                prefs[key] = value
        else:
            prefs[key] = bool(value)
    player.prefs = dict(prefs)
    return prefs
