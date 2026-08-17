"""Торги со ставками: пункт № 59 IDEAS-100.md.

python3 tests/test_auction_bids.py

Что было: `core/auction_bid.py` — заглушка с одной константой, которую не
читала ни одна строка кода. Пункт числился «требует решения владельца:
удалить или реализовать». Реализовано.

Ключевые решения, которые здесь проверяются:

* **ставка — это резерв.** Деньги списываются сразу, а не в конце. Иначе
  победитель успел бы потратить золото до удара молотка, и лот достался бы
  тому, кому нечем платить. Перебитому лидеру резерв возвращается в тот же
  момент;
* **гонка** решена условным UPDATE «перебей ровно ту ставку, которую я
  видел» — тем же приёмом, что покупка лота в `core/auction.py`. Списание
  идёт ПОСЛЕ успешного UPDATE, поэтому проигравший гонку не теряет денег;
* **лоты с молотка отделены от обычной витрины.** Иначе кнопка «Купить» в
  `core/auction.buy_lot` увела бы вещь по устаревшей цене мимо ставок, а
  `sweep_expired` вернул бы выигранный лот продавцу, оставив деньги
  победителя в резерве навсегда;
* **антиснайпинг**: ставка на последних минутах продлевает торги, иначе
  выигрывает не тот, кто больше даёт, а у кого лучше пинг.
"""
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Грейсфул-скип (пункт № 4).
from _deps import require  # noqa: E402

require("sqlalchemy", "aiosqlite", "aiogram")

# Детерминизм (пункт № 5).
from _seed import pin, unique_id  # noqa: E402

pin(119)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


async def _make_world(session):
    """Продавец, двое покупателей и именная вещь в сумке продавца."""
    from core.loot import new_uid
    from core.models import (Character, InventoryItem, Item, ItemInstance,
                             User)

    users, chars = [], []
    for name in ("Продавец", "Алиса", "Боб"):
        user = User(telegram_id=unique_id(), username=name.lower())
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name=f"{name}-{unique_id() % 1000}",
                         character_class="mage", level=10)
        session.add(char)
        await session.flush()
        users.append(user)
        chars.append(char)

    from engine.currency import add_currency

    for char in chars[1:]:
        add_currency(char, bronze=5000)

    item = Item(name="Клинок Зари", description="Клинок", item_type="weapon",
                price=200, level_requirement=1)
    session.add(item)
    await session.flush()
    inst = ItemInstance(item_id=item.id, uid=new_uid(),
                        owner_character_id=chars[0].id)
    session.add(inst)
    await session.flush()
    inv = InventoryItem(character_id=chars[0].id, item_id=item.id,
                        instance_id=inst.id, quantity=1)
    session.add(inv)
    await session.flush()
    return chars, item, inst, inv


async def scenario():
    from core import auction as A
    from core import auction_bid as B
    from core.database import async_session
    from core.enums import AuctionStatus
    from core.migrations import run_migrations
    from core.models import AuctionLot, Character, InventoryItem
    from engine.currency import total_in_bronze

    await run_migrations()

    print("\n— Выставление с молотка —")
    async with async_session() as s:
        chars, item, inst, inv = await _make_world(s)
        seller_id, alice_id, bob_id = [c.id for c in chars]

        bad = await B.list_bid_lot(s, chars[0], inv, start_bid=100, buyout=50)
        check(not bad["ok"],
              "выкуп ниже стартовой ставки отвергнут — иначе торги бессмысленны")

        res = await B.list_bid_lot(s, chars[0], inv, start_bid=100, buyout=1000)
        check(res["ok"], "лот выставлен")
        lot = res["lot"]
        lot_id = lot.id
        check(B.is_bid_lot(lot), "лот распознаётся как торговый")
        check(lot.current_bid == 0 and lot.bid_count == 0,
              "торги начинаются без ставок")
        left = await s.get(InventoryItem, inv.id)
        check(left is None, "вещь физически ушла из сумки продавца")
        await s.commit()

    print("\n— Лот с молотка не путается с обычной витриной —")
    async with async_session() as s:
        plain = await A.active_lots(s)
        check(all((l.start_bid or 0) == 0 for l in plain),
              "обычная витрина не показывает торговые лоты")
        bids = await B.active_bid_lots(s)
        check(len(bids) == 1, "витрина торгов показывает лот")

        lot = await s.get(AuctionLot, lot_id)
        bob = await s.get(Character, bob_id)
        denied = await A.buy_lot(s, bob, lot)
        check(not denied["ok"] and "молотк" in denied["reason"],
              "купить торговый лот по фиксированной цене нельзя")
        check(total_in_bronze(bob) == 5000, "деньги при отказе не списаны")

    print("\n— Ставки и возврат резерва —")
    async with async_session() as s:
        lot = await s.get(AuctionLot, lot_id)
        alice = await s.get(Character, alice_id)
        seller = await s.get(Character, seller_id)

        check(B.next_bid(lot) == 100,
              "первая ставка равна стартовой цене, а не выше")
        low = await B.place_bid(s, alice, lot, 50)
        check(not low["ok"], f"ставка ниже минимума отвергнута: {low['reason']}")
        check(total_in_bronze(alice) == 5000, "при отказе деньги не тронуты")

        own = await B.place_bid(s, seller, lot, 100)
        check(not own["ok"], "продавец не торгуется за свой лот")

        first = await B.place_bid(s, alice, lot, 100)
        check(first["ok"], "первая ставка принята")
        check(total_in_bronze(alice) == 4900,
              "деньги списаны сразу — ставка это резерв, а не обещание")
        check(first["next_bid"] == 105,
              f"следующая ставка учитывает шаг 5 %: {first['next_bid']}")
        await s.commit()

    async with async_session() as s:
        lot = await s.get(AuctionLot, lot_id)
        bob = await s.get(Character, bob_id)
        again = await B.place_bid(s, bob, lot, 100)
        check(not again["ok"], "повтор той же суммы не проходит")

        second = await B.place_bid(s, bob, lot, B.next_bid(lot))
        alice = await s.get(Character, alice_id)
        check(second["ok"], "перебивание принято")
        check(second["refunded"] == 100, "прежнему лидеру вернули его резерв")
        check(total_in_bronze(alice) == 5000,
              "кошелёк перебитого игрока восстановлен полностью")
        check(total_in_bronze(bob) == 4895, "у нового лидера списано")
        check(second["outbid_character_id"] == alice_id,
              "известен, кого перебили — есть кому отправить весть")

        mine = await B.place_bid(s, bob, lot, 500)
        check(not mine["ok"] and "лидируешь" in mine["reason"],
              "лидер не перебивает сам себя")
        await s.commit()

    print("\n— Гонка двух ставок —")
    async with async_session() as s:
        from sqlalchemy import update as sa_update

        lot = await s.get(AuctionLot, lot_id)
        alice = await s.get(Character, alice_id)
        seen = B.next_bid(lot)          # цена, которую увидела Алиса

        # Кто-то успел раньше — пишем мимо ORM, объект в памяти устарел.
        await s.execute(
            sa_update(AuctionLot).where(AuctionLot.id == lot_id)
            .values(current_bid=seen + 50, current_bidder_id=bob_id,
                    current_bidder_name="Боб")
            .execution_options(synchronize_session=False))

        late = await B.place_bid(s, alice, lot, seen)
        check(not late["ok"], f"опоздавший получил отказ: {late['reason']}")
        check(total_in_bronze(alice) == 5000,
              "деньги опоздавшего целы — списание идёт ПОСЛЕ захвата")
        await s.commit()

    print("\n— Антиснайпинг —")
    async with async_session() as s:
        lot = await s.get(AuctionLot, lot_id)
        lot.expires_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        await s.commit()
    async with async_session() as s:
        lot = await s.get(AuctionLot, lot_id)
        alice = await s.get(Character, alice_id)
        snipe = await B.place_bid(s, alice, lot, B.next_bid(lot))
        check(snipe["ok"] and snipe["extended"],
              "ставка в последние минуты продлила торги")
        left = B.time_left(lot)
        check(left.total_seconds() > 120,
              f"срок сдвинулся вперёд ({int(left.total_seconds())} с)")
        await s.commit()

    print("\n— Снятие лота —")
    async with async_session() as s:
        lot = await s.get(AuctionLot, lot_id)
        seller = await s.get(Character, seller_id)
        nope = await B.cancel_bid_lot(s, seller, lot)
        check(not nope["ok"],
              "снять торги со ставкой нельзя — участники теряли бы время")
        await s.commit()

    print("\n— Молоток по истёкшим торгам —")
    async with async_session() as s:
        lot = await s.get(AuctionLot, lot_id)
        winner_id = lot.current_bidder_id
        amount = lot.current_bid
        lot.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await s.commit()

    async with async_session() as s:
        # Обычный sweep не должен трогать торги.
        touched = await A.sweep_expired(s)
        check(all((l.start_bid or 0) == 0 for l in touched),
              "sweep_expired обходит лоты с молотка стороной")

        results = await B.close_finished(s)
        await s.commit()
        check(len(results) == 1 and results[0]["sold"],
              "торги закрыты продажей")
        check(results[0]["amount"] == amount, "цена та, что была на табло")

    async with async_session() as s:
        from sqlalchemy import select

        lot = await s.get(AuctionLot, lot_id)
        check(lot.status == AuctionStatus.SOLD.value, "лот помечен проданным")
        check(lot.buyer_id == winner_id, "покупатель записан")

        bag = (await s.execute(
            select(InventoryItem).where(InventoryItem.character_id == winner_id)
        )).scalars().all()
        check(len(bag) == 1, "вещь легла в сумку победителя")

        seller = await s.get(Character, seller_id)
        expected = max(1, int(amount * (1 - B.COMMISSION)))
        check(total_in_bronze(seller) == expected,
              f"продавцу заплатили за вычетом комиссии: {expected}🟤")

        check(await B.close_finished(s) == [],
              "повторный молоток ничего не делает (идемпотентно)")

    print("\n— Торги без ставок возвращают вещь —")
    async with async_session() as s:
        from core.loot import new_uid
        from core.models import Item, ItemInstance

        seller = await s.get(Character, seller_id)
        item = (await s.execute(
            __import__("sqlalchemy").select(Item).limit(1))).scalars().first()
        inst = ItemInstance(item_id=item.id, uid=new_uid(),
                            owner_character_id=seller_id)
        s.add(inst)
        await s.flush()
        inv = InventoryItem(character_id=seller_id, item_id=item.id,
                            instance_id=inst.id, quantity=1)
        s.add(inv)
        await s.flush()
        res = await B.list_bid_lot(s, seller, inv, start_bid=120)
        quiet_id = res["lot"].id
        res["lot"].expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await s.commit()

    async with async_session() as s:
        out = await B.close_finished(s)
        await s.commit()
        check(len(out) == 1 and not out[0]["sold"],
              "торги без ставок закрылись без продажи")
        lot = await s.get(AuctionLot, quiet_id)
        check(lot.status == AuctionStatus.EXPIRED.value, "лот просрочен")

        from sqlalchemy import select

        back = (await s.execute(
            select(InventoryItem).where(InventoryItem.character_id == seller_id)
        )).scalars().all()
        check(len(back) == 1, "вещь вернулась продавцу, а не пропала")

    print("\n— Выкуп сразу —")
    async with async_session() as s:
        from core.loot import new_uid
        from core.models import Item, ItemInstance

        seller = await s.get(Character, seller_id)
        item = (await s.execute(
            __import__("sqlalchemy").select(Item).limit(1))).scalars().first()
        inst = ItemInstance(item_id=item.id, uid=new_uid(),
                            owner_character_id=seller_id)
        s.add(inst)
        await s.flush()
        inv = InventoryItem(character_id=seller_id, item_id=item.id,
                            instance_id=inst.id, quantity=1)
        s.add(inv)
        await s.flush()
        res = await B.list_bid_lot(s, seller, inv, start_bid=100, buyout=800)
        buy_id = res["lot"].id
        await s.commit()

    async with async_session() as s:
        lot = await s.get(AuctionLot, buy_id)
        alice = await s.get(Character, alice_id)
        await B.place_bid(s, alice, lot, 100)
        await s.commit()
        alice_before = total_in_bronze(alice)

    async with async_session() as s:
        lot = await s.get(AuctionLot, buy_id)
        bob = await s.get(Character, bob_id)
        bob_before = total_in_bronze(bob)
        out = await B.buyout(s, bob, lot)
        alice = await s.get(Character, alice_id)
        check(out["ok"], "выкуп прошёл")
        check(total_in_bronze(bob) == bob_before - 800, "с покупателя списано")
        check(total_in_bronze(alice) == alice_before + 100,
              "текущему лидеру вернули резерв: он проиграл, но не платит")
        await s.commit()

    async with async_session() as s:
        lot = await s.get(AuctionLot, buy_id)
        bob = await s.get(Character, bob_id)
        twice = await B.buyout(s, bob, lot)
        check(not twice["ok"], "повторный выкуп невозможен")


def test_module_is_wired():
    """Модуль больше не мёртвый: он импортируется из бота и админки."""
    print("\n— № 59: заглушки больше нет —")
    with open(os.path.join(ROOT, "core", "auction_bid.py"), encoding="utf-8") as fh:
        src = fh.read()
    check("ЗАГЛУШКА" not in src, "docstring больше не объявляет заглушку")
    check("BID_AUCTION_KEY" not in src,
          "мёртвая константа убрана вместе с заглушкой")

    with open(os.path.join(ROOT, "bot", "runner.py"), encoding="utf-8") as fh:
        runner = fh.read()
    check("close_finished" in runner,
          "фоновый цикл бота закрывает истёкшие торги")

    with open(os.path.join(ROOT, "admin", "main.py"), encoding="utf-8") as fh:
        admin = fh.read()
    check("auction_bid" in admin, "админка знает про торги")

    from bot.handlers import routers
    from bot.handlers.auction_bids import router as bids_router

    check(bids_router in routers, "роутер торгов подключён")

    class Probe:
        def __init__(self, data):
            self.data = data

    def has_handler(data):
        probe = Probe(data)
        for handler in bids_router.callback_query.handlers:
            for flt in handler.filters or []:
                try:
                    if flt.callback(probe):
                        return True
                except Exception:
                    continue
        return False

    for cb in ("bids_menu", "bid_lot:1", "bid_place:1:100", "bid_buyout:1",
               "bid_cancel:1", "bid_sell:0", "bid_list:1:100"):
        check(has_handler(cb), f"обработчик {cb} зарегистрирован")
    check(not has_handler("bid_unknown_action"),
          "негативная проверка: чужой колбэк не ловится")

    from bot.keyboards.inline import auction_menu_keyboard

    datas = [b.callback_data for row in auction_menu_keyboard().inline_keyboard
             for b in row]
    check("bids_menu" in datas, "вход в торги есть в меню аукциона")


def main():
    asyncio.run(scenario())
    test_module_is_wired()

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ Торги со ставками работают: резерв, гонка, молоток, выкуп")
    return 0


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="shadowlands-bids-")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp}/test.db"
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        code = main()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(code)
