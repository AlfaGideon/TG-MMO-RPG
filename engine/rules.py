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
            from engine import durability, items
            inst = items.get(store, worn[slot])
            if inst is not None and int(inst.get("idx", -1)) == int(idx):
                if durability.broken(inst):
                    continue                 # сломано — слот не усиливает
                stats_src = inst.get("stats") or {}
        if stats_src is None:
            stats_src = data.ITEMS[idx][5]
        for k, v in stats_src.items():
            total[k] = total.get(k, 0) + v
    return total


def stats(player, store=None):
    """Итоговые статы. Раненый герой слабее — штраф из engine.death."""
    from engine import death, subclasses, talents, titles

    b = bonuses(player, store)
    # Титул, таланты и фамильяр складываются поверх экипировки — в том же
    # порядке и с теми же ключами, что делает core/stats.combat_stats.
    for key, add in titles.title_bonus(player).items():
        if add:
            b[key] = b.get(key, 0) + add
    tal = talents.talent_bonuses(player)
    for key in ("damage", "defense", "luck"):
        if tal.get(key):
            b[key] = b.get(key, 0) + tal[key]
    # Подкласс даёт множители, а не слагаемые. Их нельзя применять к одному
    # лишь бонусу оружия: при уроне 3 и множителе 1.25 int() округлил бы
    # обратно в 3, и берсерк ничем не отличался бы от паладина. Сервер
    # (core/stats.attack_power) множит «сила + урон оружия» — делаем так же,
    # передавая множители дальше в attack_roll и mob_roll.
    sub = subclasses.subclass_bonuses(player)
    k = death.penalty(player)
    if k < 1.0:
        return _wounded_stats(player, b, k)
    return dict(
        damage_mult=sub.get("damage_mult", 1.0),
        defense_mult=sub.get("defense_mult", 1.0),
        vampirism_pct=sub.get("vampirism_pct", 0),
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
    from engine import subclasses as _subs
    sub = _subs.subclass_bonuses(player)
    return dict(
        damage_mult=sub.get("damage_mult", 1.0),
        defense_mult=sub.get("defense_mult", 1.0),
        vampirism_pct=sub.get("vampirism_pct", 0),
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
    from engine import hero, talents
    before_points = talents.points_for_level(player.level)
    player.exp += amount
    gained = 0
    while player.exp >= exp_needed(player.level):
        player.exp -= exp_needed(player.level)
        player.level += 1
        for key, step in hero.growth(player.cls).items():
            setattr(player, key, getattr(player, key, 0) + int(step))
        player.hp = player.max_hp
        gained += 1
    # Очки талантов: одно раз в LEVELS_PER_POINT уровней. Считаем разницу,
    # а не «+1 за уровень» — так герой не потеряет очки при скачке уровней.
    earned = talents.points_for_level(player.level) - before_points
    if earned > 0:
        player.talent_points = (getattr(player, "talent_points", 0) or 0) + earned
    return gained


def attack_roll(player, mob_defense, store=None):
    s = stats(player, store)
    # Множитель подкласса применяется к «сила + урон оружия», а не к одному
    # бонусу экипировки: иначе на малых числах он терялся при округлении.
    base = int((s["strength"] + s["damage"]) * s.get("damage_mult", 1.0))
    crit = random.random() < min(0.35, s["luck"] / 100)
    dmg = max(1, base + random.randint(-2, 4) - mob_defense // 2)
    if crit:
        dmg = int(dmg * 1.8)
    return dmg, crit


def mob_roll(player, mob_damage, store=None):
    s = stats(player, store)
    dodge = random.random() < min(0.25, s["agility"] / 120)
    if dodge:
        return 0, True
    armor = int((s["defense"] + s["endurance"] // 5) * s.get("defense_mult", 1.0))
    dmg = max(0, mob_damage - armor // 2 + random.randint(-1, 2))
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


def clean_name(text, fallback="Герой"):
    """Имя героя без HTML-активных символов, не длиннее 40 знаков.

    Имя попадает в HTML-сообщения бота (боёвка, топ, аукцион, отряды) и на
    веб-экраны. first_name в Telegram может содержать `<`, `>`, `&` — такой
    игрок ломал бы разметку всех сообщений со своим именем, вплоть до
    TelegramBadRequest у бота.
    """
    cleaned = "".join(ch for ch in str(text or "") if ch not in "<>&")
    cleaned = " ".join(cleaned.split()).strip()[:40]
    return cleaned or fallback
