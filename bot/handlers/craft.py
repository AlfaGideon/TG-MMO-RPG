"""Ремесленники: крафт по рецептам и заточка предметов гриндом."""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.crafting import (
    check_recipe, craft, recipes_for_station, upgrade, upgrade_cost,
)
from core.database import async_session
from core.enums import CraftStation, ItemType
from core.models import (
    Character, CraftIngredient, CraftRecipe, InventoryItem, ItemInstance, User,
)
from bot.keyboards.inline import (
    craft_menu_keyboard, craft_recipe_keyboard, craft_recipes_keyboard,
    upgrade_list_keyboard, upgrade_item_keyboard,
)
from bot.utils.photos import send_or_edit_photo
from bot.utils.texts import item_line
from bot.utils.edit import safe_edit_text

router = Router()

STATION_TITLES = {
    CraftStation.FORGE.value: "🔨 Кузница",
    CraftStation.ALCHEMY.value: "⚗️ Алхимический стол",
    CraftStation.JEWELRY.value: "💎 Ювелирная мастерская",
    CraftStation.ANY.value: "🛠 Мастерская",
}

UPGRADABLE = {
    ItemType.WEAPON, ItemType.ARMOR, ItemType.HELMET,
    ItemType.BOOTS, ItemType.ACCESSORY,
}


async def _character(session, telegram_id: int):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None
    result = await session.execute(
        select(Character)
        .where(Character.user_id == user.id)
        .options(selectinload(Character.cell))
    )
    return result.scalar_one_or_none()


async def _station_of(session, telegram_id: int) -> str:
    """Станок NPC, рядом с которым стоит игрок (или общий)."""
    character = await _character(session, telegram_id)
    cell = character.cell if character else None
    if cell and cell.npc_station:
        return cell.npc_station
    return CraftStation.ANY.value


@router.callback_query(F.data.startswith("craft_menu"))
async def craft_menu(callback: CallbackQuery):
    """Главное меню ремесленника: крафт или заточка."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        station = await _station_of(session, callback.from_user.id)
        recipes = await recipes_for_station(session, station)
        npc_name = character.cell.npc_name if character.cell else "Ремесленник"

    from engine.currency import currency_str
    title = STATION_TITLES.get(station, STATION_TITLES[CraftStation.ANY.value])
    await safe_edit_text(
        callback,
        f"{title}\n\n"
        f"<i>{npc_name} вытирает руки о фартук.</i>\n\n"
        f"— Могу сковать вещь по рецепту или заточить то, что у тебя уже есть. "
        f"Материалы твои, работа моя.\n\n"
        f"📜 Доступно рецептов: <b>{len(recipes)}</b>\n"
        f"💰 У тебя: <b>{currency_str(character)}</b>",
        reply_markup=craft_menu_keyboard(station),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("craft_list:"))
async def craft_list(callback: CallbackQuery):
    parts = callback.data.split(":")
    station = parts[1] or CraftStation.ANY.value
    page = int(parts[2]) if len(parts) > 2 else 0

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        recipes = await recipes_for_station(session, station)

        # Помечаем галочкой то, что игрок может скрафтить прямо сейчас
        ready = {}
        for recipe in recipes:
            status = await check_recipe(session, character, recipe)
            ready[recipe.id] = status["can_craft"]

    if not recipes:
        await callback.answer("У этого мастера пока нет рецептов.", show_alert=True)
        return

    await safe_edit_text(
        callback,
        f"📜 <b>Рецепты</b>\n\n"
        f"✅ — хватает материалов, ❌ — чего-то не хватает.\n"
        f"Каждая скованная вещь уникальна: статы катаются заново.",
        reply_markup=craft_recipes_keyboard(recipes, ready, station, page),
        parse_mode="HTML",
    )


def _recipe_text(recipe: CraftRecipe, status: dict, character) -> str:
    lines = [
        f"🔨 <b>{recipe.name}</b>",
        f"Результат: {recipe.result_item.icon} <b>{recipe.result_item.name}</b>"
        + (f" ×{recipe.result_quantity}" if (recipe.result_quantity or 1) > 1 else ""),
        "",
    ]
    if recipe.description:
        lines += [f"<i>{recipe.description}</i>", ""]

    lines.append("<b>Нужно:</b>")
    missing_ids = {m["item"].id for m in status["missing"]}
    for ing in recipe.ingredients:
        mark = "❌" if ing.item_id in missing_ids else "✅"
        have = next(
            (m["have"] for m in status["missing"] if m["item"].id == ing.item_id),
            ing.quantity,
        )
        lines.append(
            f"{mark} {ing.item.icon} {ing.item.name} — {have}/{ing.quantity}"
        )

    from engine.currency import total_in_bronze, currency_str, CONVERSION
    def fmt_b(val):
        g_v = val // (CONVERSION * CONVERSION)
        rem = val % (CONVERSION * CONVERSION)
        s_v = rem // CONVERSION
        b_v = rem % CONVERSION
        parts = []
        if g_v > 0: parts.append(f"{g_v}🟡")
        if s_v > 0: parts.append(f"{s_v}⚪")
        if b_v > 0 or not parts: parts.append(f"{b_v}🟤")
        return " ".join(parts)

    gold_mark = "✅" if total_in_bronze(character) >= (recipe.gold_cost or 0) else "❌"
    lines.append(f"{gold_mark} 💰 Стоимость — {currency_str(character)}/{fmt_b(recipe.gold_cost or 0)}")
    lvl_mark = "✅" if character.level >= (recipe.min_level or 1) else "❌"
    lines.append(f"{lvl_mark} ⭐ Уровень — {character.level}/{recipe.min_level or 1}")

    chance = int((recipe.success_chance or 1.0) * 100)
    if chance < 100:
        lines += ["", f"🎲 Шанс успеха: <b>{chance}%</b> "
                      f"<i>(при неудаче материалы сгорают)</i>"]
    return "\n".join(lines)


@router.callback_query(F.data.startswith("craft_view:"))
async def craft_view(callback: CallbackQuery):
    recipe_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(CraftRecipe)
            .where(CraftRecipe.id == recipe_id)
            .options(
                selectinload(CraftRecipe.result_item),
                selectinload(CraftRecipe.ingredients).selectinload(CraftIngredient.item),
            )
        )
        recipe = result.scalar_one_or_none()
        if not recipe or not character:
            await callback.answer("Рецепт не найден.", show_alert=True)
            return

        status = await check_recipe(session, character, recipe)
        text = _recipe_text(recipe, status, character)
        image = recipe.result_item.image_url

    await send_or_edit_photo(
        callback,
        text,
        reply_markup=craft_recipe_keyboard(
            recipe.id, status["can_craft"], recipe.station
        ),
        image_url=image,
    )


@router.callback_query(F.data.startswith("craft_do:"))
async def craft_do(callback: CallbackQuery):
    recipe_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(CraftRecipe)
            .where(CraftRecipe.id == recipe_id)
            .options(
                selectinload(CraftRecipe.result_item),
                selectinload(CraftRecipe.ingredients).selectinload(CraftIngredient.item),
            )
        )
        recipe = result.scalar_one_or_none()
        if not recipe or not character:
            await callback.answer("Рецепт не найден.", show_alert=True)
            return

        outcome = await craft(session, character, recipe)
        await session.commit()
        station = recipe.station

    if not outcome["ok"]:
        if outcome.get("failed_roll"):
            await safe_edit_text(
                callback,
                f"💥 <b>Брак!</b>\n\n{outcome['reason']}\n\n"
                f"<i>Мастер разводит руками: «Бывает. Неси ещё».</i>",
                reply_markup=craft_menu_keyboard(station),
                parse_mode="HTML",
            )
            return
        await callback.answer(outcome["reason"], show_alert=True)
        return

    made = outcome["instances"]
    lines = [f"✨ <b>Готово!</b>\n", f"Мастер выковал: {recipe.result_item.name}"]
    for inst in made:
        lines.append(
            f"\n🆔 <code>{inst.uid}</code>\n"
            f"⚖️ Качество: <b>{inst.quality}%</b> | "
            f"Редкость: <code>{inst.rarity.value}</code>"
        )
        bonuses = [
            f"{label} +{getattr(inst, field)}"
            for field, label in (
                ("bonus_damage", "⚔️"), ("bonus_defense", "🛡"),
                ("bonus_strength", "💪"), ("bonus_agility", "🏃"),
                ("bonus_intelligence", "🧠"), ("bonus_endurance", "🧱"),
                ("bonus_luck", "🍀"), ("bonus_hp", "❤️"), ("bonus_mp", "💙"),
            )
            if getattr(inst, field, 0)
        ]
        if bonuses:
            lines.append(" ".join(bonuses))
    if not made:
        lines.append("\nПредмет отправлен в сумку.")

    await safe_edit_text(callback, "\n".join(lines),
        reply_markup=craft_menu_keyboard(station),
        parse_mode="HTML",
    )


# ── Заточка ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("upgrade_list"))
async def upgrade_list(callback: CallbackQuery):
    parts = callback.data.split(":")
    page = int(parts[1]) if len(parts) > 1 and parts[1] else 0

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == character.id)
            .where(InventoryItem.instance_id.isnot(None))
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
            .order_by(InventoryItem.is_equipped.desc(), InventoryItem.id)
        )
        items = [
            i for i in result.scalars().all()
            if i.item and i.item.item_type in UPGRADABLE
        ]
        station = await _station_of(session, callback.from_user.id)

    if not items:
        await callback.answer(
            "Нечего затачивать — сначала добудь снаряжение.", show_alert=True
        )
        return

    await safe_edit_text(callback, "🔨 <b>Заточка</b>\n\n"
        "Каждый уровень заточки поднимает статы предмета. "
        "Нужны золото и материалы, добытые гриндом.\n\n"
        "<i>При неудаче уровень не теряется, но ресурсы сгорают.</i>",
        reply_markup=upgrade_list_keyboard(items, station, page),
        parse_mode="HTML",
    )


def _upgrade_text(inv_item, cost, character) -> str:
    inst = inv_item.instance
    item = inv_item.item
    lines = [
        f"🔨 <b>{inv_item.display_name()}</b>",
        f"🆔 <code>{inst.uid}</code> | ⚖️ Качество {inst.quality}%",
        f"Текущая заточка: <b>+{inst.upgrade_level or 0}</b> "
        f"(предел +{item.max_upgrade_level or 10})",
        "",
    ]
    bonuses = [
        f"{label} +{value}"
        for field, label in (
            ("bonus_damage", "⚔️ Урон"), ("bonus_defense", "🛡 Защита"),
            ("bonus_strength", "💪 Сила"), ("bonus_agility", "🏃 Ловкость"),
            ("bonus_intelligence", "🧠 Инт"), ("bonus_endurance", "🧱 Вын"),
            ("bonus_luck", "🍀 Удача"), ("bonus_hp", "❤️ HP"), ("bonus_mp", "💙 MP"),
        )
        for value in [getattr(inst, field, 0)] if value
    ]
    if bonuses:
        lines += ["<b>Сейчас:</b> " + ", ".join(bonuses), ""]

    if cost is None:
        lines.append("🏆 <b>Предмет заточен до предела.</b>")
        return "\n".join(lines)

    from engine.currency import total_in_bronze, currency_str, CONVERSION
    def fmt_b(val):
        g_v = val // (CONVERSION * CONVERSION)
        rem = val % (CONVERSION * CONVERSION)
        s_v = rem // CONVERSION
        b_v = rem % CONVERSION
        parts = []
        if g_v > 0: parts.append(f"{g_v}🟡")
        if s_v > 0: parts.append(f"{s_v}⚪")
        if b_v > 0 or not parts: parts.append(f"{b_v}🟤")
        return " ".join(parts)

    gold_ok = "✅" if total_in_bronze(character) >= cost["gold"] else "❌"
    lines += [
        f"<b>Улучшить до +{cost['next_level']}:</b>",
        f"{gold_ok} 💰 Стоимость — {currency_str(character)}/{fmt_b(cost['gold'])}",
    ]
    if cost["material"] is not None and cost["material_qty"]:
        lines.append(
            f"📦 {cost['material'].icon} {cost['material'].name} "
            f"×{cost['material_qty']}"
        )
    lines.append(f"🎲 Шанс успеха: <b>{int(cost['chance'] * 100)}%</b>")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("upgrade_view:"))
async def upgrade_view(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item or not inv_item.instance or not character:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        cost = await upgrade_cost(session, inv_item.instance, inv_item.item)
        text = _upgrade_text(inv_item, cost, character)
        image = inv_item.item.image_url
        station = await _station_of(session, callback.from_user.id)

    await send_or_edit_photo(
        callback,
        text,
        reply_markup=upgrade_item_keyboard(inv_id, cost is not None, station),
        image_url=image,
    )


@router.callback_query(F.data.startswith("upgrade_do:"))
async def upgrade_do(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv_item = result.scalar_one_or_none()
        if not inv_item or not character:
            await callback.answer("Предмет не найден.", show_alert=True)
            return

        outcome = await upgrade(session, character, inv_item)
        await session.commit()
        name = inv_item.display_name()
        station = await _station_of(session, callback.from_user.id)

    if not outcome["ok"] and not outcome.get("failed_roll"):
        await callback.answer(outcome["reason"], show_alert=True)
        return

    if outcome.get("failed_roll"):
        await safe_edit_text(
            callback,
            f"💢 <b>Заточка сорвалась</b>\n\n"
            f"{outcome['reason']}\n\n"
            f"<i>Мастер сплёвывает: «Металл не принял руну. Неси ещё материала».</i>",
            reply_markup=upgrade_item_keyboard(inv_id, True, station),
            parse_mode="HTML",
        )
        return

    gains = ", ".join(
        f"{field.replace('bonus_', '')} +{value}"
        for field, value in outcome["gains"].items()
    ) or "—"
    await safe_edit_text(
        callback,
        f"⚡ <b>Заточка удалась!</b>\n\n"
        f"{name} теперь <b>+{outcome['level']}</b>\n"
        f"Прирост: {gains}",
        reply_markup=upgrade_item_keyboard(inv_id, True, station),
        parse_mode="HTML",
    )
