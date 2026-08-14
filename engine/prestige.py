"""Перерождение: сброс уровня ради постоянной прибавки к статам.

Паритет с `core/prestige.py`: тот же порог и та же «Искра Бессмертия»
(+10 % к базовым статам за круг). Числа сверяет `tests/test_parity.py`.

Разница только в хранении: сервер пишет в БД и делает `flush`, движок
меняет поля `Player` и сохраняет через `store`.
"""
REBIRTH_MIN_LEVEL = 15      # ниже этого уровня ритуал недоступен
STAT_GROWTH = 1.10          # +10 % к базовым статам за каждый круг

# Какие поля растут при перерождении и их минимальные значения.
_GROWING = (("strength", 10), ("agility", 10), ("intelligence", 10),
            ("endurance", 10), ("luck", 10), ("max_hp", 100))


def can_rebirth(p):
    """(можно ли, пояснение) — текст показывается игроку как есть."""
    if (p.level or 1) < REBIRTH_MIN_LEVEL:
        return False, (f"Перерождение доступно лишь героям, достигшим "
                       f"{REBIRTH_MIN_LEVEL}-го уровня!")
    return True, "Герой готов совершить ритуал Вечного Перерождения!"


def perform_rebirth(p, store=None) -> dict:
    """Сбросить уровень и выдать постоянный бонус к статам."""
    ok, reason = can_rebirth(p)
    if not ok:
        return {"ok": False, "reason": reason}

    p.rebirth_count = (getattr(p, "rebirth_count", 0) or 0) + 1
    p.level = 1
    p.exp = 0
    for field, floor in _GROWING:
        current = getattr(p, field, floor) or floor
        setattr(p, field, max(floor, int(current * STAT_GROWTH)))
    p.hp = p.max_hp

    if store is not None:
        store.save_player(p)

    return {
        "ok": True,
        "rebirth_count": p.rebirth_count,
        "title": "🔥 ВЕЧНОЕ ПЕРЕРОЖДЕНИЕ СОВЕРШЕНО!",
        "desc": (f"Твоя душа очистилась в пламени! Получен "
                 f"{p.rebirth_count}-й ранг «Искры Бессмертия» "
                 f"(+10% ко всем статам навсегда)!"),
    }
