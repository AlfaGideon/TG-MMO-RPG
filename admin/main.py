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
from sqlalchemy import select, func, delete, String
from sqlalchemy.orm import selectinload

from core.database import init_db, async_session
from core.migrations import run_migrations
from core.models import (
    User, Character, Location, Mob, Item, ShopItem, Battle, AppSetting, Cell,
    Quest, AdminMessage, InventoryItem, VisitedCell, DungeonTemplate, DungeonRun,
    CharacterClassDef, ItemInstance, DropEntry, CraftRecipe, CraftIngredient,
    UpgradeRule, MobSpawn, ItemHistory, AuctionLot, CharacterAffinity,
)
from core.enums import (
    LocationType, ItemType, ItemRarity, QuestStatus, ItemSource, CraftStation,
    AuctionStatus, MagicSchool, AFFINITY_GRADES, MAGIC_SCHOOLS, SOURCE_BADGES,
    SOURCE_LABELS,
)
from admin.config import settings
from admin import auth as webauth
from bot.runner import bot_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    await run_migrations()
    try:
        from core.seed_content import seed_content
        from core.spawns import ensure_all_populations
        async with async_session() as session:
            await seed_content(session)
            await ensure_all_populations(session)
            await session.commit()
    except Exception:
        pass
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

# Подписи слотов экипировки и бонусов — используются шаблонами редактора
SLOT_LABELS = {
    "weapon": "⚔️ Оружие", "armor": "🦺 Броня", "helmet": "🪖 Шлем",
    "boots": "👢 Сапоги", "accessory": "💍 Аксессуар",
}

BONUS_LABELS = {
    "bonus_strength": "💪", "bonus_agility": "🏃", "bonus_intelligence": "🧠",
    "bonus_endurance": "🛡", "bonus_luck": "🍀", "bonus_hp": "❤️",
    "bonus_mp": "💙", "bonus_damage": "⚔️", "bonus_defense": "🛡",
}

BONUS_FIELDS = tuple(BONUS_LABELS.keys())


def paginate(total: int, page: int, per_page: int):
    """Возвращает словарь с метаданными пагинации."""
    page = max(1, page)
    per_page = max(5, min(100, per_page))
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages) if total else 1
    offset = (page - 1) * per_page
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "offset": offset,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


STATION_LABELS = {
    "forge": "🔨 Кузница", "alchemy": "⚗️ Алхимия",
    "jewelry": "💎 Ювелир", "any": "🛠 Любой станок",
}


class RoleMiddleware(BaseHTTPMiddleware):
    """Attaches request.state.role: None means unrestricted (owner) access,
    otherwise one of viewer/moderator/admin for a granted web-admin session."""

    async def dispatch(self, request: Request, call_next):
        session = webauth.get_web_session(request)
        request.state.role = session[1] if session else None
        request.state.web_user_id = session[0] if session else None
        request.state.caps = None

        # Точечные права хранятся у пользователя — подтягиваем их на каждый
        # запрос, чтобы изменения применялись без перелогина.
        if session:
            try:
                async with async_session() as db:
                    user = await db.get(User, session[0])
                    if user is None or not user.is_web_admin:
                        resp = RedirectResponse(url="/admin-login", status_code=303)
                        resp.delete_cookie(webauth.COOKIE_NAME)
                        return resp
                    request.state.caps = user.web_admin_caps
                    request.state.role = user.web_admin_role or session[1]
            except Exception:
                pass

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
    caps = getattr(request.state, "caps", None)
    if not webauth.has_capability(role, cap, caps):
        label = webauth.CAP_LABELS.get(cap, cap)
        raise HTTPException(
            status_code=403,
            detail=f"Недостаточно прав для этого действия (нужен доступ «{label}»).",
        )


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
    from core.auction import sweep_expired
    from core.dungeons import is_portal_open
    from datetime import datetime

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

        # ── Chart data ──
        # Players by level (buckets)
        result = await session.execute(
            select(Character.level, func.count(Character.id))
            .group_by(Character.level)
            .order_by(Character.level)
        )
        levels_chart = [(lvl, cnt) for lvl, cnt in result.all()]

        # Gold by location
        result = await session.execute(
            select(Location.name, func.coalesce(func.sum(Character.gold), 0))
            .outerjoin(Character, Character.location_id == Location.id)
            .group_by(Location.id)
            .order_by(func.coalesce(func.sum(Character.gold), 0).desc())
            .limit(10)
        )
        gold_by_location = [(name, int(g or 0)) for name, g in result.all()]

        # Items by rarity
        result = await session.execute(
            select(Item.rarity, func.count(Item.id))
            .group_by(Item.rarity)
        )
        items_by_rarity = {r.value: c for r, c in result.all()}

        # Battle results distribution
        result = await session.execute(
            select(Battle.result, func.count(Battle.id))
            .group_by(Battle.result)
        )
        battle_results = {r.value: c for r, c in result.all()}

        # ── Health panel ──
        await sweep_expired(session)
        await session.commit()

        result = await session.execute(
            select(Location).outerjoin(Character, Character.location_id == Location.id)
            .group_by(Location.id)
            .having(func.count(Character.id) == 0)
        )
        empty_locations = result.scalars().all()

        result = await session.execute(
            select(Mob).outerjoin(
                MobSpawn,
                (MobSpawn.mob_id == Mob.id) & (MobSpawn.is_alive == True)  # noqa: E712
            )
            .group_by(Mob.id)
            .having(func.count(MobSpawn.id) == 0)
        )
        mobs_no_spawns = result.scalars().all()

        result = await session.execute(
            select(AuctionLot)
            .where(AuctionLot.status == AuctionStatus.EXPIRED.value)
            .order_by(AuctionLot.id.desc())
            .limit(10)
        )
        expired_lots = result.scalars().all()

        open_dungeons = await session.scalar(
            select(func.count(DungeonTemplate.id))
            .where(DungeonTemplate.portal_closed_at.is_(None))
            .where(DungeonTemplate.portal_opened_at.isnot(None))
        ) or 0

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
            "levels_chart": levels_chart,
            "gold_by_location": gold_by_location,
            "items_by_rarity": items_by_rarity,
            "battle_results": battle_results,
            "empty_locations": empty_locations,
            "mobs_no_spawns": mobs_no_spawns,
            "expired_lots": expired_lots,
            "open_dungeons": open_dungeons,
            "bot_running": bot_runner.is_running(),
        },
    )


# ── Players ────────────────────────────────────────────────

@app.get("/players")
async def players(request: Request, page: int = 1, q: str = ""):
    per_page = 25
    async with async_session() as session:
        base_query = select(Character).options(
            selectinload(Character.user), selectinload(Character.location)
        )
        if q.strip():
            needle = f"%{q.strip()}%"
            base_query = base_query.where(Character.name.ilike(needle))

        total = await session.scalar(
            select(func.count(Character.id)).select_from(base_query.subquery())
        ) or 0
        meta = paginate(total, page, per_page)

        result = await session.execute(
            base_query.order_by(Character.level.desc())
            .offset(meta["offset"]).limit(per_page)
        )
        chars = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "players.html",
        {"players": chars, "pagination": meta, "q": q},
    )


@app.get("/player/{char_id}")
async def player_detail(request: Request, char_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Character)
            .where(Character.id == char_id)
            .options(
                selectinload(Character.user),
                selectinload(Character.location),
                selectinload(Character.cell),
            )
        )
        char = result.scalar_one_or_none()
        if not char:
            return RedirectResponse(url="/players")
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == char_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
            .order_by(InventoryItem.is_equipped.desc(), InventoryItem.id)
        )
        inventory = result.scalars().all()
        result = await session.execute(
            select(AdminMessage)
            .where(AdminMessage.user_id == char.user_id)
            .order_by(AdminMessage.created_at.desc())
            .limit(50)
        )
        messages = result.scalars().all()
        result = await session.execute(select(Item).order_by(Item.name))
        all_items = result.scalars().all()
        result = await session.execute(select(Location).order_by(Location.id))
        all_locations = result.scalars().all()

        from core.classes import all_classes as list_classes, get_class
        from core.stats import combat_stats
        from core import magic
        classes = await list_classes(session, only_enabled=False)
        class_def = await get_class(session, char.character_class)
        totals = await combat_stats(session, char)
        affinities = await magic.get_affinities(session, char.id)

    equipped_by_slot = {
        inv.item.item_type.value: inv
        for inv in inventory if inv.is_equipped and inv.item
    }
    active_caps = webauth.caps_for(char.user.web_admin_role, char.user.web_admin_caps) \
        if char.user.is_web_admin else set()

    return templates.TemplateResponse(
        request,
        "player_detail.html",
        {
            "char": char, "inventory": inventory, "messages": messages,
            "all_items": all_items, "role_labels": webauth.ROLE_LABELS,
            "roles": webauth.ROLES, "caps": webauth.CAPS,
            "cap_groups": webauth.CAP_GROUPS, "active_caps": active_caps,
            "rank_presets": {r: webauth.rank_caps(r) for r in webauth.ROLES},
            "all_classes": classes, "class_def": class_def,
            "all_locations": all_locations, "totals": totals,
            "equipped_by_slot": equipped_by_slot,
            "slot_labels": SLOT_LABELS, "bonus_labels": BONUS_LABELS,
            "rarities": [r.value for r in ItemRarity],
            "affinities": affinities,
            "schools": [(k, v[0], v[1]) for k, v in MAGIC_SCHOOLS.items()],
            "grades": [(k, v[0]) for k, v in AFFINITY_GRADES.items()],
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
    character_class: str = Form(""),
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
    location_id: int = Form(None),
    floor: int = Form(0),
    cell_x: int = Form(None),
    cell_y: int = Form(None),
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
            if character_class.strip():
                char.character_class = character_class.strip()
            char.level = max(1, level)
            char.gold = max(0, gold)
            char.experience = max(0, experience)
            char.strength = strength
            char.agility = agility
            char.intelligence = intelligence
            char.endurance = endurance
            char.luck = luck
            char.max_hp = max(1, max_hp)
            char.max_mp = max(0, max_mp)
            char.current_hp = min(max(0, current_hp), char.max_hp)
            char.current_mp = min(max(0, current_mp), char.max_mp)
            char.is_vip = is_vip

            # Перенос по миру: ищем указанную клетку, иначе любую проходимую
            if location_id:
                char.location_id = location_id
                char.floor = max(0, floor or 0)
                target = None
                if cell_x is not None and cell_y is not None:
                    result = await session.execute(
                        select(Cell)
                        .where(Cell.location_id == location_id)
                        .where(Cell.floor == char.floor)
                        .where(Cell.x == cell_x).where(Cell.y == cell_y)
                    )
                    target = result.scalar_one_or_none()
                if target is None:
                    result = await session.execute(
                        select(Cell)
                        .where(Cell.location_id == location_id)
                        .where(Cell.floor == char.floor)
                        .where(Cell.is_passable == True)  # noqa: E712
                        .limit(1)
                    )
                    target = result.scalar_one_or_none()
                if target is not None:
                    char.cell_id = target.id

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


@app.get("/player/{char_id}/heal")
async def player_heal(request: Request, char_id: int):
    """Быстрое восстановление HP/MP до максимума."""
    guard(request, "manage_players")
    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char:
            char.current_hp = char.max_hp
            char.current_mp = char.max_mp
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/affinities")
async def player_set_affinities(
    request: Request, char_id: int,
    school1: str = Form(""), grade1: str = Form("normal"),
    school2: str = Form(""), grade2: str = Form("normal"),
):
    """Правка магического дара героя: до двух школ."""
    guard(request, "manage_players")
    from core import magic

    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char:
            pairs = []
            if school1.strip():
                pairs.append((school1.strip(), grade1))
            if school2.strip() and school2.strip() != school1.strip():
                pairs.append((school2.strip(), grade2))
            await magic.set_affinities(session, char, pairs)
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/reroll-stats")
async def player_reroll_stats(request: Request, char_id: int, grant: int = Form(0)):
    """Перекатывает статы героя заново или выдаёт ему попытки переката."""
    guard(request, "manage_players")
    from core import statroll
    from core.classes import get_class

    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char:
            if grant > 0:
                # Просто выдаём попытки — игрок перекатает сам в боте
                char.rerolls_left = grant
                char.stats_locked = False
            else:
                cls_def = await get_class(session, char.character_class)
                if cls_def is not None:
                    statroll.apply_stats(char, statroll.roll_stats(cls_def.base_stats()))
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/give-item")
async def player_give_item(
    request: Request, char_id: int,
    item_id: int = Form(...), quantity: int = Form(1),
    roll_stats: str = Form(""),
):
    """Выдаёт предмет игроку.

    С `roll_stats` предмет получает уникальный ID и статы с разбросом —
    как выпавший из моба. Без него создаётся ровно по шаблону.
    """
    guard(request, "manage_players")
    from core.loot import grant_item, create_instance, is_stackable

    async with async_session() as session:
        char = await session.get(Character, char_id)
        item = await session.get(Item, item_id)
        if not char or not item:
            return RedirectResponse(url=f"/player/{char_id}", status_code=303)

        if roll_stats:
            await grant_item(
                session, char, item, max(1, quantity),
                source=ItemSource.ADMIN.value, source_detail="Выдано админом",
            )
        elif is_stackable(item):
            result = await session.execute(
                select(InventoryItem)
                .where(InventoryItem.character_id == char.id)
                .where(InventoryItem.item_id == item.id)
                .where(InventoryItem.instance_id.is_(None))
            )
            row = result.scalar_one_or_none()
            if row:
                row.quantity = (row.quantity or 0) + max(1, quantity)
            else:
                session.add(InventoryItem(
                    character_id=char.id, item_id=item.id, quantity=max(1, quantity),
                ))
        else:
            # Точная копия шаблона: качество ровно 100 %, без префикса
            for _ in range(max(1, quantity)):
                inst = create_instance(
                    item, source=ItemSource.ADMIN.value,
                    source_detail="Выдано админом (по шаблону)",
                    force_quality=100,
                )
                inst.prefix = ""
                for field in BONUS_FIELDS:
                    setattr(inst, field, getattr(item, field) or 0)
                inst.rarity = item.rarity
                session.add(inst)
                await session.flush()
                session.add(InventoryItem(
                    character_id=char.id, item_id=item.id,
                    instance_id=inst.id, quantity=1,
                ))

        await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/inv/{inv_id}/edit")
async def player_inv_edit(
    request: Request, char_id: int, inv_id: int,
    bonus_strength: int = Form(0), bonus_agility: int = Form(0),
    bonus_intelligence: int = Form(0), bonus_endurance: int = Form(0),
    bonus_luck: int = Form(0), bonus_hp: int = Form(0), bonus_mp: int = Form(0),
    bonus_damage: int = Form(0), bonus_defense: int = Form(0),
    quality: int = Form(100), upgrade_level: int = Form(0),
    rarity: str = Form("common"), prefix: str = Form(""),
):
    """Правка статов конкретного экземпляра предмета в сумке игрока."""
    guard(request, "manage_players")
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.instance))
        )
        inv = result.scalar_one_or_none()
        if inv and inv.instance:
            inst = inv.instance
            inst.bonus_strength = bonus_strength
            inst.bonus_agility = bonus_agility
            inst.bonus_intelligence = bonus_intelligence
            inst.bonus_endurance = bonus_endurance
            inst.bonus_luck = bonus_luck
            inst.bonus_hp = bonus_hp
            inst.bonus_mp = bonus_mp
            inst.bonus_damage = bonus_damage
            inst.bonus_defense = bonus_defense
            inst.quality = max(1, min(300, quality))
            inst.upgrade_level = max(0, upgrade_level)
            inst.prefix = prefix.strip()
            try:
                inst.rarity = ItemRarity(rarity)
            except ValueError:
                pass
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}#inv", status_code=303)


@app.post("/player/{char_id}/inv/{inv_id}/reroll")
async def player_inv_reroll(request: Request, char_id: int, inv_id: int):
    """Перекатывает статы экземпляра заново по шаблону предмета."""
    guard(request, "manage_players")
    from core.loot import create_instance

    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(
                selectinload(InventoryItem.item),
                selectinload(InventoryItem.instance),
            )
        )
        inv = result.scalar_one_or_none()
        if inv and inv.instance and inv.item:
            fresh = create_instance(inv.item, source=inv.instance.source)
            inst = inv.instance
            for field in BONUS_FIELDS:
                setattr(inst, field, getattr(fresh, field))
            inst.quality = fresh.quality
            inst.rarity = fresh.rarity
            inst.prefix = fresh.prefix
            inst.upgrade_level = 0
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/inv/{inv_id}/toggle-equip")
async def player_inv_toggle_equip(request: Request, char_id: int, inv_id: int):
    """Надеть/снять предмет. Занятый слот освобождается автоматически."""
    guard(request, "manage_players")
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.item))
        )
        inv = result.scalar_one_or_none()
        if inv and inv.item:
            if inv.is_equipped:
                inv.is_equipped = False
            elif inv.item.item_type == ItemType.CONSUMABLE or \
                    inv.item.item_type == ItemType.MATERIAL:
                pass  # расходники и материалы не надеваются
            else:
                result = await session.execute(
                    select(InventoryItem)
                    .where(InventoryItem.character_id == inv.character_id)
                    .where(InventoryItem.is_equipped == True)  # noqa: E712
                    .options(selectinload(InventoryItem.item))
                )
                for other in result.scalars().all():
                    if other.item and other.item.item_type == inv.item.item_type:
                        other.is_equipped = False
                inv.is_equipped = True
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/inv/{inv_id}/delete")
async def player_inv_delete(request: Request, char_id: int, inv_id: int):
    guard(request, "manage_players")
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.id == inv_id)
            .options(selectinload(InventoryItem.instance))
        )
        inv = result.scalar_one_or_none()
        if inv:
            instance = inv.instance
            await session.delete(inv)
            if instance is not None:
                await session.delete(instance)
            await session.commit()
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/clear-inventory")
async def player_clear_inventory(request: Request, char_id: int):
    guard(request, "manage_players")
    async with async_session() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.character_id == char_id)
            .options(selectinload(InventoryItem.instance))
        )
        for inv in result.scalars().all():
            instance = inv.instance
            await session.delete(inv)
            if instance is not None:
                await session.delete(instance)
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
async def player_grant_admin(
    request: Request,
    char_id: int,
    role: str = Form("viewer"),
    caps: list[str] = Form(default=[]),
    new_password: str = Form(""),
):
    """Grants web-admin access with a rank preset plus optional per-function
    capabilities, always (re)generates a password when there isn't one, and
    notifies the player in the bot with login + password + capability list."""
    guard(request, "grant_admin")
    if role not in webauth.ROLES:
        role = "viewer"

    picked = [c for c in caps if c in webauth.ALL_CAPS]

    async with async_session() as session:
        char = await session.get(Character, char_id)
        if not char:
            return RedirectResponse(url="/players", status_code=303)

        user = await session.get(User, char.user_id)
        rotate = bool(new_password) or not user.web_admin_password
        plain_password = webauth.generate_password() if rotate else user.web_admin_password

        user.is_web_admin = True
        user.web_admin_role = role
        user.web_admin_caps = ",".join(picked)
        user.web_admin_password = plain_password
        user.web_admin_password_hash = webauth.hash_password(plain_password)
        user.web_admin_granted_at = datetime.utcnow()
        await session.commit()

        telegram_id = user.telegram_id
        granted = webauth.caps_for(role, user.web_admin_caps)

    cap_list = "\n".join(
        f"• {webauth.CAP_LABELS[k]}" for k in webauth.CAP_KEYS if k in granted) or "—"

    from core.settings_store import get_panel_url, build_login_url
    # Адрес из настроек; если не задан — берём тот, с которого открыта панель
    login_url = build_login_url(await get_panel_url() or str(request.base_url),
                                telegram_id)

    try:
        from bot.runner import bot_runner
        if bot_runner.is_running() and bot_runner.bot:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            if login_url:
                builder.button(text="🔑 Открыть веб-админку", url=login_url)
            await bot_runner.bot.send_message(
                chat_id=telegram_id,
                text=(
                    "👑 <b>Тебе выдан доступ к админ-панели!</b>\n\n"
                    f"Ранг: {webauth.ROLE_LABELS.get(role, role)}\n"
                    f"Логин (Telegram ID): <code>{telegram_id}</code>\n"
                    f"Пароль: <code>{plain_password}</code>\n\n"
                    f"<b>Твои права:</b>\n{cap_list}\n\n"
                    "Кнопка «🛠 Админка» появилась в меню бота — там всегда "
                    "можно посмотреть пароль заново."
                ),
                parse_mode="HTML",
                reply_markup=builder.as_markup() if login_url else None,
            )
    except Exception:
        pass

    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


@app.post("/player/{char_id}/revoke-admin")
async def player_revoke_admin(request: Request, char_id: int):
    guard(request, "grant_admin")
    telegram_id = None
    async with async_session() as session:
        char = await session.get(Character, char_id)
        if char:
            user = await session.get(User, char.user_id)
            user.is_web_admin = False
            user.web_admin_role = None
            user.web_admin_caps = None
            user.web_admin_password = None
            user.web_admin_password_hash = None
            await session.commit()
            telegram_id = user.telegram_id

    if telegram_id:
        try:
            from bot.runner import bot_runner
            if bot_runner.is_running() and bot_runner.bot:
                await bot_runner.bot.send_message(
                    chat_id=telegram_id,
                    text=("🚫 <b>Доступ к админ-панели отозван.</b>\n\n"
                          "<i>Кнопка «🛠 Админка» больше не доступна.</i>"),
                    parse_mode="HTML",
                )
        except Exception:
            pass
    return RedirectResponse(url=f"/player/{char_id}", status_code=303)


# ── Items ──────────────────────────────────────────────────

@app.get("/items")
async def items(request: Request, page: int = 1, q: str = ""):
    per_page = 25
    async with async_session() as session:
        base_query = select(Item)
        if q.strip():
            needle = f"%{q.strip()}%"
            base_query = base_query.where(Item.name.ilike(needle))

        total = await session.scalar(
            select(func.count(Item.id)).select_from(base_query.subquery())
        ) or 0
        meta = paginate(total, page, per_page)

        result = await session.execute(
            base_query.order_by(Item.id).offset(meta["offset"]).limit(per_page)
        )
        all_items = result.scalars().all()

        result = await session.execute(
            select(ShopItem).options(selectinload(ShopItem.item)).order_by(ShopItem.id)
        )
        shop_items = result.scalars().all()

        # Сколько уникальных экземпляров каждого шаблона гуляет по игре
        result = await session.execute(
            select(ItemInstance.item_id, func.count(ItemInstance.id))
            .group_by(ItemInstance.item_id)
        )
        instance_counts = {row[0]: row[1] for row in result.all()}

    # Для выпадающего списка «Добавить в лавку» нужны все предметы
    all_items_result = await session.execute(select(Item).order_by(Item.name))
    all_items_for_shop = all_items_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "items.html",
        {
            "items": all_items, "all_items": all_items_for_shop,
            "shop_items": shop_items, "instance_counts": instance_counts,
            "pagination": meta, "q": q,
        },
    )


@app.get("/item/{item_id}/edit")
async def item_edit_page(request: Request, item_id: int):
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            return RedirectResponse(url="/items")

        # Последние выпущенные экземпляры — видно, какие статы реально катаются
        instance_count = await session.scalar(
            select(func.count(ItemInstance.id)).where(ItemInstance.item_id == item_id)
        ) or 0
        result = await session.execute(
            select(ItemInstance, Character)
            .outerjoin(InventoryItem, InventoryItem.instance_id == ItemInstance.id)
            .outerjoin(Character, Character.id == InventoryItem.character_id)
            .where(ItemInstance.item_id == item_id)
            .order_by(ItemInstance.id.desc())
            .limit(25)
        )
        instances = [(inst, owner) for inst, owner in result.all()]

    return templates.TemplateResponse(
        request, "item_edit.html",
        {
            "item": item, "instances": instances, "instance_count": instance_count,
            "schools": [(k, v[0], v[1]) for k, v in MAGIC_SCHOOLS.items()],
        },
    )


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
    stat_variance: float = Form(0.15),
    is_unique_roll: bool = Form(False),
    is_sellable: bool = Form(False),
    max_upgrade_level: int = Form(10),
    is_one_of_a_kind: bool = Form(False),
    is_festive: bool = Form(False),
    festive_event: str = Form(""),
    magic_school: str = Form(""),
    magic_power: int = Form(0),
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
            item.stat_variance = max(0.0, min(0.6, stat_variance))
            item.is_unique_roll = is_unique_roll
            item.is_sellable = is_sellable
            item.max_upgrade_level = max(0, max_upgrade_level)
            item.is_one_of_a_kind = is_one_of_a_kind
            item.is_festive = is_festive
            item.festive_event = festive_event.strip()[:64]
            item.magic_school = magic_school.strip() or None
            item.magic_power = max(0, magic_power)
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
    stat_variance: float = Form(0.15),
    is_unique_roll: bool = Form(False),
    max_upgrade_level: int = Form(10),
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
            stat_variance=max(0.0, min(0.6, stat_variance)),
            is_unique_roll=is_unique_roll,
            max_upgrade_level=max(0, max_upgrade_level),
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
    """Удаляет шаблон вместе со всеми его экземплярами и ссылками на него."""
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(
            delete(InventoryItem).where(InventoryItem.item_id == item_id)
        )
        await session.execute(
            delete(ItemInstance).where(ItemInstance.item_id == item_id)
        )
        await session.execute(delete(DropEntry).where(DropEntry.item_id == item_id))
        await session.execute(
            delete(CraftIngredient).where(CraftIngredient.item_id == item_id)
        )
        await session.execute(delete(ShopItem).where(ShopItem.item_id == item_id))
        await session.execute(delete(Item).where(Item.id == item_id))
        await session.commit()
    return RedirectResponse(url="/items", status_code=303)


# ── Battles ────────────────────────────────────────────────

@app.get("/battles")
async def battles(request: Request, page: int = 1):
    per_page = 50
    async with async_session() as session:
        total = await session.scalar(select(func.count(Battle.id))) or 0
        meta = paginate(total, page, per_page)
        result = await session.execute(
            select(Battle)
            .options(selectinload(Battle.character), selectinload(Battle.mob))
            .order_by(Battle.id.desc())
            .offset(meta["offset"]).limit(per_page)
        )
        rows = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "battles.html",
        {"battles": rows, "pagination": meta},
    )


# ── Settings / Bot Control ─────────────────────────────────

@app.get("/settings")
async def settings_page(request: Request):
    guard(request, "settings")
    from core.settings_store import get_panel_url, build_login_url

    async with async_session() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == "bot_token")
        )
        setting = result.scalar_one_or_none()
        token_masked = ""
        if setting and setting.value:
            t = setting.value
            token_masked = t[:10] + "..." + t[-6:] if len(t) > 20 else "***"

    panel_url = await get_panel_url()
    # Подсказываем адрес, с которого админ сейчас смотрит панель
    detected = str(request.base_url).rstrip("/")

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "token_masked": token_masked,
            "bot_running": bot_runner.is_running(),
            "panel_url": panel_url,
            "detected_url": detected,
            "example_login_url": build_login_url(panel_url or detected, 123456789),
        },
    )


@app.post("/settings/save-panel-url")
async def save_panel_url(request: Request, panel_url: str = Form("")):
    """Адрес, по которому открывается панель снаружи. Именно он подставляется
    в инлайн-кнопку «🌐 Открыть панель» в боте."""
    guard(request, "settings")
    from core.settings_store import set_panel_url

    await set_panel_url(panel_url)
    return RedirectResponse(url="/settings", status_code=303)


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


# ── Dashboard Quick Actions ────────────────────────────────

@app.post("/api/heal-all")
async def api_heal_all(request: Request):
    guard(request, "manage_players")
    async with async_session() as session:
        result = await session.execute(select(Character))
        chars = result.scalars().all()
        for char in chars:
            char.current_hp = char.max_hp
            char.current_mp = char.max_mp
        await session.commit()
    return {"success": True, "healed": len(chars)}


@app.post("/api/respawn-all")
async def api_respawn_all(request: Request):
    guard(request, "manage_content")
    from core.spawns import ensure_all_populations
    async with async_session() as session:
        result = await session.execute(
            select(MobSpawn).where(MobSpawn.is_alive == False)  # noqa: E712
        )
        for spawn in result.scalars().all():
            spawn.respawn_at = datetime.utcnow() - timedelta(seconds=1)
        await session.flush()
        await ensure_all_populations(session)
        await session.commit()
    return {"success": True}


@app.post("/api/broadcast")
async def api_broadcast(request: Request, text: str = Form(...)):
    guard(request, "broadcast")
    if not text.strip():
        return {"success": False, "error": "Пустое сообщение."}

    notified = 0
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    if bot_runner.is_running() and bot_runner.bot:
        for user in users:
            try:
                await bot_runner.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"📢 <b>Сообщение от администрации:</b>\n\n{text.strip()}",
                    parse_mode="HTML",
                )
                notified += 1
            except Exception:
                pass

    return {"success": True, "notified": notified}


@app.post("/api/open-portal")
async def api_open_portal(request: Request):
    guard(request, "manage_content")
    from core.dungeons import sweep_expired_portals
    async with async_session() as session:
        await sweep_expired_portals(session)
        result = await session.execute(
            select(DungeonTemplate).where(DungeonTemplate.is_active == True)
        )
        templates_list = result.scalars().all()
        if not templates_list:
            return {"success": False, "error": "Нет активных шаблонов подземелий."}

        tpl = random.choice(templates_list)
        result = await session.execute(
            select(Cell).where(Cell.dungeon_template_id == tpl.id)
        )
        for cell in result.scalars().all():
            cell.dungeon_template_id = None
            if cell.tile_type == "portal":
                cell.tile_type = "road"

        portal_cell = await _open_dungeon_portal(session, tpl)
        await session.commit()

        if portal_cell and bot_runner.is_running() and bot_runner.bot:
            try:
                from bot.broadcast import notify_dungeon_portal_opened
                await notify_dungeon_portal_opened(
                    bot_runner.bot,
                    portal_cell.location.name,
                    portal_cell.x, portal_cell.y, portal_cell.floor or 0,
                    tpl.name, tpl.image_url,
                )
            except Exception:
                pass

    return {"success": True, "template": tpl.name if tpl else None}


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
        total_classes = await session.scalar(select(func.count(CharacterClassDef.id))) or 0
        total_drops = await session.scalar(select(func.count(DropEntry.id))) or 0
        total_recipes = await session.scalar(select(func.count(CraftRecipe.id))) or 0
        total_spawns = await session.scalar(
            select(func.count(MobSpawn.id)).where(MobSpawn.is_alive == True)  # noqa: E712
        ) or 0
        total_instances = await session.scalar(select(func.count(ItemInstance.id))) or 0
        total_unique = await session.scalar(
            select(func.count(Item.id)).where(Item.is_one_of_a_kind == True)  # noqa: E712
        ) or 0
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
            "total_classes": total_classes,
            "total_drops": total_drops,
            "total_recipes": total_recipes,
            "total_spawns": total_spawns,
            "total_instances": total_instances,
            "total_unique": total_unique,
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
        await session.refresh(cell, ["location"])

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
    npc_station: str = Form(""),
    npc_dialogue: str = Form(""),
    has_chest: bool = Form(False),
    chest_tier: int = Form(1),
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
        cell.npc_station = npc_station or None
        cell.npc_dialogue = npc_dialogue or None
        cell.has_chest = has_chest
        cell.chest_tier = max(1, chest_tier)
        if not has_chest:
            cell.chest_respawn_at = None
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
    population: int = Form(3),
    respawn_seconds: int = Form(120),
    move_interval_seconds: int = Form(45),
    can_roam: bool = Form(False),
    roam_radius: int = Form(1),
    gold_min: int = Form(0),
    gold_max: int = Form(0),
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
            population=max(0, population),
            respawn_seconds=max(5, respawn_seconds),
            move_interval_seconds=max(0, move_interval_seconds),
            can_roam=can_roam, roam_radius=max(0, roam_radius),
            gold_min=max(0, gold_min), gold_max=max(0, gold_max),
            image_url=image_url.strip(),
        )
        session.add(mob)
        await session.flush()
        if image and image.filename:
            mob.image_url = save_uploaded_image(image, "mob", mob.id)
        await session.commit()

        # Сразу наполняем локацию живыми экземплярами до лимита
        from core.spawns import ensure_population
        await ensure_population(session, mob)
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
    population: int = Form(3),
    respawn_seconds: int = Form(120),
    move_interval_seconds: int = Form(45),
    can_roam: bool = Form(False),
    roam_radius: int = Form(1),
    gold_min: int = Form(0),
    gold_max: int = Form(0),
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
            old_location = mob.location_id
            mob.location_id = location_id
            mob.is_boss = is_boss
            mob.spawn_chance = spawn_chance
            mob.population = max(0, population)
            mob.respawn_seconds = max(5, respawn_seconds)
            mob.move_interval_seconds = max(0, move_interval_seconds)
            mob.can_roam = can_roam
            mob.roam_radius = max(0, roam_radius)
            mob.gold_min = max(0, gold_min)
            mob.gold_max = max(0, gold_max)
            if image and image.filename:
                mob.image_url = save_uploaded_image(image, "mob", mob.id)
            elif image_url.strip():
                mob.image_url = image_url.strip()
            await session.commit()

            # Приводим живую популяцию к новому лимиту/локации
            from core.spawns import ensure_population
            result = await session.execute(
                select(MobSpawn)
                .where(MobSpawn.mob_id == mob.id)
                .where(MobSpawn.is_alive == True)  # noqa: E712
                .order_by(MobSpawn.id.desc())
            )
            alive = result.scalars().all()
            if old_location != mob.location_id:
                # Переехал в другую локацию — старые экземпляры убираем
                for spawn in alive:
                    await session.delete(spawn)
                alive = []
            for spawn in alive[:max(0, len(alive) - mob.population)]:
                await session.delete(spawn)
            await session.flush()
            await ensure_population(session, mob)
            await session.commit()
    return RedirectResponse(url="/editor/mobs", status_code=303)


@app.post("/editor/mobs/{mob_id}/delete")
async def mob_delete(request: Request, mob_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        # Живые экземпляры и таблица лута умирают вместе с мобом
        await session.execute(delete(MobSpawn).where(MobSpawn.mob_id == mob_id))
        await session.execute(
            delete(DropEntry)
            .where(DropEntry.owner_type == "mob")
            .where(DropEntry.owner_id == mob_id)
        )
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
        from core.dungeons import sweep_expired_portals, is_portal_open

        await sweep_expired_portals(session)
        await session.commit()

        result = await session.execute(select(DungeonTemplate).order_by(DungeonTemplate.id))
        templates_list = result.scalars().all()

        result = await session.execute(
            select(Cell).options(selectinload(Cell.location)).where(Cell.dungeon_template_id.isnot(None))
        )
        portal_by_template = {c.dungeon_template_id: c for c in result.scalars().all()}
        portal_open_by_template = {tpl.id: is_portal_open(tpl) for tpl in templates_list}
    return templates.TemplateResponse(
        request,
        "editor_dungeons.html",
        {
            "dungeon_templates": templates_list,
            "portal_by_template": portal_by_template,
            "portal_open_by_template": portal_open_by_template,
        },
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
        tpl = DungeonTemplate(
            name=name, description=description, grid_size=grid_size,
            floors_count=max(1, floors_count), min_level=min_level,
            wall_chance=wall_chance, chest_chance=chest_chance, mob_chance=mob_chance,
            mob_level_min=mob_level_min, mob_level_max=mob_level_max,
            mob_pool=mob_pool, image_url=image_url.strip(), is_active=True,
        )
        session.add(tpl)
        await session.flush()

        portal_cell = await _open_dungeon_portal(session, tpl)
        await session.commit()

        if portal_cell:
            try:
                from bot.broadcast import notify_dungeon_portal_opened
                if bot_runner.is_running() and bot_runner.bot:
                    await notify_dungeon_portal_opened(
                        bot_runner.bot,
                        portal_cell.location.name,
                        portal_cell.x, portal_cell.y, portal_cell.floor or 0,
                        tpl.name, tpl.image_url,
                    )
            except Exception:
                pass

    return RedirectResponse(url="/editor/dungeons", status_code=303)


async def _open_dungeon_portal(session, template: DungeonTemplate):
    """Picks a random passable, otherwise-unremarkable cell somewhere in the
    world and turns it into this template's dungeon entrance. Returns the
    chosen Cell (with .location eagerly usable) or None if no cell was free.
    Marks the portal as freshly opened (resets the 2h auto-close timer)."""
    result = await session.execute(
        select(Cell)
        .options(selectinload(Cell.location))
        .where(Cell.is_passable == True)
        .where(Cell.dungeon_template_id.is_(None))
        .where(Cell.has_npc == False)
        .where(Cell.target_location_id.is_(None))
        .where(Cell.mob_id.is_(None))
    )
    candidates = result.scalars().all()
    if not candidates:
        return None

    cell = random.choice(candidates)
    cell.dungeon_template_id = template.id
    cell.tile_type = "portal"
    template.portal_opened_at = datetime.utcnow()
    template.portal_closed_at = None
    await session.flush()
    return cell


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


@app.post("/editor/dungeons/{template_id}/close-portal")
async def dungeon_template_close_portal(request: Request, template_id: int):
    """Soft-close: blocks new entries by removing the world-map portal cell,
    but leaves the template (and everyone already inside a run) untouched.
    Players already inside keep playing until they die or leave on their
    own, or until the 2h hard limit is reached automatically."""
    guard(request, "manage_content")
    async with async_session() as session:
        from core.dungeons import close_portal

        tpl = await session.get(DungeonTemplate, template_id)
        if tpl:
            await close_portal(session, tpl)
            await session.commit()

            try:
                from bot.broadcast import notify_dungeon_portal_closed
                if bot_runner.is_running() and bot_runner.bot:
                    await notify_dungeon_portal_closed(bot_runner.bot, tpl.name)
            except Exception:
                pass
    return RedirectResponse(url="/editor/dungeons", status_code=303)


@app.post("/editor/dungeons/{template_id}/delete")
async def dungeon_template_delete(request: Request, template_id: int):
    """Hard delete: removes the template entirely. Any characters currently
    inside will find their dungeon gone next time they act (treated the same
    as a portal that has fully expired)."""
    guard(request, "manage_content")
    async with async_session() as session:
        result = await session.execute(
            select(Cell).where(Cell.dungeon_template_id == template_id)
        )
        for cell in result.scalars().all():
            cell.dungeon_template_id = None
            if cell.tile_type == "portal":
                cell.tile_type = "road"
        await session.execute(delete(DungeonTemplate).where(DungeonTemplate.id == template_id))
        await session.commit()
    return RedirectResponse(url="/editor/dungeons", status_code=303)


@app.post("/editor/dungeons/{template_id}/open-portal")
async def dungeon_template_open_portal(request: Request, template_id: int):
    """Manually (re)opens a portal for this template at a new random cell,
    closing any previous portal it had. Notifies all players with the
    location."""
    guard(request, "manage_content")
    async with async_session() as session:
        tpl = await session.get(DungeonTemplate, template_id)
        if not tpl:
            return RedirectResponse(url="/editor/dungeons", status_code=303)

        result = await session.execute(
            select(Cell).where(Cell.dungeon_template_id == template_id)
        )
        for cell in result.scalars().all():
            cell.dungeon_template_id = None
            if cell.tile_type == "portal":
                cell.tile_type = "road"

        portal_cell = await _open_dungeon_portal(session, tpl)
        await session.commit()

        if portal_cell:
            try:
                from bot.broadcast import notify_dungeon_portal_opened
                if bot_runner.is_running() and bot_runner.bot:
                    await notify_dungeon_portal_opened(
                        bot_runner.bot,
                        portal_cell.location.name,
                        portal_cell.x, portal_cell.y, portal_cell.floor or 0,
                        tpl.name, tpl.image_url,
                    )
            except Exception:
                pass

    return RedirectResponse(url="/editor/dungeons", status_code=303)


# ── Character Classes Editor ────────────────────────────────

@app.get("/editor/classes")
async def editor_classes(request: Request):
    """Классы персонажей: стартовые статы и прирост за уровень."""
    guard(request, "manage_content")
    async with async_session() as session:
        result = await session.execute(
            select(CharacterClassDef).order_by(
                CharacterClassDef.sort_order, CharacterClassDef.id
            )
        )
        classes = result.scalars().all()

        # Сколько живых персонажей каждого класса — чтобы не удалить нужный
        result = await session.execute(
            select(Character.character_class, func.count(Character.id))
            .group_by(Character.character_class)
        )
        usage = {str(row[0]): row[1] for row in result.all()}

    return templates.TemplateResponse(
        request, "editor_classes.html",
        {
            "classes": classes, "usage": usage,
            "schools": [(k, v[0], v[1]) for k, v in MAGIC_SCHOOLS.items()],
        },
    )


def _class_payload(form: dict) -> dict:
    """Общий разбор формы класса для создания и редактирования."""
    return dict(
        name=form["name"].strip(),
        icon=(form.get("icon") or "⚔️").strip()[:16],
        description=(form.get("description") or "").strip(),
        base_strength=form["base_strength"], base_agility=form["base_agility"],
        base_intelligence=form["base_intelligence"],
        base_endurance=form["base_endurance"], base_luck=form["base_luck"],
        base_hp=max(1, form["base_hp"]), base_mp=max(0, form["base_mp"]),
        growth_strength=form["growth_strength"], growth_agility=form["growth_agility"],
        growth_intelligence=form["growth_intelligence"],
        growth_endurance=form["growth_endurance"], growth_luck=form["growth_luck"],
        growth_hp=form["growth_hp"], growth_mp=form["growth_mp"],
        image_url=(form.get("image_url") or "").strip(),
        is_enabled=form.get("is_enabled", True),
        sort_order=form.get("sort_order", 100),
        affinity_chance=max(0.0, min(1.0, form.get("affinity_chance", 0.5))),
        dual_affinity_chance=max(0.0, min(1.0, form.get("dual_affinity_chance", 0.12))),
        preferred_schools=",".join(form.get("preferred_schools", []) or []),
    )


@app.post("/editor/classes/new")
async def class_new(
    request: Request,
    key: str = Form(...),
    name: str = Form(...),
    icon: str = Form("⚔️"),
    description: str = Form(""),
    base_strength: int = Form(10), base_agility: int = Form(10),
    base_intelligence: int = Form(10), base_endurance: int = Form(10),
    base_luck: int = Form(10), base_hp: int = Form(100), base_mp: int = Form(50),
    growth_strength: int = Form(1), growth_agility: int = Form(1),
    growth_intelligence: int = Form(1), growth_endurance: int = Form(1),
    growth_luck: int = Form(0), growth_hp: int = Form(10), growth_mp: int = Form(5),
    image_url: str = Form(""), sort_order: int = Form(100),
    is_enabled: bool = Form(False),
    affinity_chance: float = Form(0.5),
    dual_affinity_chance: float = Form(0.12),
    preferred_schools: list[str] = Form(default=[]),
):
    """Добавляет новый класс — он сразу появится в боте при создании героя."""
    guard(request, "manage_content")
    slug = "".join(
        ch for ch in key.strip().lower().replace(" ", "_") if ch.isalnum() or ch == "_"
    )[:32]
    if not slug:
        return RedirectResponse(url="/editor/classes", status_code=303)

    async with async_session() as session:
        result = await session.execute(
            select(CharacterClassDef).where(CharacterClassDef.key == slug)
        )
        if result.scalar_one_or_none():
            # Ключ занят — не плодим дубликаты
            return RedirectResponse(url="/editor/classes?err=exists", status_code=303)

        session.add(CharacterClassDef(key=slug, **_class_payload(locals())))
        await session.commit()
    return RedirectResponse(url="/editor/classes", status_code=303)


@app.post("/editor/classes/{class_id}/edit")
async def class_edit(
    request: Request, class_id: int,
    name: str = Form(...), icon: str = Form("⚔️"), description: str = Form(""),
    base_strength: int = Form(10), base_agility: int = Form(10),
    base_intelligence: int = Form(10), base_endurance: int = Form(10),
    base_luck: int = Form(10), base_hp: int = Form(100), base_mp: int = Form(50),
    growth_strength: int = Form(1), growth_agility: int = Form(1),
    growth_intelligence: int = Form(1), growth_endurance: int = Form(1),
    growth_luck: int = Form(0), growth_hp: int = Form(10), growth_mp: int = Form(5),
    image_url: str = Form(""), sort_order: int = Form(100),
    is_enabled: bool = Form(False),
    affinity_chance: float = Form(0.5),
    dual_affinity_chance: float = Form(0.12),
    preferred_schools: list[str] = Form(default=[]),
):
    guard(request, "manage_content")
    async with async_session() as session:
        cls = await session.get(CharacterClassDef, class_id)
        if cls:
            for field, value in _class_payload(locals()).items():
                setattr(cls, field, value)
            await session.commit()
    return RedirectResponse(url="/editor/classes", status_code=303)


@app.post("/editor/classes/{class_id}/delete")
async def class_delete(request: Request, class_id: int):
    """Удаляет класс, если им никто не играет; иначе просто выключает."""
    guard(request, "manage_content")
    async with async_session() as session:
        cls = await session.get(CharacterClassDef, class_id)
        if cls:
            in_use = await session.scalar(
                select(func.count(Character.id))
                .where(Character.character_class == cls.key)
            ) or 0
            if in_use:
                cls.is_enabled = False
            else:
                await session.delete(cls)
            await session.commit()
    return RedirectResponse(url="/editor/classes", status_code=303)


# ── Drop Tables Editor (что выпадает из мобов и сундуков) ───

@app.get("/editor/drops")
async def editor_drops(request: Request, owner_type: str = "mob"):
    guard(request, "manage_content")
    if owner_type not in ("mob", "chest", "dungeon"):
        owner_type = "mob"

    async with async_session() as session:
        result = await session.execute(
            select(DropEntry)
            .options(selectinload(DropEntry.item))
            .where(DropEntry.owner_type == owner_type)
            .order_by(DropEntry.owner_id, DropEntry.chance.desc())
        )
        entries = result.scalars().all()

        result = await session.execute(select(Item).order_by(Item.name))
        items = result.scalars().all()
        result = await session.execute(select(Mob).order_by(Mob.level, Mob.id))
        mobs = result.scalars().all()
        result = await session.execute(select(Location).order_by(Location.id))
        locations = result.scalars().all()
        result = await session.execute(
            select(DungeonTemplate).order_by(DungeonTemplate.id)
        )
        dungeons = result.scalars().all()

    owners = {"mob": mobs, "chest": locations, "dungeon": dungeons}[owner_type]
    owner_names = {o.id: o.name for o in owners}

    grouped = {}
    for entry in entries:
        grouped.setdefault(entry.owner_id, []).append(entry)

    return templates.TemplateResponse(
        request, "editor_drops.html",
        {
            "owner_type": owner_type, "grouped": grouped, "items": items,
            "owners": owners, "owner_names": owner_names,
            "total": len(entries),
        },
    )


@app.post("/editor/drops/new")
async def drop_new(
    request: Request,
    owner_type: str = Form("mob"),
    owner_id: str = Form(""),
    item_id: int = Form(...),
    chance: float = Form(0.2),
    min_quantity: int = Form(1),
    max_quantity: int = Form(1),
    variance_bonus: float = Form(0.0),
):
    guard(request, "manage_content")
    async with async_session() as session:
        session.add(DropEntry(
            owner_type=owner_type,
            owner_id=int(owner_id) if owner_id.strip() else None,
            item_id=item_id,
            chance=max(0.0, min(1.0, chance)),
            min_quantity=max(1, min_quantity),
            max_quantity=max(max(1, min_quantity), max_quantity),
            variance_bonus=variance_bonus,
        ))
        await session.commit()
    return RedirectResponse(url=f"/editor/drops?owner_type={owner_type}", status_code=303)


@app.post("/editor/drops/{entry_id}/edit")
async def drop_edit(
    request: Request, entry_id: int,
    chance: float = Form(0.2),
    min_quantity: int = Form(1),
    max_quantity: int = Form(1),
    variance_bonus: float = Form(0.0),
):
    guard(request, "manage_content")
    async with async_session() as session:
        entry = await session.get(DropEntry, entry_id)
        owner_type = "mob"
        if entry:
            owner_type = entry.owner_type
            entry.chance = max(0.0, min(1.0, chance))
            entry.min_quantity = max(1, min_quantity)
            entry.max_quantity = max(entry.min_quantity, max_quantity)
            entry.variance_bonus = variance_bonus
            await session.commit()
    return RedirectResponse(url=f"/editor/drops?owner_type={owner_type}", status_code=303)


@app.post("/editor/drops/{entry_id}/delete")
async def drop_delete(request: Request, entry_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        entry = await session.get(DropEntry, entry_id)
        owner_type = entry.owner_type if entry else "mob"
        await session.execute(delete(DropEntry).where(DropEntry.id == entry_id))
        await session.commit()
    return RedirectResponse(url=f"/editor/drops?owner_type={owner_type}", status_code=303)


# ── Craft Editor (рецепты и правила заточки) ────────────────

@app.get("/editor/craft")
async def editor_craft(request: Request):
    guard(request, "manage_content")
    async with async_session() as session:
        result = await session.execute(
            select(CraftRecipe)
            .options(
                selectinload(CraftRecipe.result_item),
                selectinload(CraftRecipe.ingredients).selectinload(CraftIngredient.item),
            )
            .order_by(CraftRecipe.station, CraftRecipe.min_level, CraftRecipe.id)
        )
        recipes = result.scalars().all()

        result = await session.execute(
            select(UpgradeRule)
            .options(selectinload(UpgradeRule.material_item))
            .order_by(UpgradeRule.from_level)
        )
        rules = result.scalars().all()

        result = await session.execute(select(Item).order_by(Item.name))
        items = result.scalars().all()

        # Клетки с NPC-ремесленниками — чтобы видеть, где они стоят
        result = await session.execute(
            select(Cell)
            .options(selectinload(Cell.location))
            .where(Cell.npc_station.isnot(None))
        )
        crafters = result.scalars().all()

    return templates.TemplateResponse(
        request, "editor_craft.html",
        {
            "recipes": recipes, "rules": rules, "items": items,
            "crafters": crafters,
            "stations": [(s.value, STATION_LABELS[s.value]) for s in CraftStation],
        },
    )


@app.post("/editor/craft/new")
async def recipe_new(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    station: str = Form("forge"),
    result_item_id: int = Form(...),
    result_quantity: int = Form(1),
    gold_cost: int = Form(0),
    min_level: int = Form(1),
    success_chance: float = Form(1.0),
    quality_bonus: float = Form(0.0),
):
    guard(request, "manage_content")
    async with async_session() as session:
        session.add(CraftRecipe(
            name=name.strip(), description=description.strip(), station=station,
            result_item_id=result_item_id, result_quantity=max(1, result_quantity),
            gold_cost=max(0, gold_cost), min_level=max(1, min_level),
            success_chance=max(0.05, min(1.0, success_chance)),
            quality_bonus=quality_bonus, is_enabled=True,
        ))
        await session.commit()
    return RedirectResponse(url="/editor/craft", status_code=303)


@app.post("/editor/craft/{recipe_id}/edit")
async def recipe_edit(
    request: Request, recipe_id: int,
    name: str = Form(...),
    description: str = Form(""),
    station: str = Form("forge"),
    result_item_id: int = Form(...),
    result_quantity: int = Form(1),
    gold_cost: int = Form(0),
    min_level: int = Form(1),
    success_chance: float = Form(1.0),
    quality_bonus: float = Form(0.0),
    is_enabled: bool = Form(False),
):
    guard(request, "manage_content")
    async with async_session() as session:
        recipe = await session.get(CraftRecipe, recipe_id)
        if recipe:
            recipe.name = name.strip()
            recipe.description = description.strip()
            recipe.station = station
            recipe.result_item_id = result_item_id
            recipe.result_quantity = max(1, result_quantity)
            recipe.gold_cost = max(0, gold_cost)
            recipe.min_level = max(1, min_level)
            recipe.success_chance = max(0.05, min(1.0, success_chance))
            recipe.quality_bonus = quality_bonus
            recipe.is_enabled = is_enabled
            await session.commit()
    return RedirectResponse(url="/editor/craft", status_code=303)


@app.post("/editor/craft/{recipe_id}/delete")
async def recipe_delete(request: Request, recipe_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(
            delete(CraftIngredient).where(CraftIngredient.recipe_id == recipe_id)
        )
        await session.execute(delete(CraftRecipe).where(CraftRecipe.id == recipe_id))
        await session.commit()
    return RedirectResponse(url="/editor/craft", status_code=303)


@app.post("/editor/craft/{recipe_id}/ingredient/add")
async def ingredient_add(
    request: Request, recipe_id: int,
    item_id: int = Form(...), quantity: int = Form(1),
):
    guard(request, "manage_content")
    async with async_session() as session:
        session.add(CraftIngredient(
            recipe_id=recipe_id, item_id=item_id, quantity=max(1, quantity),
        ))
        await session.commit()
    return RedirectResponse(url="/editor/craft", status_code=303)


@app.post("/editor/craft/ingredient/{ing_id}/delete")
async def ingredient_delete(request: Request, ing_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(
            delete(CraftIngredient).where(CraftIngredient.id == ing_id)
        )
        await session.commit()
    return RedirectResponse(url="/editor/craft", status_code=303)


@app.post("/editor/craft/rules/new")
async def upgrade_rule_new(
    request: Request,
    from_level: int = Form(0), to_level: int = Form(1),
    gold_cost: int = Form(50),
    material_item_id: str = Form(""),
    material_quantity: int = Form(1),
    success_chance: float = Form(0.9),
    stat_gain_percent: float = Form(0.08),
    min_stat_gain: int = Form(1),
):
    guard(request, "manage_content")
    async with async_session() as session:
        session.add(UpgradeRule(
            from_level=max(0, from_level),
            to_level=max(from_level + 1, to_level),
            gold_cost=max(0, gold_cost),
            material_item_id=int(material_item_id) if material_item_id.strip() else None,
            material_quantity=max(0, material_quantity),
            success_chance=max(0.05, min(1.0, success_chance)),
            stat_gain_percent=max(0.0, stat_gain_percent),
            min_stat_gain=max(0, min_stat_gain),
        ))
        await session.commit()
    return RedirectResponse(url="/editor/craft#rules", status_code=303)


@app.post("/editor/craft/rules/{rule_id}/edit")
async def upgrade_rule_edit(
    request: Request, rule_id: int,
    from_level: int = Form(0), to_level: int = Form(1),
    gold_cost: int = Form(50),
    material_item_id: str = Form(""),
    material_quantity: int = Form(1),
    success_chance: float = Form(0.9),
    stat_gain_percent: float = Form(0.08),
    min_stat_gain: int = Form(1),
):
    guard(request, "manage_content")
    async with async_session() as session:
        rule = await session.get(UpgradeRule, rule_id)
        if rule:
            rule.from_level = max(0, from_level)
            rule.to_level = max(from_level + 1, to_level)
            rule.gold_cost = max(0, gold_cost)
            rule.material_item_id = int(material_item_id) if material_item_id.strip() else None
            rule.material_quantity = max(0, material_quantity)
            rule.success_chance = max(0.05, min(1.0, success_chance))
            rule.stat_gain_percent = max(0.0, stat_gain_percent)
            rule.min_stat_gain = max(0, min_stat_gain)
            await session.commit()
    return RedirectResponse(url="/editor/craft#rules", status_code=303)


@app.post("/editor/craft/rules/{rule_id}/delete")
async def upgrade_rule_delete(request: Request, rule_id: int):
    guard(request, "manage_content")
    async with async_session() as session:
        await session.execute(delete(UpgradeRule).where(UpgradeRule.id == rule_id))
        await session.commit()
    return RedirectResponse(url="/editor/craft#rules", status_code=303)


# ── Mob population control ──────────────────────────────────

@app.get("/editor/spawns")
async def editor_spawns(request: Request):
    """Живая популяция мобов на карте: кто где стоит и когда воскреснет."""
    guard(request, "manage_content")
    from core.spawns import population_report

    async with async_session() as session:
        report = await population_report(session)
        result = await session.execute(
            select(MobSpawn)
            .options(
                selectinload(MobSpawn.mob),
                selectinload(MobSpawn.location),
                selectinload(MobSpawn.home_location),
            )
            .where(MobSpawn.is_alive == True)  # noqa: E712
            .order_by(MobSpawn.location_id, MobSpawn.mob_id)
        )
        alive = result.scalars().all()

    return templates.TemplateResponse(
        request, "editor_spawns.html",
        {"report": report, "alive": alive, "now": datetime.utcnow()},
    )


@app.post("/editor/spawns/respawn-all")
async def spawns_respawn_all(request: Request):
    """Мгновенно воскрешает всех и добивает популяцию до лимитов."""
    guard(request, "manage_content")
    from core.spawns import ensure_all_populations

    async with async_session() as session:
        result = await session.execute(
            select(MobSpawn).where(MobSpawn.is_alive == False)  # noqa: E712
        )
        for spawn in result.scalars().all():
            spawn.respawn_at = datetime.utcnow() - timedelta(seconds=1)
        await session.flush()
        await ensure_all_populations(session)
        await session.commit()
    return RedirectResponse(url="/editor/spawns", status_code=303)


@app.post("/editor/spawns/reset")
async def spawns_reset(request: Request):
    """Полный сброс: удаляет все спавны и расставляет мобов заново."""
    guard(request, "manage_content")
    from core.spawns import ensure_all_populations

    async with async_session() as session:
        await session.execute(delete(MobSpawn))
        await session.flush()
        await ensure_all_populations(session)
        await session.commit()
    return RedirectResponse(url="/editor/spawns", status_code=303)


@app.post("/editor/spawns/{spawn_id}/kill")
async def spawn_kill(request: Request, spawn_id: int):
    guard(request, "manage_content")
    from core.spawns import kill_spawn

    async with async_session() as session:
        result = await session.execute(
            select(MobSpawn)
            .where(MobSpawn.id == spawn_id)
            .options(selectinload(MobSpawn.mob))
        )
        spawn = result.scalar_one_or_none()
        if spawn and spawn.mob:
            await kill_spawn(session, spawn, spawn.mob)
            await session.commit()
    return RedirectResponse(url="/editor/spawns", status_code=303)


# ── Реестр экземпляров, аукцион и события ───────────────────

@app.get("/editor/instances")
async def editor_instances(
    request: Request, page: int = 1, source: str = "", q: str = ""
):
    """Все уникальные экземпляры в игре: кто владеет, откуда взялся."""
    guard(request, "manage_content")
    per_page = 50
    async with async_session() as session:
        base_query = (
            select(ItemInstance, Item, Character)
            .join(Item, Item.id == ItemInstance.item_id)
            .outerjoin(Character, Character.id == ItemInstance.owner_character_id)
        )
        if source:
            base_query = base_query.where(ItemInstance.source == source)
        if q.strip():
            needle = f"%{q.strip()}%"
            base_query = base_query.where(
                (ItemInstance.uid.ilike(needle)) | (Item.name.ilike(needle))
            )

        total = await session.scalar(
            select(func.count(ItemInstance.id)).select_from(base_query.subquery())
        ) or 0
        meta = paginate(total, page, per_page)

        rows = (await session.execute(
            base_query.order_by(ItemInstance.id.desc())
            .offset(meta["offset"]).limit(per_page)
        )).all()

        by_source = {
            row[0]: row[1] for row in (await session.execute(
                select(ItemInstance.source, func.count(ItemInstance.id))
                .group_by(ItemInstance.source)
            )).all()
        }
        uniques = await session.scalar(
            select(func.count(ItemInstance.id))
            .where(ItemInstance.is_one_of_a_kind == True)  # noqa: E712
        ) or 0
        festive = await session.scalar(
            select(func.count(ItemInstance.id))
            .where(ItemInstance.is_festive == True)  # noqa: E712
        ) or 0
        traded = await session.scalar(
            select(func.count(ItemInstance.id)).where(ItemInstance.trade_count > 0)
        ) or 0

    return templates.TemplateResponse(
        request, "editor_instances.html",
        {
            "rows": rows, "total": total, "by_source": by_source,
            "uniques": uniques, "festive": festive, "traded": traded,
            "source": source, "q": q, "pagination": meta,
            "badges": SOURCE_BADGES, "source_labels": SOURCE_LABELS,
        },
    )


@app.get("/instance/{instance_id}")
async def instance_detail(request: Request, instance_id: int):
    """Летопись конкретного предмета."""
    guard(request, "manage_content")
    async with async_session() as session:
        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == instance_id)
            .options(selectinload(ItemInstance.item))
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            return RedirectResponse(url="/editor/instances")

        rows = (await session.execute(
            select(ItemHistory)
            .where(ItemHistory.instance_id == instance_id)
            .order_by(ItemHistory.created_at, ItemHistory.id)
        )).scalars().all()

        owner = None
        if instance.owner_character_id:
            owner = await session.get(Character, instance.owner_character_id)

    from core.history import event_icon, event_label

    return templates.TemplateResponse(
        request, "instance_detail.html",
        {
            "instance": instance, "item": instance.item, "rows": rows,
            "owner": owner, "event_icon": event_icon, "event_label": event_label,
            "bonus_labels": BONUS_LABELS,
        },
    )


@app.get("/editor/auction")
async def editor_auction(request: Request, status: str = "active"):
    guard(request, "manage_content")
    async with async_session() as session:
        from core.auction import sweep_expired

        await sweep_expired(session)
        await session.commit()

        query = (
            select(AuctionLot)
            .options(
                selectinload(AuctionLot.item),
                selectinload(AuctionLot.instance),
                selectinload(AuctionLot.seller),
                selectinload(AuctionLot.buyer),
            )
            .order_by(AuctionLot.id.desc())
            .limit(200)
        )
        if status and status != "all":
            query = query.where(AuctionLot.status == status)
        lots = (await session.execute(query)).scalars().all()

        counts = {
            row[0]: row[1] for row in (await session.execute(
                select(AuctionLot.status, func.count(AuctionLot.id))
                .group_by(AuctionLot.status)
            )).all()
        }
        turnover = await session.scalar(
            select(func.sum(AuctionLot.price))
            .where(AuctionLot.status == AuctionStatus.SOLD.value)
        ) or 0

    return templates.TemplateResponse(
        request, "editor_auction.html",
        {
            "lots": lots, "counts": counts, "status": status,
            "turnover": turnover,
            "statuses": [s.value for s in AuctionStatus],
        },
    )


@app.post("/editor/auction/{lot_id}/cancel")
async def auction_lot_cancel(request: Request, lot_id: int):
    """Снимает лот и возвращает вещь продавцу."""
    guard(request, "manage_content")
    async with async_session() as session:
        from core.auction import _return_to_owner

        lot = await session.get(AuctionLot, lot_id)
        if lot and lot.status == AuctionStatus.ACTIVE.value:
            lot.status = AuctionStatus.CANCELLED.value
            seller = await session.get(Character, lot.seller_id) if lot.seller_id else None
            if seller is not None:
                await _return_to_owner(session, lot, seller, event="unlisted")
            await session.commit()
    return RedirectResponse(url="/editor/auction", status_code=303)


@app.post("/settings/festive-events")
async def save_festive_events(request: Request, events: list[str] = Form(default=[])):
    """Включает праздничные события: только их трофеи падают из мобов."""
    guard(request, "manage_content")
    from core.loot import FESTIVE_EVENTS_KEY

    value = ",".join(e.strip() for e in events if e.strip())
    async with async_session() as session:
        row = (await session.execute(
            select(AppSetting).where(AppSetting.key == FESTIVE_EVENTS_KEY)
        )).scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=FESTIVE_EVENTS_KEY, value=value))
        await session.commit()
    return RedirectResponse(url="/editor/events", status_code=303)


@app.get("/editor/events")
async def editor_events(request: Request):
    """Праздничные события и привязанные к ним трофеи."""
    guard(request, "manage_content")
    from core.loot import FESTIVE_EVENTS_KEY

    async with async_session() as session:
        raw = await session.scalar(
            select(AppSetting.value).where(AppSetting.key == FESTIVE_EVENTS_KEY)
        )
        active = {e.strip() for e in (raw or "").split(",") if e.strip()}

        festive_items = (await session.execute(
            select(Item).where(Item.is_festive == True)  # noqa: E712
            .order_by(Item.festive_event, Item.name)
        )).scalars().all()

        unique_items = (await session.execute(
            select(Item).where(Item.is_one_of_a_kind == True)  # noqa: E712
            .order_by(Item.name)
        )).scalars().all()

        # У каких реликвий уже есть владелец — они больше не выпадут
        taken = {
            row[0] for row in (await session.execute(
                select(ItemInstance.item_id)
                .where(ItemInstance.is_one_of_a_kind == True)  # noqa: E712
            )).all()
        }

    events = sorted({i.festive_event for i in festive_items if i.festive_event})
    by_event = {}
    for item in festive_items:
        by_event.setdefault(item.festive_event or "—", []).append(item)

    return templates.TemplateResponse(
        request, "editor_events.html",
        {
            "events": events, "active": active, "by_event": by_event,
            "unique_items": unique_items, "taken": taken,
        },
    )


@app.post("/editor/events/reset-unique/{item_id}")
async def reset_unique(request: Request, item_id: int):
    """Возвращает реликвию в пул: удаляет её единственный экземпляр.

    Нужно, если вещь досталась не тому или её надо разыграть заново.
    """
    guard(request, "manage_content")
    async with async_session() as session:
        instances = (await session.execute(
            select(ItemInstance).where(ItemInstance.item_id == item_id)
        )).scalars().all()
        for inst in instances:
            await session.execute(
                delete(InventoryItem).where(InventoryItem.instance_id == inst.id)
            )
            await session.execute(
                delete(ItemHistory).where(ItemHistory.instance_id == inst.id)
            )
            await session.execute(
                delete(AuctionLot).where(AuctionLot.instance_id == inst.id)
            )
            await session.delete(inst)
        await session.commit()
    return RedirectResponse(url="/editor/events", status_code=303)


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


# ── Global Search ──────────────────────────────────────────

@app.get("/api/search")
async def api_search(request: Request, q: str = ""):
    """Глобальный поиск по игрокам, предметам, мобам и локациям."""
    if len(q.strip()) < 2:
        return {"results": {}}

    needle = f"%{q.strip()}%"
    results: dict[str, list[dict]] = {}

    async with async_session() as session:
        # Players (characters)
        rows = (await session.execute(
            select(Character, User)
            .join(User, User.id == Character.user_id)
            .where((Character.name.ilike(needle)) | (User.telegram_id.cast(String).ilike(needle)))
            .order_by(Character.level.desc())
            .limit(8)
        )).all()
        results["players"] = [
            {
                "title": f"{char.name} (ур. {char.level})",
                "meta": f"TG {user.telegram_id}",
                "url": f"/player/{char.id}",
            }
            for char, user in rows
        ]

        # Items
        rows = (await session.execute(
            select(Item)
            .where(Item.name.ilike(needle))
            .order_by(Item.name)
            .limit(8)
        )).scalars().all()
        results["items"] = [
            {
                "title": f"{item.icon} {item.name}",
                "meta": item.item_type.value if item.item_type else "",
                "url": f"/item/{item.id}/edit",
            }
            for item in rows
        ]

        # Mobs
        rows = (await session.execute(
            select(Mob)
            .where(Mob.name.ilike(needle))
            .order_by(Mob.level)
            .limit(8)
        )).scalars().all()
        results["mobs"] = [
            {
                "title": f"{item.name} (ур. {item.level})",
                "meta": "босс" if item.is_boss else "моб",
                "url": f"/editor/mobs",
            }
            for item in rows
        ]

        # Locations
        rows = (await session.execute(
            select(Location)
            .where(Location.name.ilike(needle))
            .order_by(Location.id)
            .limit(8)
        )).scalars().all()
        results["locations"] = [
            {
                "title": f"{item.name}",
                "meta": item.location_type.value if item.location_type else "",
                "url": f"/editor/location/{item.id}",
            }
            for item in rows
        ]

    return {"results": results}


# ── Update from Git ────────────────────────────────────────

@app.post("/api/update")
async def api_update(request: Request, notify: str = Form("1")):
    """Pulls from GitHub and broadcasts the in-theme update notice.

    The broadcast is awaited (not fire-and-forget) so it actually reaches
    players before the process restarts — previously the task was cancelled
    by the restart and nobody ever got the notification.
    """
    guard(request, "settings")
    import subprocess
    import sys
    import threading

    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, cwd=os.getcwd(), timeout=60
        )
        success = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
    except Exception as e:
        return {"success": False, "error": str(e)}

    if not success:
        return {"success": False, "output": output, "restarting": False, "notified": 0}

    fresh = "Already up to date" not in output and "Уже обновлено" not in output

    notified = 0
    bot_off = not (bot_runner.is_running() and bot_runner.bot)
    if notify == "1" and not bot_off:
        try:
            from bot.broadcast import notify_update_deployed
            notified = await notify_update_deployed(bot_runner.bot)
        except Exception as e:
            return {"success": True, "output": output, "restarting": False,
                    "notified": 0, "notify_error": str(e), "fresh": fresh}

    if fresh:
        def _restart():
            os.execv(sys.executable, [sys.executable, "launch.py"])
        # рассылка уже ушла — рестартуем сразу после ответа
        threading.Timer(3.0, _restart).start()

    return {"success": True, "output": output, "restarting": fresh,
            "notified": notified, "bot_off": bot_off, "fresh": fresh}


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
