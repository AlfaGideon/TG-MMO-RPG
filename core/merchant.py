"""Бродячий торговец с диковинками — серверный стек.

Правила и числа совпадают с браузерным `engine/merchant.py`: появляется
при путешествии (или запускается админом вручную), торгует несколько
часов в одной локации и уходит. Игрокам заранее не сообщается — его
можно встретить только на месте.

Состояние хранится в AppSetting (MERCHANT_KEY) как JSON:

    {
      "active": true,
      "location_id": 3,
      "expires_at": "2026-08-01T12:00:00+00:00",
      "name": "🧳 Бродячий торговец",
      "greeting": "...",
      "items": [{"item_id": 5, "price": 120, "qty": 2}, ...]
    }

Товары добавляет админ (панель) или генерируются из каталога Item.
Покупка списывает золото, выдаёт предмет через core.loot.grant_item и
убирает единицу товара с витрины.
"""
import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core import history
from core.enums import ItemSource, ItemType
from core.loot import grant_item
from core.models import AppSetting, Character, Item

MERCHANT_KEY = "wandering_merchant"
ADMIN_ITEMS_KEY = "admin_merchant_items"
GENERATED_KEY = "merchant_generated_items"

MERCHANT_NAME = "🧳 Бродячий торговец"
MERCHANT_GREETING = ("Свежие диковинки! Дёшево — только для тех, кто "
                     "успел до заката.")
LIFETIME_HOURS = 6          # сколько часов торгует (как в engine.merchant)
WANDER_CHANCE = 0.12        # шанс встретить торговца при входе в локацию
MARKUP = 1.6                # наценка к базовой цене товара
MAX_WARES = 12              # потолок товаров на витрине
PRICE_SPAN = (0.8, 2.0)     # разброс цены диковинки относительно базы


def _now():
    return datetime.now(timezone.utc)


# ── состояние ──────────────────────────────────────────────

async def load(session) -> dict | None:
    """Текущее состояние торговца; просроченное гасится."""
    result = await session.execute(
        select(AppSetting).where(AppSetting.key == MERCHANT_KEY))
    setting = result.scalar_one_or_none()
    if setting is None:
        return None
    try:
        state = json.loads(setting.value or "{}")
    except (ValueError, TypeError):
        state = {}
    if not state.get("active"):
        return None
    try:
        expires = datetime.fromisoformat(state["expires_at"])
    except (KeyError, ValueError, TypeError):
        return None
    if expires <= _now():
        state["active"] = False
        setting.value = json.dumps(state, ensure_ascii=False)
        return None
    return state


async def save(session, state: dict) -> None:
    result = await session.execute(
        select(AppSetting).where(AppSetting.key == MERCHANT_KEY))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = AppSetting(key=MERCHANT_KEY, value="")
        session.add(setting)
    setting.value = json.dumps(state, ensure_ascii=False)
    await session.flush()


async def deactivate(session) -> None:
    state = await load(session)
    if state is None:
        return
    state["active"] = False
    await save(session, state)


async def activate(session, location_id: int, hours: float = LIFETIME_HOURS) -> dict:
    """Запустить торговца в локации на `hours` часов (товары сохраняются)."""
    state = {
        "active": True,
        "location_id": int(location_id),
        "expires_at": (_now() + timedelta(hours=max(1.0, float(hours)))).isoformat(),
        "name": MERCHANT_NAME,
        "greeting": MERCHANT_GREETING,
        "items": [],
    }
    old = await load(session)
    if old:
        state["items"] = old.get("items", [])
        state["name"] = old.get("name", MERCHANT_NAME)
        state["greeting"] = old.get("greeting", MERCHANT_GREETING)
    await save(session, state)
    return state


async def set_location(session, location_id: int) -> dict | None:
    state = await load(session)
    if state is None:
        return None
    state["location_id"] = int(location_id)
    await save(session, state)
    return state


async def wares(session) -> list[dict]:
    """Товары витрины с данными предмета: [{item, item_id, price, qty}]."""
    state = await load(session)
    if state is None:
        return []
    items = state.get("items") or []
    if not items:
        return []
    ids = [int(w["item_id"]) for w in items if w.get("qty", 0) > 0]
    if not ids:
        return []
    result = await session.execute(select(Item).where(Item.id.in_(ids)))
    by_id = {it.id: it for it in result.scalars().all()}
    out = []
    for w in items:
        if w.get("qty", 0) <= 0:
            continue
        item = by_id.get(int(w["item_id"]))
        if item is None:
            continue
        out.append({"item": item, "item_id": item.id,
                    "price": int(w["price"]), "qty": int(w["qty"])})
    return out


# ── наполнение витрины ─────────────────────────────────────

async def add_item(session, item_id: int, price: int, qty: int = 1) -> dict:
    """Положить предмет на витрину. Цена и количество проверяются."""
    item = await session.get(Item, int(item_id))
    if item is None:
        return {"ok": False, "reason": "Предмет не найден."}
    price = max(1, int(price or 0))
    qty = max(1, min(99, int(qty or 1)))
    state = await load(session)
    if state is None:
        state = {"active": False, "location_id": None, "expires_at": None,
                 "name": MERCHANT_NAME, "greeting": MERCHANT_GREETING,
                 "items": []}
    items = state.setdefault("items", [])
    if len(items) >= MAX_WARES:
        return {"ok": False, "reason": f"На витрине максимум {MAX_WARES} товаров."}
    items.append({"item_id": item.id, "price": price, "qty": qty})
    await save(session, state)
    return {"ok": True, "item": item.name, "price": price, "qty": qty}


async def remove_item(session, index: int) -> dict:
    state = await load(session)
    if state is None:
        return {"ok": False, "reason": "Торговец не активен."}
    items = state.get("items") or []
    if not 0 <= int(index) < len(items):
        return {"ok": False, "reason": "Товар не найден."}
    gone = items.pop(int(index))
    await save(session, state)
    return {"ok": True, "removed": gone}


async def clear_items(session) -> dict:
    state = await load(session)
    if state is None:
        return {"ok": False, "reason": "Торговец не активен."}
    state["items"] = []
    await save(session, state)
    return {"ok": True}


async def generate_items(session, count: int = 4) -> dict:
    """Случайные диковинки из каталога: цена = база × наценка × разброс."""
    result = await session.execute(
        select(Item).where(Item.is_sellable == True)  # noqa: E712
    )
    pool = [it for it in result.scalars().all() if it.is_sellable]
    if not pool:
        return {"ok": False, "reason": "В каталоге нет продаваемых предметов."}
    state = await load(session)
    if state is None:
        state = {"active": False, "location_id": None, "expires_at": None,
                 "name": MERCHANT_NAME, "greeting": MERCHANT_GREETING,
                 "items": []}
    items = state.setdefault("items", [])
    count = max(1, min(MAX_WARES - len(items), int(count or 1)))
    count = min(count, len(pool))          # не больше, чем есть в каталоге
    made = []
    for item in random.sample(pool, count):
        price = max(1, int((item.price or 10) * MARKUP * random.uniform(*PRICE_SPAN)))
        qty = (random.randint(3, 5)
               if item.item_type == ItemType.CONSUMABLE else 1)
        items.append({"item_id": item.id, "price": price, "qty": qty})
        made.append(f"{item.icon} {item.name} — {price}🪙 ×{qty}")
    await save(session, state)
    return {"ok": True, "count": len(made), "wares": made}


# ── покупка ────────────────────────────────────────────────

async def buy(session, character: Character, index: int) -> dict:
    """Покупка диковинки: золото списывается, предмет уходит в сумку."""
    state = await load(session)
    if state is None:
        return {"ok": False, "reason": "Торговец уже ушёл."}
    items = state.get("items") or []
    if not 0 <= int(index) < len(items):
        return {"ok": False, "reason": "Такого товара нет."}
    ware = items[int(index)]
    if ware.get("qty", 0) <= 0:
        return {"ok": False, "reason": "Этот товар уже раскупили."}
    price = int(ware["price"])
    if character.gold < price:
        return {"ok": False,
                "reason": f"Не хватает {price - character.gold}🪙."}
    item = await session.get(Item, int(ware["item_id"]))
    if item is None:
        return {"ok": False, "reason": "Предмет потерялся — торговец убрал его с витрины."}

    character.gold -= price
    ware["qty"] -= 1
    await save(session, state)

    added = await grant_item(
        session, character, item, quantity=1,
        source=ItemSource.SHOP.value, source_detail="бродячий торговец",
    )
    if added:
        for inv in added:
            if inv.instance_id:
                await history.record(
                    session, inv.instance, "created", character,
                    detail="куплено у бродячего торговца", price=price,
                )
    await session.flush()
    return {"ok": True, "item": item, "price": price}


# ── появление и уход ───────────────────────────────────────

async def maybe_wander(session) -> dict:
    """Шанс, что торговец переберётся в другую локацию (вызывается при
    движении игроков). Просроченный торговец уходит. Возвращает отчёт."""
    from core.models import Location

    state = await load(session)
    if state is None:
        return {"moved": False, "gone": False}
    if random.random() >= WANDER_CHANCE * 0.5:
        return {"moved": False, "gone": False}
    result = await session.execute(select(Location))
    spots = [l for l in result.scalars().all()
             if l.id != int(state.get("location_id") or 0)]
    if not spots:
        return {"moved": False, "gone": False}
    target = random.choice(spots)
    state["location_id"] = target.id
    await save(session, state)
    return {"moved": True, "gone": False, "to": target.name}
