from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.enums import CharacterClass


def main_menu_keyboard(has_character: bool = False):
    builder = InlineKeyboardBuilder()
    if not has_character:
        builder.button(text="⚔️ Создать героя", callback_data="create_character")
    else:
        builder.button(text="🧙 Профиль", callback_data="profile")
        builder.button(text="🎒 Инвентарь", callback_data="inventory")
        builder.button(text="🏪 Лавка", callback_data="shop")
        builder.button(text="👥 Пати", callback_data="party_menu")
        builder.button(text="🏆 Топ", callback_data="leaderboard")
        builder.button(text="🗿 Подземелье", callback_data="dungeon_menu")
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


def cell_movement_keyboard(can_dirs: dict, dungeon_template_id: int | None = None):
    """
    3x3 grid: 8 directions + center inspect.
    can_dirs: {'nw': bool, 'n': bool, 'ne': bool, 'w': bool, 'e': bool,
               'sw': bool, 's': bool, 'se': bool}
    """
    builder = InlineKeyboardBuilder()

    def btn(direction, icon, label):
        if can_dirs.get(direction):
            builder.button(text=f"{icon}", callback_data=f"move:{direction}")
        else:
            builder.button(text="⬛", callback_data="noop")

    # Row 1: NW, N, NE
    btn('nw', '↖️', 'СЗ')
    btn('n', '⬆️', 'С')
    btn('ne', '↗️', 'СВ')

    # Row 2: W, Inspect, E
    btn('w', '⬅️', 'З')
    builder.button(text="🔍", callback_data="inspect")
    btn('e', '➡️', 'В')

    # Row 3: SW, S, SE
    btn('sw', '↙️', 'ЮЗ')
    btn('s', '⬇️', 'Ю')
    btn('se', '↘️', 'ЮВ')

    rows = [3, 3, 3]

    if dungeon_template_id:
        builder.button(text="🕳 Войти в подземелье", callback_data=f"dungeon_enter_tpl:{dungeon_template_id}")
        rows.append(1)

    # Actions
    builder.button(text="🏕 Отдохнуть", callback_data="rest")
    builder.button(text="🎒 Инвентарь", callback_data="inventory")
    builder.button(text="🗺 Карта", callback_data="show_map")
    builder.button(text="🗿 Подземелье", callback_data="dungeon_menu")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    rows.extend([2, 2, 1])

    builder.adjust(*rows)
    return builder.as_markup()


def map_view_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="back_to_cell")
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


def dungeon_menu_keyboard(has_portal_hint: bool = True):
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 Правила", callback_data="dungeon_info")
    builder.button(text="◀️ Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def dungeon_movement_keyboard(can_dirs: dict):
    builder = InlineKeyboardBuilder()

    def btn(direction, icon):
        if can_dirs.get(direction):
            builder.button(text=f"{icon}", callback_data=f"dungeon_move:{direction}")
        else:
            builder.button(text="⬛", callback_data="noop")

    btn('nw', '↖️')
    btn('n', '⬆️')
    btn('ne', '↗️')
    btn('w', '⬅️')
    builder.button(text="🔍", callback_data="dungeon_inspect")
    btn('e', '➡️')
    btn('sw', '↙️')
    btn('s', '⬇️')
    btn('se', '↘️')
    builder.button(text="🏃 Выйти", callback_data="dungeon_exit")
    builder.adjust(3, 3, 3, 1)
    return builder.as_markup()


def dungeon_combat_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ Атаковать", callback_data="dungeon_combat_attack")
    builder.button(text="🏃 Сбежать", callback_data="dungeon_flee")
    builder.adjust(2)
    return builder.as_markup()
