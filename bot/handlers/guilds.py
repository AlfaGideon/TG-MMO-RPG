"""Гильдии, наставничество и перерождение — экраны бота.

Модули `core/guilds.py`, `core/mentorship.py` и `core/prestige.py` были
написаны и покрыты тестами (`tests/test_guilds_and_mentorship.py`,
`tests/test_progression_and_karma.py`), но ни один роутер их не вызывал:
игрок не мог ни основать гильдию, ни взять ученика, ни переродиться.
Здесь — их точки входа. Логика остаётся в `core/`, тут только экраны.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import Character, User
from bot.keyboards.inline import continue_keyboard
from bot.utils.edit import safe_edit_text

router = Router()

# Суммы взноса в казну: свободный ввод требует FSM, кнопки дают то же
# самое без состояния и без разбора мусорного текста.
DEPOSIT_STEPS = (100, 500, 2000)


async def _character(session, telegram_id: int):
    result = await session.execute(
        select(Character).join(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


def _menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Меню", callback_data="main_menu")
    return builder.as_markup()


async def _my_guild(session, character):
    """Гильдия героя или None. Модели живут в core/guilds.py."""
    from core.guilds import Guild, guild_members

    row = (await session.execute(
        select(guild_members.c.guild_id, guild_members.c.role)
        .where(guild_members.c.character_id == character.id)
    )).first()
    if row is None:
        return None, ""
    guild = (await session.execute(
        select(Guild).where(Guild.id == row[0]).options(selectinload(Guild.members))
    )).scalar_one_or_none()
    return guild, (row[1] or "member")


# ── гильдии ─────────────────────────────────────────────────

@router.callback_query(F.data == "guild_menu")
async def guild_menu(callback: CallbackQuery):
    """🏛 Гильдия: своя — карточка, чужая — список для вступления."""
    from core.guilds import Guild
    from engine.currency import currency_str

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        guild, role = await _my_guild(session, character)
        builder = InlineKeyboardBuilder()

        if guild is not None:
            role_label = {"leader": "👑 глава", "officer": "🎖 офицер"}.get(role, "🛡 участник")
            members = guild.members or []
            lines = [
                f"🏛 <b>{guild.name}</b> — уровень {guild.level or 1}", "",
                f"<i>{guild.description or 'Без девиза.'}</i>", "",
                f"Твоя роль: <b>{role_label}</b>",
                f"💰 Казна: <b>{guild.treasury_bronze or 0}</b>🟤",
                f"👥 Участников: <b>{len(members)}</b>", "",
                "<b>Состав:</b>",
            ]
            for m in members[:15]:
                lines.append(f"• {m.name} (ур. {m.level})")
            lines += ["", f"💰 Твой кошелёк: {currency_str(character)}"]
            for step in DEPOSIT_STEPS:
                builder.button(text=f"💰 В казну {step}🟤",
                               callback_data=f"guild_deposit:{step}")
        else:
            others = (await session.execute(
                select(Guild).options(selectinload(Guild.members))
                .order_by(Guild.level.desc()).limit(10)
            )).scalars().all()
            lines = [
                "🏛 <b>Гильдии</b>", "",
                "<i>— В одиночку в этих землях долго не живут.</i>", "",
                f"Основать свою: <b>2000</b>🟤 (у тебя {currency_str(character)})", "",
            ]
            if others:
                lines.append("<b>Уже существуют:</b>")
                for g in others:
                    lines.append(f"• <b>{g.name}</b> — ур. {g.level or 1}, "
                                 f"участников {len(g.members or [])}")
                    builder.button(text=f"🤝 Вступить: {g.name}",
                                   callback_data=f"guild_join:{g.id}")
            else:
                lines.append("<i>Пока ни одной гильдии не основано. Стань первым.</i>")
            builder.button(text="🏛 Основать гильдию (2000🟤)",
                           callback_data="guild_create")

        builder.button(text="◀️ Меню", callback_data="main_menu")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "guild_create")
async def guild_create(callback: CallbackQuery):
    """Основать гильдию. Имя — по имени героя: свободный ввод требует FSM."""
    from core import guilds as core_guilds

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        existing, _role = await _my_guild(session, character)
        if existing is not None:
            await callback.answer("Ты уже состоишь в гильдии.", show_alert=True)
            return

        res = await core_guilds.create_guild(
            session, character, f"Дом {character.name}",
            f"Гильдия под предводительством {character.name}")
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()

    await callback.answer("🏛 Гильдия основана! Ты её глава.", show_alert=True)
    await guild_menu(callback)


@router.callback_query(F.data.startswith("guild_join:"))
async def guild_join(callback: CallbackQuery):
    """Вступить в существующую гильдию."""
    from sqlalchemy import insert
    from core.guilds import Guild, guild_members

    guild_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        existing, _role = await _my_guild(session, character)
        if existing is not None:
            await callback.answer("Ты уже состоишь в гильдии.", show_alert=True)
            return
        guild = await session.get(Guild, guild_id)
        if guild is None:
            await callback.answer("Такой гильдии больше нет.", show_alert=True)
            return

        await session.execute(insert(guild_members).values(
            guild_id=guild.id, character_id=character.id, role="member"))
        await session.commit()
        name = guild.name

    await callback.answer(f"🤝 Ты вступил в «{name}».", show_alert=True)
    await guild_menu(callback)


@router.callback_query(F.data.startswith("guild_deposit:"))
async def guild_deposit(callback: CallbackQuery):
    """Внести взнос в казну гильдии."""
    from core import guilds as core_guilds

    amount = int(callback.data.split(":")[1])
    if amount not in DEPOSIT_STEPS:          # защита от подделанного колбэка
        await callback.answer("Недопустимая сумма.", show_alert=True)
        return

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        guild, _role = await _my_guild(session, character)
        if guild is None:
            await callback.answer("Ты не состоишь в гильдии.", show_alert=True)
            return

        res = await core_guilds.deposit_guild_treasury(session, character, guild, amount)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()

    await callback.answer(f"💰 Внесено {amount}🟤. Казна: {res['treasury']}🟤.",
                          show_alert=True)
    await guild_menu(callback)


# ── наставничество ──────────────────────────────────────────

@router.callback_query(F.data == "mentor_menu")
async def mentor_menu(callback: CallbackQuery):
    """🎓 Наставничество: ученику — поиск наставника, ветерану — статус."""
    from core import mentorship as core_mentor

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        bonuses = core_mentor.get_mentorship_bonuses(character)
        builder = InlineKeyboardBuilder()
        lines = ["🎓 <b>Наставничество</b>", "",
                 "<i>— Ветеран ведёт новичка и получает Очки Чести.</i>", ""]

        if bonuses["has_mentor"]:
            mentor = await session.get(Character, character.mentor_character_id)
            lines.append(f"🧙 Твой наставник: <b>{mentor.name if mentor else '—'}</b>")
            lines.append(f"⭐ Бонус опыта: <b>+{bonuses['exp_bonus_pct']}%</b>")
        elif (character.level or 1) <= 5:
            mentors = (await session.execute(
                select(Character).where(Character.level >= 8)
                .where(Character.id != character.id)
                .order_by(Character.level.desc()).limit(5)
            )).scalars().all()
            if mentors:
                lines.append("Выбери наставника — с ним опыт идёт быстрее на 25 %:")
                for m in mentors:
                    lines.append(f"• <b>{m.name}</b> (ур. {m.level})")
                    builder.button(text=f"🎓 В ученики к {m.name}",
                                   callback_data=f"mentor_bind:{m.id}")
            else:
                lines.append("<i>Опытных героев (8+ уровень) пока нет.</i>")
        else:
            lines.append("<i>Ты уже не новичок — учеником стать нельзя.</i>")
            if (character.level or 1) >= 8:
                lines.append("Зато можешь стать наставником: новички найдут тебя сами.")

        lines += ["", f"🏅 Очки Чести: <b>{bonuses['honor_points']}</b>"]
        builder.button(text="◀️ Меню", callback_data="main_menu")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("mentor_bind:"))
async def mentor_bind(callback: CallbackQuery):
    """Взять наставника."""
    from core import mentorship as core_mentor

    mentor_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        mentor = await session.get(Character, mentor_id)
        if not character or mentor is None:
            await callback.answer("Наставник не найден.", show_alert=True)
            return

        res = await core_mentor.bind_mentor(session, character, mentor)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()

    await callback.answer(f"🎓 {res['mentor_name']} стал твоим наставником!",
                          show_alert=True)
    await mentor_menu(callback)


# ── перерождение ────────────────────────────────────────────

@router.callback_query(F.data == "rebirth_menu")
async def rebirth_menu(callback: CallbackQuery):
    """♻️ Перерождение: сброс уровня ради постоянного бонуса к статам."""
    from core import prestige as core_prestige

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        ok, reason = core_prestige.can_rebirth(character)
        count = character.rebirth_count or 0
        lines = [
            "♻️ <b>Вечное Перерождение</b>", "",
            "<i>— Сбрось прожитое и вернись сильнее, чем был.</i>", "",
            f"🔥 Кругов пройдено: <b>{count}</b>",
            f"📈 Текущий уровень: <b>{character.level}</b> "
            f"(нужен {core_prestige.REBIRTH_MIN_LEVEL}+)", "",
            "Уровень и опыт обнулятся, но все базовые статы вырастут "
            "на <b>+10 %</b> навсегда.", "",
            ("✅ " + reason) if ok else ("⛔️ " + reason),
        ]
        builder = InlineKeyboardBuilder()
        if ok:
            builder.button(text="🔥 Совершить перерождение",
                           callback_data="rebirth_do")
        builder.button(text="◀️ Меню", callback_data="main_menu")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "rebirth_do")
async def rebirth_do(callback: CallbackQuery):
    """Провести ритуал перерождения."""
    from core import prestige as core_prestige

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        res = await core_prestige.perform_rebirth(session, character)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()

    await safe_edit_text(
        callback,
        f"<b>{res['title']}</b>\n\n{res['desc']}",
        reply_markup=continue_keyboard(),
        parse_mode="HTML",
    )
