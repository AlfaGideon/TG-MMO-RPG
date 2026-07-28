WELCOME_TEXT = """
🌑 <b>Добро пожаловать в Теневые Земли</b>

Ты стоишь на раздорожье миров. Здесь тьма поглотила королевства, древние боги забыты, а выжившие прячутся за стенами полуразрушенных крепостей.

Создай своего героя и начни путь от беспомощного изгнанника до легендарного воителя тьмы.

<i>Выбери свой путь...</i>
"""

def class_description_text(cls_def):
    """Экран класса при создании героя — статы берутся из настроек админки."""
    icon = cls_def.icon or "⚔️"
    stats = cls_def.base_stats()
    growth = cls_def.growth()

    def line(label, key, suffix=""):
        gain = growth.get(key, 0)
        plus = f" <i>(+{gain}/ур.)</i>" if gain else ""
        return f"{label}: <b>{stats[key]}</b>{suffix}{plus}"

    return (
        f"{icon} <b>{cls_def.name}</b>\n\n"
        f"{cls_def.description}\n\n"
        f"<b>Стартовые характеристики</b>\n"
        f"❤️ {line('HP', 'max_hp')}\n"
        f"💙 {line('MP', 'max_mp')}\n"
        f"💪 {line('Сила', 'strength')}\n"
        f"🏃 {line('Ловкость', 'agility')}\n"
        f"🧠 {line('Интеллект', 'intelligence')}\n"
        f"🛡 {line('Выносливость', 'endurance')}\n"
        f"🍀 {line('Удача', 'luck')}"
    )


SLOT_LABELS = {
    "weapon": "⚔️ Оружие", "armor": "🦺 Броня", "helmet": "🪖 Шлем",
    "boots": "👢 Сапоги", "accessory": "💍 Аксессуар",
}


def profile_text(character, class_def=None, combat=None):
    """Профиль героя: база + бонусы от надетых уникальных предметов."""
    icon = (class_def.icon if class_def else None) or "👤"
    class_label = class_def.name if class_def else str(character.character_class)

    base = character.effective_stats()
    stats = combat or {}
    gear = stats.get("gear", [])
    bonus = stats.get("bonus", {})

    def stat_line(emoji, label, key):
        total = stats.get(key, base.get(key, 0))
        extra = bonus.get(key, 0)
        plus = f" <i>(+{extra})</i>" if extra else ""
        return f"{emoji} {label}: <b>{total}</b>{plus}"

    max_hp = stats.get("max_hp", base["max_hp"])
    max_mp = stats.get("max_mp", base["max_mp"])
    hp_bar = _bar(character.current_hp, max_hp, "🟥", "⬛")
    mp_bar = _bar(character.current_mp, max_mp, "🟦", "⬛")

    cell = character.cell
    cell_info = (
        f"\n📍 Клетка: {cell.name} ({cell.x},{cell.y})" if cell else ""
    )
    party_info = f"\n👥 Пати: {character.party.name}" if character.party else ""

    lines = [
        f"{icon} <b>{character.name}</b> | Ур. {character.level}",
        f"Класс: <b>{class_label}</b>",
        f"⭐ Опыт: {character.experience}/{character.level * 100}",
        f"🪙 Золото: <b>{character.gold}</b>{party_info}",
        "",
        f"❤️ HP: {character.current_hp}/{max_hp}",
        hp_bar,
        f"💙 MP: {character.current_mp}/{max_mp}",
        mp_bar,
        "",
        "<b>━━ Характеристики ━━</b>",
        stat_line("💪", "Сила", "strength"),
        stat_line("🏃", "Ловкость", "agility"),
        stat_line("🧠", "Интеллект", "intelligence"),
        stat_line("🛡", "Выносливость", "endurance"),
        stat_line("🍀", "Удача", "luck"),
        "",
        "<b>━━ Бой ━━</b>",
        f"⚔️ Урон от оружия: <b>+{stats.get('damage', 0)}</b>",
        f"🛡 Защита от брони: <b>+{stats.get('defense', 0)}</b>",
        "",
        "<b>━━ Снаряжение ━━</b>",
    ]

    by_slot = {}
    for inv in gear:
        if inv.item:
            by_slot[inv.item.item_type.value] = inv
    for slot, label in SLOT_LABELS.items():
        inv = by_slot.get(slot)
        if inv is None:
            lines.append(f"{label}: <i>пусто</i>")
        else:
            uid = inv.instance.uid if inv.instance else ""
            uid_str = f" <code>{uid}</code>" if uid else ""
            lines.append(f"{label}: <b>{inv.display_name()}</b>{uid_str}")

    lines += [
        "",
        f"🗺 Локация: "
        f"{character.location.name if character.location else 'Неизвестно'}{cell_info}",
    ]
    return "\n".join(lines)


def _bar(current, maximum, fill, empty):
    if maximum <= 0:
        return ""
    total = 10
    filled = int(current / maximum * total)
    return fill * filled + empty * (total - filled)


def location_text(location):
    danger_icons = {
        "safe": "🛡 Безопасная",
        "dangerous": "⚠️ Опасная",
        "dungeon": "💀 Подземелье",
        "boss": "👹 Логово босса",
    }
    danger = danger_icons.get(location.location_type.value, "❓")
    return (
        f"🗺 <b>{location.name}</b>\n\n"
        f"{location.description}\n\n"
        f"Тип: {danger}\n"
        f"Мин. уровень: {location.min_level}\n"
        f"Размер карты: {location.grid_size}x{location.grid_size} клеток"
    )


def cell_text(cell, location_name, portal_active=False):
    # No hints about mobs, NPCs, chests - player must explore
    text = (
        f"🗺 <b>{location_name}</b>\n"
        f"📍 Клетка [{cell.x},{cell.y}] | <i>{cell.name}</i>\n\n"
        f"{cell.description}"
    )
    if portal_active:
        text += "\n\n🌀 <b>Здесь открылся портал в подземелье!</b>"
    return text


def battle_start_text(mob, current_hp=None):
    hp = mob.hp if current_hp is None else current_hp
    wounded = " <i>(ранен)</i>" if current_hp is not None and current_hp < mob.hp else ""
    return (
        f"👾 <b>{mob.name}</b> атакует!\n\n"
        f"{mob.description}\n\n"
        f"Уровень: {mob.level}\n"
        f"❤️ HP: {hp}/{mob.hp}{wounded}\n"
        f"⚔️ Урон: {mob.damage}\n"
        f"🛡 Защита: {mob.defense}"
    )


def battle_round_text(char_name, mob_name, char_dmg, mob_dmg, char_hp, mob_hp,
                      max_hp, crit=False):
    hit = f"{char_dmg} урона!" if not crit else f"<b>КРИТ! {char_dmg} урона!</b>"
    return (
        f"⚔️ <b>Раунд боя</b>\n\n"
        f"{char_name} наносит {hit}\n"
        f"{mob_name} отвечает {mob_dmg} урона!\n\n"
        f"❤️ Ты: {char_hp}/{max_hp}\n"
        f"👾 {mob_name}: {mob_hp}"
    )


def victory_text(mob, gold, exp):
    return (
        f"🎉 <b>Победа!</b>\n\n"
        f"Ты поверг {mob.name}!\n\n"
        f"💰 Золото: +{gold}\n"
        f"⭐ Опыт: +{exp}"
    )


def defeat_text():
    return (
        "💀 <b>Поражение...</b>\n\n"
        "Тьма поглотила тебя. Но смерть в этих землях не конец — "
        "ты очнулся у ближайшего костра с единицей здоровья."
    )


def dungeon_text(cell, floor):
    return (
        f"🗿 <b>Подземелье Проклятых — Этаж {floor}</b>\n"
        f"📍 [{cell.x},{cell.y}] | {cell.name}\n\n"
        f"<i>{cell.description}</i>"
    )


RARITY_ICONS = {
    "common": "⚪", "uncommon": "🟢", "rare": "🔵",
    "epic": "🟣", "legendary": "🟠",
}


def item_line(inv_item, show_uid: bool = False) -> str:
    """Строка предмета для списков: иконка, имя, редкость, ID экземпляра."""
    item = inv_item.item
    inst = inv_item.instance
    icon = item.icon if item else "❔"
    name = inv_item.display_name()
    rarity = (inst.rarity if inst else item.rarity)
    dot = RARITY_ICONS.get(getattr(rarity, "value", str(rarity)), "⚪")
    qty = f" ×{inv_item.quantity}" if (inv_item.quantity or 1) > 1 else ""
    uid = f" <code>{inst.uid}</code>" if (show_uid and inst) else ""
    return f"{dot} {icon} {name}{qty}{uid}"


def loot_text(inv_items) -> str:
    """Что выпало после боя или из сундука."""
    if not inv_items:
        return ""
    lines = ["🎁 <b>Добыча:</b>"]
    for inv in inv_items:
        lines.append("• " + item_line(inv, show_uid=True))
    return "\n".join(lines)


def item_detail_text(inv_item) -> str:
    """Карточка предмета с уникальным ID, качеством и бонусами экземпляра."""
    item = inv_item.item
    inst = inv_item.instance
    rarity = inst.rarity if inst else item.rarity
    rarity_v = getattr(rarity, "value", str(rarity))

    lines = [
        f"{item.icon} <b>{inv_item.display_name()}</b>",
        f"Тип: <code>{item.item_type.value}</code> | "
        f"Редкость: {RARITY_ICONS.get(rarity_v, '⚪')} <code>{rarity_v}</code>",
    ]
    if inst:
        lines.append(f"🆔 ID предмета: <code>{inst.uid}</code>")
        lines.append(f"⚖️ Качество: <b>{inst.quality}%</b>"
                     + (f" | 🔨 Заточка: <b>+{inst.upgrade_level}</b>"
                        if inst.upgrade_level else ""))
        if inst.source_detail:
            lines.append(f"<i>Источник: {inst.source_detail}</i>")
    lines.append("")
    lines.append(item.description)

    labels = {
        "bonus_strength": "💪 Сила", "bonus_agility": "🏃 Ловкость",
        "bonus_intelligence": "🧠 Интеллект", "bonus_endurance": "🛡 Выносливость",
        "bonus_luck": "🍀 Удача", "bonus_hp": "❤️ HP", "bonus_mp": "💙 MP",
        "bonus_damage": "⚔️ Урон", "bonus_defense": "🛡 Защита",
    }
    bonuses = inv_item.bonuses()
    base = item.base_bonuses()
    rows = []
    for field, label in labels.items():
        value = bonuses.get(field, 0)
        if not value:
            continue
        # Показываем, насколько экземпляр лучше/хуже шаблона
        delta = value - (base.get(field) or 0)
        mark = f" <i>({'+' if delta > 0 else ''}{delta} к базе)</i>" if delta else ""
        rows.append(f"{label} +{value}{mark}")

    lines.append("")
    lines.append("<b>Бонусы:</b>\n" + "\n".join(rows) if rows else "<b>Нет бонусов</b>")
    return "\n".join(lines)
