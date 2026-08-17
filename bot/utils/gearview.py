"""Картинка «во что одет герой» по разметке из панели.

Зачем модуль. Рендер `bot/utils/images.render_ui` существовал, но его
**не вызывал никто** — разметка, которую админ рисовал в панели, ни на что
не влияла. Здесь появляется потребитель: страница «🛡 Снаряжение» в профиле
собирает картинку из фона и иконок надетых вещей.

Как выбирается сцена. Сначала ищется разметка фракции героя
(`equipment_guard` и т. п.), потом общая `equipment`. Так у каждой стороны
может быть свой фон, но если админ разметил только общий — работает он.

Если разметки нет, фон не найден или ни одна вещь не надета — функция
возвращает `None`, и профиль показывает обычный портрет. Отсутствие
разметки не должно ломать экран.
"""
import hashlib
import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.models import InventoryItem, UILayout

logger = logging.getLogger(__name__)

# Готовые картинки складываем рядом с ассетами панели: их отдаёт тот же
# статик-роут, а Telegram забирает файл с диска.
CACHE_DIR = (Path(__file__).resolve().parent.parent.parent
             / "admin" / "static" / "ui" / "rendered")


async def _pick_layout(session, faction_key: str | None):
    """Разметка фракции, иначе общая. Возвращает ключ или None."""
    keys = []
    if faction_key:
        keys.append(f"equipment_{faction_key}")
    keys.append("equipment")

    rows = (await session.execute(
        select(UILayout).where(UILayout.key.in_(keys))
    )).scalars().all()
    found = {row.key: row for row in rows}
    for key in keys:
        layout = found.get(key)
        if layout is not None and (layout.slots_json or "").strip() not in ("", "[]"):
            return layout
    return None


async def _equipped_map(session, character_id: int) -> dict:
    """{имя_слота: путь_к_иконке} по надетым вещам.

    Имя слота — это тип предмета (`weapon`, `armor`…): ровно то, что ждёт
    `render_ui`. Совпадение имён и есть смысл каталога сцен в
    `core/ui_layouts.py`.
    """
    rows = (await session.execute(
        select(InventoryItem)
        .where(InventoryItem.character_id == character_id)
        .where(InventoryItem.is_equipped == True)  # noqa: E712
        .options(selectinload(InventoryItem.item))
    )).scalars().all()

    out = {}
    for inv in rows:
        item = inv.item
        if item is None or not item.image_url:
            continue
        slot = getattr(item.item_type, "value", item.item_type)
        if slot:
            out[str(slot)] = item.image_url
    return out


def _cache_name(layout_key: str, items_map: dict) -> str:
    """Имя файла зависит от набора вещей: сменил меч — новая картинка.

    Хэш вместо id персонажа: у двух героев в одинаковой экипировке будет
    один файл, и папка не разрастётся по числу игроков.
    """
    digest = hashlib.sha1(
        (layout_key + "|" + "|".join(f"{k}={v}" for k, v in sorted(items_map.items())))
        .encode("utf-8")).hexdigest()[:16]
    return f"{layout_key}_{digest}.png"


async def render_equipment(session, character) -> str | None:
    """Собрать картинку экипировки. Возвращает URL или None.

    None — штатный ответ: нет разметки, нет фона, ничего не надето или
    Pillow недоступен. Профиль в этом случае показывает портрет героя.
    """
    from core import factions as core_factions

    faction = core_factions.allegiance(character) or (character.faction or None)
    layout = await _pick_layout(session, faction)
    if layout is None:
        return None

    items_map = await _equipped_map(session, character.id)
    if not items_map:
        return None

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.debug("gearview: не создать кэш-папку: %s", exc)
        return None

    filename = _cache_name(layout.key, items_map)
    out_path = CACHE_DIR / filename
    url = f"/static/ui/rendered/{filename}"

    # Готовое не перерисовываем: экипировка меняется редко, а Pillow на
    # каждом открытии профиля — заметная нагрузка.
    if out_path.is_file():
        return url

    try:
        from bot.utils.images import render_ui

        ok = await render_ui(layout.key, items_map, str(out_path))
    except Exception as exc:
        logger.debug("gearview: рендер не удался: %s", exc)
        return None
    return url if ok else None


def clear_cache() -> int:
    """Удалить готовые картинки (после правки разметки). Сколько убрали."""
    if not CACHE_DIR.is_dir():
        return 0
    removed = 0
    for name in os.listdir(CACHE_DIR):
        if name.endswith(".png"):
            try:
                (CACHE_DIR / name).unlink()
                removed += 1
            except OSError:
                continue
    return removed
