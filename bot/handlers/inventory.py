from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import durability, history
from core import homestead as core_home
from core import stash as stash_core
from core.database import async_session
from core.models import (User, Character, InventoryItem, Item, ItemInstance,
                         Location)
from core.enums import ItemType
from core.stats import combat_stats
from bot.keyboards.inline import (
    inventory_hub_keyboard, inventory_section_keyboard, item_book_keyboard,
    main_menu_keyboard,
)
from bot.utils.texts import item_detail_text, item_line
from bot.utils.photos import send_or_edit_photo

router = Router()

# Расходники нельзя «надеть», их используют
EQUIPPABLE = {
    ItemType.WEAPON, ItemType.ARMOR, ItemType.HELMET,
    ItemType.BOOTS, ItemType.ACCESSORY,
}


async def load_inventory(session, character_id: int):
    """Инвентарь с подгруженными шаблонами и уникальными экземплярами."""
    result = await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character_id)
        .options(
            selectinload(InventoryItem.item),
            selectinload(InventoryItem.instance).selectinload(ItemInstance.item),
        )
        .order_by(
            InventoryItem.is_equipped.desc(),
            InventoryItem.id,
        )
    )
    return result.scalars().all()


async def stash_summary(session, character) -> str:
    """Строка «сколько в кармане» для экрана инвентаря."""
    kept = len(await stash_core.stashed(session, character))
    cap = await stash_core.capacity(session, character)
    return f"🔒 Карман: {kept}/{cap}"


async def _character_of(session, telegram_id: int):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    result = await session.execute(
        select(Character).where(Character.user_id == user.id)
    )
    return result.scalar_one_or_none()


def inventory_text(items, stats: dict) -> str:
    """Заголовок сумки: сводка по надетому + список."""
    equipped = [i for i in items if i.is_equipped]
    lines = [
        "🎒 <b>Инвентарь</b>",
        f"Предметов: {len(items)} | Надето: {len(equipped)}",
        "",
        f"⚔️ Урон от снаряжения: <b>+{stats['damage']}</b> | "
        f"🛡 Защита: <b>+{stats['defense']}</b>",
    ]
    bonus = stats["bonus"]
    extras = []
    for key, label in (
        ("strength", "💪"), ("agility", "🏃"), ("intelligence", "🧠"),
        ("endurance", "🛡"), ("luck", "🍀"), ("max_hp", "❤️"), ("max_mp", "💙"),
    ):
        if bonus.get(key):
            extras.append(f"{label} +{bonus[key]}")
    if extras:
        lines.append("Бонусы: " + " ".join(extras))
    lines.append("")
    lines.append("Выбери предмет:")
    return "\n".join(lines)


SECTIONS = {
    "gear": "🛡 Снаряжение",
    "bag": "🎒 Сумка · предметы",
    "mat": "🧱 Сумка · материалы",
    "stash": "🔒 Карман",
    "home": "🏠 Дом",
}

SECTION_HINTS = {
    "gear": "Надетое остаётся с тобой даже после гибели.",
    "bag": "Содержимое сумки частично теряется при гибели героя.",
    "mat": "Сырьё для ремесла: само по себе бесполезно, в кузне — незаменимо.",
    "stash": "Защищённый карман: эти вещи переживут смерть. "
             "Перекладывать можно только в безопасных землях.",
    "home": "Домашний сундук: тоже переживёт гибель, но вместительнее "
            "кармана и открывается только у своих дверей.",
}


def split_sections(items) -> dict:
    """Разложить инвентарь по отделениям: снаряжение / предметы / материалы / карман.

    Одна общая простыня мешала: надетое, руда и спрятанное в карман шли
    вперемешку, и найти нужное оружие было делом случая.
    """
    buckets = {"gear": [], "bag": [], "mat": [], "stash": [], "home": []}
    for inv in items:
        if getattr(inv, "in_home", False):
            buckets["home"].append(inv)
        elif inv.in_stash:
            buckets["stash"].append(inv)
        elif inv.is_equipped:
            buckets["gear"].append(inv)
        elif inv.item is not None and inv.item.item_type == ItemType.MATERIAL:
            buckets["mat"].append(inv)
        else:
            buckets["bag"].append(inv)
    return buckets


@router.callback_query(F.data == "inventory")
async def inventory(callback: CallbackQuery):
    """Главный экран сумки: три отделения + материалы отдельной полкой."""
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        items = await load_inventory(session, character.id)
        buckets = split_sections(items)
        stats = await combat_stats(session, character)
        cap = await stash_core.capacity(session, character)
        # Раньше красивый фон лежал в static/ui, но этот экран отправлялся
        # только текстом — поэтому Telegram его вообще не видел.
        from core import ui_images
        inventory_img = await ui_images.get(session, "inventory")

    counts = {k: len(v) for k, v in buckets.items()}
    counts["stash_cap"] = cap
    counts["home_cap"] = core_home.capacity_for(character)

    lines = [
        "🎒 <b>Снаряжение героя</b>",
        f"Всего вещей: <b>{len(items)}</b>",
        "",
        f"⚔️ Урон от снаряжения: <b>+{stats['damage']}</b> | "
        f"🛡 Защита: <b>+{stats['defense']}</b>",
    ]
    extras = []
    for key, label in (
        ("strength", "💪"), ("agility", "🏃"), ("intelligence", "🧠"),
        ("endurance", "🛡"), ("luck", "🍀"), ("max_hp", "❤️"), ("max_mp", "💙"),
    ):
        if stats["bonus"].get(key):
            extras.append(f"{label} +{stats['bonus'][key]}")
    if extras:
        lines.append("Бонусы: " + " ".join(extras))
    lines += [
        "",
        "Выбери отделение:",
        "<i>🎒 сумка теряется при гибели, 🔒 карман — нет.</i>",
    ]

    await send_or_edit_photo(
        callback,
        "\n".join(lines),
        reply_markup=inventory_hub_keyboard(counts),
        image_url=inventory_img,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("inv_sec:"))
async def inventory_section(callback: CallbackQuery):
    _, section, raw_page = callback.data.split(":")
    page = int(raw_page)
    if section not in SECTIONS:
        await callback.answer("Неизвестное отделение.", show_alert=True)
        return

    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        items = await load_inventory(session, character.id)
        bucket = split_sections(items)[section]
        cap = await stash_core.capacity(session, character)
        # Дом: состояние считаем здесь же — вне сессии БД не тронуть.
        hst = (await core_home.home_state(session, character)
               if section == "home" else None)
        from core import ui_images
        inventory_img = await ui_images.get(session, "inventory")

    title = SECTIONS[section]
    header = []
    if hst is not None:
        title += f" ({hst['count']}/{hst['capacity']})"
        if not hst["settled"]:
            header.append((f"🏠 Оселиться здесь ({hst['next_cost']}🟤)", "home_buy"))
        elif hst["next_cost"]:
            header.append((f"⬆️ Надстроить ({hst['next_cost']}🟤)", "home_up"))
    elif section == "stash":
        title += f" ({len(bucket)}/{cap})"
    else:
        title += f" ({len(bucket)})"

    if not bucket:
        text = f"<b>{title}</b>\n\n<i>Здесь пока пусто.</i>"
    else:
        text = (f"<b>{title}</b>\n<i>{SECTION_HINTS[section]}</i>\n\n"
                + "\n".join("• " + item_line(inv) for inv in bucket[page * 6:page * 6 + 6])
                + "\n\nОткрой вещь, чтобы прочитать её страницу в книге.")

    await send_or_edit_photo(
        callback,
        text,
        reply_markup=inventory_section_keyboard(bucket, section, page=page,
                                                header_buttons=header),
        image_url=inventory_img,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("inv_book:"))
async def inventory_book(callback: CallbackQuery):
    """Книга предметов: карточка вещи с описанием, историей и листанием."""
    # Формат: inv_book:<секция>:<индекс>[:<id вещи>]. Хвост с id новый —
    # старые сообщения без него продолжают работать по индексу.
    parts = callback.data.split(":")
    section, raw_index = parts[1], parts[2]
    wanted_id = int(parts[3]) if len(parts) > 3 else None
    index = int(raw_index)
    if section not in SECTIONS:
        await callback.answer("Неизвестное отделение.", show_alert=True)
        return

    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        items = await load_inventory(session, character.id)
        bucket = split_sections(items)[section]
        if not bucket:
            await callback.answer("Отделение пусто.", show_alert=True)
            return
        # Ищем ту самую вещь по id; если её уже нет (продали из другого
        # сообщения) — честно говорим об этом, а не открываем соседнюю.
        if wanted_id is not None:
            found = next((i for i, inv in enumerate(bucket)
                          if inv.id == wanted_id), None)
            if found is None:
                await callback.answer(
                    "Этой вещи уже нет в сумке — список обновился.",
                    show_alert=True)
                await inventory(callback)
                return
            index = found
        else:
            index = max(0, min(index, len(bucket) - 1))
        inv_item = bucket[index]
        item = inv_item.item

        rows = await history.load(session, inv_item.instance_id) \
            if inv_item.instance_id else []
        head = (f"📖 <b>{SECTIONS[section]}</b> — страница "
                f"<b>{index + 1}</b> из <b>{len(bucket)}</b>\n"
                "━━━━━━━━━━━━━━━\n")
        text = head + item_detail_text(inv_item, rows)

        # У материалов истории владельцев нет — даём хотя бы назначение.
        if item is not None and item.item_type == ItemType.MATERIAL:
            text += ("\n\n🔨 <i>Материал: отнеси ремесленнику — "
                     "из такого куются вещи с собственной судьбой.</i>")

        can_equip = item is not None and item.item_type in EQUIPPABLE
        if can_equip and inv_item.instance is not None and \
                durability.is_gear(inv_item.instance, item) and \
                durability.broken(inv_item.instance):
            can_equip = False
        can_use = item is not None and item.item_type == ItemType.CONSUMABLE
        can_sell = bool(inv_item.instance_id) and item is not None and item.is_sellable
        # Разобрать можно снаряжение (материалы и расходники — нет),
        # заложить — только именной экземпляр (правило core/pawnshop.py).
        can_salvage = can_equip
        can_pawn = bool(inv_item.instance_id)

        location = await session.get(Location, character.location_id)
        can_stash = (stash_core.safe_here(location)
                     and await stash_core.free_slots(session, character) > 0)
        can_home = inv_item.in_home or (core_home.at_home(character)
                                        and await core_home.free(session, character) > 0)
        if inv_item.in_stash:
            text += "\n\n🔒 <i>В защищённом кармане — не теряется при гибели.</i>"
        elif getattr(inv_item, "in_home", False):
            text += "\n\n🏠 <i>В домашнем сундуке — цел и невредим дома.</i>"
        elif not stash_core.safe_here(location):
            text += "\n\n<i>Карман открывается только в безопасных землях.</i>"

        # Если у конкретного предмета ещё нет иконки, оставляем игроку
        # полноценный экран инвентаря вместо внезапного голого текста.
        from core import ui_images
        inventory_img = await ui_images.get(session, "inventory")

    await send_or_edit_photo(
        callback,
        text,
        reply_markup=item_book_keyboard(
            inv_item.id, section, index, len(bucket),
            is_equipped=bool(inv_item.is_equipped),
            can_equip=can_equip, can_use=can_use, can_sell=can_sell,
            in_stash=bool(inv_item.in_stash), can_stash=can_stash,
            can_salvage=can_salvage, can_pawn=can_pawn,
            in_home=bool(inv_item.in_home), can_home=can_home,
        ),
        image_url=(item.image_url or inventory_img) if item else inventory_img,
    )


@router.callback_query(F.data.startswith("item:"))
async def item_detail(callback: CallbackQuery):
    """Старые сообщения с `item:<id>` — ведём в книгу нужного отделения."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        items = await load_inventory(session, character.id)
        buckets = split_sections(items)

    for section, bucket in buckets.items():
        for idx, inv in enumerate(bucket):
            if inv.id == inv_id:
                callback.data = f"inv_book:{section}:{idx}:{inv.id}"
                await inventory_book(callback)
                return
    await callback.answer("Предмет не найден.", show_alert=True)


@router.callback_query(F.data.startswith("stash_put:"))
async def stash_put(callback: CallbackQuery):
    """Убрать вещь в защищённый карман."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        inv_item = await session.get(InventoryItem, inv_id)
        if character is None or inv_item is None:
            await callback.answer("Предмет не найден.", show_alert=True)
            return
        location = await session.get(Location, character.location_id)
        if not stash_core.safe_here(location):
            await callback.answer(
                "Карман открывается только в безопасных землях.", show_alert=True)
            return
        ok, msg = await stash_core.put(session, character, inv_item)
        await session.commit()
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await item_detail(callback)


@router.callback_query(F.data.startswith("stash_take:"))
async def stash_take(callback: CallbackQuery):
    """Достать вещь из кармана обратно в сумку."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        inv_item = await session.get(InventoryItem, inv_id)
        if character is None or inv_item is None:
            await callback.answer("Предмет не найден.", show_alert=True)
            return
        location = await session.get(Location, character.location_id)
        if not stash_core.safe_here(location):
            await callback.answer(
                "Карман открывается только в безопасных землях.", show_alert=True)
            return
        ok, msg = await stash_core.take(session, character, inv_item)
        await session.commit()
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await item_detail(callback)


@router.callback_query(F.data == "home_buy")
async def home_buy(callback: CallbackQuery):
    """Осесть: дом привязывается к текущей безопасной локации."""
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        ok, msg = await core_home.settle(session, character)
        await session.commit()
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await _show_home(callback)


@router.callback_query(F.data == "home_up")
async def home_upgrade(callback: CallbackQuery):
    """Надстройка: следующий уровень дома за бронзу."""
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        ok, msg = await core_home.upgrade(session, character)
        await session.commit()
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await _show_home(callback)


@router.callback_query(F.data.startswith("home_put:"))
async def home_put(callback: CallbackQuery):
    """Вещь → домашний сундук (только у своих дверей)."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        inv_item = await session.get(InventoryItem, inv_id)
        if character is None or inv_item is None:
            await callback.answer("Предмет не найден.", show_alert=True)
            return
        ok, msg = await core_home.put(session, character, inv_item)
        await session.commit()
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await item_detail(callback)


@router.callback_query(F.data.startswith("home_take:"))
async def home_take(callback: CallbackQuery):
    """Сундук → сумка."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        inv_item = await session.get(InventoryItem, inv_id)
        if character is None or inv_item is None:
            await callback.answer("Предмет не найден.", show_alert=True)
            return
        ok, msg = await core_home.take(session, character, inv_item)
        await session.commit()
    await callback.answer(msg, show_alert=not ok)
    if ok:
        await item_detail(callback)


async def _show_home(callback: CallbackQuery):
    """Перерисовать отделение дома после покупки/надстройки."""
    callback.data = "inv_sec:home:0"
    await inventory_section(callback)


@router.callback_query(F.data.startswith("equip:"))
async def equip_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        item = inv_item.item
        if item.item_type not in EQUIPPABLE:
            await callback.answer("Это нельзя надеть.", show_alert=True)
            return

        if inv_item.instance is not None and \
                durability.is_gear(inv_item.instance, item) and \
                durability.broken(inv_item.instance):
            await callback.answer(
                "🔩 Эта вещь сломана. Почини её в кузнице!", show_alert=True
            )
            return

        character = await session.get(Character, inv_item.character_id)
        if character.level < (item.level_requirement or 1):
            await callback.answer(
                f"Нужен {item.level_requirement} уровень!", show_alert=True
            )
            return

        # Снимаем то, что уже занимает этот слот
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == character.id)
            .where(InventoryItem.is_equipped == True)  # noqa: E712
            .options(selectinload(InventoryItem.item))
        )
        for eq in result.scalars().all():
            if eq.item.item_type == item.item_type:
                eq.is_equipped = False

        inv_item.is_equipped = True
        name = inv_item.display_name()
        await session.commit()

    await callback.answer(f"Экипировано: {name}")
    # Остаёмся на странице вещи: надел — сразу видишь обновлённую карточку.
    await item_detail(callback)


@router.callback_query(F.data.startswith("unequip:"))
async def unequip_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        inv_item = await session.get(InventoryItem, inv_id)
        if inv_item:
            inv_item.is_equipped = False
            await session.commit()
    await callback.answer("Предмет снят.")
    await item_detail(callback)


@router.callback_query(F.data.startswith("use:"))
async def use_item(callback: CallbackQuery):
    """Расходники: зелья восстанавливают HP/MP по своим бонусам."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.item))
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item or inv_item.item.item_type != ItemType.CONSUMABLE:
            await callback.answer("Это нельзя использовать.", show_alert=True)
            return

        character = await session.get(Character, inv_item.character_id)
        item = inv_item.item
        bonuses = inv_item.bonuses()

        # Если у зелья не проставлены бонусы — лечим по редкости
        heal = bonuses.get("bonus_hp") or 0
        mana = bonuses.get("bonus_mp") or 0
        if not heal and not mana:
            base = {"common": 30, "uncommon": 70, "rare": 140}.get(
                item.rarity.value, 30
            )
            if "ман" in item.name.lower():
                mana = base
            else:
                heal = base

        # Карма: Благочестивые лечатся лучше (+15 %, порог из core/karma.py).
        from core import karma as core_karma
        if heal and core_karma.pious(character):
            heal = int(heal * (1 + core_karma.HEAL_BONUS))

        before_hp, before_mp = character.current_hp, character.current_mp
        character.current_hp = min(character.max_hp, character.current_hp + heal)
        character.current_mp = min(character.max_mp, character.current_mp + mana)
        gained_hp = character.current_hp - before_hp
        gained_mp = character.current_mp - before_mp

        inv_item.quantity = (inv_item.quantity or 1) - 1
        if inv_item.quantity <= 0:
            await session.delete(inv_item)
        await session.commit()

    parts = []
    if gained_hp:
        parts.append(f"❤️ +{gained_hp} HP")
    if gained_mp:
        parts.append(f"💙 +{gained_mp} MP")
    await callback.answer(
        f"{item.name}: " + (" | ".join(parts) if parts else "эффекта нет"),
        show_alert=True,
    )
    await inventory(callback)


@router.callback_query(F.data.startswith("drop:"))
async def drop_item(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.instance))
        )
        inv_item = result.scalar_one_or_none()
        if inv_item:
            instance = inv_item.instance
            await session.delete(inv_item)
            # Уникальный экземпляр умирает вместе со строкой инвентаря
            if instance is not None:
                await session.delete(instance)
            await session.commit()
    await callback.answer("Предмет выброшен.")
    await inventory(callback)


# ── разбор на материалы и ломбард ───────────────────────────
# Логика живёт в core/salvage.py и core/pawnshop.py — оба модуля были
# написаны и покрыты тестами (tests/test_economy_and_lunar.py), но до
# этих хендлеров у игрока не было ни одной кнопки, чтобы их вызвать.

@router.callback_query(F.data.startswith("salvage:"))
async def salvage_item_handler(callback: CallbackQuery):
    """🔧 Разобрать вещь на ремесленные материалы (core/salvage.py)."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.item),
                     selectinload(InventoryItem.instance))
        )
        inv_item = result.scalar_one_or_none()
        if inv_item is None or inv_item.character_id != character.id:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        from core import salvage as core_salvage
        res = await core_salvage.salvage_item(session, character, inv_item)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()

    mats = res["materials"]
    parts = [f"🔩 Ржавый лом ×{mats['iron_scrap']}"]
    if mats.get("steel_bars"):
        parts.append(f"⛓ Стальные слитки ×{mats['steel_bars']}")
    if mats.get("magic_dust"):
        parts.append(f"✨ Магическая пыль ×{mats['magic_dust']}")
    await callback.answer(
        f"🔧 {res['item_name']} разобран:\n" + "\n".join(parts), show_alert=True)
    await inventory(callback)


@router.callback_query(F.data.startswith("pawn:"))
async def pawn_item_handler(callback: CallbackQuery):
    """💍 Заложить именную вещь ростовщику (core/pawnshop.py)."""
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.item),
                     selectinload(InventoryItem.instance))
        )
        inv_item = result.scalar_one_or_none()
        if inv_item is None or inv_item.character_id != character.id:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        from core import pawnshop as core_pawnshop
        res = await core_pawnshop.create_pawn_loan(session, character, inv_item)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()

    await callback.answer(
        f"💍 Заложено за {res['loan_bronze']}🟤.\n"
        f"Выкуп: {res['buyback_price']}🟤, срок {res['days']} дн.\n"
        f"Займы — в меню «💍 Ломбард».",
        show_alert=True)
    await inventory(callback)


@router.callback_query(F.data == "pawnshop_menu")
async def pawnshop_menu(callback: CallbackQuery):
    """💍 Ломбард: список активных займов и выкуп."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from bot.utils.edit import safe_edit_text
    from core import pawnshop as core_pawnshop
    from engine.currency import currency_str

    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        loans = await core_pawnshop.list_active_loans(session, character.id)
        purse = currency_str(character)

        lines = ["💍 <b>Ломбард Падальщиков</b>", "",
                 "<i>— Вещь оставь, деньги забирай. Не выкупишь в срок — она моя.</i>",
                 "", f"💰 Кошелёк: <b>{purse}</b>", ""]
        builder = InlineKeyboardBuilder()
        if not loans:
            lines.append("<i>Твоих залогов здесь нет.</i>")
            lines.append("")
            lines.append("Заложить вещь: 🎒 Инвентарь → карточка вещи → 💍 Заложить.")
        else:
            for loan in loans:
                item = await session.get(Item, loan.item_id)
                name = item.name if item else "Неизвестная вещь"
                lines.append(f"• <b>{name}</b> — выкуп {loan.buyback_price}🟤")
                builder.button(text=f"💰 Выкупить: {name} ({loan.buyback_price}🟤)",
                               callback_data=f"pawn_redeem:{loan.id}")
        builder.button(text="◀️ Меню", callback_data="main_menu")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("pawn_redeem:"))
async def pawn_redeem_handler(callback: CallbackQuery):
    """Выкупить вещь из ломбарда (core/pawnshop.redeem_pawn_loan)."""
    loan_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character_of(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        from core import pawnshop as core_pawnshop
        res = await core_pawnshop.redeem_pawn_loan(session, character, loan_id)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()

    await callback.answer(f"💍 Вещь выкуплена за {res['cost']}🟤 и вернулась в сумку.",
                          show_alert=True)
    await pawnshop_menu(callback)
