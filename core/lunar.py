"""Лунно-солнечные циклы: серверная часть.

Каталог фаз и расчёт от времени — общие для обоих стеков и живут в
`engine/lunar.py` (единственный источник правды). Здесь остаётся только
серверное хранилище ручной заморозки: строка в таблице `AppSetting`.
"""
from engine.lunar import (  # noqa: F401
    CYCLE_DURATION_HOURS,
    PHASES,
    get_current_lunar_phase,
    lunar_phase_banner,
    phase_by_key,
)

# ── ручное переопределение фазы (админка) ───────────────────
# Фаза вычисляется от времени, поэтому «принудительно поставить
# полнолуние» без хранимого состояния невозможно. Оверрайд живёт в
# AppSetting: пусто — обычный расчёт по часам, ключ фазы — заморозка.

LUNAR_OVERRIDE_KEY = "lunar_phase_override"


def phase_by_key(key: str) -> dict | None:
    return next((p for p in PHASES if p["key"] == key), None)


async def get_phase(session) -> dict:
    """Фаза с учётом админского оверрайда. Для игровых расчётов."""
    from sqlalchemy import select
    from core.models import AppSetting

    row = (await session.execute(
        select(AppSetting).where(AppSetting.key == LUNAR_OVERRIDE_KEY)
    )).scalar_one_or_none()
    if row is not None and (row.value or "").strip():
        forced = phase_by_key(row.value.strip())
        if forced is not None:
            return forced
    return get_current_lunar_phase()


async def set_override(session, key: str) -> dict | None:
    """Заморозить фазу (пустой ключ — вернуть естественный цикл)."""
    from sqlalchemy import select
    from core.models import AppSetting

    key = (key or "").strip()
    if key and phase_by_key(key) is None:
        raise ValueError(f"Неизвестная фаза: {key}")

    row = (await session.execute(
        select(AppSetting).where(AppSetting.key == LUNAR_OVERRIDE_KEY)
    )).scalar_one_or_none()
    if row is None:
        row = AppSetting(key=LUNAR_OVERRIDE_KEY, value=key)
        session.add(row)
    else:
        row.value = key
    await session.flush()
    return phase_by_key(key) if key else None
