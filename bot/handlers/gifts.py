"""🎁 Прямые подарки между игроками — экраны бота (IDEAS-next, пункт 2).

Экономика без посредника: «рука в руку» на той же клетке. Сама логика
перехода вещи и монет — в `core/gifts.py`; здесь только выбор героя рядом,
витрина сумки и подтверждения. Экраны строятся stateless: в колбэке
едут id получателя и вещи, а право собственности и соседство проверяются
заново в момент подтверждения — «зависший» экран не сможет подарить то, что уже унесено.
От двойного тапа защищает короткий cooldown-дедуп.
"""
import html as _html
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from core.database import async_session
from core.models import Character, InventoryItem, User
from bot.keyboards.inline import main_menu_keyboard
from bot.utils.edit import safe_edit_text

router = Router()

# Защита от двойного нажатия «Подарить»: (tg, payload) -> момент.
_last_confirm: "dict[int, tuple[str, float]]" = {}
CONFIRM_COOLDOWN = 3.0


def _escape(text) -> str:
    return _html.escape(str(text or ""), quote=False)


async def _character(session, telegram_id):
    user = (await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )).scalar_one_or_none()
    if user is None:
        return None
    return (await session.execute(
        select(Character).where(Character.user_id == user.id)
    )).scalar_one_or_none()


def _fresh_click(tg: int, payload: str) -> bool:
    now = time.time()
    prev = _last_confirm.get(tg)
    if prev and prev[0] == payload and now - prev[1] < CONFIRM_COOLDOWN:
        return False
    _last_confirm[tg] = (payload, now)
    return True


@router.callback_query(F.data == "gift_select")
async def gift_select(callback: CallbackQuery):
    """Кто стоит рядом — список, как в дуэлях, но кнопки дара."""
    async with async_session() as session:
        character = await _character(session, callback.from_user.id)
        if character is None:
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
            lines = ["🎁 <b>Подарки</b>", "",
                     "<i>Рядом никого нет — подойдите на одну клетку.</i>"]
        else:
            lines = ["🎁 <b>Кому подарить</b>", "",
                     "<i>Вещь переходит мгновенно, без комиссии аукциона. "
                     "Получатель — тот, кто стоит рядом.</i>", ""]
            for o in others[:5]:
                builder.button(text=f"🎁 {_escape(o.name)} (ур. {o.level})",
                               callback_data=f"gift_to:{o.id}")
        builder.button(text="◀️ Назад", callback_data="inspect")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("gift_to:"))
async def gift_catalog(callback: CallbackQuery):
    """Что подарить: содержимое сумки + шаги монет."""
    try:
        to_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Непонятный адресат.", show_alert=True)
        return

    from core import gifts as core_gifts
    from engine.currency import total_in_bronze

    async with async_session() as session:
        sender = await _character(session, callback.from_user.id)
        recipient = await session.get(Character, to_id)
        if sender is None or recipient is None:
            await callback.answer("Даритель или получатель не найдены.",
                                  show_alert=True)
            return
        if not core_gifts.in_reach(sender, recipient):
            await callback.answer("Получатель ушёл с клетки.", show_alert=True)
            return

        items = await core_gifts.giftable_items(session, sender)
        builder = InlineKeyboardBuilder()
        lines = [f"🎁 <b>Подарок: {_escape(recipient.name)}</b>", ""]

        if items:
            lines.append("Из сумки:")
            for inv in items[:10]:
                title = inv.item.name if inv.item else "вещь"
                if inv.instance_id is not None and inv.instance is not None:
                    try:
                        title = inv.instance.display_name(inv.item)
                    except Exception:
                        pass
                qty = f" ×{inv.quantity or 1}" if (inv.quantity or 1) > 1 and inv.instance_id is None else ""
                lines.append(f"• {_escape(title)}{qty} — <b>{inv.id}</b>")
                builder.button(text=f"🎁 {_escape(title)}{qty}",
                               callback_data=f"gift_pick:{to_id}:{inv.id}")
        else:
            lines.append("<i>В сумке нечего подарить "
                         "(надетое и защищённый карман не в счёт).</i>")

        purse = total_in_bronze(sender)
        steps = [g for g in core_gifts.GOLD_STEPS if g <= purse]
        if steps:
            lines.append(f"\nМонеты (кошелёк {purse}🟤):")
            for g in steps:
                builder.button(text=f"💰 {g}🟤",
                               callback_data=f"gift_gold:{to_id}:{g}")
        builder.button(text="◀️ Назад", callback_data="gift_select")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("gift_pick:"))
async def gift_pick(callback: CallbackQuery):
    """Один клик до подарка; для стака больше одного — выбор количества."""
    try:
        _, raw_to, raw_inv = callback.data.split(":")
        to_id, inv_id = int(raw_to), int(raw_inv)
    except ValueError:
        await callback.answer("Список устарел — открой заново.", show_alert=True)
        return

    async with async_session() as session:
        sender = await _character(session, callback.from_user.id)
        recipient = await session.get(Character, to_id)
        inv = await session.get(InventoryItem, inv_id)
        if sender is None or recipient is None or inv is None \
                or inv.character_id != sender.id:
            await callback.answer("Вещь уже ушла из сумки.", show_alert=True)
            return

        title = inv.item.name if inv.item else "вещь"
        builder = InlineKeyboardBuilder()
        if inv.instance_id is None and (inv.quantity or 1) > 1:
            lines = [f"🎁 <b>{_escape(title)}</b> — сколько штук?"
                     f" (в сумке {inv.quantity})", ""]
            builder.button(text=f"Все ({inv.quantity})",
                           callback_data=f"gift_confirm:{to_id}:item:{inv.id}:{inv.quantity}")
            builder.button(text="Одну",
                           callback_data=f"gift_confirm:{to_id}:item:{inv.id}:1")
        else:
            lines = [f"🎁 <b>Подарить {_escape(title)}</b>",
                     f"Получателю: {_escape(recipient.name)}.", "",
                     "<i>Вещь уйдёт из сумки сразу после кнопки.</i>"]
            builder.button(text="✅ Подарить",
                           callback_data=f"gift_confirm:{to_id}:item:{inv.id}:1")
        builder.button(text="🚫 Отмена", callback_data=f"gift_to:{to_id}")
        builder.adjust(1)

    await safe_edit_text(callback, "\n".join(lines),
                         reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("gift_confirm:"))
async def gift_confirm(callback: CallbackQuery):
    """Финал: gift_confirm:{кто}:item:{id}:{кол-во} | :gold:{сумма}.

    Все имена и адрес получателя захватываются в строковые переменные ДО
    commit'а: после фиксации сессии async-объекты «протухают» и любое
    обращение к атрибуту — это ленивое обновление (MissingGreenlet), а
    пересоздавать сессию ради пары имён нечем.
    """
    parts = callback.data.split(":")
    if len(parts) not in (4, 5) or parts[2] not in ("item", "gold"):
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    from core import gifts as core_gifts

    async with async_session() as session:
        sender = await _character(session, callback.from_user.id)
        try:
            recipient = await session.get(Character, int(parts[1]))
        except ValueError:
            recipient = None
        if sender is None or recipient is None:
            await callback.answer("Кто-то из вас потерялся.", show_alert=True)
            return
        recipient_name = _escape(recipient.name)
        sender_name = _escape(sender.name)
        recipient_user = await session.get(User, recipient.user_id)
        recipient_tg = recipient_user.telegram_id if recipient_user else None

        if parts[2] == "item":
            if len(parts) != 5:
                await callback.answer("Кнопка устарела.", show_alert=True)
                return
            try:
                inv = await session.get(InventoryItem, int(parts[3]))
                qty = int(parts[4])
            except (ValueError, IndexError):
                await callback.answer("Кнопка устарела.", show_alert=True)
                return
            if not _fresh_click(int(callback.from_user.id),
                                f"item:{inv.id if inv else 0}:{qty}"):
                await callback.answer("Уже отправляю — не торопись.",
                                      show_alert=True)
                return
            res = await core_gifts.gift_item(session, sender, recipient,
                                             inv, qty)
            if not res.get("ok"):
                await session.rollback()
                await callback.answer(res.get("reason", "Не вышло."),
                                      show_alert=True)
                return
            await session.commit()
            done = (f"🎁 Подарено: <b>{_escape(res['name'])}</b>"
                    f" ×{res['qty']} — {recipient_name}.")
            notice = (f"🎁 <b>Тебе подарили</b> {_escape(res['name'])}"
                      f" ×{res['qty']} — от {sender_name}.")
        else:
            try:
                amount = int(parts[3])
            except ValueError:
                await callback.answer("Кнопка устарела.", show_alert=True)
                return
            if not _fresh_click(int(callback.from_user.id), f"gold:{amount}"):
                await callback.answer("Уже отправляю — не торопись.",
                                      show_alert=True)
                return
            res = await core_gifts.gift_gold(session, sender, recipient,
                                             amount)
            if not res.get("ok"):
                await session.rollback()
                await callback.answer(res.get("reason", "Не вышло."),
                                      show_alert=True)
                return
            await session.commit()
            done = f"💰 Переведено <b>{amount}</b>🟤 — {recipient_name}."
            notice = (f"💰 <b>Тебе перевели</b> {amount}🟤 "
                      f"— от {sender_name}.")

    # Получатель узнаёт о подарке лично; доставка не важнее самого дара —
    # при любой ошибке Telegram текст уже применён в БД.
    if recipient_tg:
        try:
            await callback.bot.send_message(recipient_tg, notice,
                                            parse_mode="HTML")
        except Exception:
            pass

    await safe_edit_text(callback, done,
                         reply_markup=main_menu_keyboard(has_character=True),
                         parse_mode="HTML")


@router.callback_query(F.data.startswith("gift_gold:"))
async def gift_gold_confirm(callback: CallbackQuery):
    """Монеты: «gift_gold:{кто}:{сумма}» сразу с финальным подтверждением
    в том же формате, что и вещь."""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    raw_to, raw_amount = parts[1], parts[2]
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Перевести {raw_amount}🟤",
                   callback_data=f"gift_confirm:{raw_to}:gold:{raw_amount}")
    builder.button(text="🚫 Отмена", callback_data=f"gift_to:{raw_to}")
    builder.adjust(1)
    await safe_edit_text(
        callback,
        f"💰 <b>Перевод монет</b>\n\nПодарить {raw_amount}🟤? "
        f"Сумма спишется с кошелька сразу.",
        reply_markup=builder.as_markup(), parse_mode="HTML")
