"""Атлас монстров: знание слабостей и бонус охотника.

Общий модуль для обоих стеков — `core/bestiary.py` его реэкспортирует.
Функции работают с любым объектом, у которого есть поле
`bestiary_kills_json`: и с `engine.models.Player`, и с серверным
`core.models.Character`.

Правило простое: каждые `KILLS_PER_STEP` побед над видом дают +1 % урона
по нему, потолок — `MAX_BONUS_PCT`. Записи копятся в бою.
"""
import json

KILLS_PER_STEP = 10     # столько побед даёт +1 % к урону по этому виду
MAX_BONUS_PCT = 15      # потолок прибавки, чтобы ветеран не стал непобедимым


def get_bestiary(character) -> dict:
    raw = getattr(character, "bestiary_kills_json", "") or ""
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        # Битое поле не должно ронять экран профиля и бой.
        return {}


def record_kill(character, mob_name: str) -> int:
    """Записать победу. Возвращает счётчик побед над этим видом."""
    if not mob_name:
        return 0
    b = get_bestiary(character)
    b[mob_name] = b.get(mob_name, 0) + 1
    character.bestiary_kills_json = json.dumps(b, ensure_ascii=False)
    return b[mob_name]


def slayer_pct(character, mob_name: str) -> int:
    """Прибавка к урону по этому виду в процентах (0…MAX_BONUS_PCT)."""
    if not mob_name:
        return 0
    kills = get_bestiary(character).get(mob_name, 0)
    return min(MAX_BONUS_PCT, kills // KILLS_PER_STEP)


def get_mob_slayer_bonus(character, mob_name: str) -> float:
    """Множитель урона по этому виду: 1.0 … 1.15."""
    return 1.0 + slayer_pct(character, mob_name) / 100.0


def bestiary_card_text(character) -> str:
    b = get_bestiary(character)
    if not b:
        return (
            "📖 <b>Атлас монстров и бестиарий</b>\n\n"
            "Твой бестиарий пока пуст.\n\n"
            "<i>Охоться на чудовищ, чтобы изучать их повадки и наносить им "
            "повышенный урон!</i>"
        )
    lines = ["📖 <b>Атлас монстров и знание слабостей</b>\n"]
    for mob_name, count in sorted(b.items(), key=lambda x: -x[1])[:8]:
        bonus = min(MAX_BONUS_PCT, count // KILLS_PER_STEP)
        lines.append(f"• 👾 <b>{mob_name}</b>: побед {count} (Урон: +{bonus}%)")
    return "\n".join(lines)
