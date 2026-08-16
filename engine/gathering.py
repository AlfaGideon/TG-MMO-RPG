"""Мирные занятия: рыбалка, травничество и раскопки.

Правила и таблицы шансов — **единственный источник правды** для обоих
стеков: `core/gathering.py` и `core/archaeology.py` берут их отсюда,
поэтому улов и находки одинаковы в браузере и в боте. Различается только
хранилище: сервер пишет предметы в БД, движок — в список `p.inventory`.
"""
import random

# ── рыбалка ─────────────────────────────────────────────────
# Пороги накопительные: сравниваются с одним броском random().
FISH_HEAL_HP = 30
FISH_HEAL_MP = 20
FISH_GOLD = (30, 80)        # диапазон находки в бронзе
FISH_EXP = 15

FISH_CHANCE_HEAL = 0.40     # < 0.40 — форель, лечит HP
FISH_CHANCE_MANA = 0.70     # < 0.70 — карп, лечит MP
FISH_CHANCE_GOLD = 0.90     # < 0.90 — кошель; выше — сорвалась

# ── травничество ────────────────────────────────────────────
HERBS = (
    ("🌿 Лунноцвет", "Редкий светящийся цветок"),
    ("🍄 Пепельник", "Гриб, растущий на пожарищах"),
    ("🌱 Лечебная трава", "Трава с горьким целебным соком"),
)
HERB_EXP = 20
HERB_PRICE = 15             # цена травы в бронзе

# ── археология ──────────────────────────────────────────────
FRAGMENTS_FOR_MAP = 5       # столько осколков складываются в карту
TREASURE_GOLD = (300, 700)
TREASURE_ASH = 30
TREASURE_EXP = 200


def roll_fish(rng=None):
    """Что попалось на крючок. Возвращает (вид, величина, опыт).

    Вид: heal | mana | gold | miss. Числа берёт вызывающий код и
    применяет к своему герою — так таблица шансов остаётся общей.
    """
    rng = rng or random
    roll = rng.random()
    if roll < FISH_CHANCE_HEAL:
        return "heal", FISH_HEAL_HP, FISH_EXP
    if roll < FISH_CHANCE_MANA:
        return "mana", FISH_HEAL_MP, FISH_EXP
    if roll < FISH_CHANCE_GOLD:
        return "gold", rng.randint(*FISH_GOLD), FISH_EXP
    return "miss", 0, FISH_EXP


def fish_text(kind: str, amount: int) -> str:
    """Текст улова — один и тот же в обоих стеках."""
    if kind == "heal":
        return (f"🐟 Ты выудил сочную Глубинную Форель! "
                f"Она восстановила тебе +{amount} HP.")
    if kind == "mana":
        return (f"✨ Ты поймал светящегося Зеркального Карпа! "
                f"Он восстановил тебе +{amount} MP.")
    if kind == "gold":
        return (f"💰 К крючку прицепился старый затонувший кошель со дна! "
                f"Найдено +{amount}🟤 монет.")
    return "🌊 Поплавок покачался на волнах, но рыба сорвалась с крючка. Попробуй ещё раз!"


def roll_herb(rng=None):
    """Какая трава попалась: (название, описание)."""
    rng = rng or random
    return rng.choice(HERBS)


def herb_text(name: str) -> str:
    return (f"Ты аккуратно срезал {name}! Растение аккуратно уложено "
            f"в сумку (+{HERB_EXP}⭐ опыта).")


def fragment_progress(found: int) -> tuple:
    """(сколько осколков теперь, сложилась ли карта) после находки."""
    found = int(found or 0) + 1
    if found >= FRAGMENTS_FOR_MAP:
        return 0, True
    return found, False


def fragment_text(found: int, formed_map: bool, coords=None) -> str:
    if formed_map:
        where = f" Тайник скрыт на координатах [{coords[0]},{coords[1]}]!" if coords else ""
        return (f"📜 <b>Все {FRAGMENTS_FOR_MAP} фрагментов собраны!</b>\n\n"
                f"Ты восстановил древнюю карту сокровищ!{where}")
    return f"🔍 <b>Найден фрагмент скрижали ({found}/{FRAGMENTS_FOR_MAP})!</b>"
