"""Прогресс героя: ручное распределение очков характеристик,
динамический стартовый баланс фракций и масштабируемая карта.

python3 tests/test_progression.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


# ── очки характеристик ──────────────────────────────────────

def _hero_ns():
    from types import SimpleNamespace
    return SimpleNamespace(
        strength=12, agility=10, intelligence=5, endurance=11, luck=8,
        max_hp=100, current_hp=100, max_mp=50, current_mp=50,
        stat_points=0, allocated_stats="")


def test_statpoints_math():
    from core import statpoints as sp

    print("\n— Очки характеристик —")
    check(set(sp.perks_for_level(l) for l in (2, 3, 4, 6)) == {3},
          "обычные уровни дают 3 очка")
    check(sp.perks_for_level(5) == 5 and sp.perks_for_level(10) == 8
          and sp.perks_for_level(20) == 8,
          f"круглые уровни щедрее ({sp.perks_for_level(5)}, "
          f"{sp.perks_for_level(10)}, {sp.perks_for_level(20)})")

    h = _hero_ns()
    check(not sp.allocate(h, "strength"), "без очков не вложить")
    h.stat_points = 2
    check(sp.allocate(h, "endurance") and h.stat_points == 1,
          "очко вложено, резерв убавился")
    check(h.endurance == 12 and h.max_hp == 110 and h.current_hp == 110,
          f"выносливость даёт +1 и +10 HP ({h.endurance}, {h.max_hp})")
    check(sp.allocate(h, "intelligence")
          and h.max_mp == 55 and h.current_mp == 55,
          "интеллект даёт +1 и +5 MP")
    check(sp.load_allocated(h) == {"strength": 0, "agility": 0,
                                   "intelligence": 1, "endurance": 1,
                                   "luck": 0},
          "аудит вложенных очков ведётся")

    # Базу снять нельзя: снимаем ровно вложенное и упираемся в ноль аудита.
    check(sp.deallocate(h, "strength") is False, "базу снять нельзя")
    old_str = h.strength
    h.stat_points += 1
    sp.allocate(h, "strength")
    sp.deallocate(h, "strength")
    check(h.strength == old_str, "снять вложенное — вернулась база")
    sp.deallocate(h, "endurance")
    check(h.endurance == 11 and h.max_hp == 100 and h.current_hp == 100,
          "снятие выносливости откатывает HP")
    check(not sp.deallocate(h, "endurance"), "повторно снять нельзя")

    # Текущее HP никогда не превышает максимум после снятия очков.
    h2 = _hero_ns()
    h2.stat_points = 3
    sp.allocate(h2, "endurance")
    h2.current_hp = h2.max_hp
    sp.deallocate(h2, "endurance")
    check(h2.current_hp <= h2.max_hp, "current_hp зажат под max_hp")


# ── динамический стартовый баланс фракций ───────────────────

def test_start_bonus_mult():
    from core.factions import start_bonus_mult

    print("\n— Баланс стартового бонуса фракций —")
    empty = {"guard": 0, "scavengers": 0, "cult": 0, "order": 0}
    check(all(start_bonus_mult(empty, k) == 1.0 for k in empty),
          "пустой сервер: каждой фракции ×1.0")
    even = {"guard": 4, "scavengers": 4, "cult": 4, "order": 4}
    check(all(start_bonus_mult(even, k) == 1.0 for k in even),
          "паритет 4/4/4/4: каждой ×1.0")
    skewed = {"guard": 8, "scavengers": 1, "cult": 1, "order": 1}
    small = start_bonus_mult(skewed, "cult")
    big = start_bonus_mult(skewed, "guard")
    check(small > 1.0 and big < 1.0,
          f"малочисленной больше (×{small:.2f} против ×{big:.2f} многолюдной)")
    check(big >= 0.5, "перенаселённой не меньше ×0.5")
    extreme = {"guard": 100, "scavengers": 0, "cult": 0, "order": 0}
    check(start_bonus_mult(extreme, "cult") == 2.0,
          "одинокой фракции — потолок ×2.0")


async def _start_bonus_db_async():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.database import Base
    import importlib
    importlib.import_module("core.models")
    from core import factions as core_factions

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    from core.models import Character, User
    async with sm() as s:
        users = [User(telegram_id=t) for t in (1, 2, 3)]
        s.add_all(users)
        await s.flush()
        # Двое в Страже (новая колонка faction), один — старый герой
        # (только репутация), один — без фракции (создание не завершено).
        s.add_all([
            Character(user_id=users[0].id, name="A", character_class="warrior",
                      faction="guard"),
            Character(user_id=users[1].id, name="B", character_class="warrior",
                      faction="guard"),
            Character(user_id=users[2].id, name="C", character_class="warrior",
                      reputation='{"order": 50}'),
        ])
        await s.commit()

    async with sm() as s:
        pop = await core_factions.faction_population(s)
        check(pop == {"guard": 2, "scavengers": 0, "cult": 0, "order": 1},
              f"население фракций посчитано {pop}")
        small = await core_factions.start_bonus(s, "cult", 100)
        big = await core_factions.start_bonus(s, "guard", 100)
        # 3 героя суммарно → среднее 1.75 против 1 у Культа:
        # ×1.75 → 180🟤 после округления до десятков.
        check(small["bronze"] == 180 and small["mult"] > 1.0,
              f"малочисленная фракция доплачивает ({small})")
        check(big["bronze"] < 100 and big["bronze"] % 10 == 0,
              f"многолюдной урезано ({big})")
    await engine.dispose()


# ── страница выбора фракции с балансом ──────────────────────

def test_faction_page_caption():
    from bot.handlers.start import _faction_page_text, FACTION_CARDS
    from engine.factions import ORDER

    print("\n— Книга выбора фракции влезает в подпись —")
    bonus = {"count": 3, "mult": 1.33, "bronze": 130, "base": 100}
    longest = 0
    for i in range(len(ORDER)):
        text = _faction_page_text(i, bonus=bonus)
        longest = max(longest, len(text))
        check("money" in FACTION_CARDS[ORDER[i]], "у карточки есть база денег")
    check(longest <= 1024, f"каждая страница с балансом влезает (макс {longest})")
    with_bonus = _faction_page_text(0, bonus=bonus)
    check("Героев во фракции" in with_bonus and "130🟤" in with_bonus,
          "динамическая выдача показана на странице")


# ── масштабируемая карта ────────────────────────────────────

def test_map_zoom_render(tmp_dir="data/test_maps"):
    from core import map_renderer as mr
    from types import SimpleNamespace as NS

    print("\n— Карта локации: масштаб и туман войны —")
    check(mr.zoom_radius_for(25, 2) is None, "макс. масштаб — вся локация")
    check(mr.zoom_radius_for(25, 0) < mr.zoom_radius_for(25, 1),
          "приближение сужает окно")
    check(mr.zoom_radius_for(10, 0) >= 2, "окно никогда не меньше 2 клеток")

    grid = 25
    cells = [NS(x=x, y=y, tile_type="grass" if (x + y) % 3 else "forest",
                is_passable=not (x == 0 or y == 0 or x == grid - 1 or y == grid - 1))
             for x in range(grid) for y in range(grid)]
    visited = {(x, y) for x in range(10, 15) for y in range(10, 15)}
    os.makedirs(tmp_dir, exist_ok=True)

    full = mr.render_player_map(cells, visited, 12, 12, grid,
                                f"{tmp_dir}/full.png", zoom_radius=None)
    from PIL import Image
    w, h = Image.open(full).size
    check(w == h and w >= 400, f"полная карта квадратная и крупная ({w})")

    zoomed = mr.render_player_map(
        cells, visited, 12, 12, grid, f"{tmp_dir}/zoom.png",
        zoom_radius=mr.zoom_radius_for(grid, 0))
    radius = mr.zoom_radius_for(grid, 0)
    view = 2 * radius + 1
    w2, _ = Image.open(zoomed).size
    check(w2 == view * (720 // view),
          f"приближение — окно {view}×{view} клеток вокруг героя ({w2}px)")
    check(view < grid, "в приближении помещается меньше клеток, чем на всей карте")

    # Окно у края сетки скользит, а не выходит за границу.
    edge = mr.render_player_map(cells, {(0, 0), (1, 1)}, 0, 0, grid,
                                f"{tmp_dir}/edge.png", zoom_radius=6)
    check(os.path.exists(edge), "карта у края сетки рендерится")
    path = mr.get_player_map_path(7, 3, 1, zoom=1)
    check(path.endswith("7_3_1_z1.png"), f"путь кеша различает масштаб ({path})")


def main():
    test_statpoints_math()
    test_start_bonus_mult()
    print("\n— Население фракций из БД —")
    asyncio.run(_start_bonus_db_async())
    test_faction_page_caption()
    test_map_zoom_render()
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
