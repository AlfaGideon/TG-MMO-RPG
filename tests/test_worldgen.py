"""Проверка ядра мира (core/worldgen, core/worldops): python3 tests/test_worldgen.py

In-memory SQLite: генерация, связность, швы между локациями, лестницы,
коллизии координат, resize, диагностика и безопасное удаление.
"""
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    import aiosqlite  # noqa: F401
except ImportError:
    print("⚠ Пропуск: нет sqlalchemy/aiosqlite (pip install -r requirements.txt)")
    sys.exit(0)

from core import worldgen as W, worldops as WO
from core.database import Base
from core.enums import LocationType
from core.models import Location, Cell, Character, User, Mob, MobSpawn, Quest, VisitedCell
from core.seed import CELL_STORIES

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


async def make_loc(session, name, wx, wy, grid_size=10, floors=1, ltype=LocationType.DANGEROUS, min_level=1):
    loc = Location(name=name, description="тест", location_type=ltype,
                   min_level=min_level, grid_size=grid_size, floors_count=floors,
                   world_x=wx, world_y=wy)
    session.add(loc)
    await session.flush()
    await W.build_cells(session, loc, CELL_STORIES, rng=random.Random(hash(name) % 9999))
    return loc


async def passable_path(session, loc, x1, y1, x2, y2, floor=0):
    """BFS: есть ли путь по проходимым клеткам (переходы игнорируем)."""
    from collections import deque
    result = await session.execute(
        select(Cell)
        .where(Cell.location_id == loc.id).where(Cell.floor == floor))
    by_pos = {(c.x, c.y): c for c in result.scalars().all()}
    seen, q = {(x1, y1)}, deque([(x1, y1)])
    while q:
        x, y = q.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n = (x + dx, y + dy)
            c = by_pos.get(n)
            if c and c.is_passable and n not in seen:
                seen.add(n)
                q.append(n)
    return (x2, y2) in seen


async def main():
    random.seed(7)
    Session = await make_session()

    print("\n— Генерация и связность —")
    async with Session() as s:
        a = await make_loc(s, "Деревня", 0, 0, ltype=LocationType.SAFE)
        b = await make_loc(s, "Лес", 1, 0)
        cells = (await s.execute(
            select(Cell).where(Cell.location_id == a.id))).scalars().all()
        check(len(cells) == 100, f"100 клеток в локации 10×10 ({len(cells)})")
        cx, cy = W.center_of(10)
        center = next(c for c in cells if c.x == cx and c.y == cy)
        check(center.is_passable, "центр (спавн) проходим")
        # каждая проходимая клетка должна быть досягаема из центра
        check(await passable_path(s, a, cx, cy,
                                  *(max(((c.x, c.y) for c in cells if c.is_passable),
                                        key=lambda p: abs(p[0] - cx) + abs(p[1] - cy)))),
              "все проходимые клетки досягаемы из центра")
        await s.commit()

    print("\n— Автосвязка соседей —")
    async with Session() as s:
        a = (await s.execute(select(Location).where(Location.name == "Деревня"))).scalar_one()
        b = (await s.execute(select(Location).where(Location.name == "Лес"))).scalar_one()
        report = await W.autolink(s, a)
        await s.commit()
        check(any("восток" in r for r in report), f"отчёт автосвязки: {report}")
        # Шов — ОДНА дверь в центре границы (mid), а не стена из дверей
        # по всему краю: ожидания ниже привязаны к середине.
        mid = 10 // 2
        seam_a = await W.cell_at(s, a.id, mid, 9)
        seam_b = await W.cell_at(s, b.id, mid, 0)
        check(seam_a.target_location_id == b.id and seam_a.target_x == mid
              and seam_a.target_y == 1,
              "шов A→B: граница ведёт в зеркальную клетку")
        check(seam_b.target_location_id == a.id and seam_b.target_x == mid
              and seam_b.target_y == 8,
              "шов B→A: обратный переход симметричен")
        check(await passable_path(s, a, *W.center_of(10), mid, 9),
              "от центра A прорублена дорога до ворот")
        check(await passable_path(s, b, *W.center_of(10), mid, 0),
              "от центра B прорублена дорога до ворот")

    print("\n— Лестницы двусторонние —")
    async with Session() as s:
        t = await make_loc(s, "Шахта", 2, 0, floors=3)
        await s.commit()
        cx, cy = W.center_of(10)
        up0 = await W.cell_at(s, t.id, cx, cy, 0)        # узел UP на этаже 0
        up1 = await W.cell_at(s, t.id, cx, cy, 1)        # узел UP на этаже 1
        down1 = await W.cell_at(s, t.id, cx + 1, cy, 1)  # узел DOWN на этаже 1
        down2 = await W.cell_at(s, t.id, cx + 1, cy, 2)  # узел DOWN на этаже 2
        check(up0.target_floor == 1 and up0.target_location_id == t.id, "лестница 0→1")
        check(up1.target_floor == 2, "лестница 1→2")
        check(down1.target_floor == 0 and down1.target_location_id == t.id,
              "лестница 1→0 (обратная!)")
        check(down2.target_floor == 1, "лестница 2→1 (с верхнего этажа есть спуск)")

    print("\n— Коллизии координат: обмен местами —")
    async with Session() as s:
        a = (await s.execute(select(Location).where(Location.name == "Деревня"))).scalar_one()
        b = (await s.execute(select(Location).where(Location.name == "Лес"))).scalar_one()
        ok, msg = await WO.move_location(s, a, 1, 0)  # клетка занята лесом
        await s.commit()
        check(ok and "обмен" in msg.lower(), f"обмен при коллизии: {msg}")
        check((a.world_x, a.world_y) == (1, 0) and (b.world_x, b.world_y) == (0, 0),
              "локации поменялись местами")
        pairs = await W.relink_all(s)
        await s.commit()
        # после обмена: Лес(0,0)↔Деревня(1,0) и Деревня(1,0)↔Шахта(2,0)
        check(pairs == 2, f"после обмена пересобрано 2 шва ({pairs})")
        seam = await W.cell_at(s, b.id, 10 // 2, 9)
        check(seam.target_location_id == a.id, "шов теперь от B (запад) к A (восток)")

    print("\n— Resize: расширение и обрезка —")
    async with Session() as s:
        g = await make_loc(s, "Поле", 5, 5)
        await s.commit()
        ok, msg = await WO.resize(s, g, new_size=12)
        await s.commit()
        cnt = await s.scalar(select(func.count(Cell.id))
                             .where(Cell.location_id == g.id))
        check(ok and cnt == 144, f"расширение до 12×12: {cnt} клеток, {msg}")
        ok, msg = await WO.resize(s, g, new_size=8)
        await s.commit()
        cnt = await s.scalar(select(func.count(Cell.id))
                             .where(Cell.location_id == g.id))
        check(ok and cnt == 64, f"обрезка до 8×8: {cnt} клеток")
        check(g.grid_size == 8, "grid_size обновлён в локации")

    print("\n— Диагностика и починка —")
    async with Session() as s:
        d = await make_loc(s, "Руины", 6, 5)
        # испортим локацию: стена в центре + висячий переход
        c = await W.cell_at(s, d.id, *W.center_of(10))
        c.is_passable = False
        edge = await W.cell_at(s, d.id, 1, 9)
        edge.target_location_id = d.id
        edge.target_x, edge.target_y, edge.target_floor = 9, 9, 0  # в стену
        await s.flush()
        issues = await WO.validate(s, d)
        kinds = " ".join(msg for lvl, msg in issues)
        check(any(lvl == "err" for lvl, _ in issues), f"диагностика видит ошибки ({len(issues)} шт.)")
        check("лестница" in kinds or "стену" in kinds, "висячий переход в стену замечен")
        report = await WO.autofix(s, d)
        await s.commit()
        c2 = await W.cell_at(s, d.id, *W.center_of(10))
        check(c2.is_passable, "починка вернула проходимость центру")
        check(any("ворота" in r or "↔" in r for r in report), f"отчёт починки: {report[:2]}")

    print("\n— Безопасное удаление —")
    async with Session() as s:
        victim = await make_loc(s, "Жертва", 8, 8)
        other = await make_loc(s, "Приют", 9, 8, ltype=LocationType.SAFE)
        await W.link_pair(s, victim, other, "e")
        # население: игрок, моб, спавн, квест, визиты
        user = User(telegram_id=4242, username="t")
        s.add(user)
        await s.flush()
        spawn = await WO.spawn_cell_of(s, victim)
        ch = Character(user_id=user.id, name="Подопытный", character_class="warrior",
                       location_id=victim.id, cell_id=spawn.id)
        s.add(ch)
        mob = Mob(name="Тестовый жук", description="ж", level=1, hp=10, damage=1,
                  defense=0, gold_reward=1, exp_reward=1, location_id=victim.id)
        s.add(mob)
        await s.flush()
        s.add(MobSpawn(mob_id=mob.id, home_location_id=victim.id,
                       location_id=victim.id, x=2, y=2, current_hp=10))
        s.add(Quest(name="Квест-сирота", description="д", location_id=victim.id))
        s.add(VisitedCell(character_id=ch.id, location_id=victim.id, x=1, y=1))
        await s.flush()

        info = await WO.deps(s, victim)
        check(len(info["players"]) == 1 and len(info["mobs"]) == 1
              and info["spawns"] == 1 and len(info["quests"]) == 1 and info["inbound"] > 0,
              f"отчёт о зависимостях полный: { {k: (len(v) if isinstance(v, list) else v) for k, v in info.items()} }")

        ok, report = await WO.safe_delete(s, victim)
        await s.commit()
        check(ok, "удаление прошло")
        await s.refresh(ch)
        evac = await s.get(Location, ch.location_id)
        check(evac is not None and evac.id != victim.id
              and evac.location_type == LocationType.SAFE,
              f"игрок эвакуирован в безопасную локацию («{evac.name if evac else '?'}»)")
        q = (await s.execute(select(Quest))).scalar_one()
        check(q.location_id is None, "квест отвязан")
        inbound = await s.scalar(
            select(func.count(Cell.id))
            .where(Cell.target_location_id == victim.id))
        check(inbound == 0, "чужие переходы к удалённой локации закрыты")
        left = await s.scalar(select(func.count(Location.id))
                              .where(Location.id == victim.id))
        check(left == 0, "локация удалена из БД")

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
