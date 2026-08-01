from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.enums import CharacterClass


def main_menu_keyboard(has_character: bool = False, is_admin: bool = False,
                       is_vip: bool = False, offline: bool = False):
    builder = InlineKeyboardBuilder()
    if not has_character:
        builder.button(text="⚔️ Создать героя", callback_data="create_character")
    else:
        builder.button(text="🧙 Профиль", callback_data="profile")
        builder.button(text="🎒 Инвентарь", callback_data="inventory")
        builder.button(text="🌍 Карта мира", callback_data="world_map")
        builder.button(text="👥 Пати", callback_data="party_menu")
        builder.button(text="🧭 Репутация", callback_data="reputation")
        builder.button(text="🏆 Топ", callback_data="leaderboard")
        builder.button(text="⚖️ Аукцион", callback_data="auction_menu")
        # Лавка торговца — только у NPC на клетке: за товаром надо дойти.
        # Подземелье и лавка лекаря носятся с собой лишь у VIP.
        if is_vip:
            builder.button(text="🗿 Подземелье", callback_data="dungeon_menu")
            builder.button(text="⚗️ Лавка лекаря", callback_data="healer_shop")
            builder.button(
                text="🌙 Вернуться в мир" if offline else "🌙 Я офлайн",
                callback_data="offline_resume" if offline else "offline_toggle",
            )
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


def _clamp_page(page: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(page, total - 1))


def class_select_keyboard(classes: list, page: int = 0):
    """Книжное листание классов: одна карточка класса на странице.

    Игрок сначала видит описание и бонусы текущего класса, листает
    «страницы», а уже затем нажимает выбор. Старое меню-список было
    неудобно: бонусы открывались только после отдельного нажатия.
    """
    builder = InlineKeyboardBuilder()
    total = len(classes)
    if total <= 0:
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        return builder.as_markup()

    page = _clamp_page(page, total)
    cls_def = classes[page]
    icon = cls_def.icon or "⚔️"

    builder.button(
        text=f"✅ Выбрать и далее: {icon} {cls_def.name}",
        callback_data=f"select_class:{cls_def.key}",
    )
    rows = [1]

    nav = 0
    if page > 0:
        builder.button(text="⬅️ Пред. страница", callback_data=f"class_page:{page - 1}")
        nav += 1
    if page + 1 < total:
        builder.button(text="След. страница ➡️", callback_data=f"class_page:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ Назад", callback_data="main_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def confirm_class_keyboard(char_class: str, back_page: int | None = None):
    builder = InlineKeyboardBuilder()
    builder.button(text="🟢 ✅ Подтвердить", callback_data=f"confirm_class:{char_class}")
    back_target = f"class_page:{back_page}" if back_page is not None else "create_character"
    builder.button(text="🔴 ◀️ Другой класс", callback_data=back_target)
    return builder.as_markup()


def reroll_keyboard(char_id: int, rerolls_left: int):
    """Экран броска статов: перекатить или принять как есть."""
    builder = InlineKeyboardBuilder()
    if rerolls_left > 0:
        builder.button(
            text=f"🟡 🎲 Перекатить ({rerolls_left})",
            callback_data=f"reroll_stats:{char_id}",
        )
    builder.button(text="🟢 ✅ Принять статы", callback_data=f"accept_stats:{char_id}")
    builder.adjust(1)
    return builder.as_markup()


def back_to_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ В главное меню", callback_data="main_menu")
    return builder.as_markup()


def continue_keyboard(extra: list | None = None, with_inspect: bool = True):
    """Экран после действия в мире: вернуться к тому, чем игрок занимался.

    Раньше после разговора с NPC, изучения диковины, боя или отдыха
    единственной кнопкой было «В главное меню» — игрока выбрасывало из
    прогулки по карте, и путь приходилось начинать заново. Теперь главная
    кнопка возвращает на клетку, а меню остаётся дополнительным выходом.
    """
    builder = InlineKeyboardBuilder()
    rows = []
    for text, data in (extra or []):
        builder.button(text=text, callback_data=data)
        rows.append(1)
    builder.button(text="🧭 Продолжить путь", callback_data="back_to_cell")
    rows.append(1)
    if with_inspect:
        builder.button(text="🔍 Осмотреться", callback_data="inspect")
        builder.button(text="🏠 Меню", callback_data="main_menu")
        rows.append(2)
    else:
        builder.button(text="🏠 Меню", callback_data="main_menu")
        rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def profile_book_keyboard(page: int, total: int, titles: list):
    """Листалка «книги о герое»: развороты вместо одной длинной простыни."""
    builder = InlineKeyboardBuilder()
    rows = []

    nav = 0
    if page > 0:
        builder.button(text="⬅️ Пред.", callback_data=f"profile_page:{page - 1}")
        nav += 1
    if page + 1 < total:
        builder.button(text="След. ➡️", callback_data=f"profile_page:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    # Быстрый переход на любой разворот — закладки книги.
    tabs = 0
    for idx, title in enumerate(titles):
        if idx == page:
            continue
        builder.button(text=title, callback_data=f"profile_page:{idx}")
        tabs += 1
    if tabs:
        rows.append(2 if tabs > 1 else 1)
        if tabs > 2:
            rows[-1] = 2
            rows.append(tabs - 2)

    builder.button(text="🏠 Меню", callback_data="main_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def help_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔵 📢 Обновления и изменения", callback_data="bot_updates")
    builder.button(text="🟡 💡 Место для идей", callback_data="bot_suggest")
    builder.button(text="◀️ В главное меню", callback_data="main_menu")
    builder.adjust(2, 1)
    return builder.as_markup()


def back_to_help_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="help")
    builder.button(text="🏠 В меню", callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()


def cell_movement_keyboard(can_dirs: dict, dungeon_template_id: int | None = None,
                           dir_labels: dict | None = None,
                           current_transition_label: str | None = None,
                           is_vip: bool = False,
                           has_merchant: bool = False):
    """
    3x3 grid: 8 directions + center inspect.
    can_dirs: {'nw': bool, 'n': bool, 'ne': bool, 'w': bool, 'e': bool,
               'sw': bool, 's': bool, 'se': bool}
    dir_labels: optional per-direction button text. Used to show doors
                (transitions) and rocks (blocked cells) directly on arrows.
    current_transition_label: button for the transition on the current cell
                itself (stairs/floor change).
    """
    builder = InlineKeyboardBuilder()
    dir_labels = dir_labels or {}

    def btn(direction, icon, label):
        text = dir_labels.get(direction) or icon
        if can_dirs.get(direction):
            builder.button(text=text, callback_data=f"move:{direction}")
        else:
            builder.button(text=dir_labels.get(direction) or "⬛", callback_data="noop")

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

    if current_transition_label:
        builder.button(text=current_transition_label, callback_data="cell_transition")
        rows.append(1)

    if dungeon_template_id:
        builder.button(text="🕳 Войти в подземелье", callback_data=f"dungeon_enter_tpl:{dungeon_template_id}")
        rows.append(1)

    if has_merchant:
        builder.button(text="🧳 Торговец", callback_data="merchant_menu")
        rows.append(1)

    # Actions
    builder.button(text="🏕 Отдохнуть", callback_data="rest")
    builder.button(text="🎒 Инвентарь", callback_data="inventory")
    builder.button(text="🗺 Карта", callback_data="show_map")
    if is_vip:
        # Обычный герой попадает в подземелье только через портал на клетке —
        # кнопка «в кармане» это VIP-удобство.
        builder.button(text="🗿 Подземелье", callback_data="dungeon_menu")
        rows.extend([2, 2])
    else:
        rows.extend([2, 1])
    builder.button(text="◀️ Меню", callback_data="main_menu")
    rows.append(1)

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


def merchant_book_keyboard(ware, page: int, total: int, can_buy: bool):
    """Витрина бродячего торговца: карточка товара + листание."""
    builder = InlineKeyboardBuilder()
    rows = []
    if can_buy:
        builder.button(
            text=f"🟢 💰 Купить за {ware['price']}🪙",
            callback_data=f"merchant_buy:{page}",
        )
    else:
        builder.button(text="🔒 Не по карману", callback_data="noop")
    rows.append(1)

    nav = 0
    if page > 0:
        builder.button(text="⬅️ Пред.", callback_data=f"merchant_page:{page - 1}")
        nav += 1
    if page + 1 < total:
        builder.button(text="След. ➡️", callback_data=f"merchant_page:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ К клетке", callback_data="back_to_cell")
    rows.append(1)
    builder.adjust(*rows)
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
    builder.button(text="🔴 ⚔️ Атаковать", callback_data="combat_attack")
    builder.button(text="🔵 🛡️ Защита", callback_data="combat_defend")
    builder.button(text="🟡 ✨ Умение", callback_data="combat_skill")
    builder.button(text="⚪ 🏃 Побег", callback_data="combat_flee")
    builder.adjust(2)
    return builder.as_markup()


def inventory_hub_keyboard(counts: dict):
    """Три отделения снаряжения героя вместо одной свалки.

    Карман переживает гибель, сумка — нет, надетое считается отдельно;
    внутри сумки предметы и материалы тоже разведены, потому что руда и
    шкуры забивали список и мешали найти оружие.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🛡 Снаряжение ({counts.get('gear', 0)})",
                   callback_data="inv_sec:gear:0")
    builder.button(text=f"🎒 Сумка · предметы ({counts.get('bag', 0)})",
                   callback_data="inv_sec:bag:0")
    builder.button(text=f"🧱 Сумка · материалы ({counts.get('mat', 0)})",
                   callback_data="inv_sec:mat:0")
    builder.button(
        text=f"🔒 Карман ({counts.get('stash', 0)}/{counts.get('stash_cap', 0)})",
        callback_data="inv_sec:stash:0")
    builder.button(text="🏠 Меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def inventory_section_keyboard(items: list, section: str, page: int = 0,
                               per_page: int = 6):
    """Список одного отделения. Открытие вещи ведёт в книгу предметов."""
    builder = InlineKeyboardBuilder()
    start = page * per_page
    chunk = items[start:start + per_page]

    for idx, inv_item in enumerate(chunk, start=start):
        eq = "✅ " if inv_item.is_equipped else ""
        icon = inv_item.item.icon if inv_item.item else "❔"
        qty = f" ×{inv_item.quantity}" if (inv_item.quantity or 1) > 1 else ""
        inst = inv_item.instance if inv_item.instance_id else None
        badge = f"{inst.badge()} " if inst else ""
        builder.button(
            text=f"{eq}{badge}{icon} {inv_item.display_name()}{qty}",
            callback_data=f"inv_book:{section}:{idx}",
        )
    rows = [1] * len(chunk)

    nav = 0
    if page > 0:
        builder.button(text="⬅️", callback_data=f"inv_sec:{section}:{page - 1}")
        nav += 1
    if start + per_page < len(items):
        builder.button(text="➡️", callback_data=f"inv_sec:{section}:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ К отделениям", callback_data="inventory")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def item_book_keyboard(inv_item_id: int, section: str, index: int, total: int,
                       is_equipped: bool = False, can_equip: bool = False,
                       can_use: bool = False, can_sell: bool = False,
                       in_stash: bool = False, can_stash: bool = False):
    """Книга предметов: карточка вещи + листание соседних страниц."""
    builder = InlineKeyboardBuilder()
    rows = []

    actions = 0
    if can_equip and not in_stash:
        if is_equipped:
            builder.button(text="🟡 🚫 Снять", callback_data=f"unequip:{inv_item_id}")
        else:
            builder.button(text="🟢 ✅ Экипировать", callback_data=f"equip:{inv_item_id}")
        actions += 1
    if can_use and not in_stash:
        builder.button(text="🔵 🧪 Использовать", callback_data=f"use:{inv_item_id}")
        actions += 1
    if can_sell and not is_equipped and not in_stash:
        builder.button(text="🟣 ⚖️ На аукцион", callback_data=f"auction_sell:{inv_item_id}")
        actions += 1
    if in_stash:
        builder.button(text="🟢 🎒 Достать из кармана",
                       callback_data=f"stash_take:{inv_item_id}")
        actions += 1
    elif can_stash:
        builder.button(text="🟢 🔒 Убрать в карман",
                       callback_data=f"stash_put:{inv_item_id}")
        actions += 1
    if not in_stash and not is_equipped:
        builder.button(text="🔴 🗑 Выбросить", callback_data=f"drop:{inv_item_id}")
        actions += 1
    if actions:
        rows.append(2 if actions > 1 else 1)
        if actions > 2:
            rows[-1] = 2
            left = actions - 2
            while left > 0:
                rows.append(min(2, left))
                left -= 2

    nav = 0
    if index > 0:
        builder.button(text="⬅️ Пред.",
                       callback_data=f"inv_book:{section}:{index - 1}")
        nav += 1
    if index + 1 < total:
        builder.button(text="След. ➡️",
                       callback_data=f"inv_book:{section}:{index + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ К списку",
                   callback_data=f"inv_sec:{section}:{index // 6}")
    builder.button(text="🎒 К отделениям", callback_data="inventory")
    rows.extend([1, 1])
    builder.adjust(*rows)
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


def auction_browse_keyboard(lots: list, page: int = 0, per_page: int = 6,
                            my_lot_count: int = 0):
    builder = InlineKeyboardBuilder()
    total = len(lots)
    max_page = max(0, (total - 1) // per_page) if total else 0
    page = max(0, min(page, max_page))
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
    if start + per_page < total:
        builder.button(text="➡️", callback_data=f"auction_browse:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="📢 Выставить вещь", callback_data="auction_my_items:0")
    builder.button(text=f"📋 Мои лоты ({my_lot_count})", callback_data="auction_my_lots")
    builder.button(text="◀️ К аукциону", callback_data="auction_menu")
    rows.extend([1, 1, 1])
    builder.adjust(*rows)
    return builder.as_markup()


def auction_listed_keyboard(my_lot_count: int = 0):
    """Действия сразу после выставления: свой лот ведём в раздел «Мои лоты»."""
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📋 Открыть мои лоты ({my_lot_count})", callback_data="auction_my_lots")
    builder.button(text="🛒 Общая витрина", callback_data="auction_browse:0")
    builder.button(text="🏠 К аукциону", callback_data="auction_menu")
    builder.adjust(1)
    return builder.as_markup()


def auction_lot_keyboard(lot_id: int, can_buy: bool, is_mine: bool = False):
    builder = InlineKeyboardBuilder()
    if is_mine:
        builder.button(text="🔴 ↩️ Снять с продажи", callback_data=f"auction_cancel:{lot_id}")
    elif can_buy:
        builder.button(text="🟢 💰 Купить", callback_data=f"auction_buy:{lot_id}")
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
        builder.button(text="🟢 🔨 Изготовить", callback_data=f"craft_do:{recipe_id}")
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
        builder.button(text="🟢 ⚡ Заточить", callback_data=f"upgrade_do:{inv_item_id}")
    builder.button(text="◀️ К списку", callback_data="upgrade_list:0")
    builder.button(text="🏠 К мастеру", callback_data="craft_menu")
    builder.adjust(1)
    return builder.as_markup()


def shop_book_keyboard(shop_item, page: int, total: int, can_buy: bool,
                       page_cb: str = "shop_page", back_cb: str = "back_to_cell",
                       back_text: str = "◀️ Уйти"):
    """Витрина-книга: одна страница — один товар с описанием и историей.

    Список из десятка строк ничего не рассказывал о предмете; чтобы понять,
    что покупаешь, приходилось гадать по названию. Книга показывает карточку
    целиком, а листание идёт стрелками.
    """
    builder = InlineKeyboardBuilder()
    rows = []
    if shop_item is not None:
        if can_buy:
            builder.button(
                text=f"🟢 💰 Купить за {shop_item.price}🪙",
                callback_data=f"buy:{shop_item.id}",
            )
        else:
            builder.button(text="🔒 Не по карману", callback_data="noop")
        rows.append(1)

    nav = 0
    if page > 0:
        builder.button(text="⬅️ Пред.", callback_data=f"{page_cb}:{page - 1}")
        nav += 1
    if page + 1 < total:
        builder.button(text="След. ➡️", callback_data=f"{page_cb}:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text=back_text, callback_data=back_cb)
    rows.append(1)
    builder.adjust(*rows)
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
    builder.button(text="🔴 ⚔️ Атаковать", callback_data="dungeon_combat_attack")
    builder.button(text="⚪ 🏃 Сбежать", callback_data="dungeon_flee")
    builder.adjust(2)
    return builder.as_markup()
