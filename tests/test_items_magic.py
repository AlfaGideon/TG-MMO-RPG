"""Значки источника, история, аукцион, реликвии, магия, перекат статов.

python3 tests/test_items_magic.py

Как и test_gameplay.py, поднимает временную SQLite-базу; без установленных
зависимостей набор аккуратно пропускается.
"""
import asyncio
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


async def scenario():
    from collections import Counter
    from datetime import datetime, timedelta

    from sqlalchemy import func, select

    from core import auction, history, magic, statroll
    from core.classes import get_class
    from core.database import async_session
    from core.enums import ItemSource, MagicSchool, source_badge
    from core.loot import (
        active_events, can_drop, create_instance, grant_item, one_of_a_kind_taken,
    )
    from core.migrations import run_migrations
    from core.models import (
        AppSetting, AuctionLot, Cell, Character, InventoryItem, Item, ItemHistory,
        ItemInstance, User, VisitedCell,
    )
    from core.seed import seed_database
    from core.seed_content import seed_content

    await run_migrations()
    await seed_database()

    async with async_session() as s:
        await seed_content(s)
        await s.commit()

        # ── Порядок создания героя ───────────────────────────
        # У стартового замка одна и та же координата [5,5] есть на этажах
        # 0, 1, -1 и -2. Но при подтверждении КЛАССА выбирать среди них
        # вообще не нужно: клетка определяется позже выбранной ФРАКЦИЕЙ.
        print("\n— Класс → статы → фракция → клетка —")
        spawn_rows = (await s.execute(
            select(Cell)
            .where(Cell.location_id == 1)
            .where(Cell.x == 5)
            .where(Cell.y == 5)
        )).scalars().all()
        check(len(spawn_rows) > 1,
              f"в стартовом замке [5,5] есть на нескольких этажах ({len(spawn_rows)})")
        await s.commit()  # освободить read-транзакцию перед сессией хендлера

        from types import SimpleNamespace
        from bot.handlers import start as start_handler

        class FakeCallback:
            data = "confirm_class:warrior"
            from_user = SimpleNamespace(
                id=8999, first_name="Новичок", username="newcomer",
            )

            def __init__(self):
                self.answers = []

            async def answer(self, text=None, **kwargs):
                self.answers.append((text, kwargs))

        shown = {}

        async def capture_screen(_event, text, **kwargs):
            shown["text"] = text
            shown["kwargs"] = kwargs

        s.add(User(telegram_id=8999, first_name="Новичок"))
        await s.commit()

        callback = FakeCallback()
        original_sender = start_handler.send_or_edit_photo
        start_handler.send_or_edit_photo = capture_screen
        try:
            await start_handler.confirm_class(callback)
        finally:
            start_handler.send_or_edit_photo = original_sender

        newcomer_user = (await s.execute(
            select(User).where(User.telegram_id == 8999)
        )).scalar_one_or_none()
        newcomer = None
        if newcomer_user is not None:
            newcomer = (await s.execute(
                select(Character).where(Character.user_id == newcomer_user.id)
            )).scalar_one_or_none()
        check(newcomer is not None, "кнопка «Подтвердить» сохраняет бросок героя")
        check(newcomer is not None and newcomer.location_id is None and newcomer.cell_id is None,
              "до выбора фракции локация и клетка не назначены")
        visited_before = await s.scalar(
            select(func.count(VisitedCell.id)).where(
                VisitedCell.character_id == newcomer.id
            )
        ) if newcomer else -1
        check(visited_before == 0, "до выбора фракции на карте ничего не посещено")
        check("Осталось попыток" in shown.get("text", ""),
              "после подтверждения показан экран переката статов")
        await s.commit()

        # Принятие статов открывает выбор фракции, но всё ещё не помещает
        # персонажа в какую-либо локацию.
        shown.clear()
        callback.data = f"accept_stats:{newcomer.id}"
        start_handler.send_or_edit_photo = capture_screen
        try:
            await start_handler.accept_stats(callback)
        finally:
            start_handler.send_or_edit_photo = original_sender
        await s.refresh(newcomer)
        check(newcomer.stats_locked, "статы приняты и зафиксированы")
        check(newcomer.location_id is None and newcomer.cell_id is None,
              "принятие статов ещё не выбирает клетку")
        check("Выбери свою фракцию" in shown.get("text", ""),
              "после статов показан выбор фракции")
        await s.commit()

        # И только выбор фракции назначает её замок и реальную клетку.
        shown.clear()
        callback.data = f"start_faction:{newcomer.id}:guard"
        start_handler.send_or_edit_photo = capture_screen
        try:
            await start_handler.start_faction_callback(callback)
        finally:
            start_handler.send_or_edit_photo = original_sender
        await s.refresh(newcomer)
        spawn = await s.get(Cell, newcomer.cell_id) if newcomer.cell_id else None
        check(newcomer.location_id is not None and spawn is not None,
              "выбор фракции назначает локацию и клетку")
        check(spawn is not None and spawn.floor == 0,
              "фракционная стартовая клетка находится на этаже 0")
        visited_after = await s.scalar(
            select(func.count(VisitedCell.id)).where(
                VisitedCell.character_id == newcomer.id
            )
        )
        check(visited_after == 1, "первая посещённая клетка записана после выбора фракции")

        cls = await get_class(s, "warrior")

        async def make_char(tid, name, gold=1000, level=20):
            user = User(telegram_id=tid)
            s.add(user)
            await s.flush()
            char = Character(
                user_id=user.id, name=name, character_class=cls.key,
                **cls.base_stats(), current_hp=140, current_mp=30,
                location_id=1, gold=gold, level=level,
            )
            s.add(char)
            await s.flush()
            return char

        seller = await make_char(9001, "Продавец", gold=100)
        buyer = await make_char(9002, "Покупатель", gold=9000)
        await s.commit()

        # ── Значки источника ────────────────────────────────
        print("\n— Значки способа получения —")
        sword = (await s.execute(
            select(Item).where(Item.name == "Ржавый меч")
        )).scalar_one()

        expected = {
            "mob": "⚔️", "chest": "📦", "dungeon": "🕳", "craft": "🔨",
            "shop": "🏪", "quest": "📜", "admin": "🛠",
        }
        for src, badge in expected.items():
            inst = create_instance(sword, source=src)
            check(
                inst.badge() == badge and inst.tagged_uid().startswith(badge),
                f"{src} → {badge} ({inst.tagged_uid()})",
            )

        check(source_badge("mob") != source_badge("craft"),
              "у разных источников разные значки")
        check(len(set(expected.values())) == len(expected),
              "значки не повторяются между источниками")

        # Ресурсов значки не касаются — у них нет экземпляра
        potion = (await s.execute(
            select(Item).where(Item.name == "Зелье здоровья")
        )).scalar_one()
        rows = await grant_item(s, seller, potion, 3, source="chest")
        await s.commit()
        check(rows and rows[0].instance_id is None,
              "расходники стакаются без ID и значка")
        check(rows[0].uid() == "", "у стопки нет ID предмета")

        # ── Летопись предмета ───────────────────────────────
        print("\n— История предмета —")
        dagger = (await s.execute(
            select(Item).where(Item.name == "Кинжал теней")
        )).scalar_one()
        got = await grant_item(
            s, seller, dagger, 1, source="mob", source_detail="Теневой призрак",
        )
        await s.commit()
        inv, inst = got[0], got[0].instance

        hist = await history.load(s, inst.id)
        check(len(hist) == 1, "летопись открывается записью о добыче")
        check(hist[0].event == "looted", f"событие: {hist[0].event}")
        check(hist[0].actor_name == "Продавец", "записан добытчик")
        check(inst.owner_character_id == seller.id, "владелец проставлен")

        # ── Аукцион ─────────────────────────────────────────
        print("\n— Аукцион —")
        hint = auction.suggested_price(inst, dagger)
        low, high = auction.price_bounds(inst, dagger)
        check(low < hint < high, f"оценка {hint}🪙 внутри границ {low}–{high}")

        bad = await auction.list_lot(s, seller, inv, high * 10)
        check(not bad["ok"], "завышенную цену аукцион не принимает")

        res = await auction.list_lot(s, seller, inv, hint)
        await s.commit()
        check(res["ok"], "лот выставлен")
        left = (await s.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == seller.id)
            .where(InventoryItem.instance_id == inst.id)
        )).scalars().all()
        check(not left, "предмет ушёл из сумки на витрину")

        lot = res["lot"]
        own = await auction.buy_lot(s, seller, lot)
        check(not own["ok"], "свой лот купить нельзя")

        poor = await make_char(9003, "Бедняк", gold=0)
        poor.silver = 0
        poor.bronze = 0
        await s.commit()
        no_gold = await auction.buy_lot(s, poor, lot)
        check(not no_gold["ok"], "без золота купить нельзя")

        from engine.currency import total_in_bronze
        seller_gold, buyer_gold = total_in_bronze(seller), total_in_bronze(buyer)
        out = await auction.buy_lot(s, buyer, lot)
        await s.commit()
        check(out["ok"], "покупка прошла")
        check(total_in_bronze(buyer) == buyer_gold - lot.price, "с покупателя списана цена")
        check(total_in_bronze(seller) == seller_gold + out["payout"], "продавец получил выплату")
        check(out["payout"] < lot.price, "комиссия удержана")
        check(lot.status == "sold", "лот помечен проданным")

        moved = (await s.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == buyer.id)
            .where(InventoryItem.instance_id == inst.id)
        )).scalars().all()
        check(len(moved) == 1, "вещь у покупателя")
        check(inst.owner_character_id == buyer.id, "владелец обновлён")
        check(inst.trade_count == 1, "счётчик сделок вырос")
        check(inst.badge() == "🔁", f"значок сменился на аукционный ({inst.tagged_uid()})")

        hist = await history.load(s, inst.id)
        events = [h.event for h in hist]
        check(events == ["looted", "listed", "sold"], f"история полная: {events}")
        names = await history.owners(s, inst.id)
        check(names == ["Продавец", "Покупатель"], f"цепочка владельцев: {names}")
        summary = await history.history_summary(s, inst)
        check("Владельцев: 2" in summary, "сводка считает владельцев")

        # ── Скупщик-NPC ─────────────────────────────────────
        print("\n— Скупщик-NPC —")
        got2 = await grant_item(s, buyer, dagger, 1, source="chest")
        await s.commit()
        inv2 = got2[0]
        quote = await auction.npc_quote(s, inv2)
        market = auction.suggested_price(inv2.instance, dagger)
        check(0 < quote < market, f"скупщик даёт меньше рынка ({quote} < {market})")

        from engine.currency import total_in_bronze
        gold_before = total_in_bronze(buyer)
        npc = await auction.npc_buy(s, buyer, inv2)
        await s.commit()
        check(npc["ok"], "скупщик выкупил вещь")
        check(total_in_bronze(buyer) == gold_before + quote, "деньги пришли сразу")
        npc_lots = [l for l in await auction.active_lots(s) if l.is_npc_lot]
        check(bool(npc_lots), "вещь перевыставлена скупщиком")
        check(npc_lots[0].price > quote, "скупщик перепродаёт с наценкой")

        # ── Возврат просроченных лотов ──────────────────────
        print("\n— Просроченные лоты —")
        got3 = await grant_item(s, seller, dagger, 1, source="mob")
        await s.commit()
        r3 = await auction.list_lot(s, seller, got3[0], 100)
        await s.commit()
        r3["lot"].expires_at = datetime.utcnow() - timedelta(hours=1)
        await s.commit()
        expired = await auction.sweep_expired(s)
        await s.commit()
        check(len(expired) == 1, "просроченный лот найден")
        back = (await s.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == seller.id)
            .where(InventoryItem.instance_id == r3["lot"].instance_id)
        )).scalars().all()
        check(len(back) == 1, "вещь вернулась продавцу")

        # ── Единственные в мире ─────────────────────────────
        print("\n— Реликвии в единственном экземпляре —")
        relics = (await s.execute(
            select(Item).where(Item.is_one_of_a_kind == True)  # noqa: E712
        )).scalars().all()
        check(len(relics) >= 3, f"реликвий заведено: {len(relics)}")

        relic = relics[0]
        check(await can_drop(s, relic), "до выдачи реликвия доступна")
        first = await grant_item(s, buyer, relic, 5, source="mob", source_detail="Босс")
        await s.commit()
        check(len(first) == 1, "сколько ни проси — приходит одна")
        check(first[0].instance.badge() == "🌟", "у реликвии особый значок")
        check(first[0].instance.is_one_of_a_kind, "метка уникальности на экземпляре")
        check(await one_of_a_kind_taken(s, relic), "реликвия числится занятой")
        check(not await can_drop(s, relic), "повторно выпасть не может")

        again = await grant_item(s, seller, relic, 1, source="mob")
        await s.commit()
        check(not again, "повторная выдача ничего не создаёт")
        total = await s.scalar(
            select(func.count(ItemInstance.id)).where(ItemInstance.item_id == relic.id)
        )
        check(total == 1, f"в мире ровно один экземпляр (найдено {total})")

        # ── Праздничные ─────────────────────────────────────
        print("\n— Праздничные трофеи —")
        festive = (await s.execute(
            select(Item).where(Item.is_festive == True)  # noqa: E712
        )).scalars().all()
        check(len(festive) >= 3, f"праздничных вещей: {len(festive)}")

        gift = festive[0]
        check(not await can_drop(s, gift), "вне события трофей не выпадает")
        blocked = await grant_item(s, buyer, gift, 1, source="mob")
        await s.commit()
        check(not blocked, "и не выдаётся напрямую")

        s.add(AppSetting(key="festive_events", value=gift.festive_event))
        await s.commit()
        check(gift.festive_event in await active_events(s), "событие включилось")
        check(await can_drop(s, gift), "в событие трофей доступен")
        given = await grant_item(s, buyer, gift, 1, source="mob")
        await s.commit()
        check(bool(given), "трофей выдан")
        check(given[0].instance.badge() == "🎄", "у праздничного свой значок")
        check(given[0].instance.is_festive, "метка праздника на экземпляре")

        # ── Магический дар ──────────────────────────────────
        print("\n— Предрасположенность к магии —")
        check(len(magic.SCHOOL_KEYS) == 6, f"школ ровно шесть: {magic.SCHOOL_KEYS}")
        check(all(magic.school_icon(k) and magic.school_name(k)
                  for k in magic.SCHOOL_KEYS),
              "у каждой школы есть значок и название")

        mage = await get_class(s, "mage")
        warrior = await get_class(s, "warrior")

        mage_rolls = [magic.roll_affinities(mage) for _ in range(600)]
        war_rolls = [magic.roll_affinities(warrior) for _ in range(600)]
        check(all(len(r) <= 2 for r in mage_rolls + war_rolls),
              "больше двух школ не выпадает никогда")

        mage_none = sum(1 for r in mage_rolls if not r)
        war_none = sum(1 for r in war_rolls if not r)
        check(war_none > mage_none,
              f"воин чаще без дара ({war_none} против {mage_none} у мага)")
        check(any(len(r) == 2 for r in mage_rolls), "у мага бывает две школы")
        check(any(len(r) == 0 for r in war_rolls), "у воина бывает пустой дар")

        necro = await get_class(s, "necromancer")
        schools = Counter()
        for _ in range(600):
            for school, _grade in magic.roll_affinities(necro):
                schools[school] += 1
        top = schools.most_common(1)[0][0]
        check(top == MagicSchool.SHADOW.value,
              f"некроманту чаще всего выпадает тьма (выпало: {top})")

        pairs = [(MagicSchool.FIRE.value, "strong")]
        await magic.set_affinities(s, buyer, pairs)
        await s.commit()
        rows = await magic.get_affinities(s, buyer.id)
        check(len(rows) == 1 and rows[0].school == "fire", "дар сохраняется")
        check(magic.affinity_power(rows, "fire") > 1.0, "сильный дар даёт множитель > 1")
        check(magic.affinity_power(rows, "frost") == 0.0, "чужая школа не работает")
        check(magic.spell_bonus(rows, 20) > 0, "дар прибавляет к магическому урону")
        check(magic.spell_bonus([], 20) == 0, "без дара прибавки нет")

        # Больше двух школ не сохранится
        await magic.set_affinities(s, buyer, [
            ("fire", "weak"), ("frost", "weak"), ("storm", "weak"),
        ])
        await s.commit()
        rows = await magic.get_affinities(s, buyer.id)
        check(len(rows) == 2, f"в базе не больше двух школ (сохранено {len(rows)})")

        # ── Перекат стартовых статов ────────────────────────
        print("\n— Перекат стартовых статов —")
        base = mage.base_stats()
        ratios, qualities = [], []
        for _ in range(3000):
            rolled = statroll.roll_stats(base)
            qualities.append(statroll.roll_quality(base, rolled))
            for key, value in rolled.items():
                if base.get(key):
                    ratios.append(value / base[key])

        check(min(ratios) >= 0.90 - 1e-9,
              f"ни один стат не ниже −10 % (минимум {min(ratios) * 100:.1f} %)")
        check(max(ratios) <= 1.20 + 1e-9,
              f"ни один стат не выше +20 % (максимум {max(ratios) * 100:.1f} %)")
        check(len(set(qualities)) > 10, "броски действительно разные")
        check(90 <= min(qualities) and max(qualities) <= 125,
              f"качество броска в разумных пределах {min(qualities)}–{max(qualities)}")

        check(statroll.DEFAULT_REROLLS == 10, "по умолчанию 10 попыток переката")
        check(statroll.roll_verdict(118) != statroll.roll_verdict(93),
              "хороший и слабый броски описаны по-разному")

        fresh = await make_char(9004, "Новичок")
        fresh.rerolls_left = statroll.DEFAULT_REROLLS
        fresh.stats_locked = False
        rolled = statroll.roll_stats(base)
        statroll.apply_stats(fresh, rolled)
        await s.commit()
        check(fresh.current_hp == fresh.max_hp, "после броска HP полное")
        check(fresh.max_hp == rolled["max_hp"], "статы записались в персонажа")

        # Статы у героев различаются — в этом весь смысл
        variants = set()
        for _ in range(50):
            variants.add(tuple(sorted(statroll.roll_stats(base).items())))
        check(len(variants) > 40, f"броски уникальны ({len(variants)} из 50)")


def main():
    try:
        import aiosqlite  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ImportError:
        print("⚠️  Пропущено: нет aiosqlite/sqlalchemy "
              "(pip install -r requirements.txt)")
        return 0

    tmp = tempfile.mkdtemp(prefix="shadowlands-items-")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp}/test.db"
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        asyncio.run(scenario())
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
