"""Система кармы и морального пути: Благочестивый vs Осквернитель.

Паритет с браузерным стеком: те же пороги, дельты поступков и тексты, что
в `engine/karma.py`. Числа стережёт `tests/test_parity.py` (раздел «Карма»).

Точки изменения кармы в боте (единственные):
  • упокоение нежити          — +KILL_UNDEAD (bot/handlers/battle.py,
    `_finish_victory`);
  • победа над мировым боссом — +KILL_BOSS (bot/handlers/world_extra.py,
    награда за босса);
  • разграбление чужой могилы — GRAVE_LOOT (bot/handlers/world_extra.py
    `claim_grave` и bot/handlers/location.py `harvest_ash`).

Эффекты порогов:
  • ≥ PIOUS_KARMA  — +15 % к лечению (bot/handlers/inventory.py `use_item`);
  • ≤ DEFILED_KARMA — +20 % к урону магии Тьмы (bot/handlers/battle.py
    `combat_skill`, школа `shadow`).
"""
from core.models import Character

MAX_KARMA = 500
MIN_KARMA = -500

PIOUS_KARMA = 150      # порог «Благочестивый»
DEFILED_KARMA = -150   # порог «Осквернитель»

KILL_UNDEAD = 2        # карма за упокоенную нежить
KILL_BOSS = 5          # карма за мирового босса
GRAVE_LOOT = -3        # карма за разграбление чужой могилы

HEAL_BONUS = 0.15          # +15 % к лечению у Благочестивых
DARK_DAMAGE_BONUS = 0.20   # +20 % к урону Тьмы у Осквернителей
DARK_SCHOOL = "shadow"     # ключ школы Тьмы

# Нежить — по подстроке в имени твари.
UNDEAD = ("зомби", "скелет", "призрак", "костя", "могильн", "плакальщ",
          "голем из костей", "жрец")


def change_karma(character: Character, delta: int) -> int:
    """Изменить показатель кармы с клампом в [MIN_KARMA, MAX_KARMA]."""
    cur = getattr(character, "karma_score", 0) or 0
    new_val = max(MIN_KARMA, min(MAX_KARMA, cur + int(delta)))
    character.karma_score = new_val
    return new_val


def karma_status(character: Character) -> tuple:
    """(значок, титул кармы, описание эффекта)."""
    score = getattr(character, "karma_score", 0) or 0
    if score >= PIOUS_KARMA:
        return ("✨", "Благочестивый праведник",
                "Благословение света: +15% к лечению и защита от фатального удара.")
    if score <= DEFILED_KARMA:
        return ("💀", "Осквернитель могил",
                "Тёмное клеймо: +20% к урону магии Тьмы, но паладины смотрят волком.")
    return ("⚖️", "Нейтральный странник", "Твои дела пока чисты и не отягощены грехом.")


def pious(character: Character) -> bool:
    return (getattr(character, "karma_score", 0) or 0) >= PIOUS_KARMA


def defiled(character: Character) -> bool:
    return (getattr(character, "karma_score", 0) or 0) <= DEFILED_KARMA


def is_undead(mob_name: str) -> bool:
    return any(w in (mob_name or "").lower() for w in UNDEAD)


def on_kill(character: Character, mob) -> str:
    """Карма за убитую тварь (моб с атрибутом name или просто строка).

    Возвращает строку для экрана победы ('' — ничего не изменилось).
    """
    name = getattr(mob, "name", mob) or ""
    if is_undead(str(name)):
        new_val = change_karma(character, KILL_UNDEAD)
        return f"✨ Карма: <b>+{KILL_UNDEAD}</b> за упокоение нежити (теперь {new_val})."
    return ""


def on_boss(character: Character) -> str:
    new_val = change_karma(character, KILL_BOSS)
    return f"✨ Карма: <b>+{KILL_BOSS}</b> — мир вздохнул свободнее (теперь {new_val})."


def on_grave_loot(character: Character) -> str:
    new_val = change_karma(character, GRAVE_LOOT)
    return f"💀 Карма: <b>{GRAVE_LOOT}</b> — разрытая могила не принесёт покоя (теперь {new_val})."


def karma_line(character: Character) -> str:
    """Строка для профиля: значок, число и титул."""
    icon, title, _desc = karma_status(character)
    return f"{icon} Карма: <b>{getattr(character, 'karma_score', 0) or 0}</b> — {title}"
