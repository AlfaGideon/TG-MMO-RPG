"""Персональные напоминания (IDEAS-next, пункт 10).

Рассылка `bot/broadcast.py` говорит со всеми, а игроку чаще нужны три
личные весточки:

* ⏳ лот на аукционе скоро истечёт — успеть назначить цену / перебить
  ставку (молоток и возврат вещи работали и раньше, но игрок узнавал о
  финише только зайдя в бота);
* 🌀 портал подземелья закроется через 15 минут — последний chance зайти;
* ⚔️ зависший вызов на дуэль — вызванный мог просто не увидеть личное
  сообщение, а вызывавший — ждать вечно (вызов живёт 5 минут).

Консоль бота (`bot/runner.py`, `_reminder_loop`) периодически вызывает
`collect_due_reminders` и рассылает результат. Функция чистая: ничего не
отправляет и не коммитит — список сообщений легко тестировать. Повторы
гасит in-memory-дедупликация (как и сами вызовы дуэлей): рестарт — новый
раунд напоминаний, что правильно после простоя.
"""
import json
import logging
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core import notify as notify_common
from core.models import AuctionLot, AuctionStatus, Character, DungeonTemplate, User

logger = logging.getLogger(__name__)


def _prefs_of(raw):
    """JSON-поле `prefs` → нормализованные настройки (дефолты из engine)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except Exception:
            raw = {}
    return notify_common.normalized(raw)


async def _prefs_by_tg(session) -> dict[int, dict]:
    """Настройки вестей по telegram_id всех, у кого есть герой."""
    result = await session.execute(
        select(User.telegram_id, Character.prefs)
        .join(Character, Character.user_id == User.id)
    )
    return {int(tg): _prefs_of(raw) for tg, raw in result.all()}


def _allowed(prefs: dict, channel: str) -> bool:
    """Канал включён и сейчас не тихие часы."""
    return (notify_common.enabled(prefs, channel)
            and not notify_common.in_quiet_hours(prefs))

AUCTION_WARN_BEFORE = timedelta(minutes=10)     # «скоро истечёт»
PORTAL_WARN_BEFORE = timedelta(minutes=15)      # «портал закрывается»
DUEL_REMIND_AFTER = timedelta(minutes=2)        # «вызов всё ещё висит»
DEDUP_TTL = 6 * 3600                            # не напоминать одно и то же 6 ч

# ключ напоминания -> когда отправляли
_sent: "dict[str, float]" = {}


def _once(key: str) -> bool:
    """True — напоминание по этому ключу ещё не уходило (в пределах TTL)."""
    now = time.time()
    if len(_sent) > 4096:                        # страховка от разрастания
        for stale in [k for k, t in _sent.items() if now - t > DEDUP_TTL]:
            _sent.pop(stale, None)
    last = _sent.get(key)
    if last is not None and now - last < DEDUP_TTL:
        return False
    _sent[key] = now
    return True


def reset_dedup() -> None:
    """Забыть отправленные ключи (для тестов и принудительных повторов)."""
    _sent.clear()


async def _telegram_of(session, character_id) -> int | None:
    """Telegram-адресат по id персонажа (через владельца)."""
    if not character_id:
        return None
    ch = await session.get(Character, int(character_id))
    if ch is None:
        return None
    user = await session.get(User, ch.user_id)
    return user.telegram_id if user else None


def _lot_title(lot: AuctionLot) -> str:
    try:
        if lot.instance is not None and lot.item is not None:
            return str(lot.instance.display_name(lot.item))
        if lot.item is not None:
            return str(lot.item.name)
    except Exception:
        pass
    return "лот"


async def collect_due_reminders(session, now: float | None = None) -> list[dict]:
    """Собрать уместные сейчас напоминания.

    Возвращает список `{"tg_id": int, "text": str}` (личный адресат) либо
    `{"broadcast": True, "text": str}` — тем, у кого открыт портал,
    сообщает рассылка. Ни отправки, ни commit'а здесь нет намеренно.
    `now` (unix-секунды) — только для тестов; в бою берётся текущее время.
    """
    from datetime import datetime, timezone

    from core.dates import aware, utcnow

    now_dt = (datetime.fromtimestamp(now, tz=timezone.utc) if now is not None
              else utcnow())
    now_ts = now_dt.timestamp()
    out: list[dict] = []
    prefs_map = await _prefs_by_tg(session)

    # ── аукцион: скоро финиш ─────────────────────────────────
    lots = (await session.execute(
        select(AuctionLot)
        .options(selectinload(AuctionLot.item), selectinload(AuctionLot.instance))
        .where(AuctionLot.status == AuctionStatus.ACTIVE.value)
        .where(AuctionLot.expires_at.isnot(None))
    )).scalars().all()
    for lot in lots:
        if lot.expires_at is None:
            continue
        left = aware(lot.expires_at) - now_dt
        if left <= timedelta(0) or left > AUCTION_WARN_BEFORE:
            continue
        mins = max(1, int(left.total_seconds() // 60))
        name = _lot_title(lot)
        bidding = int(lot.start_bid or 0) > 0
        seller_tg = await _telegram_of(session, lot.seller_id)
        if seller_tg:
            if bidding:
                leader = lot.current_bidder_name or "никто"
                text = (f"⏳ <b>Торги закрываются через ~{mins} мин.</b>\n\n"
                        f"«{name}», ставка <b>{lot.current_bid}</b>🟤, лидер: {leader}.\n"
                        f"Перебей — и вещь твоя; не перебьют — ты продашь.")
                key = f"auc:bid:{lot.id}"
            else:
                text = (f"⏳ <b>Аукцион скоро истечёт</b> (~{mins} мин).\n\n"
                        f"«{name}» за {lot.price}🟤 никто не купил — "
                        f"после истечения вещь вернётся к тебе.")
                key = f"auc:sale:{lot.id}"
            if _allowed(prefs_map.get(int(seller_tg), {}), "auction") and _once(key):
                out.append({"tg_id": seller_tg, "text": text})
        # Лидеру торгов — отдельная весточка: он может и не продавец.
        bidder_tg = await _telegram_of(session, lot.current_bidder_id)
        if (bidding and bidder_tg and bidder_tg != seller_tg
                and _allowed(prefs_map.get(int(bidder_tg), {}), "auction")):
            if _once(f"auc:leader:{lot.id}"):
                out.append({"tg_id": bidder_tg, "text":
                            f"⏳ <b>Твоя ставка лидирует недолго.</b>\n\n"
                            f"«{name}» — {lot.current_bid}🟤, торги закроются "
                            f"через ~{mins} мин. Перебей себя, если вещь нужна."})

    # ── порталы: скоро закрытие ──────────────────────────────
    from core.dungeons import PORTAL_MAX_LIFETIME, _aware

    templates = (await session.execute(
        select(DungeonTemplate)
        .where(DungeonTemplate.portal_opened_at.isnot(None))
        .where(DungeonTemplate.portal_closed_at.is_(None))
    )).scalars().all()
    for tpl in templates:
        if not tpl.portal_opened_at:
            continue
        until = _aware(tpl.portal_opened_at) + PORTAL_MAX_LIFETIME
        left = until - now_dt
        if left <= timedelta(0) or left > PORTAL_WARN_BEFORE:
            continue
        mins = max(1, int(left.total_seconds() // 60))
        muted = {int(tg) for tg, prefs in prefs_map.items()
                 if not _allowed(prefs, "portal")}
        if _once(f"portal:{tpl.id}:{int(_aware(tpl.portal_opened_at).timestamp())}"):
            entry = {"broadcast": True, "text":
                     f"🌀 <b>Портал закрывается</b> через ~{mins} мин: "
                     f"«{tpl.name}». Успей зайти — потом придётся ждать"
                     f" нового открытия."}
            if muted:
                entry["exclude"] = sorted(muted)
            out.append(entry)

    # ── дуэли: вызов всё ещё висит ───────────────────────────
    # duel_invites ключуется id ПЕРСОНАЖА вызванного (bot/handlers/
    # world_extra.py), поэтому адресата (telegram) надо достать из БД.
    try:
        from bot.handlers.world_extra import duel_invites

        for target_id, inv in list(duel_invites.items()):
            age = now_ts - (inv[2] if len(inv) > 2 else now_ts)
            if age < DUEL_REMIND_AFTER.total_seconds():
                continue
            if _once(f"duel:{target_id}:{int(inv[2] if len(inv) > 2 else 0)}"):
                target_tg = await _telegram_of(session, target_id)
                if not target_tg:
                    continue
                if not _allowed(prefs_map.get(int(target_tg), {}), "duel"):
                    continue
                wager = inv[1]
                stake = f" со ставкой {wager}🟤" if wager else ""
                out.append({"tg_id": int(target_tg), "text":
                            f"⚔️ <b>Тебя вызывают на дуэль</b>{stake} — "
                            f"сообщение с кнопками ждёт ответа; "
                            f"через несколько минут вызов сгорит."})
    except Exception as e:   # память процесса могла и не успеть подняться
        logger.debug(f"duel reminder skipped: {e}")

    return out
