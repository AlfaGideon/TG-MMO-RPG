from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.enums import CharacterClass


def main_menu_keyboard(has_character: bool = False, is_admin: bool = False,
                       is_vip: bool = False, offline: bool = False):
    builder = InlineKeyboardBuilder()
    if not has_character:
        builder.button(text="⚔️ Создать героя", callback_data="create_character")
    else:
        builder.button(text="🩸 Пульс", callback_data="pulse")
        builder.button(text="🔕 Вести", callback_data="notify")
        builder.button(text="🧙 Профиль", callback_data="profile")
        builder.button(text="🎒 Инвентарь", callback_data="inventory")
        # Кнопка «В путь» теперь ведет сразу на экран перемещения (стрелки).
        # «Карта» остается для обзора локации.
        builder.button(text="🗺 Карта", callback_data="show_map")
        builder.button(text="🥾 В путь", callback_data="back_to_cell")
        builder.button(text="👥 Пати", callback_data="party_menu")
        builder.button(text="🏛 Гильдия", callback_data="guild_menu")
        builder.button(text="🧭 Репутация", callback_data="reputation")
        builder.button(text="🔮 Знамения", callback_data="omens_menu")
        builder.button(text="🎓 Наставник", callback_data="mentor_menu")
        builder.button(text="💀 Награды", callback_data="bounty_menu")
        builder.button(text="📖 Бестиарий", callback_data="bestiary_menu")
        builder.button(text="📜 Задания", callback_data="quests_menu")
        builder.button(text="💬 Сообщество", callback_data="chat_menu")
        builder.button(text="🏆 Топ", callback_data="leaderboard")
        builder.button(text="🏛 Летопись", callback_data="legends_hall")
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
        from aiogram.types import WebAppInfo
        builder.button(text="🌐 Открыть панель", web_app=WebAppInfo(url=login_url))
    builder.button(text="◀️ В главное меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def _clamp_page(page: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(page, total - 1))


def class_select_keyboard(classes: list, page: int = 0, faction: str | None = None):
    """Книжное листание классов: одна карточка класса на странице.

    Игрок сначала видит описание и бонусы текущего класса, листает
    «страницы», а уже затем нажимает выбор. Старое меню-список было
    неудобно: бонусы открывались только после отдельного нажатия.

    Фракция пробрасывается в callback-данные: порядок создания — сначала
    знамя, потом класс, поэтому страницы показывают портрет класса в
    цветах выбранной стороны. Без фракции (старые сообщения в чатах)
    формат данных прежний, всё работает как раньше.
    """
    sfx = f":{faction}" if faction else ""
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
        callback_data=f"select_class:{cls_def.key}{sfx}",
    )
    rows = [1]

    nav = 0
    if page > 0:
        builder.button(text="⬅️ Пред. страница", callback_data=f"class_page:{page - 1}{sfx}")
        nav += 1
    if page + 1 < total:
        builder.button(text="След. страница ➡️", callback_data=f"class_page:{page + 1}{sfx}")
        nav += 1
    if nav:
        rows.append(nav)

    # Назад — к выбору знамени (фракция идёт первой), в старом формате —
    # просто в главное меню.
    if faction:
        builder.button(text="◀️ К выбору фракции", callback_data="create_character")
    else:
        builder.button(text="◀️ Назад", callback_data="main_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def confirm_class_keyboard(char_class: str, back_page: int | None = None,
                           faction: str | None = None):
    sfx = f":{faction}" if faction else ""
    builder = InlineKeyboardBuilder()
    builder.button(text="🟢 ✅ Подтвердить", callback_data=f"confirm_class:{char_class}{sfx}")
    back_target = (f"class_page:{back_page}{sfx}" if back_page is not None
                   else "create_character")
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


def notify_keyboard(prefs: dict):
    """Центр вестей: тумблеры каналов и тихие часы."""
    from engine.notify import CHANNELS

    builder = InlineKeyboardBuilder()
    for key, label in CHANNELS:
        state = "✅ вкл" if prefs.get(key, True) else "⛔ выкл"
        builder.button(text=f"{label}: {state}", callback_data=f"notify_toggle:{key}")
    quiet = prefs.get("quiet_enabled", False)
    builder.button(text=f"🌙 Тихие часы: {'вкл' if quiet else 'выкл'}",
                   callback_data="notify_quiet")
    builder.button(text="🔕 В пульс", callback_data="pulse")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1, 1, 2)
    return builder.as_markup()


def pulse_keyboard(has_boss: bool = False, has_siege: bool = False):
    """Кнопки «Пульса героя»: быстрые переходы к событиям и меню."""
    builder = InlineKeyboardBuilder()
    if has_boss:
        builder.button(text="🏰 Идти к боссу", callback_data="world_boss")
    if has_siege:
        builder.button(text="🔥 Осада", callback_data="siege_menu")
    builder.button(text="📜 Задания", callback_data="quests_menu")
    builder.button(text="🧭 В мир", callback_data="back_to_cell")
    builder.button(text="🧙 Профиль", callback_data="profile")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1 if (has_boss or has_siege) else 2, 2)
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


def profile_book_keyboard(page: int, total: int, titles: list,
                          free_points: int | None = None,
                          can_rebirth: bool = False):
    """Навигация «книги о герое»: только закладки-разделы и выход в меню.

    Раньше здесь были и стрелки «Пред./След.», и закладки всех разделов —
    двойная навигация давала до шести кнопок под маленькой карточкой.
    Закладки сами ведут на любой разворот одним нажатием, поэтому стрелки
    убраны как лишние.

    `free_points` — число свободных очков характеристик; передаётся на
    странице «📊 Характеристики» и добавляет кнопку распределения очков.
    """
    builder = InlineKeyboardBuilder()
    rows = []

    tabs = 0
    for idx, title in enumerate(titles):
        if idx == page:
            continue
        builder.button(text=title, callback_data=f"profile_page:{idx}")
        tabs += 1
    if tabs:
        rows = [2] * (tabs // 2) + ([1] if tabs % 2 else [])

    if free_points is not None:
        builder.button(
            text=f"🎯 Очки характеристик ({free_points})",
            callback_data="stat_alloc",
        )
        rows.append(1)

    # Перерождение (core/prestige.py) — только когда герой дорос до порога:
    # показывать заведомо недоступную кнопку всем значит дразнить новичков.
    if can_rebirth:
        builder.button(text="♻️ Перерождение", callback_data="rebirth_menu")
        rows.append(1)

    builder.button(text="🏠 Меню", callback_data="main_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def stat_alloc_keyboard(values: dict, free_points: int):
    """Панель распределения очков характеристик: минус — стратегия — плюс.

    `values`: {ключ стата: (всего, вложено)} — подпись средней кнопки
    собирается тут, чтобы обработчикам оставалось только хранить очки.
    Средняя кнопка ничего не переключает — по нажатию показывает, что даёт
    следующее очко в этот стат.
    """
    from core import statpoints

    builder = InlineKeyboardBuilder()
    for key in statpoints.ALLOCATABLE:
        emoji, label = statpoints.STAT_LABELS[key]
        total_v, allocated = values.get(key, (0, 0))
        minus = "➖" if allocated > 0 else "▫️"
        plus = "➕" if free_points > 0 else "▫️"
        alloc_note = f" · +{allocated}" if allocated else ""
        builder.button(text=minus, callback_data=f"stat_del:{key}")
        builder.button(text=f"{emoji} {label}: {total_v}{alloc_note}",
                       callback_data=f"stat_hint:{key}")
        builder.button(text=plus, callback_data=f"stat_add:{key}")
    builder.button(text="📊 К характеристикам", callback_data="profile_stats_page")
    builder.button(text="🏠 Меню", callback_data="main_menu")
    builder.adjust(*([3] * len(statpoints.ALLOCATABLE)), 1, 1)
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


def _zoom_buttons(builder, screen: str, zoom: int) -> int:
    """Ряд «отдалить / масштаб / приблизить» для экранов карты.

    Возвращает ширину добавленного ряда (для builder.adjust).
    Уровень 0 — самый близкий вид, ZOOM_LEVELS-1 — вся локация.
    """
    from core.map_renderer import ZOOM_LEVELS

    zoom = max(0, min(int(zoom), ZOOM_LEVELS - 1))
    width = 0
    if zoom < ZOOM_LEVELS - 1:
        builder.button(text="➖ Отдалить",
                       callback_data=f"map_zoom:{screen}:{zoom + 1}")
        width += 1
    builder.button(text=f"🔍 {zoom + 1}/{ZOOM_LEVELS}", callback_data="noop")
    width += 1
    if zoom > 0:
        builder.button(text="➕ Приблизить",
                       callback_data=f"map_zoom:{screen}:{zoom - 1}")
        width += 1
    return width


def cell_movement_keyboard(can_dirs: dict, dungeon_template_id: int | None = None,
                           dir_labels: dict | None = None,
                           current_transition_label: str | None = None,
                           is_vip: bool = False,
                           current_transitions: list | None = None,
                           has_merchant: bool = False,
                           is_castle_basement: bool = False,
                           zoom: int | None = None):
    """
    3x3 grid: 8 directions + center inspect.
    can_dirs: {'nw': bool, 'n': bool, 'ne': bool, 'w': bool, 'e': bool,
               'sw': bool, 's': bool, 'se': bool}
    dir_labels: optional per-direction button text. Used to show doors
                (transitions) and rocks (blocked cells) directly on arrows.
    current_transition_label: совместимость со старой одиночной ссылкой.
    current_transitions: список (текст, callback) для общей лестничной клетки;
                на среднем этаже содержит сразу «вверх» и «вниз».
    zoom: уровень масштаба карты, если на экране сгенерированная карта
                (тогда под сеткой направлений появляется ряд +/-).
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

    # Лестница всегда сразу под стрелками. На промежуточном этаже обе
    # кнопки стоят в одном ряду: «вверх» и «вниз».
    transitions = list(current_transitions or [])
    if not transitions and current_transition_label:
        transitions = [(current_transition_label, "cell_transition")]
    for label, callback_data in transitions:
        builder.button(text=label, callback_data=callback_data)
    if transitions:
        rows.append(len(transitions))

    # Масштаб идёт уже после этажей, чтобы кнопки лестницы не терялись
    # между стрелками перемещения и служебной навигацией карты.
    if zoom is not None:
        zoom_row = _zoom_buttons(builder, "cell", zoom)
        rows.append(zoom_row)

    if dungeon_template_id:
        builder.button(text="🕳 Войти в подземелье", callback_data=f"dungeon_enter_tpl:{dungeon_template_id}")
        rows.append(1)

    if has_merchant:
        builder.button(text="🧳 Торговец", callback_data="merchant_menu")
        rows.append(1)

    if is_castle_basement:
        builder.button(text="⛏️ Прокопать подкоп", callback_data="dig_tunnel")
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


def map_view_keyboard(zoom: int = 2):
    """Раздел «Карта»: масштаб + мировая карта + быстрые путешествия.

    Карта крутится кнопками ➕/➖ прямо под картинкой — приближение
    даёт крупный вид вокруг героя, отдаление — всю локацию.
    """
    from core.map_renderer import ZOOM_LEVELS

    builder = InlineKeyboardBuilder()
    zoom_w = _zoom_buttons(builder, "map", zoom)
    builder.button(text="🌍 Карта мира", callback_data="world_map")
    builder.button(text="🏠 Быстрое перемещение", callback_data="journey")
    builder.button(text="◀️ Назад", callback_data="back_to_cell")
    builder.adjust(zoom_w, 1, 1, 1)
    return builder.as_markup()


def world_map_keyboard():
    """Мировая карта — только обзор.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="🗺 К карте локации", callback_data="show_map")
    builder.button(text="◀️ Назад в мир", callback_data="back_to_cell")
    builder.adjust(1)
    return builder.as_markup()


def travel_keyboard(destinations: list):
    """Экран «Быстрое перемещение»: список посещённых локаций.
    """
    builder = InlineKeyboardBuilder()
    for loc in destinations[:8]:
        builder.button(text=f"🏠 {loc.name}", callback_data=f"travel:{loc.id}")
    builder.button(text="🗺 К карте локации", callback_data="show_map")
    builder.button(text="◀️ Назад в мир", callback_data="back_to_cell")
    builder.adjust(1)
    return builder.as_markup()


def merchant_book_keyboard(ware, page: int, total: int, can_buy: bool):
    """Витрина бродячего торговца: карточка товара + листание."""
    builder = InlineKeyboardBuilder()
    rows = []
    if can_buy:
        builder.button(
            text=f"🟢 💰 Купить за {ware['price']}🟤",
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
                     has_landmark: bool = False, has_grave: bool = False,
                     has_players: bool = False, has_outpost: bool = False,
                     has_caravan: bool = False, has_siege: bool = False,
                     has_water: bool = False, has_forest: bool = False,
                     can_dig: bool = False, has_treasure: bool = False,
                     is_town: bool = False, illusory_dirs: list | None = None):
    builder = InlineKeyboardBuilder()
    # Иллюзорная стена рядом: развеять её можно только стоя вплотную.
    for direction, label in (illusory_dirs or []):
        builder.button(text=f"🔍 Простучать стену {label}",
                       callback_data=f"reveal_wall:{direction}")
    if has_outpost:
        builder.button(text="🏰 Аванпост фракций", callback_data="outpost_menu")
    if has_siege:
        builder.button(text="🔥 Осада Цитадели", callback_data="siege_menu")
    if has_caravan:
        builder.button(text="🐫 Торговый караван", callback_data="caravan_menu")
    if has_mob:
        builder.button(text="⚔️ Атаковать", callback_data="cell_attack")
    if has_players:
        builder.button(text="⚔️ Напасть на игрока", callback_data="pvp_select")
        # Прямой обмен «рука в руку» (IDEAS-next пункт 2): та же клетка,
        # никакой комиссии аукциона.
        builder.button(text="🎁 Подарить игроку", callback_data="gift_select")
    if has_landmark:
        builder.button(text="❇️ Изучить", callback_data="study_landmark")
    if has_grave:
        builder.button(text="💰 Забрать из могилы", callback_data="claim_grave")
        builder.button(text="🕯 Почтить память (+Прах предков)", callback_data="harvest_ash")
        builder.button(text="👻 Призрачный торговец", callback_data="spectral_nomad_menu")
    if has_water:
        builder.button(text="🎣 Закинуть удочку (Рыбалка)", callback_data="gather_fish")
    if has_forest:
        builder.button(text="🌿 Сбор трав (Травничество)", callback_data="gather_herbs")
    # Археология (core/archaeology.py): копать можно везде за городом,
    # а «выкопать клад» появляется только на клетке из карты сокровищ.
    if has_treasure:
        builder.button(text="🏆 Выкопать клад по карте!", callback_data="dig_treasure")
    if can_dig:
        builder.button(text="⛏ Копать землю (Археология)", callback_data="dig_relic")
    if is_town:
        builder.button(text="🏦 Вклад в лавку", callback_data="invest_menu")
        builder.button(text="💍 Ломбард", callback_data="pawnshop_menu")
        builder.button(text="🕯 Чёрный рынок", callback_data="blackmarket_menu")
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


def spectral_nomad_keyboard(wares: list, my_ash: int):
    builder = InlineKeyboardBuilder()
    for w in wares:
        builder.button(text=f"{w['name']} ({w['cost_ash']} 🕯)", callback_data=f"spec_buy:{w['key']}")
    builder.button(text="◀️ Назад", callback_data="inspect")
    builder.adjust(1)
    return builder.as_markup()


def bounty_board_keyboard(bounties: list):
    builder = InlineKeyboardBuilder()
    for b in bounties:
        mname = b.mob.name if b.mob else "Монстр"
        loc_name = b.location.name if b.location else "Мир"
        builder.button(text=f"💀 {b.bounty_title or 'Убийца'}: {mname} ({loc_name})", callback_data=f"bounty_track:{b.id}")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def outpost_keyboard(outpost_id: int, can_attack: bool = True, can_repair: bool = False):
    builder = InlineKeyboardBuilder()
    if can_attack:
        builder.button(text="⚔️ Штурмовать аванпост", callback_data=f"outpost_hit:{outpost_id}")
    if can_repair:
        builder.button(text="🔨 Укрепить аванпост (+HP)", callback_data=f"outpost_hit:{outpost_id}")
    builder.button(text="◀️ Назад", callback_data="inspect")
    builder.adjust(1)
    return builder.as_markup()


def caravan_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="🛡 Сопроводить обоз (+Опыт, Защита)", callback_data=f"caravan_act:{event_id}:escort")
    builder.button(text="⚔️ Разграбить караван (+Добыча)", callback_data=f"caravan_act:{event_id}:ambush")
    builder.button(text="◀️ Назад", callback_data="inspect")
    builder.adjust(1)
    return builder.as_markup()


def sabotage_menu_keyboard(target_loc_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="☠️ Отравить запасы колодцев", callback_data=f"sabotage_do:{target_loc_id}:poison_supplies")
    builder.button(text="🔔 Поставить сигнальные растяжки", callback_data=f"sabotage_do:{target_loc_id}:scout_alarm")
    builder.button(text="🔨 Испортить кузнечные меха", callback_data=f"sabotage_do:{target_loc_id}:disrupt_forge")
    builder.button(text="◀️ Назад", callback_data="dig_tunnel")
    builder.adjust(1)
    return builder.as_markup()


def faction_treasury_keyboard(faction_key: str, is_leader: bool = False):
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Пожертвовать 100🟤", callback_data=f"treasury_donate:{faction_key}:100")
    builder.button(text="💰 Пожертвовать 500🟤", callback_data=f"treasury_donate:{faction_key}:500")
    if is_leader:
        builder.button(text="⚔️ Указ: Милитаризация", callback_data=f"decree_enact:{faction_key}:militarization")
        builder.button(text="💰 Указ: Торговый бум", callback_data=f"decree_enact:{faction_key}:trade_boom")
        builder.button(text="🛡 Указ: Цитадель", callback_data=f"decree_enact:{faction_key}:citadel")
        builder.button(text="🔮 Указ: Тайные знания", callback_data=f"decree_enact:{faction_key}:knowledge")
    builder.button(text="◀️ Назад", callback_data="reputation")
    builder.adjust(1)
    return builder.as_markup()


def combat_keyboard(is_channeling: bool = False, stance: str = "balanced"):
    builder = InlineKeyboardBuilder()
    if is_channeling:
        builder.button(text="💥 ПРЕРВАТЬ ЗАКЛИНАНИЕ!", callback_data="combat_interrupt")
    builder.button(text="🔴 ⚔️ Атаковать", callback_data="combat_attack")
    builder.button(text="🔵 🛡️ Защита", callback_data="combat_defend")
    builder.button(text="🟡 ✨ Умение", callback_data="combat_skill")
    builder.button(text="🥋 Стойка", callback_data="combat_stance_menu")
    builder.button(text="⚪ 🏃 Побег", callback_data="combat_flee")
    if is_channeling:
        builder.adjust(1, 2, 2, 1)
    else:
        builder.adjust(2, 2, 1)
    return builder.as_markup()


def combat_stance_keyboard(current_stance: str = "balanced"):
    builder = InlineKeyboardBuilder()
    builder.button(text="🗡 Берсерк (+30% урон, −20% броня)", callback_data="combat_set_stance:berserk")
    builder.button(text="🛡 Парирование (+25% броня, контратака)", callback_data="combat_set_stance:parry")
    builder.button(text="🧘 Концентрация (+25% магия, +MP)", callback_data="combat_set_stance:focus")
    builder.button(text="⚖️ Баланс (обычная)", callback_data="combat_set_stance:balanced")
    builder.button(text="◀️ Назад в бой", callback_data="combat_back")
    builder.adjust(1)
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
    builder.button(
        text=f"🏠 Дом ({counts.get('home', 0)}/{counts.get('home_cap', 0)})",
        callback_data="inv_sec:home:0")
    builder.button(text="🏠 Меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def inventory_section_keyboard(items: list, section: str, page: int = 0,
                               per_page: int = 6, header_buttons=None):
    """Список одного отделения. Открытие вещи ведёт в книгу предметов.

    `header_buttons` — дополнительные кнопки над списком: так в
    отделении дома живут «осесть» и «надстроить», не связанные с
    конкретной вещью.
    """
    builder = InlineKeyboardBuilder()
    start = page * per_page
    chunk = items[start:start + per_page]

    head = list(header_buttons or [])
    for text, cb in head:
        builder.button(text=text, callback_data=cb)

    for idx, inv_item in enumerate(chunk, start=start):
        eq = "✅ " if inv_item.is_equipped else ""
        icon = inv_item.item.icon if inv_item.item else "❔"
        qty = f" ×{inv_item.quantity}" if (inv_item.quantity or 1) > 1 else ""
        inst = inv_item.instance if inv_item.instance_id else None
        badge = f"{inst.badge()} " if inst else ""
        # В колбэке — id вещи, а не её место в списке: список мог
        # сдвинуться (что-то продали, сломали, положили в карман), и
        # старая кнопка открывала бы соседний предмет.
        builder.button(
            text=f"{eq}{badge}{icon} {inv_item.display_name()}{qty}",
            callback_data=f"inv_book:{section}:{idx}:{inv_item.id}",
        )
    rows = [1] * len(head) + [1] * len(chunk)

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
                       in_stash: bool = False, can_stash: bool = False,
                       can_salvage: bool = False, can_pawn: bool = False,
                       in_home: bool = False, can_home: bool = False):
    """Книга предметов: карточка вещи + листание соседних страниц."""
    builder = InlineKeyboardBuilder()
    rows = []

    actions = 0
    # Дом — тот же сейф, что и карман: пока вещь в сундуке, её нельзя
    # надеть, продать или заложить — сначала достань.
    locked = in_stash or in_home
    if can_equip and not locked:
        if is_equipped:
            builder.button(text="🟡 🚫 Снять", callback_data=f"unequip:{inv_item_id}")
        else:
            builder.button(text="🟢 ✅ Экипировать", callback_data=f"equip:{inv_item_id}")
        actions += 1
    if can_use and not locked:
        builder.button(text="🔵 🧪 Использовать", callback_data=f"use:{inv_item_id}")
        actions += 1
    if can_sell and not is_equipped and not locked:
        builder.button(text="🟣 ⚖️ На аукцион", callback_data=f"auction_sell:{inv_item_id}")
        actions += 1
    # Разбор на материалы (core/salvage.py) и залог у ростовщика
    # (core/pawnshop.py) — только для своей, не надетой и не спрятанной вещи.
    if can_salvage and not is_equipped and not locked:
        builder.button(text="🟠 🔧 Разобрать", callback_data=f"salvage:{inv_item_id}")
        actions += 1
    if can_pawn and not is_equipped and not locked:
        builder.button(text="⚫️ 💍 Заложить", callback_data=f"pawn:{inv_item_id}")
        actions += 1
    if in_stash:
        builder.button(text="🟢 🎒 Достать из кармана",
                       callback_data=f"stash_take:{inv_item_id}")
        actions += 1
    elif can_stash:
        builder.button(text="🟢 🔒 Убрать в карман",
                       callback_data=f"stash_put:{inv_item_id}")
        actions += 1
    if in_home:
        builder.button(text="🏠 🎒 Достать из сундука",
                       callback_data=f"home_take:{inv_item_id}")
        actions += 1
    elif can_home:
        builder.button(text="🏠 Отнести в сундук",
                       callback_data=f"home_put:{inv_item_id}")
        actions += 1
    if not locked and not is_equipped:
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
    builder.button(text="🔨 Торги с молотка", callback_data="bids_menu")
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
            text=f"{badge}{icon} {name} — {lot.price}🟤",
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
            text=f"{label} — {price}🟤",
            callback_data=f"auction_list:{inv_id}:{price}",
        )
    rows = [1] * len(prices)
    builder.button(
        text=f"⚡ Сразу скупщику — {npc_price}🟤",
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
            text=f"↩️ {icon} {name} ({lot.price}🟤)",
            callback_data=f"auction_cancel:{lot.id}",
        )
    builder.button(text="◀️ К аукциону", callback_data="auction_menu")
    builder.adjust(1)
    return builder.as_markup()


def craft_menu_keyboard(station: str = "any"):
    builder = InlineKeyboardBuilder()
    builder.button(text="📜 Рецепты", callback_data=f"craft_list:{station}:0")
    builder.button(text="📋 Стол заказов игроков", callback_data="craft_orders_menu")
    builder.button(text="🔨 Заточить предмет", callback_data="upgrade_list:0")
    builder.button(text="🔩 Починить снаряжение", callback_data="repair_list:0")
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


def repair_list_keyboard(items: list, station: str, page: int = 0,
                         per_page: int = 6):
    """Список изношенного снаряжения на починку."""
    builder = InlineKeyboardBuilder()
    start = page * per_page
    chunk = items[start:start + per_page]

    for inv in chunk:
        eq = "✅ " if inv.is_equipped else ""
        icon = inv.item.icon if inv.item else "❔"
        builder.button(
            text=f"{eq}{icon} {inv.display_name()}",
            callback_data=f"repair_view:{inv.id}",
        )
    rows = [1] * len(chunk)

    nav = 0
    if page > 0:
        builder.button(text="⬅️", callback_data=f"repair_list:{page - 1}")
        nav += 1
    if start + per_page < len(items):
        builder.button(text="➡️", callback_data=f"repair_list:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="◀️ К мастеру", callback_data="craft_menu")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


def repair_item_keyboard(inv_item_id: int, can_repair: bool, station: str):
    builder = InlineKeyboardBuilder()
    if can_repair:
        builder.button(text="🟢 🔩 Починить", callback_data=f"repair_do:{inv_item_id}")
    builder.button(text="◀️ К списку", callback_data="repair_list:0")
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
                text=f"🟢 💰 Купить за {shop_item.price}🟤",
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


def faction_select_keyboard(char_id: int, page: int = 0):
    """Книга выбора фракции: одна страница — один герб с бонусами.

    Раньше выбор был четырьмя кнопками под длинной простынёй текста —
    фракции выбирали вслепую, не увидев ни герба, ни награды. Как и в
    книге классов, теперь игрок листает страницы, рассматривает герб и
    бонусы, и только потом жмёт «Выбрать».
    """
    from engine.factions import FACTIONS, ORDER

    builder = InlineKeyboardBuilder()
    total = len(ORDER)
    page = max(0, min(page, total - 1))
    key = ORDER[page]
    icon, name = FACTIONS[key][0], FACTIONS[key][1]

    builder.button(
        text=f"✅ Выбрать: {icon} {name}",
        callback_data=f"start_faction:{char_id}:{key}",
    )
    rows = [1]

    nav = 0
    if page > 0:
        builder.button(text="⬅️ Пред. знамя", callback_data=f"faction_page:{char_id}:{page - 1}")
        nav += 1
    if page + 1 < total:
        builder.button(text="След. знамя ➡️", callback_data=f"faction_page:{char_id}:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)

    builder.button(text="📖 Книга лора фракций", callback_data=f"faction_lore:{char_id}:{page}")
    rows.append(1)
    builder.adjust(*rows)
    return builder.as_markup()


# ── КЛАВИАТУРЫ КОЛИЗЕЯ, ФАМИЛЬЯРОВ И АЛТАРЕЙ ─────────────────

def arena_menu_keyboard(opponents: list, my_rating: int, my_tokens: int):
    builder = InlineKeyboardBuilder()
    for opp in opponents:
        builder.button(
            text=f"⚔️ {opp.name} ({opp.arena_rating} 🏆 | GS: {opp.gear_score})",
            callback_data=f"arena_duel:{opp.id}"
        )
    builder.button(text="🔄 Обновить список", callback_data="arena_menu")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def familiar_menu_keyboard(has_familiar: bool = False):
    builder = InlineKeyboardBuilder()
    if not has_familiar:
        builder.button(text="🦅 Приручить Ворона-падальщика (500🟤)", callback_data="familiar_adopt:crow")
        builder.button(text="💡 Приручить Светляка Бездны (500🟤)", callback_data="familiar_adopt:firefly")
        builder.button(text="🐺 Приручить Теневого пса (600🟤)", callback_data="familiar_adopt:hound")
    else:
        builder.button(text="🍗 Покормить и развить спутника", callback_data="familiar_feed")
        builder.button(text="🔄 Сменить питомца", callback_data="familiar_change")
    builder.button(text="◀️ В профиль", callback_data="profile")
    builder.adjust(1)
    return builder.as_markup()


def altar_keyboard(run_id: int, altar_type: str):
    builder = InlineKeyboardBuilder()
    if altar_type == "abyssal":
        builder.button(text="🖤 Принять Дар Бездны (+40% урон, −25% HP)", callback_data=f"dungeon_altar:{run_id}:abyssal")
    elif altar_type == "blood":
        builder.button(text="🩸 Заключить Кровавую сделку (100% Heal, −150🟤)", callback_data=f"dungeon_altar:{run_id}:blood")
    else:
        builder.button(text="👁 Прикоснуться к Оку Прозрения (Открыть карту)", callback_data=f"dungeon_altar:{run_id}:insight")
    builder.button(text="🚶 Пройти мимо", callback_data="dungeon_menu")
    builder.adjust(1)
    return builder.as_markup()


def endless_stair_keyboard(run_id: int, next_floor: int):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🪜 Спуститься на этаж {next_floor} (Сложнее + Лут)", callback_data=f"dungeon_dive:{run_id}")
    builder.button(text="💰 Забрать добычу и выйти наружу", callback_data="dungeon_exit")
    builder.adjust(1)
    return builder.as_markup()


def trap_keyboard(cell_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="🛠 Обезвредить ловушку (Ловкость)", callback_data=f"dungeon_disarm:{cell_id}")
    builder.button(text="🏃 Осторожно перешагнуть", callback_data="dungeon_menu")
    builder.adjust(1)
    return builder.as_markup()


def captive_keyboard(cell_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="🕊 Освободить пленника (+Награда)", callback_data=f"dungeon_free:{cell_id}")
    builder.button(text="🚶 Пройти мимо", callback_data="dungeon_menu")
    builder.adjust(1)
    return builder.as_markup()


def craft_orders_keyboard(orders: list):
    builder = InlineKeyboardBuilder()
    for o in orders:
        rec_name = o.recipe.result_item.name if o.recipe and o.recipe.result_item else "Предмет"
        builder.button(
            text=f"🔨 {rec_name} (+{o.reward_bronze}🟤)",
            callback_data=f"fulfill_order:{o.id}"
        )
    builder.button(text="◀️ В мастерскую", callback_data="craft_menu")
    builder.adjust(1)
    return builder.as_markup()
