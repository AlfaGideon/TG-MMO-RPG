"""Админка: настройка курса валют (1:100 по умолчанию)."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from core.database import async_session
from core.models import GameSettings

router = APIRouter(prefix="/admin/settings", tags=["settings"])


@router.get("/currency", response_class=HTMLResponse)
async def currency_settings(request: Request):
    async with async_session() as session:
        result = await session.execute(
            select(GameSettings).where(GameSettings.key == "currency_conversion")
        )
        setting = result.scalar_one_or_none()
        rate = int(setting.value) if setting else 100

    html = f"""
    <h2>💰 Настройка курса валют</h2>
    <form method="post" action="/admin/settings/currency">
        <label>Курс (1 старшая = X младшей):</label><br>
        <input type="number" name="rate" value="{rate}" min="10" max="1000" required>
        <button type="submit">Сохранить</button>
    </form>
    <p><i>По умолчанию 100 (бронза → серебро → золото)</i></p>
    """
    return HTMLResponse(html)


@router.post("/currency")
async def save_currency(rate: int = Form(...)):
    async with async_session() as session:
        result = await session.execute(
            select(GameSettings).where(GameSettings.key == "currency_conversion")
        )
        setting = result.scalar_one_or_none()
        if not setting:
            setting = GameSettings(key="currency_conversion", value=str(rate))
            session.add(setting)
        else:
            setting.value = str(rate)
        await session.commit()
    return {"status": "ok", "rate": rate}
