"""HTTP API игрового приложения и отдача мобильного SPA.

Роутер монтируется в admin/main.py. Все игровые методы требуют
`Authorization: Bearer <токен>` (выдаётся эндпоинтами /auth/*). Сам SPA
отдаётся с того же хоста на /player — поэтому он работает и как Telegram
Mini App, и внутри APK WebView без CORS.
"""
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session
from core.models import User
from playerapp import battle as battle_svc
from playerapp import inventory as inv_svc
from playerapp import service
from playerapp.auth import (
    consume_code, create_session, current_user, user_for_init_data,
)
from playerapp.service import ServiceError, load_character

router = APIRouter(prefix="/api/player")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


# ── Тела запросов ───────────────────────────────────────────────────

class CodeBody(BaseModel):
    code: str = ""


class TelegramBody(BaseModel):
    initData: str = ""


class MoveBody(BaseModel):
    direction: str = ""


class InventoryBody(BaseModel):
    inventory_id: int


# ── Вспомогательное ─────────────────────────────────────────────────

async def _character(user: User):
    async with async_session() as session:
        character = await load_character(session, user)
        if character is None:
            raise ServiceError(
                "Персонаж ещё не создан. Открой бота и пройди создание героя."
            )
        return session, character


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, ServiceError):
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    raise exc


# ── Аутентификация ──────────────────────────────────────────────────

@router.post("/auth/code")
async def auth_code(body: CodeBody, request: Request):
    async with async_session() as session:
        user = await consume_code(session, body.code)
        if user is None:
            return JSONResponse(
                {"ok": False, "error": "Код неверен или просрочен. Запроси новый в боте: /app"},
                status_code=401,
            )
        if user.is_banned:
            return JSONResponse({"ok": False, "error": "Аккаунт заблокирован."}, status_code=403)
        token = await create_session(
            session, user, source="code",
            user_agent=request.headers.get("user-agent"),
        )
        character = await load_character(session, user)
    return {"ok": True, "token": token, "has_character": character is not None}


@router.post("/auth/telegram")
async def auth_telegram(body: TelegramBody, request: Request):
    async with async_session() as session:
        user = await user_for_init_data(session, body.initData)
        if user is None:
            return JSONResponse(
                {"ok": False, "error": "Подпись Telegram не подтверждена."}, status_code=403
            )
        if user.is_banned:
            return JSONResponse({"ok": False, "error": "Аккаунт заблокирован."}, status_code=403)
        token = await create_session(
            session, user, source="telegram",
            user_agent=request.headers.get("user-agent"),
        )
        character = await load_character(session, user)
    return {"ok": True, "token": token, "has_character": character is not None}


# ── Игровые методы ──────────────────────────────────────────────────

@router.get("/me")
async def me(user: User = Depends(current_user)):
    async with async_session() as session:
        character = await load_character(session, user)
        if character is None:
            return {"ok": True, "has_character": False}
        return {"ok": True, "has_character": True,
                "profile": service.profile_dict(character, user)}


@router.get("/cell")
async def cell(user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return {"ok": True, "cell": await service.cell_view(session, character)}
    except Exception as exc:
        return _error(exc)


@router.post("/move")
async def move(body: MoveBody, user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return await service.move(session, character, body.direction)
    except Exception as exc:
        return _error(exc)


@router.post("/inspect")
async def inspect(user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return await service.inspect_cell(session, character)
    except Exception as exc:
        return _error(exc)


@router.post("/rest")
async def rest(user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return await service.rest(session, character)
    except Exception as exc:
        return _error(exc)


@router.get("/inventory")
async def inventory(user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return {"ok": True, "inventory": await inv_svc.list_inventory(session, character)}
    except Exception as exc:
        return _error(exc)


@router.post("/inventory/equip")
async def equip(body: InventoryBody, user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return await inv_svc.equip(session, character, body.inventory_id)
    except Exception as exc:
        return _error(exc)


@router.post("/inventory/unequip")
async def unequip(body: InventoryBody, user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return await inv_svc.unequip(session, character, body.inventory_id)
    except Exception as exc:
        return _error(exc)


# ── Бой ─────────────────────────────────────────────────────────────

@router.get("/battle")
async def battle_state(user: User = Depends(current_user)):
    async with async_session() as session:
        _, character = await _character(user)
        raw = battle_svc.active_battle(character.id)
        if raw is None:
            return {"ok": True, "active": False, "state": None}
        return {"ok": True, "active": True,
                "state": battle_svc._public_state(raw, character)}


@router.post("/battle/start")
async def battle_start(user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            state = await battle_svc.start_battle(session, character)
            return {"ok": True, "state": battle_svc._public_state(state, character)}
    except Exception as exc:
        return _error(exc)


@router.post("/battle/attack")
async def battle_attack(user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return {"ok": True, "result": await battle_svc.attack(session, character)}
    except Exception as exc:
        return _error(exc)


@router.post("/battle/flee")
async def battle_flee(user: User = Depends(current_user)):
    try:
        async with async_session() as session:
            _, character = await _character(user)
            return {"ok": True, "result": await battle_svc.flee(session, character)}
    except Exception as exc:
        return _error(exc)


# ── Отдача SPA ──────────────────────────────────────────────────────

@router.get("/", include_in_schema=False)
async def spa_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
