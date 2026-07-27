import os
import shutil
import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from core.database import init_db, async_session
from core.migrations import run_migrations
from core.models import (
    User, Character, Location, Mob, Item, ShopItem, Battle, AppSetting, Cell,
    Quest, AdminMessage, InventoryItem
)
from core.enums import LocationType, ItemType, ItemRarity, QuestStatus
from admin.config import settings
from bot.runner import bot_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    await run_migrations()
    yield


app = FastAPI(title="Shadow Lands Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="admin/static"), name="static")
templates = Jinja2Templates(directory="admin/templates")


# ── Dashboard ──────────────────────────────────────────────

@app.get("/")
async def dashboard(request: Request):
    async with async_session() as session:
        total_players = await session.scalar(select(func.count(User.id)))
        total_characters = await session.scalar(select(func.count(Character.id)))
        total_battles = await session.scalar(select(func.count(Battle.id)))
        total_gold = await session.scalar(select(func.sum(Character.gold))) or 0
        avg_level = round(await session.scalar(select(func.avg(Character.level))) or 0, 1)

        result = await session.execute(
            select(Character.location_id, func.count(Character.id).label("cnt"))
            .group_by(Character.location_id)
            .order_by(func.count(Character.id).desc())
        )
        top_loc_row = result.first()
        top_location = "—"
        if top_loc_row:
            loc = await session.get(Location, top_loc_row.location_id)
            top_location = loc.name if loc else "—"

        result = await session.execute(
            select(Battle)
            .options(selectinload(Battle.character), selectinload(Battle.mob))
            .order_by(Battle.id.desc())
            .limit(20)
        )
        recent_battles = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "total_players": total_players,
            "total_characters": total_characters,
            "total_battles": total_battles,
            "total_gold": total_gold,
            "avg_level": avg_level,
            "top_location": top_location,
            "recent_battles": recent_battles,
        },
    )


# ── Players ────────────────────────────────────────────────

@app.get("/players")
async def players(request: Request):
    async with async_session() as session:
        result = await session.execute(
            select(Character)
            .options(selectinload(Character.user), selectinload(Character.location))
            .order_by(Character.level.desc())
        )
        chars = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "players.html",
        {"players": chars},
    )


@app.get("/player/{char_id}")
async def player_detail(request: Request, char_id: int):
    async with async_session() as session:
        char = await session.get(Character, char_id)
        if not char:
            return RedirectResponse(url="/players")
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == char_id)
            .options(selectinload(InventoryItem.item))
        )
        inventory = result.scalars().all()
        result = await session.execute(
            select(AdminMessage)
            .where(AdminMessage.user_id == char.user_id)
            .order_by(AdminMessage.created_at.desc())
            .limit(50)
        )
        messages = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "player_detail.html",
        {"char": char, "inventory": inventory, "messages": messages},
    )


@app.post("/player/{char_id}/edit")
async def player_edit(
    char_id: int,
    name: str = Form(...),
    level: int = Form(1),
    gold: int = Form(0),
    experience: int = Form(0),
    strength: int = Form(10),
    agility: int = Form(10),
    intelligence: int = Form(10),
    endurance: int = Form(10),
    luck: int = Form(10),
    max_hp: int = Form(100),
    max_mp: int = Form(50),
    current_hp: int = Form(100),
    current_mp: int = Form(50),
    is_vip: bool = Form(False),
    vip_days: int = Form(0),
):
    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char:
            char.name = name
            char.level = level
            char.gold = gold
            char.experience = experience
            char.strength = strength
            char.agility = agility
            char.intelligence = intelligence
            char.endurance = endurance
            char.luck = luck
            char.max_hp = max_hp
            char.max_mp = max_mp
            char.current_hp = current_hp
            char.current_mp = current_mp
            char.is_vip = is_vip
            if vip_days > 0:
                char.vip_until = datetime.utcnow() + timedelta(days=vip_days)
            elif not is_vip:
                char.vip_until = None
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/give-item")
async def player_give_item(char_id: int, item_id: int = Form(...), quantity: int = Form(1)):
    async with async_session() as session:
        char = await session.get(Character, char_id)
        item = await session.get(Item, item_id)
        if char and item:
            inv = InventoryItem(character_id=char.id, item_id=item.id, quantity=quantity)
            session.add(inv)
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/send-message")
async def player_send_message(char_id: int, text: str = Form(...)):
    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char and text.strip():
            msg = AdminMessage(user_id=char.user_id, from_admin=True, text=text.strip())
            session.add(msg)
            await session.commit()
            # Try to send via bot if running
            try:
                from bot.runner import bot_runner
                if bot_runner.is_running() and bot_runner.bot:
                    await bot_runner.bot.send_message(
                        chat_id=char.user.telegram_id,
                        text=f"📩 <b>Сообщение от администратора:</b>\n\n{text.strip()}",
                        parse_mode="HTML"
                    )
            except Exception:
                pass
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


# ── Items ──────────────────────────────────────────────────

@app.get("/items")
async def items(request: Request):
    async with async_session() as session:
        result = await session.execute(select(Item).order_by(Item.id))
        all_items = result.scalars().all()
        result = await session.execute(
            select(ShopItem).options(selectinload(ShopItem.item)).order_by(ShopItem.id)
        )
        shop_items = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "items.html",
        {"items": all_items, "shop_items": shop_items},
    )


@app.get("/item/{item_id}/edit")
async def item_edit_page(request: Request, item_id: int):
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            return RedirectResponse(url="/items")
    return templates.TemplateResponse(request, "item_edit.html", {"item": item})


@app.post("/item/{item_id}/edit")
async def item_edit(
    item_id: int,
    name: str = Form(...),
    description: str = Form(""),
    item_type: str = Form(...),
    rarity: str = Form("common"),
    level_requirement: int = Form(1),
    price: int = Form(0),
    bonus_strength: int = Form(0),
    bonus_agility: int = Form(0),
    bonus_intelligence: int = Form(0),
    bonus_endurance: int = Form(0),
    bonus_luck: int = Form(0),
    bonus_hp: int = Form(0),
    bonus_mp: int = Form(0),
    bonus_damage: int = Form(0),
    bonus_defense: int = Form(0),
    icon: str = Form("⚔️"),
):
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if item:
            item.name = name
            item.description = description
            item.item_type = ItemType(item_type)
            item.rarity = ItemRarity(rarity)
            item.level_requirement = level_requirement
            item.price = price
            item.bonus_strength = bonus_strength
            item.bonus_agility = bonus_agility
            item.bonus_intelligence = bonus_intelligence
            item.bonus_endurance = bonus_endurance
            item.bonus_luck = bonus_luck
            item.bonus_hp = bonus_hp
            item.bonus_mp = bonus_mp
            item.bonus_damage = bonus_damage
            item.bonus_defense = bonus_defense
            item.icon = icon
            await session.commit()
    return RedirectResponse(url="/items", status_code=303)


@app.post("/item/new")
async def item_new(
    name: str = Form(...),
    description: str = Form(""),
    item_type: str = Form(...),
    rarity: str = Form("common"),
    level_requirement: int = Form(1),
    price: int = Form(0),
    bonus_strength: int = Form(0),
    bonus_agility: int = Form(0),
    bonus_intelligence: int = Form(0),
    bonus_endurance: int = Form(0),
    bonus_luck: int = Form(0),
    bonus_hp: int = Form(0),
    bonus_mp: int = Form(0),
    bonus_damage: int = Form(0),
    bonus_defense: int = Form(0),
    icon: str = Form("⚔️"),
):
    async with async_session() as session:
        item = Item(
            name=name, description=description, item_type=ItemType(item_type),
            rarity=ItemRarity(rarity), level_requirement=level_requirement, price=price,
            bonus_strength=bonus_strength, bonus_agility=bonus_agility,
            bonus_intelligence=bonus_intelligence, bonus_endurance=bonus_endurance,
            bonus_luck=bonus_luck, bonus_hp=bonus_hp, bonus_mp=bonus_mp,
            bonus_damage=bonus_damage, bonus_defense=bonus_defense, icon=icon,
        )
        session.add(item)
        await session.commit()
    return RedirectResponse(url="/items", status_code=303)


@app.post("/item/{item_id}/delete")
async def item_delete(item_id: int):
    async with async_session() as session:
        await session.execute(delete(Item).where(Item.id == item_id))
        await session.commit()
    return RedirectResponse(url="/items", status_code=303)


# ── Battles ────────────────────────────────────────────────

@app.get("/battles")
async def battles(request: Request):
    async with async_session() as session:
        result = await session.execute(
            select(Battle)
            .options(selectinload(Battle.character), selectinload(Battle.mob))
            .order_by(Battle.id.desc())
            .limit(100)
        )
        rows = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "battles.html",
        {"battles": rows},
    )


# ── Settings / Bot Control ─────────────────────────────────

@app.get("/settings")
async def settings_page(request: Request):
    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == "bot_token")
        )
        setting = result.scalar_one_or_none()
        token_masked = ""
        if setting and setting.value:
            t = setting.value
            token_masked = t[:10] + "..." + t[-6:] if len(t) > 20 else "***"

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "token_masked": token_masked,
            "bot_running": bot_runner.is_running(),
        },
    )


@app.post("/settings/save-token")
async def save_token(request: Request, bot_token: str = Form(...)):
    token = bot_token.strip()
    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == "bot_token")
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = token
        else:
            setting = AppSetting(key="bot_token", value=token)
            session.add(setting)
        await session.commit()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/api/bot/start")
async def api_bot_start():
    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == "bot_token")
        )
        setting = result.scalar_one_or_none()
        if not setting or not setting.value.strip():
            return {"success": False, "error": "Токен не задан. Перейдите в Настройки."}

        ok = await bot_runner.start(setting.value.strip())
        return {"success": ok, "running": bot_runner.is_running()}


@app.post("/api/bot/stop")
async def api_bot_stop():
    ok = await bot_runner.stop()
    return {"success": ok, "running": bot_runner.is_running()}


@app.get("/api/bot/status")
async def api_bot_status():
    return {"running": bot_runner.is_running()}


# ── Location Editor ────────────────────────────────────────

@app.get("/editor/locations")
async def editor_locations(request: Request):
    async with async_session() as session:
        result = await session.execute(select(Location).order_by(Location.id))
        locations = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "editor_locations.html",
        {"locations": locations},
    )


@app.get("/editor/location/new")
async def editor_location_new_page(request: Request):
    return templates.TemplateResponse(request, "editor_location_new.html", {})


@app.post("/editor/location/new")
async def editor_location_new(
    name: str = Form(...),
    description: str = Form(""),
    location_type: str = Form("safe"),
    min_level: int = Form(1),
    grid_size: int = Form(10),
    world_x: int = Form(0),
    world_y: int = Form(0),
):
    from core.seed import CELL_STORIES
    async with async_session() as session:
        loc = Location(
            name=name, description=description,
            location_type=LocationType(location_type),
            min_level=min_level, grid_size=grid_size,
            world_x=world_x, world_y=world_y,
        )
        session.add(loc)
        await session.flush()

        # Generate cells
        story_idx = random.randint(0, len(CELL_STORIES) - 1)
        cells = []
        for x in range(grid_size):
            for y in range(grid_size):
                is_border = (x == 0 or x == grid_size - 1 or y == 0 or y == grid_size - 1)
                is_wall = is_border or (not is_border and random.random() < 0.15 and (x, y) != (5, 5))
                name_s, desc_s, tile = CELL_STORIES[story_idx % len(CELL_STORIES)]
                story_idx += 1
                cell = Cell(
                    location_id=loc.id, x=x, y=y,
                    name=name_s, description=desc_s,
                    is_passable=not is_wall,
                    tile_type=tile if not is_wall else "wall",
                )
                session.add(cell)
                cells.append(cell)
        await session.flush()
        await session.commit()
    return RedirectResponse(url=f"/editor/location/{loc.id}", status_code=303)


@app.get("/editor/location/{location_id}")
async def editor_location(request: Request, location_id: int):
    async with async_session() as session:
        location = await session.get(Location, location_id)
        if not location:
            return RedirectResponse(url="/editor/locations")

        result = await session.execute(
            select(Cell).where(Cell.location_id == location_id)
        )
        cells = result.scalars().all()
        cells_dict = {(c.x, c.y): c for c in cells}

    return templates.TemplateResponse(
        request,
        "editor_location.html",
        {"location": location, "cells_dict": cells_dict},
    )


@app.post("/editor/location/{location_id}/save")
async def editor_location_save(
    location_id: int,
    name: str = Form(...),
    description: str = Form(""),
    location_type: str = Form(...),
    min_level: int = Form(1),
    grid_size: int = Form(10),
    world_x: int = Form(0),
    world_y: int = Form(0),
):
    async with async_session() as session:
        location = await session.get(Location, location_id)
        if location:
            location.name = name
            location.description = description
            location.location_type = LocationType(location_type)
            location.min_level = min_level
            location.grid_size = grid_size
            location.world_x = world_x
            location.world_y = world_y
            await session.commit()
    return RedirectResponse(url=f"/editor/location/{location_id}", status_code=303)


@app.get("/editor/cell/{cell_id}")
async def editor_cell(request: Request, cell_id: int):
    async with async_session() as session:
        cell = await session.get(Cell, cell_id)
        if not cell:
            return RedirectResponse(url="/editor/locations")

        result = await session.execute(select(Location).order_by(Location.id))
        all_locations = result.scalars().all()

        neighbors = {}
        for dir_name, (dx, dy) in {"Север": (-1, 0), "Юг": (1, 0), "Запад": (0, -1), "Восток": (0, 1)}.items():
            result = await session.execute(
                select(Cell)
                .where(Cell.location_id == cell.location_id)
                .where(Cell.x == cell.x + dx)
                .where(Cell.y == cell.y + dy)
            )
            neighbors[dir_name] = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "editor_cell.html",
        {"cell": cell, "neighbors": neighbors, "all_locations": all_locations},
    )


@app.post("/editor/cell/{cell_id}/save")
async def editor_cell_save(
    request: Request,
    cell_id: int,
    name: str = Form(...),
    description: str = Form(""),
    tile_type: str = Form("grass"),
    is_passable: bool = Form(False),
    has_npc: bool = Form(False),
    npc_name: str = Form(""),
    npc_type: str = Form(""),
    npc_dialogue: str = Form(""),
    has_chest: bool = Form(False),
    has_house: bool = Form(False),
    has_tree: bool = Form(False),
    has_campfire: bool = Form(False),
    image_url: str = Form(""),
    image: UploadFile = File(None),
    target_location_id: str = Form(""),
    target_x: str = Form(""),
    target_y: str = Form(""),
):
    async with async_session() as session:
        cell = await session.get(Cell, cell_id)
        if not cell:
            return RedirectResponse(url="/editor/locations")

        cell.name = name
        cell.description = description
        cell.tile_type = tile_type
        cell.is_passable = is_passable
        cell.has_npc = has_npc
        cell.npc_name = npc_name or None
        cell.npc_type = npc_type or None
        cell.npc_dialogue = npc_dialogue or None
        cell.has_chest = has_chest
        cell.has_house = has_house
        cell.has_tree = has_tree
        cell.has_campfire = has_campfire

        if target_location_id.strip():
            cell.target_location_id = int(target_location_id)
            cell.target_x = int(target_x) if target_x.strip() else None
            cell.target_y = int(target_y) if target_y.strip() else None
        else:
            cell.target_location_id = None
            cell.target_x = None
            cell.target_y = None

        if image and image.filename:
            ext = os.path.splitext(image.filename)[1] or ".png"
            filename = f"cell_{cell_id}{ext}"
            upload_dir = "admin/static/cells"
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, filename)
            with open(filepath, "wb") as f:
                shutil.copyfileobj(image.file, f)
            cell.image_url = f"/static/cells/{filename}"
        elif image_url:
            cell.image_url = image_url

        await session.commit()

        from core.map_renderer import get_cell_image_path
        cached = get_cell_image_path(cell_id)
        if os.path.exists(cached):
            os.remove(cached)

    return RedirectResponse(url=f"/editor/cell/{cell_id}", status_code=303)


# ── World Map Editor ───────────────────────────────────────

@app.get("/editor/world")
async def editor_world(request: Request):
    async with async_session() as session:
        result = await session.execute(select(Location).order_by(Location.id))
        locations = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "editor_world.html",
        {"locations": locations},
    )


# ── Mobs Editor ────────────────────────────────────────────

@app.get("/editor/mobs")
async def editor_mobs(request: Request):
    async with async_session() as session:
        result = await session.execute(
            select(Mob).options(selectinload(Mob.location)).order_by(Mob.id)
        )
        mobs = result.scalars().all()
        result = await session.execute(select(Location).order_by(Location.id))
        locations = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "editor_mobs.html",
        {"mobs": mobs, "locations": locations},
    )


@app.post("/editor/mobs/new")
async def mob_new(
    name: str = Form(...),
    description: str = Form(""),
    level: int = Form(1),
    hp: int = Form(30),
    damage: int = Form(5),
    defense: int = Form(2),
    gold_reward: int = Form(10),
    exp_reward: int = Form(15),
    location_id: int = Form(None),
    is_boss: bool = Form(False),
    spawn_chance: float = Form(0.3),
):
    async with async_session() as session:
        mob = Mob(
            name=name, description=description, level=level, hp=hp,
            damage=damage, defense=defense, gold_reward=gold_reward,
            exp_reward=exp_reward, location_id=location_id,
            is_boss=is_boss, spawn_chance=spawn_chance,
        )
        session.add(mob)
        await session.commit()
    return RedirectResponse(url="/editor/mobs", status_code=303)


@app.post("/editor/mobs/{mob_id}/edit")
async def mob_edit(
    mob_id: int,
    name: str = Form(...),
    description: str = Form(""),
    level: int = Form(1),
    hp: int = Form(30),
    damage: int = Form(5),
    defense: int = Form(2),
    gold_reward: int = Form(10),
    exp_reward: int = Form(15),
    location_id: int = Form(None),
    is_boss: bool = Form(False),
    spawn_chance: float = Form(0.3),
):
    async with async_session() as session:
        mob = await session.get(Mob, mob_id)
        if mob:
            mob.name = name
            mob.description = description
            mob.level = level
            mob.hp = hp
            mob.damage = damage
            mob.defense = defense
            mob.gold_reward = gold_reward
            mob.exp_reward = exp_reward
            mob.location_id = location_id
            mob.is_boss = is_boss
            mob.spawn_chance = spawn_chance
            await session.commit()
    return RedirectResponse(url="/editor/mobs", status_code=303)


@app.post("/editor/mobs/{mob_id}/delete")
async def mob_delete(mob_id: int):
    async with async_session() as session:
        await session.execute(delete(Mob).where(Mob.id == mob_id))
        await session.commit()
    return RedirectResponse(url="/editor/mobs", status_code=303)


# ── Quests Editor ──────────────────────────────────────────

@app.get("/editor/quests")
async def editor_quests(request: Request):
    async with async_session() as session:
        result = await session.execute(
            select(Quest).options(selectinload(Quest.reward_item)).order_by(Quest.id)
        )
        quests = result.scalars().all()
        result = await session.execute(select(Item).order_by(Item.id))
        items = result.scalars().all()
        result = await session.execute(select(Location).order_by(Location.id))
        locations = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "editor_quests.html",
        {"quests": quests, "items": items, "locations": locations},
    )


@app.post("/editor/quests/new")
async def quest_new(
    name: str = Form(...),
    description: str = Form(""),
    objective_type: str = Form("kill"),
    objective_target: str = Form(""),
    objective_count: int = Form(1),
    reward_gold: int = Form(0),
    reward_exp: int = Form(0),
    reward_item_id: str = Form(""),
    min_level: int = Form(1),
    location_id: str = Form(""),
    npc_name: str = Form(""),
):
    async with async_session() as session:
        q = Quest(
            name=name, description=description, objective_type=objective_type,
            objective_target=objective_target, objective_count=objective_count,
            reward_gold=reward_gold, reward_exp=reward_exp,
            reward_item_id=int(reward_item_id) if reward_item_id.strip() else None,
            min_level=min_level,
            location_id=int(location_id) if location_id.strip() else None,
            npc_name=npc_name or None,
        )
        session.add(q)
        await session.commit()
    return RedirectResponse(url="/editor/quests", status_code=303)


@app.post("/editor/quests/{quest_id}/edit")
async def quest_edit(
    quest_id: int,
    name: str = Form(...),
    description: str = Form(""),
    objective_type: str = Form("kill"),
    objective_target: str = Form(""),
    objective_count: int = Form(1),
    reward_gold: int = Form(0),
    reward_exp: int = Form(0),
    reward_item_id: str = Form(""),
    min_level: int = Form(1),
    location_id: str = Form(""),
    npc_name: str = Form(""),
):
    async with async_session() as session:
        q = await session.get(Quest, quest_id)
        if q:
            q.name = name
            q.description = description
            q.objective_type = objective_type
            q.objective_target = objective_target
            q.objective_count = objective_count
            q.reward_gold = reward_gold
            q.reward_exp = reward_exp
            q.reward_item_id = int(reward_item_id) if reward_item_id.strip() else None
            q.min_level = min_level
            q.location_id = int(location_id) if location_id.strip() else None
            q.npc_name = npc_name or None
            await session.commit()
    return RedirectResponse(url="/editor/quests", status_code=303)


@app.post("/editor/quests/{quest_id}/delete")
async def quest_delete(quest_id: int):
    async with async_session() as session:
        await session.execute(delete(Quest).where(Quest.id == quest_id))
        await session.commit()
    return RedirectResponse(url="/editor/quests", status_code=303)


# ── NPC Editor (cells with NPCs) ───────────────────────────

@app.get("/editor/npcs")
async def editor_npcs(request: Request):
    async with async_session() as session:
        result = await session.execute(
            select(Cell).where(Cell.has_npc == True).options(selectinload(Cell.location))
        )
        npc_cells = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "editor_npcs.html",
        {"npc_cells": npc_cells},
    )


# ── Update from Git ────────────────────────────────────────

@app.post("/api/update")
async def api_update():
    import subprocess
    import sys
    import threading
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, cwd=os.getcwd(), timeout=30
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        if success and "Already up to date" not in output and "Уже обновлено" not in output:
            # Schedule auto-restart in 3 seconds so the HTTP response can be sent first
            def _restart():
                import os
                os.execv(sys.executable, [sys.executable, "launch.py"])
            threading.Timer(3.0, _restart).start()
            return {"success": True, "output": output, "restarting": True}
        return {"success": success, "output": output, "restarting": False}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    import uvicorn
    uvicorn.run(
        "admin.main:app",
        host=settings.ADMIN_HOST,
        port=settings.ADMIN_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
