"""Расширенные статы и Gear Score."""

def calculate_gear_score(character):
    """Подсчёт Gear Score на основе статов."""
    gs = 0
    gs += getattr(character, "gear_score", 0)
    gs += int(getattr(character, "strength", 0) * 0.8)
    gs += int(getattr(character, "agility", 0) * 0.7)
    gs += int(getattr(character, "dexterity", 0) * 0.9)
    gs += int(getattr(character, "intelligence", 0) * 0.6)
    gs += int(getattr(character, "crit_chance", 0) * 2)
    gs += int(getattr(character, "crit_damage", 0) * 0.8)
    gs += int(getattr(character, "life_on_hit", 0) * 3)
    gs += int(getattr(character, "thorns_damage", 0) * 2)
    return max(0, gs)


def get_russian_stat_name(key: str) -> str:
    """Русские названия всех статов."""
    names = {
        "gear_score": "Очки снаряжения (GS)",
        "max_hp": "Макс. здоровье",
        "damage": "Урон",
        "defense": "Защита",
        "damage_reduction": "Снижение урона",
        "strength": "Сила",
        "agility": "Ловкость",
        "dexterity": "Ловкость",
        "intelligence": "Интеллект",
        "crit_chance": "Шанс крита",
        "crit_damage": "Урон крита",
        "double_hit_chance": "Шанс двойного удара",
        "dodge_chance": "Шанс уклонения",
        "block_chance": "Шанс блока",
        "life_on_hit": "Жизнь за удар",
        "life_on_kill": "Жизнь за убийство",
        "thorns_damage": "Урон шипами",
        "exp_gain_mult": "Получение опыта",
        "gold_gain_mult": "Получение золота",
        "item_drop_chance": "Шанс дропа предметов",
        "material_drop_chance": "Шанс дропа материалов",
        "rune_drop_chance": "Шанс рун",
        "ruby_drop_chance": "Шанс рубинов",
        "extra_kill_chance": "Шанс доп. убийства",
        "water_conversion": "Конверсия воды",
        "poison_conversion": "Конверсия яда",
    }
    return names.get(key, key.replace("_", " ").title())
