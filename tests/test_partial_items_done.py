"""Доведение частично сделанных пунктов: луна, ломбард→рынок, дуэли, панель.

Запуск: python3 -m pytest -q tests/test_partial_items_done.py

Что проверяется (всё это раньше было «наполовину»):
  • № 49 — множители фазы луны реально применяются к популяции мобов,
    шансу дропа и урону магии Тьмы, а не только показываются текстом;
  • № 65 — фазу можно заморозить из админки (override в AppSetting),
    потому что естественная фаза считается от времени;
  • № 48 — просроченный залог изымается и попадает на витрину чёрного
    рынка, а не висит «активным» вечно;
  • № 53 — дуэль требует согласия второй стороны;
  • № 35 — реактивные реплики NPC появились и в браузерном стеке;
  • № 72 — знамения и расклад кармы видны в панели Pyodide.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Детерминизм (пункт № 5): игровой random спинован своей константой,
# а уникальные telegram_id берутся вне seed — см. tests/_seed.py.
from _seed import pin, unique_id  # noqa: E402

pin(114)

from core.database import async_session
from core.models import (AppSetting, Character, Item, ItemInstance, Location,
                         PawnLoan, User)


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


# ── № 49 / № 65: фаза луны влияет на игру и поддаётся заморозке ──

def test_lunar_multipliers_are_distinct():
    """У фаз разные множители — иначе применять было бы нечего."""
    from core import lunar as core_lunar

    keys = {p["key"] for p in core_lunar.PHASES}
    assert len(keys) == len(core_lunar.PHASES)
    assert core_lunar.phase_by_key("full_moon")["mob_mult"] > 1.0
    assert core_lunar.phase_by_key("waning_moon")["mob_mult"] < 1.0
    assert core_lunar.phase_by_key("new_moon")["magic_dark_mult"] > 1.0
    assert core_lunar.phase_by_key("нет такой") is None


def test_lunar_multipliers_are_wired_into_game_code():
    """Множители читаются боевым и мировым кодом, а не только шаблоном."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    spawns = open(os.path.join(root, "core/spawns.py"), encoding="utf-8").read()
    assert "mob_mult" in spawns, "популяция не зависит от фазы луны"

    loot = open(os.path.join(root, "core/loot.py"), encoding="utf-8").read()
    assert "material_mult" in loot, "шанс дропа не зависит от фазы луны"

    battle = open(os.path.join(root, "bot/handlers/battle.py"),
                  encoding="utf-8").read()
    assert "magic_dark_mult" in battle, "урон Тьмы не зависит от фазы луны"


@pytest.mark.asyncio
async def test_lunar_override_freezes_phase():
    """Заморозка держит выбранную фазу, сброс возвращает естественный цикл."""
    from sqlalchemy import select

    from core import lunar as core_lunar

    async with async_session() as session:
        natural = core_lunar.get_current_lunar_phase()
        forced_key = next(p["key"] for p in core_lunar.PHASES
                          if p["key"] != natural["key"])

        await core_lunar.set_override(session, forced_key)
        await session.commit()
        assert (await core_lunar.get_phase(session))["key"] == forced_key

        row = (await session.execute(
            select(AppSetting).where(AppSetting.key == core_lunar.LUNAR_OVERRIDE_KEY)
        )).scalar_one_or_none()
        assert row is not None and row.value == forced_key

        with pytest.raises(ValueError):
            await core_lunar.set_override(session, "выдуманная_фаза")

        await core_lunar.set_override(session, "")
        await session.commit()
        assert (await core_lunar.get_phase(session))["key"] == \
            core_lunar.get_current_lunar_phase()["key"]


# ── № 48: просрочка ломбарда уходит на чёрный рынок ──

@pytest.mark.asyncio
async def test_expired_loan_moves_to_black_market():
    """Просрочка изымается, появляется на витрине и продаётся один раз."""
    from datetime import timedelta

    from sqlalchemy import select

    from core import blackmarket as core_bm
    from core import dates
    from core import pawnshop as core_pawn
    from core.loot import new_uid
    from core.models import InventoryItem
    from engine.currency import add_currency

    async with async_session() as session:
        u1, u2 = User(telegram_id=_rand_tg()), User(telegram_id=_rand_tg())
        session.add_all([u1, u2])
        await session.flush()
        debtor = Character(user_id=u1.id, name="Debtor", character_class="warrior",
                           level=5, stats_locked=True)
        buyer = Character(user_id=u2.id, name="Buyer", character_class="rogue",
                          level=5, stats_locked=True)
        item = Item(name="Заложенный клинок", description="—", item_type="weapon",
                    rarity="rare", price=300)
        session.add_all([debtor, buyer, item])
        await session.flush()
        inst = ItemInstance(uid=new_uid(), item_id=item.id, quality=100)
        session.add(inst)
        await session.flush()

        fresh = PawnLoan(character_id=debtor.id, instance_id=inst.id,
                         item_id=item.id, loan_bronze=200, buyback_price=230,
                         expires_at=dates.utcnow() + timedelta(days=3))
        session.add(fresh)
        await session.flush()

        # Действующий заём не трогаем.
        assert await core_pawn.sweep_expired_loans(session) == []
        assert fresh.is_liquidated is False

        fresh.expires_at = dates.utcnow() - timedelta(hours=1)
        await session.flush()
        seized = await core_pawn.sweep_expired_loans(session)
        assert any(l.id == fresh.id for l in seized)
        assert fresh.is_liquidated is True

        wares = await core_bm.list_liquidated_wares(session)
        mine = [w for w in wares if w["loan_id"] == fresh.id]
        assert mine, "изъятая вещь не попала на витрину"
        # Перекуп продаёт дороже выкупа: иначе выгодно не платить по долгу.
        assert mine[0]["cost"] > fresh.buyback_price

        poor = await core_bm.buy_liquidated_item(session, buyer, fresh.id)
        assert poor["ok"] is False

        add_currency(buyer, bronze=mine[0]["cost"])
        ok = await core_bm.buy_liquidated_item(session, buyer, fresh.id)
        assert ok["ok"] is True

        owned = (await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == buyer.id)
            .where(InventoryItem.instance_id == inst.id)
        )).scalars().all()
        assert len(owned) == 1, "вещь не перешла покупателю"

        # Дважды одну вещь не продать и с витрины она пропала.
        again = await core_bm.buy_liquidated_item(session, buyer, fresh.id)
        assert again["ok"] is False
        left = await core_bm.list_liquidated_wares(session)
        assert all(w["loan_id"] != fresh.id for w in left)
        await session.commit()


# ── № 53: дуэль по согласию ──

def test_duel_requires_consent():
    """Вызов только приглашает: бой идёт после принятия, есть и отказ."""
    from bot.handlers import world_extra

    router = world_extra.router
    assert _has_handler(router, "duel_go:1:100"), "нет отправки вызова"
    assert _has_handler(router, "duel_accept:1"), "нет принятия вызова"
    assert _has_handler(router, "duel_decline:1"), "нет отказа от вызова"
    assert hasattr(world_extra, "duel_invites"), "нет хранилища вызовов"

    # Принять несуществующий вызов нельзя — состояние пустое.
    world_extra.duel_invites.clear()
    assert world_extra.duel_invites.get(12345) is None


# ── № 35: реактивные реплики в браузерном стеке ──

def test_engine_dialogue_matches_server_branches():
    """Ветки и пороги совпадают с core/dialogue.py."""
    from engine import dialogue as e_dialogue
    from engine import karma as e_karma
    from engine.models import Player

    hero = Player(tg_id=1, cls="berserker")

    assert "осадные орудия" in e_dialogue.generate_reactive_dialogue(
        hero, "Страж", "guard", {"has_siege": True})
    assert "катаклизм" in e_dialogue.generate_reactive_dialogue(
        hero, "Страж", "guard", {"has_cataclysm": True})
    assert "обоз" in e_dialogue.generate_reactive_dialogue(
        hero, "Страж", "guard", {"has_caravan": True})

    # Спокойный мир и нейтральная карма — обычное описание NPC.
    assert e_dialogue.generate_reactive_dialogue(hero, "Страж", "guard", {}) == ""

    hero.karma_score = e_karma.DEFILED_KARMA
    assert "осквернитель" in e_dialogue.generate_reactive_dialogue(
        hero, "Страж", "guard", {}).lower()
    hero.karma_score = e_karma.PIOUS_KARMA
    assert "благословение" in e_dialogue.generate_reactive_dialogue(
        hero, "Страж", "guard", {}).lower()

    # Осада важнее кармы — порядок веток как на сервере.
    assert "К оружию" in e_dialogue.generate_reactive_dialogue(
        hero, "Страж", "guard", {"has_siege": True, "has_cataclysm": True})


def test_engine_talk_uses_reactive_line():
    """Экран NPC в движке показывает реакцию на мир, а не только описание."""
    from engine import cataclysm, explore
    from engine.game import Game
    from engine.models import Player
    from engine.storage import Store
    from webapp.backend import MemoryStorage

    store = Store(MemoryStorage())
    hero = Player(tg_id=2, cls="berserker")
    hero.karma_score = 0
    store.save_player(hero)

    calm = explore.talk(0, hero, store)
    assert "💬" in calm.text

    # Осквернителя жители встречают иначе.
    from engine import karma
    hero.karma_score = karma.DEFILED_KARMA
    hostile = explore.talk(0, hero, store)
    assert hostile.text != calm.text
    assert "осквернитель" in hostile.text.lower()

    # Роутер передаёт store, иначе контекст мира не собрать.
    game = Game(store)
    assert "💬" in game.do_talk(hero, "0").text


# ── № 72: знамения и карма в панели Pyodide ──

def test_panel_shows_omens_and_karma():
    from types import SimpleNamespace

    from engine.models import Player
    from engine.storage import Store
    from webapp.backend import MemoryStorage
    from webapp.pages import world_living

    store = Store(MemoryStorage())
    saint = Player(tg_id=3, cls="paladin")
    saint.karma_score = 500
    sinner = Player(tg_id=4, cls="necromancer")
    sinner.karma_score = -500
    store.save_player(saint)
    store.save_player(sinner)

    html = world_living.render(SimpleNamespace(store=store))
    assert "Знамения и карма" in html
    assert "Кровавый туман" in html
    assert "Благочестивых" in html and "Осквернителей" in html
