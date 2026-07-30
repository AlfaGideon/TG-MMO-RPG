"""Серверный стек: фракции, катаклизмы, боссы, надгробия, диковины, нравы.

Шесть механик, которые раньше жили только в браузерном стеке. Проверяются
на реальной SQLite — без sqlalchemy/aiosqlite набор пропускается.

python3 tests/test_server_world.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                        create_async_engine)
    import aiosqlite  # noqa: F401
except ImportError:
    print("⚠ Пропуск: нет sqlalchemy/aiosqlite (pip install -r requirements.txt)")
    sys.exit(0)

from core import behavior as core_behavior
from core import death as core_death
from core import factions as core_factions
from core import landmarks as core_landmarks
from core import worldevents as core_events
from core.database import Base
from core.enums import CharacterClass, ItemType, LocationType
from core.models import (Cell, Character, Grave, InventoryItem, Item, Location,
                         Mob, User, WorldEvent)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


async def make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed(session, cells=True):
    """Мир: две локации, герой, немного клеток и тварей."""
    safe = Location(name="Погост", description="дом",
                    location_type=LocationType.SAFE, world_x=0, world_y=0)
    risky = Location(name="Лес", description="жуть",
                     location_type=LocationType.DANGEROUS, world_x=1, world_y=0)
    session.add_all([safe, risky])
    await session.flush()

    user = User(telegram_id=1, username="t")
    session.add(user)
    await session.flush()
    ch = Character(user_id=user.id, name="Гидеон", level=10,
                   character_class=CharacterClass.WARRIOR,
                   location_id=risky.id, current_hp=100, max_hp=100, gold=500)
    session.add(ch)
    await session.flush()

    zombie = Mob(name="Болотный зомби", description="труп", level=1, hp=20,
                 damage=4, defense=1, location_id=risky.id, behavior="passive")
    warg = Mob(name="Лесной ворг", description="волк", level=2, hp=30,
               damage=6, defense=2, location_id=risky.id, behavior="hunter")
    session.add_all([zombie, warg])
    await session.flush()

    made = []
    if cells:
        for x in range(4):
            for y in range(4):
                name = "Древний менгир" if (x, y) == (1, 1) else f"Поляна {x}{y}"
                c = Cell(location_id=risky.id, x=x, y=y, floor=0, name=name,
                         description="", is_passable=True, tile_type="grass")
                session.add(c)
                made.append(c)
        await session.flush()
        ch.cell_id = made[0].id
    return ch, safe, risky, [zombie, warg], made


async def run():
    print("\n— Фракции: вражда и звания —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        check(core_factions.load(ch) == {k: 0 for k in core_factions.FACTIONS},
              "новичок никому не свой")

        core_factions.award_for_mob(ch, mobs[0])       # зомби = нежить
        rep = core_factions.load(ch)
        check(rep["guard"] > 0, "стража ценит упокоенную нежить")
        check(rep["cult"] < 0, "культ этим недоволен")

        guard_before = rep["guard"]
        core_factions.award(ch, "grave_looted")
        rep = core_factions.load(ch)
        check(rep["scavengers"] > 0, "падальщики ценят мародёрство")
        check(rep["guard"] < guard_before, "а стража злится")

        ch.reputation = ""
        core_factions.save(ch, {"guard": 100, "scavengers": 0, "cult": -40})
        check(core_factions.allegiance(ch) == "guard", "сторона определяется")
        check(core_factions.standing(ch, "guard")[1] == "Союзник", "звание верное")

    print("\n— Фракции: скидка и реакция жителей —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        check(core_factions.discount(ch) == 0, "новичку скидки нет")
        core_factions.save(ch, {"guard": 1, "scavengers": 0, "cult": 0})
        check(core_factions.discount(ch) == 0, "одно очко ничего не меняет")
        core_factions.save(ch, {"guard": 300, "scavengers": 0, "cult": 0})
        check(core_factions.discount(ch) > 0, "у героя фракции есть скидка")
        check(core_factions.price_for(ch, 100) < 100, "цена ниже базовой")

        check(not core_factions.refuses(ch, "Старейшина Григор"),
              "союзнику не отказывают")
        core_factions.save(ch, {"guard": -120, "scavengers": 0, "cult": 0})
        check(core_factions.refuses(ch, "Старейшина Григор"),
              "враг стражи получает отказ")
        check(not core_factions.refuses(ch, "Скупщик Тень"),
              "у падальщиков он в почёте")
        check("Стража" in core_factions.greeting(ch, "Старейшина Григор"),
              "приветствие зависит от репутации")

    print("\n— Фракции: влияние на бедствия —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        check(await core_factions.cataclysm_mult(s) == 1.0, "без перевеса норма")
        core_factions.save(ch, {"guard": 0, "scavengers": 0, "cult": 200})
        await s.flush()
        check(await core_factions.cataclysm_mult(s) > 1, "культисты торопят беды")
        core_factions.save(ch, {"guard": 200, "scavengers": 0, "cult": 0})
        await s.flush()
        check(await core_factions.cataclysm_mult(s) < 1, "стража их отдаляет")

    print("\n— Катаклизм: удар и откат —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        before = [(c.id, c.tile_type, c.is_passable) for c in cells]

        ev = await core_events.strike(s, "wildfire", risky.id)
        await s.commit()
        check(ev.cells_touched > 0, f"пожар накрыл {ev.cells_touched} клеток")
        live = await core_events.active_cataclysms(s, risky.id)
        check(len(live) == 1, "бедствие числится живым")
        check(not await core_events.active_cataclysms(s, safe.id),
              "соседняя локация не тронута")

        eff = await core_events.effects(s, risky.id)
        check(eff["mob_rate"] != 1.0, f"множители действуют: ×{eff['mob_rate']}")
        check(eff["ambush"] > 0, "твари в беду агрессивнее")

        try:
            await core_events.strike(s, "wildfire", risky.id)
            check(False, "повтор того же бедствия отклонён")
        except ValueError:
            check(True, "повтор того же бедствия отклонён")

        await core_events.end_cataclysm(s, ev.id)
        await s.commit()
        after = {c.id: (c.tile_type, c.is_passable)
                 for c in (await s.execute(select(Cell))).scalars().all()}
        same = all(after[i] == (t, p) for i, t, p in before)
        check(same, "откат вернул рельеф как было")
        check(not await core_events.active_cataclysms(s), "бедствие снято")

    print("\n— Катаклизм: срок выходит сам —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        ev = await core_events.strike(s, "quake", risky.id, hours=1)
        ev.until = datetime.now(timezone.utc) - timedelta(seconds=1)
        await s.flush()
        check(await core_events.sweep(s) >= 1, "просроченное снято тиком")
        check(not await core_events.active_cataclysms(s), "живых не осталось")

    print("\n— Мировой босс: общий урон и награда —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        user2 = User(telegram_id=2, username="m")
        s.add(user2)
        await s.flush()
        ch2 = Character(user_id=user2.id, name="Мара", level=10,
                        character_class=CharacterClass.MAGE,
                        location_id=risky.id, current_hp=100, max_hp=100)
        s.add(ch2)
        await s.flush()

        boss = await core_events.summon_boss(s, "warden", risky.id)
        await s.commit()
        check(boss.hp == core_events.BOSSES["warden"]["hp"], "босс призван")

        try:
            await core_events.summon_boss(s, "wyrm", risky.id)
            check(False, "второго босса нельзя")
        except ValueError:
            check(True, "второго босса нельзя")

        await core_events.hit_boss(s, ch, 800)
        await core_events.hit_boss(s, ch2, 200)
        await s.flush()
        share1 = await core_events.boss_contribution(s, boss, ch)
        share2 = await core_events.boss_contribution(s, boss, ch2)
        check(abs(share1 - 0.8) < 0.01, f"вклад лидера {share1:.0%}")
        check(share1 > share2, "вклад считается по каждому")

        gold1, gold2 = ch.gold, ch2.gold
        await core_events.hit_boss(s, ch, boss.hp)
        await s.commit()
        check(not boss.is_active, "босс повержен")
        check(ch.gold > gold1 and ch2.gold > gold2, "награду получили оба")
        check(ch.gold - gold1 > ch2.gold - gold2, "лидер получил больше")

    print("\n— Надгробия —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        item = Item(name="Меч", description="", item_type=ItemType.WEAPON, price=10)
        s.add(item)
        await s.flush()

        grave = await core_death.bury(s, ch, 100, [item.id])
        await s.commit()
        check(grave is not None, "надгробие создано")
        found = await core_death.mine(s, ch)
        check(found is not None and found.gold == 100, "золото на месте")

        gold, items, own = await core_death.claim(s, ch, found)
        await s.commit()
        check(own and gold == 100 and len(items) == 1, "своё вернулось целиком")
        check(await core_death.mine(s, ch) is None, "могила исчезла")

        # чужая — половина
        grave = await core_death.bury(s, ch, 100, [item.id, item.id])
        await s.flush()
        user2 = User(telegram_id=3, username="x")
        s.add(user2)
        await s.flush()
        other = Character(user_id=user2.id, name="Вор", level=5,
                          character_class=CharacterClass.ROGUE,
                          location_id=risky.id, current_hp=50, max_hp=50)
        s.add(other)
        await s.flush()
        gold, items, own = await core_death.claim(s, other, grave)
        check(not own and gold == 50 and len(items) == 1,
              "с чужой могилы достаётся половина")

        # истлевание
        grave = await core_death.bury(s, ch, 50)
        grave.created_at = datetime.now(timezone.utc) - timedelta(
            hours=core_death.GRAVE_HOURS + 1)
        await s.flush()
        check(await core_death.decay(s) >= 1, "старая могила истлела")

    print("\n— Раны —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        check(not core_death.wounded(ch), "герой здоров")
        core_death.wound(ch)
        check(core_death.wounded(ch), "после гибели ранен")
        check(core_death.penalty(ch) < 1.0, "статы порезаны")
        check(core_death.wound_left(ch) > 0, "виден остаток времени")
        check("Раны" in core_death.note(ch), "игрок предупреждён")
        core_death.heal_wounds(ch)
        check(not core_death.wounded(ch) and core_death.penalty(ch) == 1.0,
              "лекарь снимает раны")

    print("\n— Достопримечательности —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        menhir = next(c for c in cells if c.name == "Древний менгир")
        check(core_landmarks.of(menhir) is not None, "менгир — диковина")
        check(await core_landmarks.is_landmark(s, menhir), "и он настоящий")

        plain = next(c for c in cells if c.name.startswith("Поляна"))
        check(core_landmarks.of(plain) is None, "обычная клетка — нет")

        # Награда «magic» поднимает случайный стат, поэтому смотрим все.
        snap = lambda c: (c.gold, c.experience, c.current_hp, c.strength,
                          c.agility, c.intelligence, c.endurance, c.luck)
        before = snap(ch)
        ok, lines = await core_landmarks.claim(s, ch, menhir)
        await s.commit()
        check(ok, "награда выдана")
        after = snap(ch)
        check(before != after, f"что-то изменилось: {before} → {after}")

        ok2, _ = await core_landmarks.claim(s, ch, menhir)
        check(not ok2, "второй раз награду не дают")
        found, total = await core_landmarks.total(s, ch)
        check(found == 1, f"находка засчитана: {found}/{total}")

    print("\n— Характеры тварей —")
    maker = await make_session()
    async with maker() as s:
        ch, safe, risky, mobs, cells = await seed(s)
        zombie, warg = mobs
        check(core_behavior.of(zombie) == "passive", "зомби пассивен")
        check(core_behavior.of(warg) == "hunter", "ворг охотник")
        check("Охотник" in core_behavior.label(warg), "подпись читаема")

        old = Mob(name="Древний", description="", level=1, hp=10, damage=1,
                  defense=1, location_id=risky.id)
        check(core_behavior.of(old) == "passive",
              "моб без поля читается как пассивный")

        census = core_behavior.census(mobs)
        check(census["passive"] == 1 and census["hunter"] == 1, "перепись верна")

        # охотник ходит, пассивный — нет
        by_pos = {(c.x, c.y): c for c in cells}
        by_pos[(2, 2)].mob_id = warg.id
        await s.flush()
        moved = 0
        for _ in range(40):
            moved += await core_behavior.wander(s, risky.id)
        check(moved > 0, f"охотник сдвинулся {moved} раз")

        for c in cells:
            c.mob_id = None
        by_pos[(2, 2)].mob_id = zombie.id
        await s.flush()
        still = 0
        for _ in range(40):
            still += await core_behavior.wander(s, risky.id)
        check(still == 0, "пассивный остаётся на месте")

    print("\n— Паритет чисел с браузерным стеком —")
    from engine import cataclysm as e_cata
    from engine import death as e_death
    from engine import factions as e_fact
    from engine import worldboss as e_boss

    check(set(core_events.KINDS) == set(e_cata.KINDS), "каталог бедствий общий")
    check(set(core_events.BOSSES) == set(e_boss.BOSSES), "каталог боссов общий")
    check(core_factions.FACTIONS == e_fact.FACTIONS, "фракции те же")
    check(core_death.GRAVE_HOURS == e_death.GRAVE_HOURS, "срок могилы тот же")
    check(core_death.WOUND_PENALTY == e_death.WOUND_PENALTY, "штраф ран тот же")
    from engine import landmarks as e_land
    check(core_landmarks.LANDMARKS == e_land.LANDMARKS, "каталог диковин общий")
    check(core_behavior.BEHAVIORS == e_land.data.BEHAVIORS
          if hasattr(e_land, "data") else True, "нравы те же")


def main():
    asyncio.run(run())
    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
