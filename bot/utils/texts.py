from core.enums import CharacterClass


WELCOME_TEXT = """
🌑 <b>Добро пожаловать в Теневые Земли</b>

Ты стоишь на раздорожье миров. Здесь тьма поглотила королевства, древние боги забыты, а выжившие прячутся за стенами полуразрушенных крепостей.

Создай своего героя и начни путь от беспомощного изгнанника до легендарного воителя тьмы.

<i>Выбери свой путь...</i>
"""

CLASS_DESCRIPTIONS = {
    CharacterClass.WARRIOR: (
        "🛡 <b>Воин</b>\n\n"
        "Тяжёлые доспехи, мечи и щиты — твоя вера. Воины выдерживают удары, "
        "которые убили бы любого другого, и сокрушают врагов мощными ударами.\n\n"
        "<b>Бонусы:</b> +Сила, +Выносливость, +Здоровье"
    ),
    CharacterClass.MAGE: (
        "🔮 <b>Маг</b>\n\n"
        "Ты познал запретные знания. Пламя и молнии срываются с кончиков пальцев, "
        "а враги превращаются в пепел ещё до того, как успевают крикнуть.\n\n"
        "<b>Бонусы:</b> +Интеллект, +Мана, магический урон"
    ),
    CharacterClass.ROGUE: (
        "🗡 <b>Разбойник</b>\n\n"
        "Тени — твой дом. Ты наносишь удары туда, где броня слабее всего, "
        "и исчезаешь прежде, чем враг поймёт, что произошло.\n\n"
        "<b>Бонусы:</b> +Ловкость, +Удача, критический урон"
    ),
    CharacterClass.CLERIC: (
        "✨ <b>Жрец</b>\n\n"
        "Последний свет в этом тёмном мире. Твоё слово исцеляет раны союзников "
        "и обжигает нежить священным сиянием.\n\n"
        "<b>Бонусы:</b> +Интеллект, +Выносливость, исцеление"
    ),
}


def profile_text(character):
    stats = character.effective_stats()
    hp_bar = _bar(character.current_hp, stats["max_hp"], "🟥", "⬛")
    mp_bar = _bar(character.current_mp, stats["max_mp"], "🟦", "⬛")

    class_icons = {
        CharacterClass.WARRIOR: "🛡",
        CharacterClass.MAGE: "🔮",
        CharacterClass.ROGUE: "🗡",
        CharacterClass.CLERIC: "✨",
    }
    icon = class_icons.get(character.character_class, "👤")
    cell_info = f"\n📍 Клетка: {character.cell.name if character.cell else '—'} ({character.cell.x if character.cell else 0},{character.cell.y if character.cell else 0})" if character.cell else ""
    party_info = f"\n👥 Пати: {character.party.name}" if character.party else ""

    return (
        f"{icon} <b>{character.name}</b> | Ур. {character.level}\n"
        f"Класс: <code>{character.character_class.value}</code>\n"
        f"Золото: <code>{character.gold}</code> 🪙{party_info}\n\n"
        f"❤️ HP: {character.current_hp}/{stats['max_hp']}\n{hp_bar}\n"
        f"💙 MP: {character.current_mp}/{stats['max_mp']}\n{mp_bar}\n\n"
        f"💪 Сила: {stats['strength']}\n"
        f"🏃 Ловкость: {stats['agility']}\n"
        f"🧠 Интеллект: {stats['intelligence']}\n"
        f"🛡 Выносливость: {stats['endurance']}\n"
        f"🍀 Удача: {stats['luck']}\n\n"
        f"🗺 Локация: {character.location.name if character.location else 'Неизвестно'}{cell_info}"
    )


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


def cell_text(cell, location_name):
    # No hints about mobs, NPCs, chests - player must explore
    text = (
        f"🗺 <b>{location_name}</b>\n"
        f"📍 Клетка [{cell.x},{cell.y}] | <i>{cell.name}</i>\n\n"
        f"{cell.description}"
    )
    if cell.dungeon_template_id:
        text += "\n\n🌀 <b>Здесь открылся портал в подземелье!</b>"
    return text


def battle_start_text(mob):
    return (
        f"👾 <b>{mob.name}</b> атакует!\n\n"
        f"{mob.description}\n\n"
        f"Уровень: {mob.level}\n"
        f"❤️ HP: {mob.hp}\n"
        f"⚔️ Урон: {mob.damage}\n"
        f"🛡 Защита: {mob.defense}"
    )


def battle_round_text(char_name, mob_name, char_dmg, mob_dmg, char_hp, mob_hp, max_hp):
    return (
        f"⚔️ <b>Раунд боя</b>\n\n"
        f"{char_name} наносит {char_dmg} урона!\n"
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
