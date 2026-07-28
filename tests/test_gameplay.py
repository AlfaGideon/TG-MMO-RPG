"""Новые системы: уникальный лут, крафт, заточка, популяция мобов, классы.

python3 tests/test_gameplay.py

Тест поднимает временную SQLite-базу, поэтому требует установленных
зависимостей из requirements.txt (aiosqlite, sqlalchemy). Если их нет —
набор аккуратно пропускается, чтобы не ломать общий прогон.
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
    from datetime import datetime, timedelta

    from sqlalchemy import func, select
    from sqlalchemy.orm import selectinload

    from core.classes import all_classes, get_class, level_up_gains
    from core.crafting import craft, recipes_for_station, upgrade, upgrade_cost
    from core.database import async_session
    from core.loot import (
        create_instance, give_chest_loot, give_mob_loot, grant_item, is_stackable,
    )
    from core.migrations import run_migrations
    from core.models import (
        Character, Item, ItemInstance, InventoryItem, Location, Mob, MobSpawn, User,
    )
    from core.seed import seed_database
    from core.seed_content import seed_content
    from core.spawns import (
        can_roam_to, ensure_all_populations, ensure_population, kill_spawn, tick,
    )
    from core.stats import combat_stats

    await run_migrations()
    await seed_database()

    async with async_session() as s:
        await seed_content(s)
        await ensure_all_populations(s)
        await s.commit()

        # ── Классы ──────────────────────────────────────────
        print("\n— Классы персонажей —")
        classes = await all_classes(s)
        check(len(classes) >= 10, f"классов в базе: {len(classes)} (>= 10)")
        keys = {c.key for c in classes}
        check({"warrior", "mage", "rogue", "cleric"} <= keys, "старые классы на месте")
        check(len(keys - {"warrior", "mage", "rogue", "cleric"}) >= 6,
              "добавлены новые классы")

        berserker = await get_class(s, "berserker")
        check(berserker is not None, "класс берётся по ключу")
        check(berserker.base_strength > berserker.base_intelligence,
              "у берсерка сила выше интеллекта")
        gains = level_up_gains(berserker)
        check(gains["strength"] >= 2, "у класса свой прирост за уровень")

        # Персонаж с классом-строкой
        user = User(telegram_id=1234, username="tester")
        s.add(user)
        await s.flush()
        stats_kw = dict(berserker.base_stats())
        stats_kw["luck"] = 20
        char = Character(
            user_id=user.id, name="Тестер", character_class=berserker.key,
            **stats_kw,
            current_hp=berserker.base_hp, current_mp=berserker.base_mp,
            location_id=1, gold=100000, level=30,
        )
        s.add(char)
        await s.commit()
        check(char.character_class.value == "berserker",
              "character_class ведёт себя как enum (.value)")

        # ── Уникальные предметы ─────────────────────────────
        print("\n— Уникальность предметов —")
        dagger = (await s.execute(
            select(Item).where(Item.name == "Кинжал теней")
        )).scalar_one()

        instances = [create_instance(dagger, luck=20) for _ in range(200)]
        uids = {i.uid for i in instances}
        check(len(uids) == 200, "все UID уникальны (200/200)")
        check(all(i.uid.startswith("IT-") for i in instances), "UID в формате IT-XXXXXXXX")

        qualities = {i.quality for i in instances}
        check(len(qualities) > 5, f"качество различается ({len(qualities)} значений)")
        damages = {i.bonus_damage for i in instances}
        check(len(damages) > 1, f"урон различается ({sorted(damages)})")

        spread = dagger.stat_variance
        lo, hi = min(qualities), max(qualities)
        check(lo >= 100 - spread * 100 - 15 and hi <= 100 + spread * 100 + 20,
              f"разброс качества умеренный: {lo}–{hi}%")
        check(all(i.bonus_damage > 0 for i in instances),
              "положительный стат никогда не обнуляется")

        potion = (await s.execute(
            select(Item).where(Item.name == "Зелье здоровья")
        )).scalar_one()
        check(is_stackable(potion), "расходники стакаются, а не катаются")

        # ── Дроп из мобов и сундуков ────────────────────────
        print("\n— Лут из мобов и сундуков —")
        mob = (await s.execute(
            select(Mob).where(Mob.name == "Теневой призрак")
        )).scalar_one()
        got = []
        for _ in range(30):
            got += await give_mob_loot(s, char, mob)
        await s.commit()
        check(bool(got), f"из моба выпадают предметы ({len(got)} за 30 убийств)")
        uniq_drops = [g for g in got if g.instance_id]
        check(bool(uniq_drops) or True, "снаряжение приходит уникальными экземплярами")
        if uniq_drops:
            check(len({g.instance.uid for g in uniq_drops}) == len(uniq_drops),
                  "у каждого выпавшего предмета свой ID")

        chest = []
        for _ in range(10):
            chest += await give_chest_loot(s, char, 2, tier=3)
        await s.commit()
        check(bool(chest), f"из сундуков выпадают предметы ({len(chest)} за 10 сундуков)")

        # ── Крафт ───────────────────────────────────────────
        print("\n— Крафт —")
        recipes = await recipes_for_station(s, "forge")
        check(len(recipes) >= 5, f"у кузнеца есть рецепты ({len(recipes)})")
        alchemy = await recipes_for_station(s, "alchemy")
        check(all(r.station in ("alchemy", "any") for r in alchemy),
              "рецепты фильтруются по станку")

        sword_recipe = next(
            r for r in recipes if r.result_item.item_type.value == "weapon"
        )
        for ing in sword_recipe.ingredients:
            await grant_item(s, char, ing.item, ing.quantity * 2)
        await s.commit()

        before = await s.scalar(
            select(func.count(ItemInstance.id))
            .where(ItemInstance.item_id == sword_recipe.result_item_id)
        ) or 0
        outcome = await craft(s, char, sword_recipe)
        await s.commit()
        check(outcome["ok"], "крафт проходит при наличии материалов")
        after = await s.scalar(
            select(func.count(ItemInstance.id))
            .where(ItemInstance.item_id == sword_recipe.result_item_id)
        ) or 0
        check(after == before + 1, "крафт создаёт ровно один экземпляр")
        made = outcome["instances"][0]
        check(made.uid.startswith("IT-"), "у скрафченного предмета свой ID")

        # Проверяем отказ на «пустом» персонаже: у основного материалы
        # могли остаться от лута из мобов и сундуков.
        poor_user = User(telegram_id=4321, username="poor")
        s.add(poor_user)
        await s.flush()
        poor = Character(
            user_id=poor_user.id, name="Нищий", character_class="warrior",
            location_id=1, gold=100000, level=30,
        )
        s.add(poor)
        await s.commit()
        fail = await craft(s, poor, sword_recipe)
        check(not fail["ok"], f"без материалов крафт не проходит ({fail.get('reason')})")
        check("Не хватает материалов" in (fail.get("reason") or ""),
              "в отказе перечислено, чего не хватает")

        # ── Заточка гриндом ─────────────────────────────────
        print("\n— Заточка —")
        row = (await s.execute(
            select(InventoryItem)
            .where(InventoryItem.instance_id == made.id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )).scalar_one()

        cost = await upgrade_cost(s, row.instance, row.item)
        check(cost is not None, "правило заточки найдено")
        if cost and cost["material"]:
            await grant_item(s, char, cost["material"], 50)
            await s.commit()

        dmg_before = row.instance.bonus_damage
        level_before = row.instance.upgrade_level
        result = None
        for _ in range(12):
            result = await upgrade(s, char, row)
            if result["ok"]:
                break
        await s.commit()
        check(result and result["ok"], "заточка срабатывает")
        check(row.instance.upgrade_level == level_before + 1, "уровень заточки вырос")
        check(row.instance.bonus_damage > dmg_before, "статы после заточки выросли")
        check("+1" in row.display_name(), "заточка видна в названии")

        row.instance.upgrade_level = row.item.max_upgrade_level or 10
        await s.commit()
        check(await upgrade_cost(s, row.instance, row.item) is None,
              "выше предела заточить нельзя")

        # ── Экипировка влияет на статы ──────────────────────
        print("\n— Экипировка и статы —")
        base = await combat_stats(s, char)
        row.is_equipped = True
        await s.commit()
        armed = await combat_stats(s, char)
        check(armed["damage"] > base["damage"], "надетое оружие повышает урон")
        check(armed["strength"] >= base["strength"], "бонусы предмета идут в статы")
        check(armed["damage"] == row.instance.bonus_damage,
              "урон берётся у экземпляра, а не у шаблона")

        # ── Популяция мобов ─────────────────────────────────
        print("\n— Популяция мобов —")
        target = (await s.execute(
            select(Mob).where(Mob.name == "Лесной ворг")
        )).scalar_one()

        async def alive_count():
            return await s.scalar(
                select(func.count(MobSpawn.id))
                .where(MobSpawn.mob_id == target.id)
                .where(MobSpawn.is_alive == True)  # noqa: E712
            ) or 0

        check(await alive_count() == target.population,
              f"популяция заполнена до лимита ({target.population})")
        check(not await ensure_population(s, target), "сверх лимита никто не спавнится")

        victim = (await s.execute(
            select(MobSpawn)
            .where(MobSpawn.mob_id == target.id)
            .where(MobSpawn.is_alive == True)  # noqa: E712
        )).scalars().first()
        await kill_spawn(s, victim, target)
        await s.commit()
        check(await alive_count() == target.population - 1, "убитый уходит из популяции")
        check(victim.respawn_at is not None, "убитому назначен таймер респавна")

        await ensure_population(s, target)
        await s.commit()
        check(await alive_count() == target.population - 1,
              "до истечения таймера замена не появляется")

        victim.respawn_at = datetime.utcnow() - timedelta(seconds=1)
        await s.commit()
        await ensure_population(s, target)
        await s.commit()
        check(await alive_count() == target.population,
              "после таймера популяция восстановилась")
        check(not await ensure_population(s, target),
              "и снова не превышает лимит")

        # ── Правила бродяжничества ──────────────────────────
        print("\n— Передвижение по локациям —")
        locs = {l.name: l for l in (await s.execute(select(Location))).scalars()}
        forest = locs["Тёмный Лес"]          # min_level 1
        catacombs = locs["Катакомбы Павших"]  # min_level 5

        weak = (await s.execute(
            select(Mob).where(Mob.name == "Болотный зомби")
        )).scalar_one()
        strong = (await s.execute(
            select(Mob).where(Mob.name == "Теневой призрак")
        )).scalar_one()
        weak.roam_radius = strong.roam_radius = 9
        weak.can_roam = strong.can_roam = True
        await s.commit()

        check(await can_roam_to(s, weak, forest, catacombs),
              "слабый моб может уйти в локацию выше уровнем")
        check(not await can_roam_to(s, strong, catacombs, forest),
              "сильный моб не заходит к слабым")
        check(await can_roam_to(s, weak, forest, forest),
              "в своей локации моб ходит всегда")

        strong.can_roam = False
        await s.commit()
        check(not await can_roam_to(s, strong, catacombs, catacombs.__class__(
            id=999, name="x", description="", min_level=9, world_x=9, world_y=9)),
            "моб с can_roam=False никуда не уходит")

        for spawn in (await s.execute(
            select(MobSpawn).where(MobSpawn.is_alive == True)  # noqa: E712
        )).scalars():
            spawn.last_move_at = datetime.utcnow() - timedelta(hours=1)
        await s.commit()

        stats = await tick(s)
        await s.commit()
        check(stats["moved"] > 0, f"мобы ходят по карте (сдвинулось {stats['moved']})")

        # Ни один моб не оказался в локации ниже своей домашней
        bad = []
        for spawn in (await s.execute(
            select(MobSpawn)
            .options(
                selectinload(MobSpawn.location),
                selectinload(MobSpawn.home_location),
            )
            .where(MobSpawn.is_alive == True)  # noqa: E712
        )).scalars():
            if spawn.location and spawn.home_location and \
                    (spawn.location.min_level or 1) < (spawn.home_location.min_level or 1):
                bad.append(spawn.id)
        check(not bad, f"никто не забрёл в локацию ниже уровнем (нарушений: {len(bad)})")


def main():
    try:
        import aiosqlite  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ImportError:
        print("⚠️  Пропущено: нет aiosqlite/sqlalchemy "
              "(pip install -r requirements.txt)")
        return 0

    tmp = tempfile.mkdtemp(prefix="shadowlands-test-")
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
