"""Карма: моральный путь героя — Благочестивый vs Осквернитель.

Паритет с серверным стеком: те же пороги, дельты поступков и тексты, что в
`core/karma.py`. Числа стережёт `tests/test_parity.py` (раздел «Карма»).

Как карма меняется (единственные точки, больше нигде):
  • упокоение нежити        — +KILL_UNDEAD (в `engine/combat._reward`);
  • победа над мировым боссом — +KILL_BOSS (в `engine/worldboss._reward_all`);
  • разграбление чужой могилы — GRAVE_LOOT (в `engine/death.claim`).

Что карма даёт:
  • ≥ PIOUS_KARMA  — Благочестивый: +15 % к лечению (`engine/inventory.use`),
    защита от фатального удара (зарезервировано, см. IDEAS-100.md);
  • ≤ DEFILED_KARMA — Осквернитель: +20 % к урону магии Тьмы
    (`engine/combat.action`, школа `shadow`);
  • между порогами — нейтрально, без эффектов.
"""
from engine.models import Player

MAX_KARMA = 500
MIN_KARMA = -500

PIOUS_KARMA = 150      # порог «Благочестивый»
DEFILED_KARMA = -150   # порог «Осквернитель»

KILL_UNDEAD = 2        # карма за упокоенную нежить
KILL_BOSS = 5          # карма за мирового босса
GRAVE_LOOT = -3        # карма за разграбление чужой могилы

HEAL_BONUS = 0.15          # +15 % к лечению у Благочестивых
DARK_DAMAGE_BONUS = 0.20   # +20 % к урону Тьмы у Осквернителей
DARK_SCHOOL = "shadow"     # ключ школы Тьмы в data.MAGIC_SCHOOLS

# Нежить — по подстроке в имени твари (как в engine/factions.UNDEAD).
UNDEAD = ("зомби", "скелет", "призрак", "костя", "могильн", "плакальщ",
          "голем из костей", "жрец")


def change_karma(p: Player, delta: int) -> int:
    """Изменить карму с клампом в [MIN_KARMA, MAX_KARMA]. Возвращает новое."""
    cur = getattr(p, "karma_score", 0) or 0
    new_val = max(MIN_KARMA, min(MAX_KARMA, cur + int(delta)))
    p.karma_score = new_val
    return new_val


def karma_status(p: Player):
    """(значок, титул, описание эффекта). Тексты идентичны core/karma.py."""
    score = getattr(p, "karma_score", 0) or 0
    if score >= PIOUS_KARMA:
        return ("✨", "Благочестивый праведник",
                "Благословение света: +15% к лечению и защита от фатального удара.")
    if score <= DEFILED_KARMA:
        return ("💀", "Осквернитель могил",
                "Тёмное клеймо: +20% к урону магии Тьмы, но паладины смотрят волком.")
    return ("⚖️", "Нейтральный странник", "Твои дела пока чисты и не отягощены грехом.")


def pious(p: Player) -> bool:
    return (getattr(p, "karma_score", 0) or 0) >= PIOUS_KARMA


def defiled(p: Player) -> bool:
    return (getattr(p, "karma_score", 0) or 0) <= DEFILED_KARMA


def is_undead(mob_name: str) -> bool:
    return any(w in (mob_name or "").lower() for w in UNDEAD)


def on_kill(p: Player, mob_name: str):
    """Карма за убитую тварь. Возвращает строку для экрана победы ('' если ничего)."""
    if is_undead(mob_name):
        new_val = change_karma(p, KILL_UNDEAD)
        return f"✨ Карма: <b>+{KILL_UNDEAD}</b> за упокоение нежити (теперь {new_val})."
    return ""


def on_boss(p: Player):
    """Карма за победу над мировым боссом."""
    new_val = change_karma(p, KILL_BOSS)
    return f"✨ Карма: <b>+{KILL_BOSS}</b> — мир вздохнул свободнее (теперь {new_val})."


def on_grave_loot(p: Player):
    """Карма за разграбление чужой могилы."""
    new_val = change_karma(p, GRAVE_LOOT)
    return f"💀 Карма: <b>{GRAVE_LOOT}</b> — разрытая могила не принесёт покоя (теперь {new_val})."


def karma_line(p: Player) -> str:
    """Строка для профиля: значок, число и титул."""
    icon, title, _desc = karma_status(p)
    return f"{icon} Карма: <b>{getattr(p, 'karma_score', 0) or 0}</b> — {title}"
