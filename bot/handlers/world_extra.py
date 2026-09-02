"""Репутация, надгробия, диковины и мировой босс — экраны бота.

Паритет с браузерным стеком: те же механики, что в `engine/factions.py`,
`engine/death.py`, `engine/landmarks.py` и `engine/worldboss.py`, только
поверх БД. Логика и числа берутся из общих модулей `core/*`.

Вынесено отдельным файлом, чтобы не раздувать location.py и battle.py.
"""
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import behavior as core_behavior
from core import death as core_death
from core import factions as core_factions
from core import landmarks as core_landmarks
from core import worldevents as core_events
from core.database import async_session
from core.models import Character, User
from bot.keyboards.inline import continue_keyboard, main_menu_keyboard
from bot.utils.edit import safe_edit_text

router = Router()


async def _character(session, telegram_id):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    result = await session.execute(
        select(Character)
        .where(Character.user_id == user.id)
        .options(selectinload(Character.cell))
    )
    return result.scalar_one_or_none()


def _back_keyboard():
    """Итог мирового действия: вернуться к прогулке, а не в меню.

    Диковины и надгробия находят прямо на клетке — выбрасывать после них
    игрока в главное меню значит обрывать вылазку на полпути.
    """
    return continue_keyboard()


def _menu_keyboard():
    """Для экранов, открытых из меню (репутация): назад в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Меню", callback_data="main_menu")
    return builder.as_markup()


@router.callback_query(F.data == "omens_menu")
async def omens_menu(callback: CallbackQuery):
    """🔮 Знамения: предвестия бед (каталог — engine/omens.py, общий для стеков)."""
    from core import omens as core_omens

    # Знамения читаются из БД: к каталогу подмешиваются добавленные из
    # админки (№ 68), а при живом бедствии первым идёт его предвестие
    # (№ 86) — раньше список был статичным и с миром не связан.
    async with async_session() as session:
        rows = await core_omens.current(session)
        head = await core_omens.banner(session)
        kinds = await core_omens.active_kinds(session)
        character = await _character(session, callback.from_user.id)
        who = character.name if character else "Герой"
        char_id = character.id if character else None

    # Живая лента админки (№ 70): видно, что игроки читают знамения и
    # какое бедствие им предвещают.
    try:
        from core.realtime import publish_sync

        publish_sync("omen_shown", {
            "character_id": char_id, "name": who,
            "title": rows[0]["title"] if rows else "",
            "cataclysm": kinds[0] if kinds else None,
        })
    except Exception:
        pass

    lines = [head, "",
             "🔮 <b>Знамения</b>", "",
             "<i>Старики в Погосте шепчутся о дурных приметах:</i>", ""]
    for o in rows:
        lines.append(f"{o['icon']} <b>{o['title']}</b>")
        lines.append(f"<i>{o['desc']}</i>")
    lines += ["", "<i>Говорят, за знамением всегда приходит беда…</i>"]

    await safe_edit_text(
        callback,
        "\n".join(lines),
        reply_markup=_menu_keyboard(),
        parse_mode="HTML",
    )


# ── репутация ───────────────────────────────────────────────

@router.callback_query(F.data == "reputation")
async def reputation(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        from core import factions as core_factions
        my_faction = core_factions.allegiance(character)
        my_rep = core_factions.value(character, my_faction) if my_faction else 0

        # Load current leader
        leader_id = None
        if my_faction:
            from core.models import AppSetting
            leader_row = await session.scalar(
                select(AppSetting).where(AppSetting.key == f"faction_leader_{my_faction}")
            )
            if leader_row and leader_row.value:
                leader_id = int(leader_row.value)

        leader_name = "Никто"
        if leader_id:
            leader_char = await session.get(Character, leader_id)
            if leader_char:
                leader_name = leader_char.name

        # Decrees and Outposts summary
        dec_info = await core_factions.active_decree_bonuses(session, my_faction)
        outpost_info = await core_factions.faction_outpost_bonuses(session, my_faction)

        text = core_factions.card_text(character)

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()

        if my_faction:
            text += f"\n\n👑 <b>Лидер твоей фракции:</b> {leader_name}"
            text += f"\n📜 <b>Активный указ:</b> {dec_info['name']}"
            text += f"\n🏰 <b>Удерживаемых аванпостов:</b> {outpost_info['outposts_count']} (+{outpost_info['damage_pct']}% атака, +{outpost_info['exp_pct']}% опыт)"
            is_leader = (leader_id == character.id)
            if is_leader:
                text += " <i>(Ты являешься лидером этой фракции! 👑)</i>"

            builder.button(text="🏛 Казна и Указы фракции", callback_data=f"faction_treasury:{my_faction}")
            if not is_leader and my_rep >= 300:
                builder.button(text="👑 Стать лидером фракции (50k🟤)", callback_data=f"become_leader:{my_faction}")

        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)

    await safe_edit_text(
        callback,
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("faction_treasury:"))
async def faction_treasury_menu(callback: CallbackQuery):
    faction_key = callback.data.split(":")[1]
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Ошибка.", show_alert=True)
            return

        from core import factions as core_factions
        from core.models import AppSetting
        dec = await core_factions.get_or_create_decree(session, faction_key)
        leader_row = await session.scalar(
            select(AppSetting).where(AppSetting.key == f"faction_leader_{faction_key}")
        )
        is_leader = (leader_row and leader_row.value and int(leader_row.value) == character.id)

        from bot.keyboards.inline import faction_treasury_keyboard
        active_dec = core_factions.DECREES.get(dec.active_decree, {}).get("name", "Нет")
        until_str = dec.active_until.strftime("%d.%m %H:%M") if dec.active_until else "—"

        text = (
            f"🏛 <b>Казна и Совет фракции: {core_factions.FACTIONS[faction_key][1]}</b>\n\n"
            f"💰 В казне фракции: <b>{dec.treasury_bronze or 0}🟤</b>\n"
            f"📜 Текущий указ: <b>{active_dec}</b> (до {until_str})\n\n"
            f"<i>Пожертвования пополняют общую казну и повышают репутацию. "
            f"Лидер фракции может издавать указы, усиливающие всех соратников на 12 часов.</i>"
        )

    await safe_edit_text(
        callback,
        text,
        reply_markup=faction_treasury_keyboard(faction_key, is_leader=is_leader),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("treasury_donate:"))
async def treasury_donate_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    faction_key, amount = parts[1], int(parts[2])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Ошибка.", show_alert=True)
            return

        from core import factions as core_factions
        res = await core_factions.donate_treasury(session, character, faction_key, amount)
        await session.commit()

    if not res["ok"]:
        await callback.answer(res["reason"], show_alert=True)
        return

    await callback.answer(f"💰 Ты пожертвовал {amount}🟤 в казну фракции! (В казне: {res['treasury']}🟤)", show_alert=True)
    await faction_treasury_menu(callback)


@router.callback_query(F.data.startswith("decree_enact:"))
async def decree_enact_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    faction_key, dec_key = parts[1], parts[2]
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Ошибка.", show_alert=True)
            return

        from core import factions as core_factions
        res = await core_factions.enact_decree(session, character, faction_key, dec_key)
        await session.commit()

    if not res["ok"]:
        await callback.answer(res["reason"], show_alert=True)
        return

    await callback.answer(f"📜 Указ «{res['decree']}» успешно издан для всей фракции!", show_alert=True)
    await faction_treasury_menu(callback)


@router.callback_query(F.data.startswith("become_leader:"))
async def become_leader_callback(callback: CallbackQuery):
    faction_key = callback.data.split(":")[1]

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        from core import factions as core_factions
        my_faction = core_factions.allegiance(character)
        if my_faction != faction_key:
            await callback.answer("Вы не принадлежите к этой фракции!", show_alert=True)
            return

        my_rep = core_factions.value(character, my_faction)
        if my_rep < 300:
            await callback.answer("Требуется максимальная репутация (300)!", show_alert=True)
            return

        from engine.currency import total_in_bronze, deduct_currency
        if total_in_bronze(character) < 50000:
            await callback.answer("Недостаточно средств! Требуется 50,000🟤 (бронзы).", show_alert=True)
            return

        # Deduct currency
        deduct_currency(character, 50000)

        # Set leader in settings
        from core.models import AppSetting
        leader_row = await session.scalar(
            select(AppSetting).where(AppSetting.key == f"faction_leader_{faction_key}")
        )
        if not leader_row:
            leader_row = AppSetting(key=f"faction_leader_{faction_key}", value=str(character.id))
            session.add(leader_row)
        else:
            leader_row.value = str(character.id)

        await session.commit()

    await callback.answer("Поздравляем! Вы стали Лидером фракции! 👑", show_alert=True)
    await reputation(callback)


# ── надгробия ───────────────────────────────────────────────

@router.callback_query(F.data == "claim_grave")
async def claim_grave(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None or character.cell is None:
            await callback.answer("Ошибка.", show_alert=True)
            return
        cell = character.cell
        grave = await core_death.at(session, cell.location_id, cell.x, cell.y,
                                    floor=cell.floor or 0)
        if grave is None:
            await callback.answer("Здесь нечего забирать.", show_alert=True)
            return
        gold, items, own = await core_death.claim(session, character, grave)
        if not own:
            core_factions.award(character, "grave_looted")
            from core import karma as core_karma
            karma_text = core_karma.on_grave_loot(character)
        else:
            karma_text = ""
        await session.commit()

    got = [f"+{gold} 🟤"] if gold else []
    if items:
        got.append(f"🎒 вещей: {len(items)}")
    body = ", ".join(got) if got else "здесь уже пусто"
    if own:
        text = (f"🪦 <b>Ты вернулся за своим.</b>\n\n{body}\n\n"
                f"<i>Земля отпускает то, что взяла.</i>")
    else:
        kar = f"\n{karma_text}" if karma_text else ""
        text = (f"🪦 <b>Чужая могила</b>\n\nТы забрал: {body}\n\n"
                f"<i>Половина рассыпалась прахом — мародёрство не в чести.</i>{kar}")
    await safe_edit_text(
        callback,
        text,
        reply_markup=_back_keyboard(),
        parse_mode="HTML",
    )


# ── достопримечательности ───────────────────────────────────

@router.callback_query(F.data == "study_landmark")
async def study_landmark(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None or character.cell is None:
            await callback.answer("Ошибка.", show_alert=True)
            return
        ok, lines = await core_landmarks.claim(session, character,
                                               character.cell)
        if not ok:
            await callback.answer(lines[0], show_alert=True)
            return
        await session.commit()
    await safe_edit_text(
        callback,
        "\n".join(lines),
        reply_markup=_back_keyboard(),
        parse_mode="HTML",
    )


# ── мировой босс ────────────────────────────────────────────

def _boss_keyboard(can_hit):
    builder = InlineKeyboardBuilder()
    if can_hit:
        builder.button(text="⚔️ Ударить", callback_data="boss_hit")
    builder.button(text="🔄 Обновить", callback_data="world_boss")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "world_boss")
async def world_boss(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return
        ev = await core_events.active_boss(session)
        if ev is None:
            await safe_edit_text(
                callback,
                "🏰 <b>Мировой босс</b>\n\n<i>Сейчас в мире тихо.</i>",
                reply_markup=_back_keyboard(),
                parse_mode="HTML",
            )
            return
        b = core_events.BOSSES[ev.key]
        share = await core_events.boss_contribution(session, ev, character)
        here = character.location_id == ev.location_id
        can_hit = here and character.level >= b["level"]
        text = (
            f"{core_events.title('boss', ev.key)}\n<i>{b['story']}</i>\n\n"
            f"❤️ {ev.hp}/{ev.max_hp}\n"
            f"👥 твой вклад: {int(share * 100)}%\n"
        )
        if ev.phase:
            text += "\n🔥 <i>Вторая фаза: босс призвал свиту.</i>"
        if not here:
            text += "\n⚠️ <i>Ты не в той локации.</i>"
        elif character.level < b["level"]:
            text += f"\n⚠️ <i>Нужен {b['level']} уровень.</i>"
        await session.commit()
    await safe_edit_text(
        callback,
        text,
        reply_markup=_boss_keyboard(can_hit),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "boss_hit")
async def boss_hit(callback: CallbackQuery):
    import random

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        ev = await core_events.active_boss(session)
        if character is None or ev is None:
            await callback.answer("Босса уже нет.", show_alert=True)
            return
        b = core_events.BOSSES[ev.key]
        if character.location_id != ev.location_id:
            await callback.answer("Босс не здесь.", show_alert=True)
            return
        if character.level < b["level"]:
            await callback.answer(f"Нужен {b['level']} уровень.", show_alert=True)
            return

        dealt = max(1, (character.strength or 0) * 2 + random.randint(0, 10)
                    - b["defense"])
        left, phased = await core_events.hit_boss(session, character, dealt)
        back = max(0, int(b["damage"] * random.uniform(0.5, 1.0))
                   - (character.endurance or 0) // 3)
        character.current_hp = max(1, (character.current_hp or 1) - back)
        await session.commit()

    if left <= 0:
        await safe_edit_text(
            callback,
            "🏆 <b>Босс повержен!</b>\n\n<i>Награды разошлись всем, кто бился.</i>",
            reply_markup=_back_keyboard(),
            parse_mode="HTML",
        )
        return
    await callback.answer(f"Ты нанёс {dealt}. Получил {back}. Осталось {left}.")
    await world_boss(callback)


# ── КОЛИЗЕЙ ТЕНЕЙ (АСИНХРОННЫЙ PVP) ─────────────────────────

@router.callback_query(F.data == "arena_menu")
async def arena_menu_handler(callback: CallbackQuery):
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        from core import arena as core_arena
        from bot.keyboards.inline import arena_menu_keyboard

        await core_arena.update_character_shadow(session, character)
        opponents = await core_arena.get_shadow_opponents(session, character, limit=4)
        await session.commit()

        rating = character.arena_rating or 1000
        tokens = character.gladiator_tokens or 0

        text = (
            f"⚔️ <b>Колизей Теней</b>\n\n"
            f"Здесь бродят астральные слепки других героев. Брось вызов их теням, чтобы доказать превосходство!\n\n"
            f"🏆 Твой рейтинг Арены: <b>{rating}</b>\n"
            f"🩸 Кровавых жетонов: <b>{tokens}</b>\n\n"
            f"<i>Выбери соперника для дуэли:</i>"
        )

    await safe_edit_text(
        callback,
        text,
        reply_markup=arena_menu_keyboard(opponents, rating, tokens),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("arena_duel:"))
async def arena_duel_handler(callback: CallbackQuery):
    shadow_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        from core.models import CharacterShadow
        shadow = await session.get(CharacterShadow, shadow_id)
        if not character or not shadow:
            await callback.answer("Соперник не найден.", show_alert=True)
            return

        from core import arena as core_arena
        res = await core_arena.duel_shadow(session, character, shadow)
        await session.commit()

    title = "🏆 <b>ПОБЕДА НА АРЕНЕ!</b>" if res["victory"] else "💀 <b>ПОРАЖЕНИЕ НА АРЕНЕ</b>"
    log_text = "\n".join(res["log"][-4:])
    sign = "+" if res["rating_change"] > 0 else ""
    reward_text = f"\n\nРейтинг: {sign}{res['rating_change']} (Итог: {res['new_rating']} 🏆)\nНаграда: +{res['tokens']} 🩸 Кровавых жетонов"

    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ К списку дуэлей", callback_data="arena_menu")
    builder.button(text="◀️ Меню", callback_data="main_menu")
    builder.adjust(1)

    await safe_edit_text(
        callback,
        f"{title}\n\n{log_text}{reward_text}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )



# ── доска наград за головы ──────────────────────────────────
# core/bounty.py существовал, но ни record_mob_kill, ни list_active_bounties
# не вызывались: мобы-убийцы не получали имён, а доска была недостижима.
# Теперь имя присваивается при гибели игрока (bot/handlers/battle.py),
# а здесь — список целей и их местоположение.

@router.callback_query(F.data == "bounty_menu")
async def bounty_menu(callback: CallbackQuery):
    """💀 Награды: список мобов-убийц и куш за их головы."""
    from core import bounty as core_bounty
    from bot.keyboards.inline import bounty_board_keyboard

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        bounties = await core_bounty.list_active_bounties(session)
        lines = ["💀 <b>Доска наград</b>", "",
                 "<i>— Эти твари уже пролили кровь героев. За их головы платят.</i>", ""]
        if not bounties:
            lines.append("<i>Пока никто не отличился. Доска пуста — и это хорошо.</i>")
        else:
            for b in bounties[:10]:
                mob_name = b.mob.name if b.mob else "Неизвестная тварь"
                loc_name = b.location.name if b.location else "неизвестно где"
                reward = core_bounty.calculate_bounty_reward(b)
                lines.append(
                    f"{b.bounty_title or 'Убийца'} — <b>{mob_name}</b>\n"
                    f"   📍 {loc_name} · жертв: {b.kill_count} · "
                    f"награда: <b>{reward}</b>🟤")
        lines += ["", "<i>Найди цель в мире и убей — награда придёт сама.</i>"]

    await safe_edit_text(
        callback, "\n".join(lines),
        reply_markup=bounty_board_keyboard(bounties[:10]),
        parse_mode="HTML")


@router.callback_query(F.data.startswith("bounty_track:"))
async def bounty_track(callback: CallbackQuery):
    """Подсказать, где искать цель (кнопка была без обработчика)."""
    from core.models import MobSpawn

    spawn_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        spawn = (await session.execute(
            select(MobSpawn).where(MobSpawn.id == spawn_id)
            .options(selectinload(MobSpawn.mob), selectinload(MobSpawn.location),
                     selectinload(MobSpawn.cell))
        )).scalar_one_or_none()
        if spawn is None or not spawn.is_alive:
            await callback.answer("Цель уже мертва или исчезла.", show_alert=True)
            return
        mob_name = spawn.mob.name if spawn.mob else "тварь"
        loc_name = spawn.location.name if spawn.location else "неизвестно где"
        cell = spawn.cell
        where = f" [{cell.x},{cell.y}]" if cell else ""

    await callback.answer(
        f"💀 {mob_name}\nИщи здесь: {loc_name}{where}", show_alert=True)


# ── дуэль с игроком на клетке ───────────────────────────────
# Кнопка «⚔️ Напасть на игрока» (pvp_select) существовала в клавиатуре
# осмотра, но обработчика у неё не было — нажатие ничего не делало.

DUEL_WAGERS = (0, 100, 500)


@router.callback_query(F.data == "pvp_select")
async def pvp_select(callback: CallbackQuery):
    """Выбор соперника среди героев на той же клетке."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None or character.cell is None:
            await callback.answer("Ошибка.", show_alert=True)
            return

        others = (await session.execute(
            select(Character)
            .where(Character.cell_id == character.cell_id)
            .where(Character.location_id == character.location_id)
            .where(Character.floor == (character.floor or 0))
            .where(Character.id != character.id)
            .where(Character.stats_locked == True)  # noqa: E712
        )).scalars().all()

        builder = InlineKeyboardBuilder()
        if not others:
            lines = ["⚔️ <b>Дуэль</b>", "", "<i>Здесь больше никого нет.</i>"]
        else:
            lines = ["⚔️ <b>Дуэль чести</b>", "",
                     "<i>— Ставка на бочку, клинки наголо. Победитель забирает банк "
                     "(5 % идёт арене).</i>", "",
                     "Кто на этой клетке:"]
            for o in others[:5]:
                lines.append(f"• <b>{o.name}</b> (ур. {o.level})")
                for wager in DUEL_WAGERS:
                    label = "без ставки" if wager == 0 else f"{wager}🟤"
                    builder.button(text=f"⚔️ {o.name} — {label}",
                                   callback_data=f"duel_go:{o.id}:{wager}")
        builder.button(text="◀️ Назад", callback_data="inspect")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


# Вызовы на дуэль: {id вызванного: (id вызвавшего, ставка, момент вызова)}.
# Состояние живёт в памяти процесса, как и боевое (combat_state в
# battle.py): незакрытый вызов теряется при рестарте — это лучше, чем
# таблица ради записи, живущей минуту.
#
# Третье поле (время) добавлено вместе с админской секцией «Арена»
# (IDEAS-100.md № 67): без него вызов висел вечно — принять его можно было
# и через сутки, когда соперник давно ушёл с клетки, а ставка уже была
# потрачена. Теперь протухшие вызовы отсеиваются.
DUEL_INVITE_TTL = 300          # секунд: дольше пяти минут вызов не ждёт

duel_invites: dict[int, tuple[int, int, float]] = {}


def prune_duel_invites(now=None) -> int:
    """Убрать протухшие вызовы. Возвращает, сколько убрано."""
    now = time.time() if now is None else now
    stale = [tid for tid, inv in duel_invites.items()
             if now - (inv[2] if len(inv) > 2 else 0) > DUEL_INVITE_TTL]
    for tid in stale:
        duel_invites.pop(tid, None)
    return len(stale)


def pending_duels(now=None) -> list[dict]:
    """Живые вызовы — для секции «Арена» в админке (admin/main.py)."""
    now = time.time() if now is None else now
    prune_duel_invites(now)
    return [{"target_id": tid, "challenger_tg": inv[0], "wager": inv[1],
             "age": int(now - (inv[2] if len(inv) > 2 else now)),
             "expires_in": max(0, int(DUEL_INVITE_TTL
                                      - (now - (inv[2] if len(inv) > 2 else now))))}
            for tid, inv in duel_invites.items()]


def cancel_duel_invite(target_id: int) -> bool:
    """Снять зависший вызов вручную (кнопка в админке)."""
    return duel_invites.pop(int(target_id), None) is not None


@router.callback_query(F.data.startswith("duel_go:"))
async def duel_invite(callback: CallbackQuery):
    """Отправить вызов на дуэль. Бой начнётся только после согласия."""
    _, raw_id, raw_wager = callback.data.split(":")
    target_id, wager = int(raw_id), int(raw_wager)
    if wager not in DUEL_WAGERS:          # защита от подделанного колбэка
        await callback.answer("Недопустимая ставка.", show_alert=True)
        return

    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        target = await session.get(Character, target_id)
        if character is None or target is None:
            await callback.answer("Соперник не найден.", show_alert=True)
            return
        if target.id == character.id:
            await callback.answer("Нельзя драться с самим собой.", show_alert=True)
            return
        if (target.cell_id != character.cell_id
                or (target.floor or 0) != (character.floor or 0)):
            await callback.answer("Соперник ушёл с этой клетки.", show_alert=True)
            return

        from engine.currency import total_in_bronze
        if total_in_bronze(character) < wager:
            await callback.answer(f"У тебя не хватает {wager}🟤 на ставку.",
                                  show_alert=True)
            return

        target_user = await session.get(User, target.user_id)
        target_tg = target_user.telegram_id if target_user else None
        challenger_name, target_name = character.name, target.name

    if not target_tg:
        await callback.answer("Соперник недоступен.", show_alert=True)
        return

    prune_duel_invites()
    duel_invites[target_id] = (int(callback.from_user.id), wager, time.time())

    stake = "без ставки" if wager == 0 else f"ставка {wager}🟤"
    builder = InlineKeyboardBuilder()
    builder.button(text=f"⚔️ Принять вызов ({stake})",
                   callback_data=f"duel_accept:{target_id}")
    builder.button(text="🚫 Отказаться", callback_data=f"duel_decline:{target_id}")
    builder.adjust(1)
    try:
        await callback.bot.send_message(
            target_tg,
            f"⚔️ <b>Тебя вызвали на дуэль!</b>\n\n"
            f"<b>{challenger_name}</b> обнажил клинок против тебя — {stake}.\n\n"
            f"<i>Победитель забирает банк, 5 % идёт арене.</i>",
            reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        duel_invites.pop(target_id, None)
        await callback.answer("Соперник недоступен для вызова.", show_alert=True)
        return

    await safe_edit_text(
        callback,
        f"⚔️ <b>Вызов брошен</b>\n\n"
        f"Ты вызвал <b>{target_name}</b> на дуэль ({stake}).\n\n"
        f"<i>Ждём ответа. Бой начнётся, только если соперник согласится.</i>",
        reply_markup=continue_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("duel_decline:"))
async def duel_decline(callback: CallbackQuery):
    """Отклонить вызов."""
    target_id = int(callback.data.split(":")[1])
    duel_invites.pop(target_id, None)
    await safe_edit_text(
        callback,
        "🚫 <b>Ты отказался от дуэли.</b>\n\n<i>Иногда это мудрее.</i>",
        reply_markup=continue_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("duel_accept:"))
async def duel_accept(callback: CallbackQuery):
    """Принять вызов и провести дуэль (core/duels.resolve_wager_duel)."""
    target_id = int(callback.data.split(":")[1])
    prune_duel_invites()
    invite = duel_invites.pop(target_id, None)
    if invite is None:
        await callback.answer("Вызов истёк или уже разрешён.", show_alert=True)
        return
    challenger_tg, wager = invite[0], invite[1]

    async with async_session() as session:
        defender = await _character(session, callback.from_user.id)
        challenger = await _character(session, challenger_tg)
        if defender is None or challenger is None:
            await callback.answer("Соперник не найден.", show_alert=True)
            return
        if defender.id != target_id:      # вызов адресован не этому герою
            await callback.answer("Этот вызов не тебе.", show_alert=True)
            return
        if (defender.cell_id != challenger.cell_id
                or (defender.floor or 0) != (challenger.floor or 0)):
            await callback.answer("Соперник ушёл с клетки — дуэль отменена.",
                                  show_alert=True)
            return

        from core import duels as core_duels
        res = await core_duels.resolve_wager_duel(session, challenger, defender, wager)
        if not res["ok"]:
            await callback.answer(res["reason"], show_alert=True)
            return
        await session.commit()
        challenger_user = await session.get(User, challenger.user_id)
        challenger_tg_id = challenger_user.telegram_id if challenger_user else None

    tail = "\n".join(res["log"][-4:])
    text = (
        f"⚔️ <b>Дуэль окончена</b>\n\n"
        f"Раундов: {res['rounds']}\n\n{tail}\n\n"
        f"🏆 Победил: <b>{res['winner_name']}</b>\n"
        f"💰 Банк: <b>{res['payout']}</b>🟤 — победителю"
    )
    await safe_edit_text(callback, text, reply_markup=continue_keyboard(),
                         parse_mode="HTML")
    # Вызвавший тоже должен узнать исход, а не гадать.
    if challenger_tg_id:
        try:
            await callback.bot.send_message(challenger_tg_id, text, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data == "legends_hall")
async def legends_hall_handler(callback: CallbackQuery):
    """🏛 Летопись сервера (IDEAS-100 № 60): зал славы для игроков.

    Экран собирает общая `hall_of_legends_text` — та же вёрстка, что в
    браузерном стеке (`engine/progress.legends_screen`). Записи пишут
    `core/worldevents` (первый разгром мирового босса, первое пережитое
    бедствие); экран доступен всем, кнопка — в главном меню.
    """
    from core import legends as core_legends

    async with async_session() as session:
        records = await core_legends.get_hall_of_legends(session)
        text = core_legends.hall_of_legends_text(records)
    await safe_edit_text(callback, text,
                         reply_markup=main_menu_keyboard(has_character=True),
                         parse_mode="HTML")
