"""Атлас монстров (Bestiary): знание слабостей и бонусы охотника."""
import json
from core.models import Character


def get_bestiary(character: Character) -> dict:
    raw = getattr(character, "bestiary_kills_json", "") or ""
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def record_kill(character: Character, mob_name: str) -> int:
    """Записать убийство моба в бестиарий."""
    if not mob_name:
        return 0
    b = get_bestiary(character)
    b[mob_name] = b.get(mob_name, 0) + 1
    character.bestiary_kills_json = json.dumps(b, ensure_ascii=False)
    return b[mob_name]


def get_mob_slayer_bonus(character: Character, mob_name: str) -> float:
    """Бонус к урону по этому типу монстра (+1% за каждые 10 убийств, макс +15%)."""
    if not mob_name:
        return 1.0
    kills = get_bestiary(character).get(mob_name, 0)
    bonus_pct = min(15, (kills // 10))
    return 1.0 + bonus_pct / 100.0


def bestiary_card_text(character: Character) -> str:
    b = get_bestiary(character)
    if not b:
        return (
            "📖 <b>Атлас монстров и бестиарий</b>\n\n"
            "Твой бестиарий пока пуст.\n\n"
            "<i>Охоться на чудовищ, чтобы изучать их повадки и наносить им повышенный урон!</i>"
        )
    lines = ["📖 <b>Атлас монстров и знание слабостей</b>\n"]
    for mob_name, count in sorted(b.items(), key=lambda x: -x[1])[:8]:
        bonus = min(15, (count // 10))
        lines.append(f"• 👾 <b>{mob_name}</b>: побед {count} (Урон: +{bonus}%)")
    return "\n".join(lines)
