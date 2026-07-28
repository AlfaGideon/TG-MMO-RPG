import os
import shutil
import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from core.database import init_db, async_session
from core.migrations import run_migrations
from core.models import (
    User, Character, Location, Mob, Item, ShopItem, Battle, AppSetting, Cell,
    Quest, AdminMessage, InventoryItem, VisitedCell, DungeonTemplate, DungeonRun,
)
from core.enums import LocationType, ItemType, ItemRarity, QuestStatus
from admin.config import settings
from admin import auth as webauth
from bot.runner import bot_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    await run_migrations()
    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == "bot_token")
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value and setting.value.strip():
            await bot_runner.start(setting.value.strip())
    yield
    if bot_runner.is_running():
        await bot_runner.stop()


app = FastAPI(title="Shadow Lands Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="admin/static"), name="static")
templates = Jinja2Templates(directory="admin/templates")

PUBLIC_PATHS = {"/admin-login", "/admin-logout"}


class RoleMiddleware(BaseHTTPMiddleware):
    """Attaches request.state.role: None means unrestricted (owner) access,
    otherwise one of viewer/moderator/admin for a granted web-admin session."""

    async def dispatch(self, request: Request, call_next):
        session = webauth.get_web_session(request)
        request.state.role = session[1] if session else None
        request.state.web_user_id = session[0] if session else None
        response = await call_next(request)
        return response


app.add_middleware(RoleMiddleware)


@app.exception_handler(HTTPException)
async def access_denied_handler(request: Request, exc: HTTPException):
    if exc.status_code == 403:
        return templates.TemplateResponse(
            request, "access_denied.html", {"detail": exc.detail}, status_code=403
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


def guard(request: Request, cap: str):
    """Raise 403 if the current session (granted web-admin role) lacks `cap`.
    Direct/owner access (no cookie) always passes."""
    role = getattr(request.state, "role", None)
    if not webauth.has_capability(role, cap):
        raise HTTPException(status_code=403, detail=f"Недостаточно прав для этого действия (нужна роль с доступом «{cap}»).")


# ── Web-admin login (for granted access) ────────────────────

@app.get("/admin-login")
async def admin_login_page(request: Request, uid: str = ""):
    return templates.TemplateResponse(request, "login.html", {"uid": uid, "error": None})


@app.post("/admin-login")
async def admin_login_submit(request: Request, uid: str = Form(...), password: str = Form(...)):
    try:
        telegram_id = int(uid.strip())
    except ValueError:
        return templates.TemplateResponse(
            request, "login.html", {"uid": uid, "error": "Некорректный Telegram ID."}
        )

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

    if (
        not user
        or not user.is_web_admin
        or not user.web_admin_password_hash
        or not webauth.verify_password(password, user.web_admin_password_hash)
    ):
        return templates.TemplateResponse(
            request, "login.html", {"uid": uid, "error": "Неверный Telegram ID или пароль."}
        )

    token = webauth.make_session_token(user.id, user.web_admin_role or "viewer")
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(
        webauth.COOKIE_NAME, token,
        max_age=webauth.SESSION_MAX_AGE, httponly=True, samesite="lax",
    )
    return resp


@app.get("/admin-logout")
async def admin_logout():
    resp = RedirectResponse(url="/admin-login", status_code=303)
    resp.delete_cookie(webauth.COOKIE_NAME)
    return resp


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
        result = await session.execute(
            select(Character)
            .where(Character.id == char_id)
            .options(selectinload(Character.user), selectinload(Character.location))
        )
        char = result.scalar_one_or_none()
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
        result = await session.execute(select(Item).order_by(Item.id))
        all_items = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "player_detail.html",
        {
            "char": char, "inventory": inventory, "messages": messages,
            "all_items": all_items, "role_labels": webauth.ROLE_LABELS, "roles": webauth.ROLES,
        },
    )


def save_uploaded_image(image: UploadFile, entity_type: str, entity_id: int, fallback_url: str = "") -> str:
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1] or ".png"
        filename = f"{entity_type}_{entity_id}{ext}"
        upload_dir = f"admin/static/uploads/{entity_type}"
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as f:
            shutil.copyfileobj(image.file, f)
        return f"/static/uploads/{entity_type}/{filename}"
    elif fallback_url and fallback_url.strip():
        return fallback_url.strip()
    return ""


@app.post("/player/{char_id}/edit")
async def player_edit(
    request: Request,
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
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    guard(request, "manage_players")
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
            if image and image.filename:
                char.image_url = save_uploaded_image(image, "character", char.id)
            elif image_url.strip():
                char.image_url = image_url.strip()
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/give-item")
async def player_give_item(request: Request, char_id: int, item_id: int = Form(...), quantity: int = Form(1)):
    guard(request, "manage_players")
    async with async_session() as session:
        char = await session.get(Character, char_id)
        item = await session.get(Item, item_id)
        if char and item:
            inv = InventoryItem(character_id=char.id, item_id=item.id, quantity=quantity)
            session.add(inv)
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/send-message")
async def player_send_message(request: Request, char_id: int, text: str = Form(...)):
    guard(request, "manage_players")
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


# ── VIP & Web-admin access grants ───────────────────────────

@app.post("/player/{char_id}/grant-vip")
async def player_grant_vip(request: Request, char_id: int, vip_days: int = Form(30)):
    guard(request, "manage_players")
    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char:
            char.is_vip = True
            char.vip_until = datetime.utcnow() + timedelta(days=max(1, vip_days))
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/revoke-vip")
async def player_revoke_vip(request: Request, char_id: int):
    guard(request, "manage_players")
    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char:
            char.is_vip = False
            char.vip_until = None
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/grant-admin")
async def player_grant_admin(request: Request, char_id: int, role: str = Form("viewer")):
    """Grants the player web-admin access with a chosen role, generates a fresh
    password, and (if the bot is running) sends them an inline button linking to
    the login page along with the plaintext password."""
    guard(request, "manage_admins")
    if role not in webauth.ROLES:
        role = "viewer"

    plain_password = webauth.generate_password()

    async with async_session() as session:
        char = await session.get(Character, char_id)
        if not char:
            return RedirectResponse(url="/players", status_code=303)

        user = await session.get(User, char.user_id)
        user.is_web_admin = True
        user.web_admin_role = role
        user.web_admin_password_hash = webauth.hash_password(plain_password)
        user.web_admin_granted_at = datetime.utcnow()
        await session.commit()

        telegram_id = user.telegram_id

        try:
            from bot.runner import bot_runner
            if bot_runner.is_running() and bot_runner.bot:
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                base_url = str(request.base_url).rstrip("/")
                login_url = f"{base_url}/admin-login?uid={telegram_id}"
                builder = InlineKeyboardBuilder()
                builder.button(text="🔑 Открыть веб-админку", url=login_url)
                role_label = webauth.ROLE_LABELS.get(role, role)
                await bot_runner.bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        "👑 <b>Тебе выдан доступ к веб-админке!</b>\n\n"
                        f"Роль: {role_label}\n"
                        f"Telegram ID (логин): <code>{telegram_id}</code>\n"
                        f"Пароль: <code>{plain_password}</code>\n\n"
                        "Нажми кнопку ниже, чтобы войти."
                    ),
                    parse_mode="HTML",
                    reply_markup=builder.as_markup(),
                )
        except Exception:
            pass

    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/revoke-admin")
async def player_revoke_admin(request: Request, char_id: int):
    guard(request, "manage_admins")
    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char:
            user = await session.get(User, char.user_id)
            user.is_web_admin = False
            user.web_admin_role = None
            user.web_admin_password_hash = None
            await session.commit()
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
    request: Request,
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
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    guard(request, "manage_content")
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
            if image and image.filename:
                item.image_url = save_uploaded_image(image, "item", item.id)
            elif image_url.strip():
                item.image_url = image_url.strip()
            await session.commit()
    return RedirectResponse(url="/items", status_code=303)


@app.post("/item/new")
async def item_new(
    request: Request,
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
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    guard(request, "manage_content")
    async with async_session() as session:
        item = Item(
            name=name, description=description, item_type=ItemType(item_type),
            rarity=ItemRarity(rarity), level_requirement=level_requirement, price=price,
            bonus_strength=bonus_strength, bonus_agility=bonus_agility,
            bonus_intelligence=bonus_intelligence, bonus_endurance=bonus_endurance,
            bonus_luck=bonus_luck, bonus_hp=bonus_hp, bonus_mp=bonus_mp,
            bonus_damage=bonus_damage, bonus_defense=bonus_defense, icon=icon,
            image_url=image_url.strip(),
        )
        session.add(item)
        await session.flush()
        if image and image.filename:
            item.image_url = save_uploaded_image(image, "item", item.id)
        await session.commit()
    return RedirectResponse(url="/items", status_code=303)


@app.post("/item/{item_id}/delete")
async def item_delete(request: Request, item_id: int):
    guard(request, "manage_content")
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
    guard(request, "manage_settings")
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
    guard(request, "manage_settings")
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
async def api_bot_start(request: Request):
    guard(request, "manage_settings")
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
async def api_bot_stop(request: Request):
    guard(request, "manage_settings")
    ok = await bot_runner.stop()
    return {"success": ok, "running": bot_runner.is_running()}


@app.get("/api/bot/status")
async def api_bot_status():
    return {"running": bot_runner.is_running()}


# ── Content Hub ────────────────────────────────────────────

@app.get("/content")
async def content_hub(request: Request):
    guard(request, "manage_content")
    async with async_session() as session:
        total_locations = await session.scalar(select(func.count(Location.id))) or 0
        total_mobs = await session.scalar(select(func.count(Mob.id))) or 0
        total_npcs = await session.scalar(select(func.count(Cell.id)).where(Cell.has_npc == True)) or 0
        total_quests = await session.scalar(select(func.count(Quest.id))) or 0
        total_items = await session.scalar(select(func.count(Item.id))) or 0
        total_dungeons = await session.scalar(select(func.count(DungeonTemplate.id))) or 0
    return templates.TemplateResponse(
        request,
        "content.html",
        {
            "total_locations": total_locations,
            "total_mobs": total_mobs,
            "total_npcs": total_npcs,
            "total_quests": total_quests,
            "total_items": total_items,
            "total_dungeons": total_dungeons,
        },
    )


# ── Location Editor ────────────────────────────────────────

@app.get("/editor/locations")
async def editor_locations(request: Request):
    guard(request, "manage_content")
    async with async_session() as session:
        result = await session.execute(select(Location).order_by(Location.id))
        locations = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "editor_locations.html",
        {"locations": locations},
    )


@app.get("/editor/location/new")
async def editor_location_new_page(request: Request, world_x: int = 0, world_y: int = 0):
    guard(request, "manage_content")
    return templates.TemplateResponse(request, "editor_location_new.html", {"world_x": world_x, "world_y": world_y})


@app.post("/editor/location/new")
async def editor_location_new(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    location_type: str = Form("safe"),
    min_level: int = Form(1),
    grid_size: int = Form(10),
    floors_count: int = Form(1),
    world_x: int = Form(0),
    world_y: int = Form(0),
):
    guard(request, "manage_content")
    from core.seed import CELL_STORIES
    async with async_session() as session:
        loc = Location(
            name=name, description=description,
            location_type=LocationType(location_type),
            min_level=min_level, grid_size=grid_size,
            floors_count=max(1, floors_count),
            world_x=world_x, world_y=world_y,
        )
        session.add(loc)
        await session.flush()

        # Generate cells for every floor
        story_idx = random.randint(0, len(CELL_STORIES) - 1)
        for floor in range(loc.floors_count):
            cells = []
            for x in range(grid_size):
                for y in range(grid_size):
                    is_border = (x == 0 or x == grid_size - 1 or y == 0 or y == grid_size - 1)
                    is_wall = is_border or (not is_border and random.random() < 0.15 and (x, y) != (5, 5))
                    name_s, desc_s, tile = CELL_STORIES[story_idx % len(CELL_STORIES)]
                    story_idx += 1
                    cell = Cell(
                        location_id=loc.id, x=x, y=y, floor=floor,
                        name=name_s, description=desc_s,
                        is_passable=not is_wall,
                        tile_type=tile if not is_wall else "wall",
                    )
                    session.add(cell)
                    cells.append(cell)
            # Stairs between floors: place at spawn cell (5,5) if grid supports it
            if loc.floors_count > 1 and grid_size > 6:
                pass  # linked after all floors are flushed, below
        await session.flush()

        # Link consecutive floors via a staircase at (5,5) <-> (5,5)
        if loc.floors_count > 1:
            for floor in range(loc.floors_count - 1):
                result = await session.execute(
                    select(Cell).where(Cell.location_id == loc.id).where(Cell.floor == floor)
                    .where(Cell.x == 5).where(Cell.y == 5)
                )
                down_cell = result.scalar_one_or_none()
                result = await session.execute(
                    select(Cell).where(Cell.location_id == loc.id).where(Cell.floor == floor + 1)
                    .where(Cell.x == 5).where(Cell.y == 5)
                )
                up_cell = result.scalar_one_or_none()
                if down_cell and up_cell:
                    down_cell.is_passable = True
                    down_cell.tile_type = "road"
                    down_cell.target_location_id = loc.id
                    down_cell.target_x = 5
                    down_cell.target_y = 5
                    down_cell.target_floor = floor + 1
                    up_cell.is_passable = True
                    up_cell.tile_type = "road"

        await session.commit()
    return RedirectResponse(url=f"/editor/location/{loc.id}", status_code=303)


@app.post("/editor/location/{location_id}/delete")
async def editor_location_delete(request: Request, location_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(delete(Location).where(Location.id == location_id))
        await session.commit()
    return RedirectResponse(url="/editor/locations", status_code=303)


@app.get("/editor/location/{location_id}")
async def editor_location(request: Request, location_id: int, floor: int = 0):
    guard(request, "manage_content")
    async with async_session() as session:
        location = await session.get(Location, location_id)
        if not location:
            return RedirectResponse(url="/editor/locations")

        result = await session.execute(
            select(Cell).where(Cell.location_id == location_id).where(Cell.floor == floor)
        )
        cells = result.scalars().all()
        cells_dict = {(c.x, c.y): c for c in cells}

    return templates.TemplateResponse(
        request,
        "editor_location.html",
        {"location": location, "cells_dict": cells_dict, "current_floor": floor,
         "floors_range": range(location.floors_count or 1)},
    )


@app.post("/editor/location/{location_id}/save")
async def editor_location_save(
    request: Request,
    location_id: int,
    name: str = Form(...),
    description: str = Form(""),
    location_type: str = Form(...),
    min_level: int = Form(1),
    grid_size: int = Form(10),
    floors_count: int = Form(1),
    world_x: int = Form(0),
    world_y: int = Form(0),
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    guard(request, "manage_content")
    async with async_session() as session:
        location = await session.get(Location, location_id)
        if location:
            location.name = name
            location.description = description
            location.location_type = LocationType(location_type)
            location.min_level = min_level
            location.grid_size = grid_size
            location.floors_count = max(1, floors_count)
            location.world_x = world_x
            location.world_y = world_y
            if image and image.filename:
                location.image_url = save_uploaded_image(image, "location", location.id)
            elif image_url.strip():
                location.image_url = image_url.strip()
            await session.commit()
    return RedirectResponse(url=f"/editor/location/{location_id}", status_code=303)


@app.get("/editor/cell/{cell_id}")
async def editor_cell(request: Request, cell_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        cell = await session.get(Cell, cell_id)
        if not cell:
            return RedirectResponse(url="/editor/locations")

        result = await session.execute(select(Location).order_by(Location.id))
        all_locations = result.scalars().all()

        result = await session.execute(
            select(DungeonTemplate).where(DungeonTemplate.is_active == True).order_by(DungeonTemplate.id)
        )
        dungeon_templates = result.scalars().all()

        neighbors = {}
        for dir_name, (dx, dy) in {"Север": (-1, 0), "Юг": (1, 0), "Запад": (0, -1), "Восток": (0, 1)}.items():
            result = await session.execute(
                select(Cell)
                .where(Cell.location_id == cell.location_id)
                .where(Cell.floor == (cell.floor or 0))
                .where(Cell.x == cell.x + dx)
                .where(Cell.y == cell.y + dy)
            )
            neighbors[dir_name] = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "editor_cell.html",
        {"cell": cell, "neighbors": neighbors, "all_locations": all_locations,
         "dungeon_templates": dungeon_templates},
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
    target_floor: str = Form(""),
    dungeon_template_id: str = Form(""),
):
    guard(request, "manage_content")
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
        cell.dungeon_template_id = int(dungeon_template_id) if dungeon_template_id.strip() else None

        if target_location_id.strip():
            cell.target_location_id = int(target_location_id)
            cell.target_x = int(target_x) if target_x.strip() else None
            cell.target_y = int(target_y) if target_y.strip() else None
            cell.target_floor = int(target_floor) if target_floor.strip() else 0
        else:
            cell.target_location_id = None
            cell.target_x = None
            cell.target_y = None
            cell.target_floor = None

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

WORLD_GRID_SIZE = 10  # 10x10 locations of up to 10x10 cells => up to 100x100 world


@app.get("/editor/world")
async def editor_world(request: Request):
    guard(request, "manage_content")
    async with async_session() as session:
        result = await session.execute(select(Location).order_by(Location.id))
        locations = result.scalars().all()
        result = await session.execute(
            select(func.count(Character.id), Character.location_id)
            .group_by(Character.location_id)
        )
        pop_by_loc = {row[1]: row[0] for row in result.all()}

    grid = {(loc.world_x, loc.world_y): loc for loc in locations if 0 <= loc.world_x < WORLD_GRID_SIZE and 0 <= loc.world_y < WORLD_GRID_SIZE}

    return templates.TemplateResponse(
        request,
        "editor_world.html",
        {
            "locations": locations, "grid": grid, "grid_range": range(WORLD_GRID_SIZE),
            "world_grid_size": WORLD_GRID_SIZE, "pop_by_loc": pop_by_loc,
        },
    )


@app.post("/editor/world/place")
async def editor_world_place(request: Request, location_id: int = Form(...), world_x: int = Form(...), world_y: int = Form(...)):
    guard(request, "manage_content")
    async with async_session() as session:
        loc = await session.get(Location, location_id)
        if loc:
            loc.world_x = max(0, min(WORLD_GRID_SIZE - 1, world_x))
            loc.world_y = max(0, min(WORLD_GRID_SIZE - 1, world_y))
            await session.commit()
    return RedirectResponse(url="/editor/world", status_code=303)


# ── Mobs Editor ────────────────────────────────────────────

@app.get("/editor/mobs")
async def editor_mobs(request: Request):
    guard(request, "manage_content")
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
    request: Request,
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
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    guard(request, "manage_content")
    async with async_session() as session:
        mob = Mob(
            name=name, description=description, level=level, hp=hp,
            damage=damage, defense=defense, gold_reward=gold_reward,
            exp_reward=exp_reward, location_id=location_id,
            is_boss=is_boss, spawn_chance=spawn_chance,
            image_url=image_url.strip(),
        )
        session.add(mob)
        await session.flush()
        if image and image.filename:
            mob.image_url = save_uploaded_image(image, "mob", mob.id)
        await session.commit()
    return RedirectResponse(url="/editor/mobs", status_code=303)


@app.post("/editor/mobs/{mob_id}/edit")
async def mob_edit(
    request: Request,
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
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    guard(request, "manage_content")
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
            if image and image.filename:
                mob.image_url = save_uploaded_image(image, "mob", mob.id)
            elif image_url.strip():
                mob.image_url = image_url.strip()
            await session.commit()
    return RedirectResponse(url="/editor/mobs", status_code=303)


@app.post("/editor/mobs/{mob_id}/delete")
async def mob_delete(request: Request, mob_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(delete(Mob).where(Mob.id == mob_id))
        await session.commit()
    return RedirectResponse(url="/editor/mobs", status_code=303)


# ── Quests Editor ──────────────────────────────────────────

@app.get("/editor/quests")
async def editor_quests(request: Request):
    guard(request, "manage_content")
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
    request: Request,
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
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    guard(request, "manage_content")
    async with async_session() as session:
        q = Quest(
            name=name, description=description, objective_type=objective_type,
            objective_target=objective_target, objective_count=objective_count,
            reward_gold=reward_gold, reward_exp=reward_exp,
            reward_item_id=int(reward_item_id) if reward_item_id.strip() else None,
            min_level=min_level,
            location_id=int(location_id) if location_id.strip() else None,
            npc_name=npc_name or None,
            image_url=image_url.strip(),
        )
        session.add(q)
        await session.flush()
        if image and image.filename:
            q.image_url = save_uploaded_image(image, "quest", q.id)
        await session.commit()
    return RedirectResponse(url="/editor/quests", status_code=303)


@app.post("/editor/quests/{quest_id}/edit")
async def quest_edit(
    request: Request,
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
    image_url: str = Form(""),
    image: UploadFile = File(None),
):
    guard(request, "manage_content")
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
            if image and image.filename:
                q.image_url = save_uploaded_image(image, "quest", q.id)
            elif image_url.strip():
                q.image_url = image_url.strip()
            await session.commit()
    return RedirectResponse(url="/editor/quests", status_code=303)


@app.post("/editor/quests/{quest_id}/delete")
async def quest_delete(request: Request, quest_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(delete(Quest).where(Quest.id == quest_id))
        await session.commit()
    return RedirectResponse(url="/editor/quests", status_code=303)


# ── NPC Editor (cells with NPCs) ───────────────────────────

@app.get("/editor/npcs")
async def editor_npcs(request: Request):
    guard(request, "manage_content")
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


# ── Shop Editor ──────────────────────────────────────────────

@app.post("/shop/add")
async def shop_add(request: Request, item_id: int = Form(...), price: int = Form(0), stock: int = Form(-1)):
    guard(request, "manage_content")
    async with async_session() as session:
        session.add(ShopItem(item_id=item_id, price=price, stock=stock))
        await session.commit()
    return RedirectResponse(url="/items#shop", status_code=303)


@app.post("/shop/{shop_item_id}/edit")
async def shop_edit(request: Request, shop_item_id: int, price: int = Form(0), stock: int = Form(-1)):
    guard(request, "manage_content")
    async with async_session() as session:
        si = await session.get(ShopItem, shop_item_id)
        if si:
            si.price = price
            si.stock = stock
            await session.commit()
    return RedirectResponse(url="/items#shop", status_code=303)


@app.post("/shop/{shop_item_id}/delete")
async def shop_delete(request: Request, shop_item_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(delete(ShopItem).where(ShopItem.id == shop_item_id))
        await session.commit()
    return RedirectResponse(url="/items#shop", status_code=303)


# ── Dungeon Templates Editor (procedural, standalone from the 100x100 world) ──

@app.get("/editor/dungeons")
async def editor_dungeons(request: Request):
    guard(request, "manage_content")
    async with async_session() as session:
        result = await session.execute(select(DungeonTemplate).order_by(DungeonTemplate.id))
        templates_list = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "editor_dungeons.html",
        {"dungeon_templates": templates_list},
    )


@app.post("/editor/dungeons/new")
async def dungeon_template_new(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    grid_size: int = Form(25),
    floors_count: int = Form(1),
    min_level: int = Form(1),
    wall_chance: float = Form(0.22),
    chest_chance: float = Form(0.06),
    mob_chance: float = Form(0.18),
    mob_level_min: int = Form(1),
    mob_level_max: int = Form(5),
    mob_pool: str = Form(""),
    image_url: str = Form(""),
):
    guard(request, "manage_content")
    async with async_session() as session:
        session.add(DungeonTemplate(
            name=name, description=description, grid_size=grid_size,
            floors_count=max(1, floors_count), min_level=min_level,
            wall_chance=wall_chance, chest_chance=chest_chance, mob_chance=mob_chance,
            mob_level_min=mob_level_min, mob_level_max=mob_level_max,
            mob_pool=mob_pool, image_url=image_url.strip(), is_active=True,
        ))
        await session.commit()
    return RedirectResponse(url="/editor/dungeons", status_code=303)


@app.post("/editor/dungeons/{template_id}/edit")
async def dungeon_template_edit(
    request: Request,
    template_id: int,
    name: str = Form(...),
    description: str = Form(""),
    grid_size: int = Form(25),
    floors_count: int = Form(1),
    min_level: int = Form(1),
    wall_chance: float = Form(0.22),
    chest_chance: float = Form(0.06),
    mob_chance: float = Form(0.18),
    mob_level_min: int = Form(1),
    mob_level_max: int = Form(5),
    mob_pool: str = Form(""),
    image_url: str = Form(""),
    is_active: bool = Form(False),
):
    guard(request, "manage_content")
    async with async_session() as session:
        tpl = await session.get(DungeonTemplate, template_id)
        if tpl:
            tpl.name = name
            tpl.description = description
            tpl.grid_size = grid_size
            tpl.floors_count = max(1, floors_count)
            tpl.min_level = min_level
            tpl.wall_chance = wall_chance
            tpl.chest_chance = chest_chance
            tpl.mob_chance = mob_chance
            tpl.mob_level_min = mob_level_min
            tpl.mob_level_max = mob_level_max
            tpl.mob_pool = mob_pool
            tpl.image_url = image_url.strip()
            tpl.is_active = is_active
            await session.commit()
    return RedirectResponse(url="/editor/dungeons", status_code=303)


@app.post("/editor/dungeons/{template_id}/delete")
async def dungeon_template_delete(request: Request, template_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(delete(DungeonTemplate).where(DungeonTemplate.id == template_id))
        await session.commit()
    return RedirectResponse(url="/editor/dungeons", status_code=303)


# ── Players Map (who is where) ──────────────────────────────

@app.get("/map")
async def players_map(request: Request):
    async with async_session() as session:
        result = await session.execute(select(Location).order_by(Location.world_x, Location.world_y))
        locations = result.scalars().all()

        result = await session.execute(
            select(Character.location_id, Character.floor, func.count(Character.id))
            .group_by(Character.location_id, Character.floor)
        )
        pop_rows = result.all()
        pop_by_loc = {}
        for loc_id, floor, cnt in pop_rows:
            pop_by_loc.setdefault(loc_id, {})[floor or 0] = cnt

        result = await session.execute(
            select(Character)
            .options(selectinload(Character.location), selectinload(Character.user))
            .order_by(Character.location_id, Character.floor, Character.name)
        )
        characters = result.scalars().all()

    grid = {(loc.world_x, loc.world_y): loc for loc in locations if 0 <= loc.world_x < WORLD_GRID_SIZE and 0 <= loc.world_y < WORLD_GRID_SIZE}
    total_online_proxy = sum(sum(f.values()) for f in pop_by_loc.values())

    return templates.TemplateResponse(
        request,
        "players_map.html",
        {
            "locations": locations, "grid": grid, "grid_range": range(WORLD_GRID_SIZE),
            "pop_by_loc": pop_by_loc, "characters": characters,
            "total_characters": total_online_proxy,
        },
    )


# ── Update from Git ────────────────────────────────────────

@app.post("/api/update")
async def api_update(request: Request):
    guard(request, "manage_settings")
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
