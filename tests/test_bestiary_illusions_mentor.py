"""Бестиарий, иллюзорные стены и бонус наставника — точки входа.

Запуск: python3 -m pytest -q tests/test_bestiary_illusions_mentor.py

Что закрывают эти проверки (всё найдено аудитом кода):
  • `core/bestiary.record_kill` и `get_mob_slayer_bonus` не вызывались
    нигде — атлас монстров не заполнялся, бонус охотника не работал;
  • `Cell.is_illusory_wall` **никто никогда не выставлял**, поэтому
    `core/illusions.reveal_illusory_wall` был недостижим: иллюзорных стен
    в мире не существовало;
  • `core/mentorship.get_mentorship_bonuses` возвращал +25 % опыта, но
    прибавка нигде не применялась, а `reward_mentor_for_progress` не
    вызывался при победах ученика.
"""
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(103)

from core.database import async_session
from core.models import Cell, Character, Location, User


def _rand_tg():
    return unique_id()


class _FakeCallback:
    def __init__(self, data):
        self.data = data


def _has_handler(router, callback_data: str) -> bool:
    probe = _FakeCallback(callback_data)
    for handler in router.callback_query.handlers:
        for flt in handler.filters or []:
            try:
                if flt.callback(probe):
                    return True
            except Exception:
                continue
    return False


# ── кнопки и обработчики ────────────────────────────────────

def test_bestiary_button_and_handler():
    from bot.keyboards.inline import main_menu_keyboard
    from bot.handlers.character import router as character_router

    data = [b.callback_data for row in
            main_menu_keyboard(has_character=True).inline_keyboard for b in row]
    assert "bestiary_menu" in data
    assert _has_handler(character_router, "bestiary_menu")


def test_reveal_wall_button_appears_only_near_illusion():
    """Кнопка «Простучать» появляется только при иллюзии по соседству."""
    from bot.keyboards.inline import inspect_keyboard
    from bot.handlers.location import router as location_router

    plain = inspect_keyboard(has_mob=False, has_npc=False, has_chest=False)
    assert not any(b.callback_data.startswith("reveal_wall:")
                   for row in plain.inline_keyboard for b in row)

    near = inspect_keyboard(has_mob=False, has_npc=False, has_chest=False,
                            illusory_dirs=[("n", "⬆️")])
    assert "reveal_wall:n" in [b.callback_data for row in near.inline_keyboard
                               for b in row]
    assert _has_handler(location_router, "reveal_wall:n")
    assert not _has_handler(location_router, "reveal_wall_выдумка")


# ── бестиарий ───────────────────────────────────────────────

def test_bestiary_records_kills_and_caps_bonus():
    """Записи копятся, бонус растёт по 1 % за 10 побед и упирается в 15 %."""
    from core import bestiary as core_bestiary
    from core.models import Character as Ch

    char = Ch(name="Hunter", character_class="warrior", level=5)
    assert core_bestiary.get_bestiary(char) == {}
    assert core_bestiary.get_mob_slayer_bonus(char, "Ворг") == 1.0

    for _ in range(10):
        core_bestiary.record_kill(char, "Ворг")
    assert core_bestiary.get_bestiary(char)["Ворг"] == 10
    assert core_bestiary.get_mob_slayer_bonus(char, "Ворг") == pytest.approx(1.01)

    # Другой вид считается отдельно.
    core_bestiary.record_kill(char, "Скелет")
    assert core_bestiary.get_mob_slayer_bonus(char, "Скелет") == 1.0

    for _ in range(2000):                      # заведомо выше потолка
        core_bestiary.record_kill(char, "Ворг")
    assert core_bestiary.get_mob_slayer_bonus(char, "Ворг") == pytest.approx(1.15)

    assert "Ворг" in core_bestiary.bestiary_card_text(char)


def test_bestiary_survives_broken_json():
    """Битое поле в БД не роняет экран — бестиарий читается как пустой."""
    from core import bestiary as core_bestiary
    from core.models import Character as Ch

    char = Ch(name="Broken", character_class="mage", level=2)
    char.bestiary_kills_json = "{не json"
    assert core_bestiary.get_bestiary(char) == {}
    assert core_bestiary.get_mob_slayer_bonus(char, "Кто угодно") == 1.0


# ── иллюзорные стены ────────────────────────────────────────

def test_worldgen_marks_illusory_walls():
    """Разметка помечает только внутренние стены и не ломает связность."""
    from types import SimpleNamespace

    from core import worldgen as W

    size = 10
    cells = []
    for x in range(size):
        for y in range(size):
            border = x in (0, size - 1) or y in (0, size - 1)
            inner_wall = (x + y) % 3 == 0 and not border
            wall = border or inner_wall
            cells.append(SimpleNamespace(
                x=x, y=y, is_passable=not wall,
                tile_type="wall" if wall else "grass",
                is_illusory_wall=False))

    rng = random.Random(7)
    # Форсируем разметку: со штатным шансом 2 % набор был бы флаки.
    marked = W.mark_illusory_walls(cells, size, rng=SimpleNamespace(
        shuffle=rng.shuffle, random=lambda: 0.0))

    assert marked, "ни одна стена не помечена"
    assert len(marked) <= W.MAX_ILLUSORY_PER_FLOOR
    for cell in marked:
        assert cell.is_illusory_wall is True
        assert cell.is_passable is False, "иллюзия остаётся стеной до вскрытия"
        assert 0 < cell.x < size - 1 and 0 < cell.y < size - 1, "помечена граница"

    # При нулевом шансе не помечается ничего.
    fresh = [SimpleNamespace(x=2, y=2, is_passable=False, tile_type="wall",
                             is_illusory_wall=False)]
    assert W.mark_illusory_walls(fresh, size, rng=SimpleNamespace(
        shuffle=lambda seq: None, random=lambda: 1.0)) == []


@pytest.mark.asyncio
async def test_reveal_illusory_wall_opens_grotto():
    """Вскрытие делает клетку проходимой, кладёт сундук и даёт опыт."""
    from core import illusions as core_illusions

    async with async_session() as session:
        user = User(telegram_id=_rand_tg(), username="seeker")
        session.add(user)
        await session.flush()
        char = Character(user_id=user.id, name="Seeker", character_class="mage",
                         level=4, experience=0, stats_locked=True)
        loc = Location(name="Пещеры Иллюзий", description="—",
                       location_type="dungeon", min_level=1)
        session.add_all([char, loc])
        await session.flush()

        plain = Cell(location_id=loc.id, x=1, y=1, name="Стена",
                     description="—", tile_type="wall", is_passable=False)
        fake = Cell(location_id=loc.id, x=2, y=2, name="Стена",
                    description="—", tile_type="wall", is_passable=False,
                    is_illusory_wall=True)
        session.add_all([plain, fake])
        await session.flush()

        miss = await core_illusions.reveal_illusory_wall(session, char, plain)
        assert miss["ok"] is False
        assert plain.is_passable is False

        exp_before = char.experience or 0
        hit = await core_illusions.reveal_illusory_wall(session, char, fake)
        assert hit["ok"] is True
        assert fake.is_passable is True and fake.is_illusory_wall is False
        assert fake.has_chest is True
        assert (char.experience or 0) > exp_before

        # Повторно вскрыть ту же стену нельзя.
        again = await core_illusions.reveal_illusory_wall(session, char, fake)
        assert again["ok"] is False
        await session.commit()


# ── бонус наставника ────────────────────────────────────────

@pytest.mark.asyncio
async def test_mentor_bonus_and_honor_points_flow():
    """Ученик получает +25 % опыта, наставник — Очки Чести."""
    from core import mentorship as core_mentor

    async with async_session() as session:
        u1, u2 = User(telegram_id=_rand_tg()), User(telegram_id=_rand_tg())
        session.add_all([u1, u2])
        await session.flush()
        mentor = Character(user_id=u1.id, name="Sensei", character_class="warrior",
                           level=12, honor_points=0, stats_locked=True)
        pupil = Character(user_id=u2.id, name="Padawan", character_class="mage",
                          level=2, stats_locked=True)
        session.add_all([mentor, pupil])
        await session.flush()

        # Без наставника прибавки нет.
        assert core_mentor.get_mentorship_bonuses(pupil)["exp_bonus_pct"] == 0
        assert await core_mentor.reward_mentor_for_progress(session, pupil) == 0

        await core_mentor.bind_mentor(session, pupil, mentor)
        bonuses = core_mentor.get_mentorship_bonuses(pupil)
        assert bonuses["exp_bonus_pct"] == 25

        # Ровно та арифметика, что применяется в _finish_victory.
        base_exp = 100
        assert int(base_exp * bonuses["exp_bonus_pct"] / 100) == 25

        gained = await core_mentor.reward_mentor_for_progress(session, pupil)
        assert gained > 0
        assert (mentor.honor_points or 0) == gained
        await session.commit()


def test_auction_bid_is_no_longer_a_stub():
    """Раньше здесь сторожили заглушку — теперь сторожим реализацию.

    Пункт № 59 закрыт: `core/auction_bid.py` больше не мёртвый модуль с
    одной константой, а рабочие торги. Тест перевёрнут намеренно, чтобы
    случайный откат к заглушке заметили сразу. Подробные проверки самой
    механики — в `tests/test_auction_bids.py`.
    """
    from core import auction_bid

    doc = auction_bid.__doc__ or ""
    assert "ЗАГЛУШКА" not in doc, \
        "модуль снова объявляет себя заглушкой — торги потеряны"
    assert not hasattr(auction_bid, "BID_AUCTION_KEY"), \
        "мёртвая константа должна была уйти вместе с заглушкой"

    # Публичный интерфейс торгов на месте.
    for name in ("place_bid", "buyout", "close_finished", "list_bid_lot",
                 "cancel_bid_lot", "next_bid", "is_bid_lot"):
        assert callable(getattr(auction_bid, name, None)), \
            f"в auction_bid нет функции {name}"
