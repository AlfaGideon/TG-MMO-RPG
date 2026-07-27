import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from core.database import init_db, async_session
from core.models import User, Character, Location, Mob, Item, ShopItem, Battle, AppSetting
from admin.config import settings
from bot.runner import bot_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    await init_db()
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


# ── Items ──────────────────────────────────────────────────

@app.get("/items")
async def items(request: Request):
    async with async_session() as session:
        result = await session.execute(
            select(ShopItem)
            .options(selectinload(ShopItem.item))
            .order_by(ShopItem.id)
        )
        shop_items = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "items.html",
        {"items": shop_items},
    )


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
