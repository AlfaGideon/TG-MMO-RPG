"""Пати: поиск союзников, приглашения и заявки на вступление.

Раньше пати можно было только создать и покинуть: присоединиться было
некому и некак («попроси друга пригласить», но самих приглашений не
существовало).

Теперь есть 🔍 поиск: выдаёт героев своей фракции (где бы они ни были) и
тех, кто сейчас в той же локации. Пати с враждующей фракцией невозможна —
по кольцу вражды Стража↔Гильдия↔Культ↔Орден↔Стража, союзники по диагонали
(Стража+Культ, Гильдия+Орден) в пати быть могут.

Паритет с engine.party: до MAX_SIZE героев, звать может один только
предводитель, участие — только по согласию (приглашение принимает игрок,
заявку на вступление — предводитель).
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from core.database import async_session
from core.models import User, Character, Party, PartyInvite
from core import factions as core_factions
from core.vip import offline_protected
from bot.utils.edit import safe_edit_text

router = Router()

MAX_SIZE = 3        # больше — уже толпа, бой станет нечитаемым (паритет с engine)
SEARCH_LIMIT = 12   # сколько кандидатов показывает поиск


# ── сервис ──────────────────────────────────────────────────

async def _me(session, telegram_id: int):
    """Пользователь и его герой по telegram_id (None, None), если не найдены."""
    user = (await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )).scalar_one_or_none()
    character = None
    if user:
        character = (await session.execute(
            select(Character)
            .where(Character.user_id == user.id)
            .options(selectinload(Character.party), selectinload(Character.user))
        )).scalar_one_or_none()
    return user, character


async def _party_size(session, party_id: int) -> int:
    return len((await session.execute(
        select(Character.id).where(Character.party_id == party_id)
    )).all())


async def _notify(telegram_id: int, text: str, reply_markup=None) -> None:
    """Личное сообщение игроку от бота (тот же канал, что у лотов аукциона)."""
    try:
        from bot.runner import bot_runner
        if bot_runner.is_running() and bot_runner.bot:
            await bot_runner.bot.send_message(
                chat_id=telegram_id, text=text,
                parse_mode="HTML", reply_markup=reply_markup,
            )
    except Exception:
        pass


def _faction_of(character):
    """(ключ, значок, название) фракции героя или None для нейтрала."""
    key = core_factions.allegiance(character)
    if not key or key not in core_factions.FACTIONS:
        return None
    icon, name = core_factions.FACTIONS[key][0], core_factions.FACTIONS[key][1]
    return key, icon, name


def _faction_badge(character) -> str:
    f = _faction_of(character)
    return f"{f[1]} " if f else ""


async def _find_candidates(session, character):
    """Кого можно позвать: своя фракция (вся) + все, кто в той же локации.

    Враждующие фракции исключены всегда — пати с ними невозможна. VIP в
    режиме «я офлайн» миру не виден — в выдаче его нет. Забаненных тоже.
    Возвращает [(Character, near: bool)] — ближние первыми, дальше по уровню.
    """
    my_faction = core_factions.allegiance(character)
    my_floor = character.floor or 0
    rows = (await session.execute(
        select(Character)
        .where(Character.id != character.id)
        .options(selectinload(Character.user), selectinload(Character.location))
    )).scalars().all()

    candidates = []
    for other in rows:
        if other.user is None or other.user.is_banned:
            continue
        if offline_protected(other):
            continue
        other_faction = core_factions.allegiance(other)
        if core_factions.hostile(my_faction, other_faction):
            continue
        near = (
            other.location_id is not None
            and character.location_id is not None
            and other.location_id == character.location_id
            and (other.floor or 0) == my_floor
        )
        same_faction = bool(my_faction) and other_faction == my_faction
        if not (near or same_faction):
            continue
        candidates.append((other, near))

    candidates.sort(key=lambda c: (not c[1], -c[0].level))
    return candidates[:SEARCH_LIMIT]


def _answer_kb(invite_id: int):
    """Кнопки «Принять/Отклонить» в личном сообщении адресату заявки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять", callback_data=f"party_inv_yes:{invite_id}")
    builder.button(text="❌ Отклонить", callback_data=f"party_inv_no:{invite_id}")
    builder.adjust(2)
    return builder.as_markup()


# ── экран пати ──────────────────────────────────────────────

@router.callback_query(F.data == "party_menu")
async def party_menu(callback: CallbackQuery):
    async with async_session() as session:
        user, character = await _me(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        # Входящие приглашения/заявки — на случай, если личное сообщение
        # с кнопками потерялось в чате, они отвечаются и отсюда.
        pending = (await session.execute(
            select(PartyInvite)
            .where(PartyInvite.to_character_id == character.id)
            .where(PartyInvite.status == "pending")
            .order_by(PartyInvite.created_at.desc())
            .limit(3)
        )).scalars().all()
        from_names = {}
        for inv in pending:
            c = await session.get(Character, inv.from_character_id)
            from_names[inv.id] = c.name if c else "Кто-то"

        builder = InlineKeyboardBuilder()
        rows = []
        lines = []

        if pending:
            lines.append("📨 <b>Ждут твоего ответа:</b>")
            for inv in pending:
                what = "приглашение в пати" if inv.kind == "invite" else "заявка на вступление"
                lines.append(f"• {what} от <b>{from_names[inv.id]}</b>")
                builder.button(text=f"✅ {from_names[inv.id][:18]}",
                               callback_data=f"party_inv_yes:{inv.id}")
                builder.button(text="❌ Отклонить",
                               callback_data=f"party_inv_no:{inv.id}")
                rows.append(2)
            lines.append("")

        if character.party:
            party = character.party
            members = (await session.execute(
                select(Character)
                .where(Character.party_id == party.id)
                .options(selectinload(Character.user), selectinload(Character.location))
            )).scalars().all()

            lines.append(f"👥 <b>Пати: {party.name}</b> · состав {len(members)}/{MAX_SIZE}\n")
            for m in members:
                crown = "👑 " if m.id == party.leader_id else ""
                near = (
                    m.id != character.id
                    and m.location_id is not None
                    and m.location_id == character.location_id
                    and (m.floor or 0) == (character.floor or 0)
                )
                lines.append(
                    f"{crown}{_faction_badge(m)}{m.name} (ур. {m.level})"
                    + (" · 📍 рядом" if near else "")
                )
            is_leader = party.leader_id == character.id

            if is_leader and len(members) < MAX_SIZE:
                builder.button(text="🔍 Найти и позвать", callback_data="party_search")
                rows.append(1)
            if not is_leader:
                lines.append("\n<i>Звать новых героев может только 👑 предводитель.</i>")
            builder.button(text="🚪 Выйти из пати", callback_data="party_leave")
            rows.append(1)
            builder.button(text="◀️ Назад", callback_data="main_menu")
            rows.append(1)
        else:
            lines.append(
                "👥 <b>Пати</b>\n\nТы странствуешь в одиночку.\n\n"
                f"<i>В пати до {MAX_SIZE} героев. Позвать можно соратников "
                "своей фракции и игроков рядом — 🔍 поиск покажет всех "
                "подходящих. С враждующей фракцией пати невозможна.</i>"
            )
            builder.button(text="➕ Создать пати", callback_data="party_create")
            builder.button(text="🔍 Найти пати или союзника", callback_data="party_search")
            rows.append(2)
            builder.button(text="◀️ Назад", callback_data="main_menu")
            rows.append(1)

        builder.adjust(*rows)
        await safe_edit_text(callback, "\n".join(lines),
                             reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()


# ── поиск игроков ───────────────────────────────────────────

@router.callback_query(F.data == "party_search")
async def party_search(callback: CallbackQuery):
    async with async_session() as session:
        user, character = await _me(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        if (character.party and character.party.leader_id != character.id):
            await callback.answer("Звать в пати может только 👑 предводитель.",
                                  show_alert=True)
            return

        candidates = await _find_candidates(session, character)

        lines = ["🔍 <b>Поиск союзников</b>\n"]
        f = _faction_of(character)
        if f:
            lines.append(f"Твоя фракция: {f[1]} <b>{f[2]}</b>")
        lines.append(
            "<i>Показаны герои твоей фракции и все, кто сейчас в той же "
            "локации. Враждующие с тобой силы из выдачи убраны.</i>\n"
        )

        builder = InlineKeyboardBuilder()
        rows = []
        shown = 0
        for other, near in candidates:
            if character.party_id and other.party_id == character.party_id:
                continue  # уже в моей пати
            if character.party_id and other.party_id:
                continue  # занят чужой пати — позвать не выйдет

            where = "📍 рядом" if near else (f"{_faction_badge(other)}своя фракция")
            loc = other.location.name if other.location else "—"
            shown += 1

            if character.party_id:
                lines.append(f"{shown}. <b>{other.name}</b> (ур. {other.level}) "
                             f"— {where}, {loc}")
                builder.button(text=f"✉️ Позвать {other.name[:16]}",
                               callback_data=f"party_ask:{other.id}")
            elif other.party_id:
                party = await session.get(Party, other.party_id)
                size = await _party_size(session, other.party_id)
                if party is None or size >= MAX_SIZE:
                    shown -= 1
                    continue  # призрачная или полная пати — проситься некуда
                lines.append(f"{shown}. <b>{other.name}</b> (ур. {other.level}) "
                             f"— {where}, {loc}\n"
                             f"   <i>в пати «{party.name}» ({size}/{MAX_SIZE}) — "
                             f"можно попроситься</i>")
                builder.button(text=f"✉️ Проситься к {other.name[:14]}",
                               callback_data=f"party_ask:{other.id}")
            else:
                lines.append(f"{shown}. <b>{other.name}</b> (ур. {other.level}) "
                             f"— {where}, {loc}")
                builder.button(text=f"✉️ Созвать пати с {other.name[:12]}",
                               callback_data=f"party_ask:{other.id}")
            rows.append(1)

        if not shown:
            lines.append(
                "😔 Подходящих героев не нашлось.\n"
                "Подойди к поселениям или подожди пополнения во фракции."
            )
        builder.button(text="◀️ К пати", callback_data="party_menu")
        rows.append(1)
        builder.adjust(*rows)
        await safe_edit_text(callback, "\n".join(lines),
                             reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()


# ── отправка приглашения / заявки ───────────────────────────

@router.callback_query(F.data.startswith("party_ask:"))
async def party_ask(callback: CallbackQuery):
    """Одна кнопка на все случаи: позвать, попроситься или создать пати и позвать."""
    target_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user, character = await _me(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        target = (await session.execute(
            select(Character)
            .where(Character.id == target_id)
            .options(selectinload(Character.user))
        )).scalar_one_or_none()
        if not target or target.user is None:
            await callback.answer("Герой не найден.", show_alert=True)
            return
        if target.id == character.id:
            await callback.answer("Себя звать не нужно.", show_alert=True)
            return

        # Кольцо вражды твёрже кнопок: враждующие фракции в пати не бывают.
        my_f = core_factions.allegiance(character)
        t_f = core_factions.allegiance(target)
        if core_factions.hostile(my_f, t_f):
            a = core_factions.FACTIONS[my_f][1] if my_f in core_factions.FACTIONS else "—"
            b = core_factions.FACTIONS[t_f][1] if t_f in core_factions.FACTIONS else "—"
            await callback.answer(
                f"⚔️ Пати невозможна: {a} и {b} враждуют по кольцу.",
                show_alert=True)
            return

        created_now = False
        if character.party_id:
            # Режим «позвать в мою пати» — только для предводителя.
            party = await session.get(Party, character.party_id)
            if party is None:
                character.party_id = None
                await session.commit()
                await callback.answer("Старая пати рассыпалась. Попробуй ещё раз.",
                                      show_alert=True)
                return
            if party.leader_id != character.id:
                await callback.answer("Звать может только 👑 предводитель.",
                                      show_alert=True)
                return
            if target.party_id:
                await callback.answer(f"{target.name} уже состоит в пати.",
                                      show_alert=True)
                return
            if await _party_size(session, party.id) >= MAX_SIZE:
                await callback.answer(f"В пати уже {MAX_SIZE} героя — больше некуда.",
                                      show_alert=True)
                return
            kind = "invite"
            to_char = target
        elif target.party_id:
            # Режим «попроситься в чужую пати» — отвечает её предводитель.
            party = await session.get(Party, target.party_id)
            if party is None:
                await callback.answer("Эта пати только что распалась.",
                                      show_alert=True)
                return
            if await _party_size(session, party.id) >= MAX_SIZE:
                await callback.answer("Эта пати уже полная.", show_alert=True)
                return
            to_char = (await session.execute(
                select(Character)
                .where(Character.id == party.leader_id)
                .options(selectinload(Character.user))
            )).scalar_one_or_none()
            if not to_char or to_char.user is None:
                await callback.answer("У этой пати нет предводителя.",
                                      show_alert=True)
                return
            kind = "join"
        else:
            # Оба одиночки: создаём пати и сразу зовём в неё.
            party = Party(name=f"Отряд {character.name}", leader_id=character.id)
            session.add(party)
            await session.flush()
            character.party_id = party.id
            created_now = True
            kind = "invite"
            to_char = target

        # Не плодим дубликаты висящих заявок (у новой пати их быть не может).
        if not created_now:
            dup = (await session.execute(
                select(PartyInvite)
                .where(PartyInvite.party_id == party.id)
                .where(PartyInvite.from_character_id == character.id)
                .where(PartyInvite.to_character_id == to_char.id)
                .where(PartyInvite.kind == kind)
                .where(PartyInvite.status == "pending")
            )).scalar_one_or_none()
            if dup:
                await callback.answer("Заявка уже отправлена и ждёт ответа.",
                                      show_alert=True)
                return

        inv = PartyInvite(
            party_id=party.id,
            from_character_id=character.id,
            to_character_id=to_char.id,
            kind=kind,
            status="pending",
        )
        session.add(inv)
        await session.commit()

        if kind == "invite":
            note = (
                f"🤝 <b>{character.name}</b> (ур. {character.level}) зовёт тебя "
                f"в пати «<b>{party.name}</b>»!\n\n"
                f"<i>Пати до {MAX_SIZE} героев — вместе и добыча веселее.</i>"
            )
        else:
            note = (
                f"🤝 <b>{character.name}</b> (ур. {character.level}) просится "
                f"в твою пати «<b>{party.name}</b>».\n\nПринять героя?"
            )
        await _notify(to_char.user.telegram_id, note, _answer_kb(inv.id))

    if created_now:
        await callback.answer(f"📨 Пати создана! Приглашение отправлено: {target.name}.",
                              show_alert=True)
        await party_menu(callback)
    elif kind == "invite":
        await callback.answer(f"📨 Приглашение отправлено: {target.name}.",
                              show_alert=True)
        await party_search(callback)
    else:
        await callback.answer(f"📨 Заявка отправлена предводителю пати «{party.name}».",
                              show_alert=True)
        await party_search(callback)


# ── ответы на заявки ────────────────────────────────────────

@router.callback_query(F.data.startswith("party_inv_yes:"))
async def party_inv_accept(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user, character = await _me(session, callback.from_user.id)
        inv = await session.get(PartyInvite, inv_id)
        if not inv or not character or inv.to_character_id != character.id:
            await callback.answer("Эта заявка не тебе или уже устарела.",
                                  show_alert=True)
            return
        if inv.status != "pending":
            await callback.answer("Эта заявка уже закрыта.", show_alert=True)
            return

        party = await session.get(Party, inv.party_id)
        sender = await session.get(Character, inv.from_character_id)
        if party is None or sender is None:
            inv.status = "cancelled"
            await session.commit()
            await safe_edit_text(callback, "🤝 Эта пати уже распалась.",
                                 parse_mode="HTML")
            await callback.answer()
            return

        joiner = character if inv.kind == "invite" else sender
        if joiner.party_id:
            inv.status = "cancelled"
            await session.commit()
            await safe_edit_text(
                callback, "🤝 Вступающий уже состоит в другой пати.",
                parse_mode="HTML")
            await callback.answer("Он уже в другой пати.", show_alert=True)
            return
        if await _party_size(session, party.id) >= MAX_SIZE:
            inv.status = "cancelled"
            await session.commit()
            await safe_edit_text(
                callback, f"🤝 Пати «{party.name}» уже полная ({MAX_SIZE} героя).",
                parse_mode="HTML")
            await callback.answer("Пати уже полная.", show_alert=True)
            return

        # Вражда могла появиться уже после отправки заявки — перепроверяем.
        leader = await session.get(Character, party.leader_id)
        j_f = core_factions.allegiance(joiner)
        l_f = core_factions.allegiance(leader) if leader else None
        if core_factions.hostile(j_f, l_f):
            inv.status = "cancelled"
            await session.commit()
            await safe_edit_text(
                callback, "⚔️ Пати невозможна: фракции враждуют по кольцу.",
                parse_mode="HTML")
            await callback.answer("Фракции враждуют.", show_alert=True)
            return

        joiner.party_id = party.id
        inv.status = "accepted"
        await session.commit()
        size_now = await _party_size(session, party.id)

        sender_user = await session.get(User, sender.user_id)

    await safe_edit_text(
        callback,
        f"🤝 <b>Готово!</b>\n\n<b>{joiner.name}</b> теперь в пати "
        f"«<b>{party.name}</b>» ({size_now}/{MAX_SIZE}).",
        parse_mode="HTML",
    )
    await callback.answer("Добро пожаловать в пати!")

    if sender_user:
        if inv.kind == "invite":
            text = (f"✅ <b>{joiner.name}</b> принял твоё приглашение — "
                    f"пати «{party.name}» пополнилась!")
        else:
            text = (f"✅ Твою заявку приняли: ты теперь в пати "
                    f"«{party.name}»!")
        await _notify(sender_user.telegram_id, text)


@router.callback_query(F.data.startswith("party_inv_no:"))
async def party_inv_decline(callback: CallbackQuery):
    inv_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        user, character = await _me(session, callback.from_user.id)
        inv = await session.get(PartyInvite, inv_id)
        if not inv or not character or inv.to_character_id != character.id:
            await callback.answer("Эта заявка не тебе или уже устарела.",
                                  show_alert=True)
            return
        if inv.status != "pending":
            await callback.answer("Эта заявка уже закрыта.", show_alert=True)
            return

        inv.status = "declined"
        party = await session.get(Party, inv.party_id)
        sender = await session.get(Character, inv.from_character_id)
        sender_user = await session.get(User, sender.user_id) if sender else None
        party_name = party.name if party else "пати"
        await session.commit()

    await safe_edit_text(callback, "❌ Ты отклонил заявку.", parse_mode="HTML")
    await callback.answer("Отклонено.")

    if sender_user:
        if inv.kind == "invite":
            text = (f"❌ <b>{character.name}</b> отклонил приглашение "
                    f"в пати «{party_name}».")
        else:
            text = f"❌ Твою заявку в пати «{party_name}» отклонили."
        await _notify(sender_user.telegram_id, text)


# ── создание и выход ────────────────────────────────────────

@router.callback_query(F.data == "party_create")
async def party_create(callback: CallbackQuery):
    async with async_session() as session:
        user, character = await _me(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        if character.party_id:
            await callback.answer("Ты уже в пати!", show_alert=True)
            return

        party = Party(name=f"Отряд {character.name}", leader_id=character.id)
        session.add(party)
        await session.flush()
        character.party_id = party.id
        await session.commit()

    await callback.answer("Пати создана!")
    await party_menu(callback)


@router.callback_query(F.data == "party_leave")
async def party_leave(callback: CallbackQuery):
    async with async_session() as session:
        user, character = await _me(session, callback.from_user.id)
        if not character:
            await callback.answer("Сначала создай персонажа!", show_alert=True)
            return

        if not character.party_id:
            await callback.answer("Ты не в пати.", show_alert=True)
            return

        party = await session.get(Party, character.party_id)
        character.party_id = None
        await session.commit()

        # If leader leaves, disband or transfer
        if party and party.leader_id == character.id:
            result = await session.execute(
                select(Character).where(Character.party_id == party.id)
            )
            remaining = result.scalars().all()
            if remaining:
                party.leader_id = remaining[0].id
            else:
                # Висящие заявки распущенной пати закрываем, не оставляя трупов.
                await session.execute(
                    update(PartyInvite)
                    .where(PartyInvite.party_id == party.id)
                    .where(PartyInvite.status == "pending")
                    .values(status="cancelled")
                )
                await session.delete(party)
        await session.commit()

    await callback.answer("Ты покинул пати.")
    await party_menu(callback)
