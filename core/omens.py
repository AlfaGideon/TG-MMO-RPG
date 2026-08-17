"""Знамения: серверная часть.

Каталог знамений — один на оба стека и лежит в `engine/omens.py`
(единственный источник правды, как каталог бедствий для
`core/worldevents.py`). Здесь — хранилище динамики и точка вызова для бота.

Что появилось в этой партии:

* **№ 68** — знамения, добавленные из админки, лежат в `AppSetting`
  (ключ `engine.omens.CUSTOM_KEY`) JSON-списком и подмешиваются к каталогу
  той же функцией `engine.omens.catalog`, что и в браузерном стеке;
* **№ 86** — если в мире бушует бедствие, первым показывается ЕГО
  предвестие: строка `omen` из `engine/cataclysm_kinds.KINDS` (она была
  написана для каждого вида, но до сих пор нигде не читалась).

Синхронные функции без сессии (`get_current_omens()` без аргументов)
сохранены — их зовёт браузерная панель и старые тесты.
"""
import json

from sqlalchemy import select

from engine.omens import (  # noqa: F401
    CUSTOM_KEY,
    OMENS,
    catalog,
    custom_omens,
    for_cataclysm,
    omen_banner,
    omens_lines,
    omens_text,
)
from engine.omens import get_current_omens as _engine_current


def get_current_omens(settings=None, active_kinds=()) -> list:
    """Текущие знамения (синхронно, без БД). Совместимость со старым кодом."""
    return _engine_current(settings, active_kinds)


async def load_settings(session) -> dict:
    """Настройки знамений из БД в том виде, который понимает engine/omens."""
    from core.models import AppSetting

    row = (await session.execute(
        select(AppSetting).where(AppSetting.key == CUSTOM_KEY)
    )).scalar_one_or_none()
    return {CUSTOM_KEY: (row.value if row is not None else "")}


async def active_kinds(session) -> list:
    """Ключи бушующих сейчас бедствий — для привязки знамений (№ 86)."""
    from core import worldevents as core_events

    try:
        events = await core_events.active_cataclysms(session)
    except Exception:
        # Таблица событий может отсутствовать в свежей базе: знамения
        # не должны ронять экран из-за этого.
        return []
    return [e.key for e in events if e.key]


async def current(session) -> list:
    """Знамения с учётом и админских добавок, и живых бедствий."""
    return get_current_omens(await load_settings(session),
                             await active_kinds(session))


async def banner(session) -> str:
    """Баннер знамения для экранов бота."""
    return omen_banner(await load_settings(session),
                       await active_kinds(session))


async def save_custom(session, rows: list) -> list:
    """Записать список пользовательских знамений (админка).

    Валидация — общая: прогоняем через `custom_omens`, поэтому в базу не
    попадут записи без заголовка или с полями не того типа.
    """
    from core.models import AppSetting

    clean = custom_omens({CUSTOM_KEY: rows})
    payload = json.dumps(
        [{"icon": r["icon"], "title": r["title"], "desc": r["desc"]}
         for r in clean], ensure_ascii=False)

    row = (await session.execute(
        select(AppSetting).where(AppSetting.key == CUSTOM_KEY)
    )).scalar_one_or_none()
    if row is None:
        session.add(AppSetting(key=CUSTOM_KEY, value=payload))
    else:
        row.value = payload
    await session.flush()
    return clean


async def add_custom(session, icon: str, title: str, desc: str) -> list:
    """Добавить одно знамение."""
    existing = custom_omens(await load_settings(session))
    existing.append({"icon": icon, "title": title, "desc": desc})
    return await save_custom(session, existing)


async def delete_custom(session, index: int) -> list:
    """Удалить знамение по его номеру в списке добавленных."""
    existing = custom_omens(await load_settings(session))
    if 0 <= index < len(existing):
        existing.pop(index)
    return await save_custom(session, existing)
