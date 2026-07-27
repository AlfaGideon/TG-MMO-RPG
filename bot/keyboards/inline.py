from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.enums import CharacterClass


def main_menu_keyboard(has_character: bool = False):
    builder = InlineKeyboardBuilder()
    if not has_character:
        builder.button(text="⚔️ Создать героя", callback_data="create_character")
    else:
        builder.button(text="🧙 Профиль", callback_data="profile")
        builder.button(text="🗺 Локации", callback_data="locations")
        builder.button(text="🎒 Инвентарь", callback_data="inventory")
        builder.button(text="🏪 Лавка", callback_data="shop")
        builder.button(text="👥 Пати", callback_data="party_menu")
        builder.button(text="🏆 Топ", callback_data="leaderboard")
    builder.button(text="❓ Помощь", callback_data="help")
    builder.adjust(2)
    return builder.as_markup()


def class_select_keyboard():
    builder = InlineKeyboardBuilder()
    classes = [
        ("🛡 Воин", CharacterClass.WARRIOR),
        ("🔮 Маг", CharacterClass.MAGE),
        ("🗡 Разбойник", CharacterClass.ROGUE),
        ("✨ Жрец", CharacterClass.CLERIC),
    ]
    for text, cls in classes:
        builder.button(text=text, callback_data=f"select_class:{cls.value}")
    builder.button(text="◀️ Назад", callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()


def confirm_class_keyboard(char_class: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"confirm_class:{char_class}")
    builder.button(text="◀️ Выбрать другой", callback_data="create_character")
    return builder.as_markup()


def back_to_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ В главное меню", callback_data="main_menu")
    return builder.as_markup()


def locations_keyboard(locations: list, current_location_id: int):
    builder = InlineKeyboardBuilder()
    for loc in locations:
        prefix = "📍" if loc.id == current_location_id else ""
        builder.button(
            text=f"{prefix} {loc.name}",
            callback_data=f"travel:{loc.id}"
        )
    builder.button(text="◀️ Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def cell_movement_keyboard(can_north: bool, can_south: bool, can_west: bool, can_east: bool):
    builder = InlineKeyboardBuilder()
    if can_north:
        builder.button(text="⬆️ Север", callback_data="move:north")
    else:
        builder.button(text="🚫 Север", callback_data="noop")
    row2 = []
    if can_west:
        row2.append(("⬅️ Запад", "move:west"))
    else:
        row2.append(("🚫 Запад", "noop"))
    row2.append(("🔍 Осмотреться", "inspect"))
    if can_east:
        row2.append(("➡️ Восток", "move:east"))
    else:
        row2.append(("🚫 Восток", "noop"))
    for text, data in row2:
        builder.button(text=text, callback_data=data)
    if can_south:
        builder.button(text="⬇️ Юг", callback_data="move:south")
    else:
        builder.button(text="🚫 Юг", callback_data="noop")
    builder.button(text="🏕 Отдохнуть", callback_data="rest")
    builder.button(text="🎒 Инвентарь", callback_data="inventory")
    builder.button(text="🗺 Локации", callback_data="locations")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1, 3, 1, 2)
    return builder.as_markup()


def inspect_keyboard(has_mob: bool, has_npc: bool, has_chest: bool):
    builder = InlineKeyboardBuilder()
    if has_mob:
        builder.button(text="⚔️ Атаковать", callback_data="cell_attack")
    if has_npc:
        builder.button(text="💬 Поговорить", callback_data="talk_npc")
    if has_chest:
        builder.button(text="📦 Открыть сундук", callback_data="open_chest")
    builder.button(text="◀️ Назад", callback_data="back_to_cell")
    builder.adjust(1)
    return builder.as_markup()


def combat_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ Атаковать", callback_data="combat_attack")
    builder.button(text="🛡 Защита", callback_data="combat_defend")
    builder.button(text="✨ Умение", callback_data="combat_skill")
    builder.button(text="🏃 Побег", callback_data="combat_flee")
    builder.adjust(2)
    return builder.as_markup()


def inventory_keyboard(items: list, page: int = 0, per_page: int = 5):
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    for inv_item in page_items:
        eq = "[E] " if inv_item.is_equipped else ""
        builder.button(
            text=f"{eq}{inv_item.item.icon} {inv_item.item.name} x{inv_item.quantity}",
            callback_data=f"item:{inv_item.id}"
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(("⬅️", f"inv_page:{page - 1}"))
    if end < len(items):
        nav_buttons.append(("➡️", f"inv_page:{page + 1}"))

    for text, data in nav_buttons:
        builder.button(text=text, callback_data=data)

    builder.button(text="◀️ Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def item_action_keyboard(inv_item_id: int, is_equipped: bool):
    builder = InlineKeyboardBuilder()
    if is_equipped:
        builder.button(text="Снять", callback_data=f"unequip:{inv_item_id}")
    else:
        builder.button(text="Экипировать", callback_data=f"equip:{inv_item_id}")
    builder.button(text="Выбросить", callback_data=f"drop:{inv_item_id}")
    builder.button(text="◀️ Назад", callback_data="inventory")
    builder.adjust(2)
    return builder.as_markup()


def shop_keyboard(shop_items: list):
    builder = InlineKeyboardBuilder()
    for si in shop_items:
        builder.button(
            text=f"{si.item.icon} {si.item.name} — {si.price}🪙",
            callback_data=f"buy:{si.id}"
        )
    builder.button(text="◀️ Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def leaderboard_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="По уровню", callback_data="lb:level")
    builder.button(text="По золоту", callback_data="lb:gold")
    builder.button(text="◀️ Назад", callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()
