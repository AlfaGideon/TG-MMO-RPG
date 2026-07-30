from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.enums import CharacterClass


def main_menu_keyboard(has_character: bool = False, is_admin: bool = False):
    builder = InlineKeyboardBuilder()
    if not has_character:
        builder.button(text="⚔️ Создать героя", callback_data="create_character")
    else:
        builder.button(text="🧙 Профиль", callback_data="profile")
        builder.button(text="🎒 Инвентарь", callback_data="inventory")
        builder.button(text="🌍 Карта мира", callback_data="world_map")
        builder.button(text="🏪 Лавка", callback_data="shop")
        builder.button(text="👥 Пати", callback_data="party_menu")
        builder.button(text="🧭 Репутация", callback_data="reputation")
        builder.button(text="🏆 Топ", callback_data="leaderboard")
        builder.button(text="🗿 Подземелье", callback_data="dungeon_menu")
        builder.button(text="⚖️ Аукцион", callback_data="auction_menu")
    builder.button(text="❓ Помощь", callback_data="help")
    builder.adjust(2)
    if is_admin:
        builder.row(InlineKeyboardButton(text="🛠 Админка", callback_data="admin_panel"))
    return builder.as_markup()


def admin_panel_keyboard(login_url: str = ""):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔑 Показать пароль", callback_data="admin_password")
    if login_url:
        builder.button(text="🌐 Открыть панель", url=login_url)
    builder.button(text="◀️ В главное меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


CLASSES_PER_PAGE = 6


def class_select_keyboard(classes: list, page: int = 0):
    """Список классов из БД, постранично — их может быть сколько угодно."""
    builder = InlineKeyboardBuilder()
    start = page * CLASSES_PER_PAGE
    chunk = classes[start:start + CLASSES_PER_PAGE]

    for cls_def in chunk:
        icon = cls_def.icon or "⚔️"
        builder.button(
            text=f"{icon} {cls_def.name}",
            callback_data=f"select_class:{cls_def.key}",
        )
    rows = [2] * ((len(chunk) + 1) // 2)

    nav = 0
    if page > 0:
        builder.button(text="⬅️", callback_data=f"class_page:{page - 1}")
        nav += 1
    if start + CLASSES_PER_PAGE < len(classes):
        builder.button(text="➡️", callback_data=f"class_page:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ Назад", callback_data="main_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def confirm_class_keyboard(char_class: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"confirm_class:{char_class}")
    builder.button(text="◀️ Выбрать другой", callback_data="create_character")
    return builder.as_markup()


def reroll_keyboard(char_id: int, rerolls_left: int):
    """Экран броска статов: перекатить или принять как есть."""
    builder = InlineKeyboardBuilder()
    if rerolls_left > 0:
        builder.button(
            text=f"🎲 Перекатить ({rerolls_left})",
            callback_data=f"reroll_stats:{char_id}",
        )
    builder.button(text="✅ Принять статы", callback_data=f"accept_stats:{char_id}")
    builder.adjust(1)
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
    builder.button(text="🌍 Карта мира", callback_data="world_map")
    builder.button(text="◀️ Назад", callback_data="back_to_cell")
    builder.adjust(1)
    return builder.as_markup()


def travel_keyboard(safe_locations: list):
    """Карта мира: список посещённых безопасных локаций для быстрого travel."""
    builder = InlineKeyboardBuilder()
    for loc in safe_locations[:8]:
        builder.button(text=f"🏠 {loc.name}", callback_data=f"travel:{loc.id}")
    builder.button(text="◀️ Назад", callback_data="back_to_cell")
    builder.adjust(1)
    return builder.as_markup()


def inspect_keyboard(has_mob: bool, has_npc: bool, has_chest: bool,
                     is_crafter: bool = False, is_auctioneer: bool = False,
                     has_landmark: bool = False, has_grave: bool = False):
    builder = InlineKeyboardBuilder()
    if has_mob:
        builder.button(text="⚔️ Атаковать", callback_data="cell_attack")
    if has_landmark:
        builder.button(text="❇️ Изучить", callback_data="study_landmark")
    if has_grave:
        builder.button(text="💰 Забрать из могилы", callback_data="claim_grave")
    if has_npc:
        builder.button(text="💬 Поговорить", callback_data="talk_npc")
    if is_crafter:
        builder.button(text="🔨 Ремесло и заточка", callback_data="craft_menu")
    if is_auctioneer:
        builder.button(text="⚖️ Аукцион", callback_data="auction_menu")
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


def inventory_keyboard(items: list, page: int = 0, per_page: int = 6):
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    for inv_item in page_items:
        eq = "✅ " if inv_item.is_equipped else ""
        icon = inv_item.item.icon if inv_item.item else "❔"
        name = inv_item.display_name()
        qty = f" ×{inv_item.quantity}" if (inv_item.quantity or 1) > 1 else ""
        # Значок способа получения прямо в списке — видно происхождение вещи
        inst = inv_item.instance if inv_item.instance_id else None
        badge = f"{inst.badge()} " if inst else ""
        builder.button(
            text=f"{eq}{badge}{icon} {name}{qty}",
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


def item_action_keyboard(inv_item_id: int, is_equipped: bool,
                         can_equip: bool = True, can_use: bool = False,
                         can_sell: bool = False, in_stash: bool = False,
                         can_stash: bool = False):
    builder = InlineKeyboardBuilder()
    if can_equip and not in_stash:
        if is_equipped:
            builder.button(text="🚫 Снять", callback_data=f"unequip:{inv_item_id}")
        else:
            builder.button(text="✅ Экипировать", callback_data=f"equip:{inv_item_id}")
    if can_use and not in_stash:
        builder.button(text="🧪 Использовать", callback_data=f"use:{inv_item_id}")
    if can_sell and not is_equipped and not in_stash:
        builder.button(text="⚖️ На аукцион", callback_data=f"auction_sell:{inv_item_id}")
    # Защищённый карман: вещь оттуда не теряется при гибели.
    if in_stash:
        builder.button(text="🎒 Достать из кармана",
                       callback_data=f"stash_take:{inv_item_id}")
    elif can_stash:
        builder.button(text="🔒 Убрать в карман",
                       callback_data=f"stash_put:{inv_item_id}")
    if not in_stash:
        builder.button(text="🗑 Выбросить", callback_data=f"drop:{inv_item_id}")
    builder.button(text="◀️ Назад", callback_data="inventory")
    builder.adjust(2)
    return builder.as_markup()


# ── Аукцион ────────────────────────────────────────────────

def auction_menu_keyboard(my_lot_count: int = 0):
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Витрина", callback_data="auction_browse:0")
    builder.button(text="📢 Выставить вещь", callback_data="auction_my_items:0")
    builder.button(text=f"📋 Мои лоты ({my_lot_count})", callback_data="auction_my_lots")
    builder.button(text="◀️ Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def auction_browse_keyboard(lots: list, page: int = 0, per_page: int = 6):
    builder = InlineKeyboardBuilder()
    start = page * per_page
    chunk = lots[start:start + per_page]

    for lot in chunk:
        icon = lot.item.icon if lot.item else "❔"
        inst = lot.instance
        badge = inst.badge() if inst else "🔹"
        name = inst.display_name(lot.item) if inst else (lot.item.name if lot.item else "Лот")
        builder.button(
            text=f"{badge}{icon} {name} — {lot.price}🪙",
            callback_data=f"auction_lot:{lot.id}",
        )
    rows = [1] * len(chunk)

    nav = 0
    if page > 0:
        builder.button(text="⬅️", callback_data=f"auction_browse:{page - 1}")
        nav += 1
    if start + per_page < len(lots):
        builder.button(text="➡️", callback_data=f"auction_browse:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ К аукциону", callback_data="auction_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def auction_lot_keyboard(lot_id: int, can_buy: bool, is_mine: bool = False):
    builder = InlineKeyboardBuilder()
    if is_mine:
        builder.button(text="↩️ Снять с продажи", callback_data=f"auction_cancel:{lot_id}")
    elif can_buy:
        builder.button(text="💰 Купить", callback_data=f"auction_buy:{lot_id}")
    builder.button(text="◀️ К витрине", callback_data="auction_browse:0")
    builder.button(text="🏠 К аукциону", callback_data="auction_menu")
    builder.adjust(1)
    return builder.as_markup()


def auction_sell_list_keyboard(items: list, page: int = 0, per_page: int = 6):
    builder = InlineKeyboardBuilder()
    start = page * per_page
    chunk = items[start:start + per_page]

    for inv in chunk:
        icon = inv.item.icon if inv.item else "❔"
        inst = inv.instance
        badge = inst.badge() if inst else "🔹"
        builder.button(
            text=f"{badge}{icon} {inv.display_name()}",
            callback_data=f"auction_sell:{inv.id}",
        )
    rows = [1] * len(chunk)

    nav = 0
    if page > 0:
        builder.button(text="⬅️", callback_data=f"auction_my_items:{page - 1}")
        nav += 1
    if start + per_page < len(items):
        builder.button(text="➡️", callback_data=f"auction_my_items:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ К аукциону", callback_data="auction_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def auction_price_keyboard(inv_id: int, prices: list, npc_price: int):
    """Готовые варианты цены — вводить числа в чате неудобно."""
    builder = InlineKeyboardBuilder()
    for label, price in prices:
        builder.button(
            text=f"{label} — {price}🪙",
            callback_data=f"auction_list:{inv_id}:{price}",
        )
    rows = [1] * len(prices)
    builder.button(
        text=f"⚡ Сразу скупщику — {npc_price}🪙",
        callback_data=f"auction_npc_sell:{inv_id}",
    )
    builder.button(text="◀️ Назад", callback_data="auction_my_items:0")
    rows.extend([1, 1])
    builder.adjust(*rows)
    return builder.as_markup()


def auction_my_lots_keyboard(lots: list):
    builder = InlineKeyboardBuilder()
    for lot in lots:
        icon = lot.item.icon if lot.item else "❔"
        name = lot.instance.display_name(lot.item) if lot.instance else "Лот"
        builder.button(
            text=f"↩️ {icon} {name} ({lot.price}🪙)",
            callback_data=f"auction_cancel:{lot.id}",
        )
    builder.button(text="◀️ К аукциону", callback_data="auction_menu")
    builder.adjust(1)
    return builder.as_markup()


def craft_menu_keyboard(station: str = "any"):
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 Рецепты", callback_data=f"craft_list:{station}:0")
    builder.button(text="🔨 Заточить предмет", callback_data="upgrade_list:0")
    builder.button(text="◀️ Назад", callback_data="back_to_cell")
    builder.adjust(1)
    return builder.as_markup()


def craft_recipes_keyboard(recipes: list, ready: dict, station: str, page: int = 0,
                           per_page: int = 6):
    builder = InlineKeyboardBuilder()
    start = page * per_page
    chunk = recipes[start:start + per_page]

    for recipe in chunk:
        mark = "✅" if ready.get(recipe.id) else "❌"
        icon = recipe.result_item.icon if recipe.result_item else "🔨"
        builder.button(
            text=f"{mark} {icon} {recipe.name}",
            callback_data=f"craft_view:{recipe.id}",
        )
    rows = [1] * len(chunk)

    nav = 0
    if page > 0:
        builder.button(text="⬅️", callback_data=f"craft_list:{station}:{page - 1}")
        nav += 1
    if start + per_page < len(recipes):
        builder.button(text="➡️", callback_data=f"craft_list:{station}:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ К мастеру", callback_data="craft_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def craft_recipe_keyboard(recipe_id: int, can_craft: bool, station: str):
    builder = InlineKeyboardBuilder()
    if can_craft:
        builder.button(text="🔨 Изготовить", callback_data=f"craft_do:{recipe_id}")
    builder.button(text="◀️ К рецептам", callback_data=f"craft_list:{station}:0")
    builder.button(text="🏠 К мастеру", callback_data="craft_menu")
    builder.adjust(1)
    return builder.as_markup()


def upgrade_list_keyboard(items: list, station: str, page: int = 0, per_page: int = 6):
    builder = InlineKeyboardBuilder()
    start = page * per_page
    chunk = items[start:start + per_page]

    for inv in chunk:
        eq = "✅ " if inv.is_equipped else ""
        icon = inv.item.icon if inv.item else "❔"
        builder.button(
            text=f"{eq}{icon} {inv.display_name()}",
            callback_data=f"upgrade_view:{inv.id}",
        )
    rows = [1] * len(chunk)

    nav = 0
    if page > 0:
        builder.button(text="⬅️", callback_data=f"upgrade_list:{page - 1}")
        nav += 1
    if start + per_page < len(items):
        builder.button(text="➡️", callback_data=f"upgrade_list:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ К мастеру", callback_data="craft_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def upgrade_item_keyboard(inv_item_id: int, can_upgrade: bool, station: str):
    builder = InlineKeyboardBuilder()
    if can_upgrade:
        builder.button(text="⚡ Заточить", callback_data=f"upgrade_do:{inv_item_id}")
    builder.button(text="◀️ К списку", callback_data="upgrade_list:0")
    builder.button(text="🏠 К мастеру", callback_data="craft_menu")
    builder.adjust(1)
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
    builder.button(text="🗺 Карта", callback_data="dungeon_map")
    builder.button(text="🏃 Выйти", callback_data="dungeon_exit")
    builder.adjust(3, 3, 3, 2)
    return builder.as_markup()


def dungeon_map_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="dungeon_back")
    return builder.as_markup()


def dungeon_combat_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ Атаковать", callback_data="dungeon_combat_attack")
    builder.button(text="🏃 Сбежать", callback_data="dungeon_flee")
    builder.adjust(2)
    return builder.as_markup()
