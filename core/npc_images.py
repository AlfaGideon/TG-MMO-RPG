"""Стандартные портреты жителей мира.

Пути здесь являются дефолтами, а не жёсткой привязкой: картинка, которую
администратор задал у клетки NPC, всегда имеет приоритет. Этот модуль нужен
и сидеру (чтобы старые базы получили портреты), и боту (как запасной вариант
для неполной или старой записи в БД).
"""
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.assets import local_asset_exists
from core.models import Cell


NPC_FILES = {
    "Инквизитор Эдуард": "eduard.jpg",
    "Интендант Бенедикт": "benedikt.jpg",
    "Оружейник Рауль": "raul.jpg",
    "Писарь Иеремия": "jeremia.jpg",
    "Старейшина Григор": "grigor.jpg",
    "Лорд Малакар": "malakar.jpg",
    "Торговец шёпотом Ксавьер": "ksavier.jpg",
    "Кузнец скверны Кром": "krom.jpg",
    "Ростовщик Теневой секты": "sect_usurer.jpg",
    "Тенелов Вирд": "wyrd.jpg",
    "Главарь банды Грюм": "gryum.jpg",
    "Скупщик краденого Барни": "barney.jpg",
    "Оружейник Глубин Шрам": "shram.jpg",
    "Оценщик Гильдии Клык": "klyk.jpg",
    "Хранитель ключей": "key_keeper.jpg",
    "Капитан Радклифф": "radcliffe.jpg",
    "Лавочник Кормак": "kormak.jpg",
    "Оружейник Торвальд": "torvald.jpg",
    "Летописец Пепла Морган": "morgan.jpg",
    "Торговец Варн": "varn.jpg",
    "Лекарь Мира": "mira.jpg",
    "Кузнец Дорн": "dorn.jpg",
    "Травница Эльса": "elsa.jpg",
    "Ювелир Кассий": "kassiy.jpg",
    "Скупщик Молчун": "molchun.jpg",
}

# Для авторских NPC без отдельного портрета. Название замка устойчивее,
# чем тип NPC: у рассказчика, лекаря и торговца одной стороны общий стиль.
_LOCATION_FALLBACKS = (
    ("Рассвета", "order_npc.jpg"),
    ("Теней", "cult_npc.jpg"),
    ("Глубин", "scavengers_npc.jpg"),
    ("Пепла", "guard_npc.jpg"),
)


def npc_image_url(npc_name: str | None, location_name: str | None = None) -> str:
    """Путь ``/static/...`` к стандартному портрету или пустая строка."""
    filename = NPC_FILES.get((npc_name or "").strip())
    if filename:
        url = f"/static/npcs/{filename}"
        return url if local_asset_exists(url) else ""

    name = location_name or ""
    for marker, fallback in _LOCATION_FALLBACKS:
        if marker in name:
            url = f"/static/npcs/{fallback}"
            return url if local_asset_exists(url) else ""
    return ""


async def ensure_npc_images(session) -> int:
    """Заполнить пустые портреты NPC на уже существующих базах.

    Не затирает ни загруженные администратором файлы, ни внешние URL. Вызов
    безопасен на каждом старте: затрагивает только клетки с пустым полем.
    """
    result = await session.execute(
        select(Cell)
        .where(Cell.has_npc == True)  # noqa: E712
        .options(selectinload(Cell.location))
    )
    changed = 0
    for cell in result.scalars():
        if (cell.image_url or "").strip():
            continue
        location = cell.location
        url = npc_image_url(cell.npc_name, location.name if location else None)
        if url:
            cell.image_url = url
            changed += 1
    return changed
