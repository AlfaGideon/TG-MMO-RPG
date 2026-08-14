"""Лунные фазы: общий каталог и расчёт от времени.

Каталог фаз и множители — **единственный источник правды** для обоих
стеков: `core/lunar.py` реэкспортирует `PHASES` отсюда, поэтому
полнолуние одинаково злит тварей и в браузере, и в боте.

Различие стеков только в хранилище ручной заморозки фазы:
  * сервер — строка в таблице `AppSetting` (`core/lunar.get_phase`);
  * браузер — ключ в `store.settings` (`phase_of` ниже).
Сам расчёт от времени общий, поэтому фаза совпадает без синхронизации.
"""
import time

PHASES = [
    {
        "key": "full_moon",
        "name": "🌕 Полнолуние",
        "desc": "Монстры впадают в неистовство (+30% спавн мобов, +25% дроп материалов).",
        "mob_mult": 1.30,
        "material_mult": 1.25,
        "magic_dark_mult": 1.0,
    },
    {
        "key": "waning_moon",
        "name": "🌘 Убывающая Луна",
        "desc": "Время затишья: жители спокойны, торговцы дают −10% скидки.",
        "mob_mult": 0.85,
        "material_mult": 1.0,
        "magic_dark_mult": 1.0,
    },
    {
        "key": "new_moon",
        "name": "🌑 Новолуние (Тёмная Луна)",
        "desc": "Врата бездны приоткрыты: магия тьмы усилена на +25%, нежить восстаёт быстрее.",
        "mob_mult": 1.15,
        "material_mult": 1.0,
        "magic_dark_mult": 1.25,
    },
    {
        "key": "waxing_moon",
        "name": "🌓 Растущая Луна",
        "desc": "Прилив жизненных сил: шанс критического удара всех героев увеличен на +10%.",
        "mob_mult": 1.0,
        "material_mult": 1.10,
        "magic_dark_mult": 1.0,
    },
]

CYCLE_DURATION_HOURS = 24        # полный цикл за сутки
OVERRIDE_KEY = "lunar_phase"     # ключ ручной заморозки в store.settings


def get_current_lunar_phase(timestamp=None) -> dict:
    """Естественная фаза по серверному времени: 4 фазы по 6 часов."""
    t = time.time() if timestamp is None else timestamp
    hours = (t / 3600) % CYCLE_DURATION_HOURS
    phase_idx = int(hours // (CYCLE_DURATION_HOURS / len(PHASES)))
    return PHASES[phase_idx % len(PHASES)]


def phase_by_key(key: str):
    return next((p for p in PHASES if p["key"] == key), None)


def phase_of(store) -> dict:
    """Фаза с учётом заморозки из панели (браузерный стек)."""
    if store is None:
        return get_current_lunar_phase()
    forced = (store.settings.get(OVERRIDE_KEY) or "").strip()
    if forced:
        found = phase_by_key(forced)
        if found is not None:
            return found
    return get_current_lunar_phase()


def set_override(store, key: str):
    """Заморозить фазу (пустой ключ — вернуть естественный цикл)."""
    key = (key or "").strip()
    if key and phase_by_key(key) is None:
        raise ValueError(f"Неизвестная фаза: {key}")
    store.settings[OVERRIDE_KEY] = key
    store.save()
    return phase_by_key(key) if key else None


def lunar_phase_banner(store=None) -> str:
    phase = phase_of(store) if store is not None else get_current_lunar_phase()
    return f"{phase['name']}\n<i>{phase['desc']}</i>"
