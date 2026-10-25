"""Мобильное игровое приложение (playerapp): вход, API-контракт и правила.

Покрываем то, что видит приемка отдельного APK:
* код входа из бота одноразовый и протухает; Bearer-сессия живёт,
  отзывается и не пускает забаненных;
* профиль/клетка/движение/отдых/сундук — те же core-правила, что у бота,
  поэтому прогресс общий by design;
* бой идёт против живого MobSpawn, пишет Battle и начисляет опыт/золото;
* экипировка меняет слоты персонажа;
* HTTP-роутер /api/player/* требует Bearer и отдаёт SPA.

Запуск: python3 -m pytest -q tests/test_player_app.py
"""
import os
import sys

import pytest
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _seed import pin, unique_id  # noqa: E402

pin(4044)

from core.database import async_session  # noqa: E402
from core.enums import BattleResult, ItemRarity, ItemType  # noqa: E402
from core.models import (  # noqa: E402
    Battle, Cell, Character, InventoryItem, Item, Location, Mob, MobSpawn, User,
)
from playerapp import auth, battle as battle_svc, inventory as inv_svc, service  # noqa: E402
from playerapp.models import PlayerLoginCode, PlayerSession  # noqa: E402


# ── Фабрики тестового мира ───────────────────────────────────────────

async def _make_user(session):
    user = User(telegram_id=unique_id())
    session.add(user)
    await session.flush()
    return user


async def _reload_spawn(session, spawn_id):
    """Свежие колонки спавна без refresh: refresh в async-сессии тянет
    lazy-связь mob вне greenlet, а обычный SELECT обновляет только поля."""
    return (await session.execute(
        select(MobSpawn).where(MobSpawn.id == spawn_id)
    )).scalar_one()


async def _make_hero(session, user, location, cell, *, hp=120):
    hero = Character(
        user_id=user.id, name="Герой " + str(unique_id() % 100000),
        character_class="warrior", faction="guard",
        stats_locked=True, rerolls_left=0, reputation="",
        bronze=0, silver=0, gold=0,
        strength=15, agility=10, intelligence=6, endurance=14, luck=8,
        max_hp=hp, current_hp=hp, max_mp=40, current_mp=40,
        level=1, experience=0,
        location_id=location.id, cell_id=cell.id, floor=0,
    )
    session.add(hero)
    await session.flush()
    return hero


async def _make_world(session, *, campfire=False, chest=False, with_neighbor=True,
                      mob_hp=None, mob_damage=2):
    user = await _make_user(session)
    loc = Location(name="Полигон " + str(unique_id() % 100000),
                   description="тестовая локация", grid_size=10,
                   world_x=unique_id() % 50, world_y=unique_id() % 50)
    session.add(loc)
    await session.flush()
    cell = Cell(location_id=loc.id, x=5, y=5, floor=0, is_passable=True,
                has_campfire=campfire, has_chest=chest, chest_tier=1,
                description="старая клетка")
    session.add(cell)
    await session.flush()
    cell2 = None
    if with_neighbor:
        # Ось x — север/юг, ось y — запад/восток (см. service.DIRECTIONS),
        # поэтому восточный сосед имеет ту же x и y+1.
        cell2 = Cell(location_id=loc.id, x=5, y=6, floor=0, is_passable=True)
        session.add(cell2)
        await session.flush()
    hero = await _make_hero(session, user, loc, cell)
    spawn = None
    if mob_hp is not None:
        mob = Mob(name="Крыса " + str(unique_id() % 100000), description="тестовый моб",
                  level=1, hp=mob_hp, damage=mob_damage, defense=0,
                  gold_min=1, gold_max=3, gold_reward=2, exp_reward=4,
                  location_id=loc.id, population=1, respawn_seconds=5)
        session.add(mob)
        await session.flush()
        spawn = MobSpawn(mob_id=mob.id, home_location_id=loc.id, location_id=loc.id,
                         floor=0, x=cell.x, y=cell.y, current_hp=mob_hp, is_alive=True)
        session.add(spawn)
    await session.commit()
    # Перезагружаем героя ровно так, как это делает боевой API: с
    # selectinload(location/cell), иначе lazy-связи вне greenlet недоступны.
    hero = await service.load_character(session, user)
    return user, hero, loc, cell, cell2, spawn


# ── 1. Коды входа и Bearer-сессии ────────────────────────────────────

async def test_login_code_is_single_use_and_expires():
    async with async_session() as session:
        user = await _make_user(session)
        await session.commit()

        code = await auth.issue_code(session, user.telegram_id)
        assert len(code) == 6 and code.isdigit()
        assert set(code) <= set("23456789")  # без 0/1

        consumed = await auth.consume_code(session, code)
        assert consumed is not None and consumed.id == user.id
        # Повторно тот же код не работает.
        assert await auth.consume_code(session, code) is None

        # Протухший код не пускает.
        stale = await auth.issue_code(session, user.telegram_id)
        row = await session.scalar(
            select(PlayerLoginCode).where(PlayerLoginCode.code == stale)
        )
        from datetime import datetime, timedelta
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        await session.commit()
        assert await auth.consume_code(session, stale) is None

        # Несуществующий код — тоже None, без исключений.
        assert await auth.consume_code(session, "000000") is None


async def test_bearer_session_roundtrip_revoke_and_ban():
    async with async_session() as session:
        user = await _make_user(session)
        await session.commit()

        token = await auth.create_session(session, user, source="code",
                                          user_agent="pytest")
        # В БД лежит только хэш, сырого токена там нет.
        row = await session.scalar(select(PlayerSession))
        assert row.token_hash != token and len(row.token_hash) == 64

        found = await auth.user_for_token(session, token)
        assert found is not None and found.id == user.id
        assert await auth.user_for_token(session, "мусор") is None

        row.revoked = True
        await session.commit()
        assert await auth.user_for_token(session, token) is None

        # Сессия живого пользователя, но забаненного, доступа не даёт.
        token2 = await auth.create_session(session, user, source="telegram",
                                           user_agent=None)
        user.is_banned = True
        await session.commit()
        assert await auth.user_for_token(session, token2) is None


# ── 2. Профиль, клетка, движение, отдых ──────────────────────────────

async def test_profile_cell_move_and_rest_rules():
    async with async_session() as session:
        user, hero, loc, cell, cell2, _ = await _make_world(
            session, campfire=True)

        profile = service.profile_dict(hero, user)
        assert profile["name"] == hero.name
        assert profile["hp"] == {"current": hero.max_hp, "max": hero.max_hp}
        assert profile["stats"]["strength"] == 15
        assert profile["location"] == loc.name

        view = await service.cell_view(session, hero)
        assert view["location"] == loc.name
        assert view["campfire"] is True
        dirs = {n["direction"] for n in view["neighbors"]}
        assert "e" in dirs and "w" not in dirs  # сосед только с востока

        # Шаг на восток переставляет героя и отмечает клетку посещённой.
        moved = await service.move(session, hero, "e")
        assert moved["ok"] is True
        assert hero.cell_id == cell2.id

        # Мусорное направление и шаг без клетки (с (6,5) на север пусто).
        with pytest.raises(service.ServiceError):
            await service.move(session, hero, "zzz")
        with pytest.raises(service.ServiceError):
            await service.move(session, hero, "n")
        # Запад (5,5) существует и проходим — возвращаемся.
        back = await service.move(session, hero, "w")
        assert back["ok"] is True and hero.cell_id == cell.id

        # Отдых у костра лечит после урона.
        hero.current_hp = 5
        await session.commit()
        rested = await service.rest(session, hero)
        assert rested["ok"] is True
        assert hero.current_hp > 5

        # В чистом поле отдыхать нельзя.
        cell2.has_campfire = False
        cell2.has_house = False
        hero.cell_id = cell2.id
        hero.cell = cell2  # держим id и связь согласованными, как move()
        await session.commit()
        with pytest.raises(service.ServiceError):
            await service.rest(session, hero)


async def test_chest_inspect_is_atomic_and_single_claim():
    async with async_session() as session:
        _, hero, _, cell, _, _ = await _make_world(session, chest=True,
                                                   with_neighbor=False)
        bronze_before = hero.bronze
        result = await service.inspect_cell(session, hero)
        assert result["ok"] is True
        assert result["gold_bronze"] > 0
        assert hero.bronze == bronze_before + result["gold_bronze"]
        assert isinstance(result["loot"], list)

        # Сундук сразу помечен открытым: повторный осмотр отклонён.
        with pytest.raises(service.ServiceError):
            await service.inspect_cell(session, hero)


# ── 3. Бой ───────────────────────────────────────────────────────────

async def test_battle_victory_credits_exp_gold_and_battle_record():
    async with async_session() as session:
        _, hero, _, cell, _, spawn = await _make_world(
            session, mob_hp=1, mob_damage=1)

        state = await battle_svc.start_battle(session, hero)
        assert state["mob_name"].startswith("Крыса ")
        spawn = await _reload_spawn(session, spawn.id)
        assert spawn.engaged_by_id == hero.id  # спавн захвачен

        # Моб с 1 HP падает с первого удара.
        result = await battle_svc.attack(session, hero)
        assert result["victory"] is True and result["defeat"] is False
        assert result["mob"]["hp"] == 0
        assert result["gold_bronze"] >= 1 and result["exp"] == 4
        assert battle_svc.active_battle(hero.id) is None

        spawn = await _reload_spawn(session, spawn.id)
        assert spawn.is_alive is False and spawn.engaged_by_id is None
        assert hero.experience == 4

        record = await session.scalar(
            select(Battle).where(Battle.character_id == hero.id)
        )
        assert record is not None and record.result == BattleResult.VICTORY
        assert record.gold_earned == result["gold_bronze"]

        # Мёртвый спавн повторно в бой не берётся.
        with pytest.raises(service.ServiceError):
            await battle_svc.start_battle(session, hero)


async def test_battle_flee_has_known_contract():
    async with async_session() as session:
        _, hero, _, _, _, spawn = await _make_world(
            session, mob_hp=50, mob_damage=1)
        await battle_svc.start_battle(session, hero)
        result = await battle_svc.flee(session, hero)

        if result.get("escaped"):
            # Успешный побег: бой закрыт, запись ESCAPE, захват снят.
            assert battle_svc.active_battle(hero.id) is None
            spawn = await _reload_spawn(session, spawn.id)
            assert spawn.engaged_by_id is None
            record = await session.scalar(
                select(Battle).where(Battle.character_id == hero.id)
            )
            assert record is not None and record.result == BattleResult.ESCAPE
        else:
            # Неудачный побег: моб бьёт в спину, бой продолжается.
            assert result["active"] is True and result["mob"]["hp"] == 50
            assert battle_svc.active_battle(hero.id) is not None
            battle_svc._combat.pop(hero.id, None)


async def test_start_battle_claims_spawn_once():
    async with async_session() as session:
        _, hero1, _, cell, _, spawn = await _make_world(session, mob_hp=20)
        # Второй герой стоит на ТОЙ ЖЕ клетке, что и занятый спавн.
        user2 = await _make_user(session)
        hero2 = await _make_hero(
            session, user2,
            await session.get(Location, spawn.location_id), cell)
        await session.commit()
        hero2 = await service.load_character(session, user2)

        await battle_svc.start_battle(session, hero1)
        # Тот же спавн занят — второй герой получает отказ.
        with pytest.raises(service.ServiceError):
            await battle_svc.start_battle(session, hero2)
        battle_svc._combat.pop(hero1.id, None)


# ── 4. Инвентарь ─────────────────────────────────────────────────────

async def test_equip_and_unequip_weapon_slot():
    async with async_session() as session:
        user, hero, loc, cell, _, _ = await _make_world(session)
        item = Item(name="Меч полигонный", description="тестовый",
                    item_type=ItemType.WEAPON, rarity=ItemRarity.COMMON,
                    level_requirement=1, price=10)
        session.add(item)
        await session.flush()
        inv = InventoryItem(character_id=hero.id, item_id=item.id, quantity=1)
        session.add(inv)
        await session.commit()

        listing = await inv_svc.list_inventory(session, hero)
        assert len(listing["bag"]) == 1 and not listing["equipped"]
        bag_row = listing["bag"][0]
        assert bag_row["inventory_id"] == inv.id

        await inv_svc.equip(session, hero, inv.id)
        assert hero.weapon_id == item.id
        listing = await inv_svc.list_inventory(session, hero)
        assert len(listing["equipped"]) == 1 and not listing["bag"]

        await inv_svc.unequip(session, hero, inv.id)
        assert hero.weapon_id is None
        listing = await inv_svc.list_inventory(session, hero)
        assert not listing["equipped"] and len(listing["bag"]) == 1

        # Расходник надеть нельзя.
        potion = Item(name="Зелье", description="хм", item_type=ItemType.CONSUMABLE,
                      rarity=ItemRarity.COMMON, level_requirement=1)
        session.add(potion)
        await session.flush()
        junk = InventoryItem(character_id=hero.id, item_id=potion.id, quantity=1)
        session.add(junk)
        await session.commit()
        with pytest.raises(service.ServiceError):
            await inv_svc.equip(session, hero, junk.id)


# ── 5. HTTP-контракт роутера ─────────────────────────────────────────

async def test_http_router_requires_bearer_and_serves_spa():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from playerapp.api import router as player_router

    async with async_session() as session:
        user, hero, loc, cell, cell2, _ = await _make_world(
            session, campfire=True, with_neighbor=True)
        code = await auth.issue_code(session, user.telegram_id)

    app = FastAPI()
    app.include_router(player_router)
    with TestClient(app) as client:
        # Без токена игровые методы закрыты.
        assert client.get("/api/player/me").status_code == 401
        assert client.get("/api/player/cell").status_code == 401

        # Мусорный код отвергнут.
        bad = client.post("/api/player/auth/code", json={"code": "999999"})
        assert bad.status_code == 401 and bad.json()["ok"] is False

        # Настоящий код меняет на Bearer-токен и видит персонажа из бота.
        ok = client.post("/api/player/auth/code", json={"code": code})
        assert ok.status_code == 200
        body = ok.json()
        assert body["ok"] is True and body["has_character"] is True
        headers = {"Authorization": "Bearer " + body["token"]}

        me = client.get("/api/player/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["profile"]["name"] == hero.name

        cell_resp = client.get("/api/player/cell", headers=headers)
        assert cell_resp.status_code == 200
        assert cell_resp.json()["cell"]["location"] == loc.name

        move_resp = client.post("/api/player/move", headers=headers,
                                json={"direction": "e"})
        assert move_resp.status_code == 200
        assert move_resp.json()["cell"]["cell"]["x"] == cell2.x

        battle = client.get("/api/player/battle", headers=headers)
        assert battle.status_code == 200
        assert battle.json() == {"ok": True, "active": False, "state": None}

        # Битый Bearer после валидного входа — 401, без 500.
        assert client.get("/api/player/me",
                          headers={"Authorization": "Bearer nope"}).status_code == 401

        # SPA отдаётся с корня роутера.
        spa = client.get("/api/player/")
        assert spa.status_code == 200 and "Теневые Земли" in spa.text


async def test_telegram_init_data_login_and_http_endpoint():
    # Путь входа внутри Telegram Mini App: подписанная initData строка.
    import hashlib
    import hmac
    import json as json_mod
    import time
    from urllib.parse import urlencode

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core.models import AppSetting
    from playerapp.api import router as player_router

    TOKEN = "123456:PLAYER_APP_TEST_TOKEN"

    def signed_init_data(tg_id: int, token: str) -> str:
        fields = {
            "auth_date": str(int(time.time())),
            "user": json_mod.dumps({"id": tg_id, "first_name": "Игрок"},
                                   ensure_ascii=False),
            "signature": "fake-ed25519",
        }
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        fields["hash"] = hmac.new(
            secret, data_check.encode(), hashlib.sha256).hexdigest()
        return urlencode(fields)

    async with async_session() as session:
        tg_id = unique_id()
        user = User(telegram_id=tg_id)
        session.add(user)
        # bot_token кладём идемпотентно: ключ UNIQUE, БД общая на прогон.
        setting = await session.scalar(
            select(AppSetting).where(AppSetting.key == "bot_token"))
        if setting is None:
            session.add(AppSetting(key="bot_token", value=TOKEN))
        else:
            setting.value = TOKEN
        await session.commit()

        good = signed_init_data(tg_id, TOKEN)
        found = await auth.user_for_init_data(session, good)
        assert found is not None and found.id == user.id

        # Подпись, сделанная чужим токеном, не проходит.
        forged = signed_init_data(tg_id, "999:WRONG_TOKEN")
        assert await auth.user_for_init_data(session, forged) is None

    app = FastAPI()
    app.include_router(player_router)
    with TestClient(app) as client:
        ok = client.post("/api/player/auth/telegram", json={"initData": good})
        assert ok.status_code == 200 and ok.json()["ok"] is True
        assert ok.json()["has_character"] is False  # пользователь без героя

        bad = client.post("/api/player/auth/telegram",
                          json={"initData": "user=%7B%7D&hash=deadbeef"})
        assert bad.status_code == 403 and bad.json()["ok"] is False


async def test_full_admin_app_serves_player_spa_and_static():
    # Точки входа, которые реально открывают бот (Mini App) и APK WebView.
    from fastapi.testclient import TestClient

    import admin.main as admin_module

    with TestClient(admin_module.app) as client:
        # /player без хвоста — редирект на канонический /player/.
        redirect = client.get("/player", follow_redirects=False)
        assert redirect.status_code in (302, 307)
        assert redirect.headers["location"] == "/player/"

        index = client.get("/player/")
        assert index.status_code == 200 and "Теневые Земли" in index.text

        # Локальная статика SPA смонтирована и отдаётся без авторизации.
        for asset in ("/player-static/app.js", "/player-static/player.css"):
            resp = client.get(asset)
            assert resp.status_code == 200, asset

        # Игровой API под защитой Bearer даже на полном приложении.
        assert client.get("/api/player/me").status_code == 401
