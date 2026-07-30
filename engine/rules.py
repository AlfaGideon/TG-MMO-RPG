"""Боевые формулы, прокачка, экипировка."""
import random

from engine import data

SLOTS = {"weapon": "weapon", "armor": "armor", "helmet": "helmet",
         "boots": "boots", "accessory": "accessory"}


def item(idx):
    """Кортеж предмета -> dict."""
    name, typ, rarity, price, icon, bonus = data.ITEMS[idx]
    return dict(idx=idx, name=name, type=typ, rarity=rarity,
                price=price, icon=icon, bonus=bonus)


def bonuses(player, store=None):
    """Суммарные бонусы надетых предметов.

    Если у слота надет именной экземпляр (`player.worn`), берутся его
    откатанные статы, а не значения шаблона: два одинаковых меча дают
    разный бонус. Без store и без экземпляров работает по шаблонам.
    """
    worn = getattr(player, "worn", None) or {}
    total = {}
    for slot, idx in player.equipped.items():
        stats_src = None
        if store is not None and worn.get(slot):
            from engine import items
            inst = items.get(store, worn[slot])
            if inst is not None and int(inst.get("idx", -1)) == int(idx):
                stats_src = inst.get("stats") or {}
        if stats_src is None:
            stats_src = data.ITEMS[idx][5]
        for k, v in stats_src.items():
            total[k] = total.get(k, 0) + v
    return total


def stats(player, store=None):
    """Итоговые статы. Раненый герой слабее — штраф из engine.death."""
    from engine import death

    b = bonuses(player, store)
    k = death.penalty(player)
    if k < 1.0:
        return _wounded_stats(player, b, k)
    return dict(
        strength=player.strength + b.get("strength", 0),
        agility=player.agility + b.get("agility", 0),
        intelligence=player.intelligence + b.get("intelligence", 0),
        endurance=player.endurance + b.get("endurance", 0),
        luck=player.luck + b.get("luck", 0),
        max_hp=player.max_hp + b.get("hp", 0),
        max_mp=player.max_mp + b.get("mp", 0),
        damage=b.get("damage", 0),
        defense=b.get("defense", 0),
    )


def _wounded_stats(player, b, k):
    """Те же статы, но с множителем ранения. Максимумы HP/MP не режем:
    иначе текущее здоровье оказалось бы выше предела и полоска сломалась."""
    scale = lambda v: max(1, int(v * k))
    return dict(
        strength=scale(player.strength + b.get("strength", 0)),
        agility=scale(player.agility + b.get("agility", 0)),
        intelligence=scale(player.intelligence + b.get("intelligence", 0)),
        endurance=scale(player.endurance + b.get("endurance", 0)),
        luck=scale(player.luck + b.get("luck", 0)),
        max_hp=player.max_hp + b.get("hp", 0),
        max_mp=player.max_mp + b.get("mp", 0),
        damage=scale(b.get("damage", 0)) if b.get("damage") else 0,
        defense=scale(b.get("defense", 0)) if b.get("defense") else 0,
    )


def exp_needed(level):
    return level * 100


def add_exp(player, amount):
    """Начисляет опыт, возвращает число новых уровней.

    Прирост статов у каждого класса свой (engine.data.CLASS_GROWTH):
    берсерк растёт в силе, некромант — в интеллекте и мане.
    """
    from engine import hero
    player.exp += amount
    gained = 0
    while player.exp >= exp_needed(player.level):
        player.exp -= exp_needed(player.level)
        player.level += 1
        for key, step in hero.growth(player.cls).items():
            setattr(player, key, getattr(player, key, 0) + int(step))
        player.hp = player.max_hp
        gained += 1
    return gained


def attack_roll(player, mob_defense):
    s = stats(player)
    base = s["strength"] + s["damage"]
    crit = random.random() < min(0.35, s["luck"] / 100)
    dmg = max(1, base + random.randint(-2, 4) - mob_defense // 2)
    if crit:
        dmg = int(dmg * 1.8)
    return dmg, crit


def mob_roll(player, mob_damage):
    s = stats(player)
    dodge = random.random() < min(0.25, s["agility"] / 120)
    if dodge:
        return 0, True
    dmg = max(0, mob_damage - s["endurance"] // 5 - s["defense"] // 2 + random.randint(-1, 2))
    return dmg, False


def loot_roll(mob_index):
    """Шанс выпадения предмета с моба."""
    if random.random() > 0.35:
        return -1
    level = data.MOBS[mob_index][2]
    pool = [i for i, it in enumerate(data.ITEMS) if it[3] <= 20 + level * 15]
    return random.choice(pool) if pool else -1


def bar(cur, mx, fill="🟥", empty="⬛", size=10):
    if mx <= 0:
        return ""
    n = max(0, min(size, int(cur / mx * size)))
    return fill * n + empty * (size - n)
