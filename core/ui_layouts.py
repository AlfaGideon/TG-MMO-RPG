"""Разметка интерфейсов: каталог сцен, пресеты слотов, галерея фонов.

Проблема, которую решает этот модуль. Раздел «Разметка интерфейсов» просил
вписать руками две вещи, взять которые было неоткуда:

* **ключ разметки** — строку вида `inventory_order`. Ни списка допустимых
  ключей, ни подсказки: угадаешь неверно — бот твою разметку не найдёт;
* **URL фоновой картинки** — путь вида `/static/ui/equipment_order.png`.
  Узнать его можно было только заглянув в файловую систему сервера.

Плюс **имена слотов**: рендер (`bot/utils/images.render_ui`) ищет слот по
имени, совпадающему с типом предмета (`weapon`, `armor`…), а редактор
называл их `slot_1`, `slot_2`. Такая разметка не работала никогда, и
узнать об этом было невозможно — ошибка молчаливая.

Здесь всё это становится данными: сцены с описанием и нужными слотами,
готовые пресеты, список картинок из папки. Панель показывает выбор, а не
пустое поле ввода.
"""
import os
from pathlib import Path

# Папка с фонами интерфейсов. Именно её показывает галерея.
UI_DIR = Path(__file__).resolve().parent.parent / "admin" / "static" / "ui"
UI_URL_PREFIX = "/static/ui/"

# Типы предметов, которые надеваются: имя слота обязано совпадать с ними,
# иначе render_ui не найдёт, что рисовать (см. core/enums.ItemType).
EQUIPMENT_SLOTS = [
    {"name": "weapon", "label": "Оружие", "icon": "⚔️"},
    {"name": "armor", "label": "Броня", "icon": "🦺"},
    {"name": "helmet", "label": "Шлем", "icon": "🪖"},
    {"name": "boots", "label": "Сапоги", "icon": "👢"},
    {"name": "accessory", "label": "Аксессуар", "icon": "💍"},
]

# Сумка: слоты нумерованные, порядок = порядок ячеек на картинке.
BAG_SLOT_COUNT = 12


def bag_slots() -> list:
    return [{"name": f"bag_{i + 1}", "label": f"Ячейка {i + 1}", "icon": "🎒"}
            for i in range(BAG_SLOT_COUNT)]


# ── каталог сцен ────────────────────────────────────────────
# Ключ разметки больше не выдумывается: он выбирается из этого списка.
# `slots` — имена, которые ждёт рендер; `hint` объясняет, где картинка
# появится у игрока.

SCENES = [
    {
        "key": "equipment",
        "title": "Экипировка героя",
        "icon": "🛡",
        "hint": "Экран «надето» в профиле: бот подставит иконки надетых вещей "
                "в размеченные ячейки.",
        "slots": EQUIPMENT_SLOTS,
        "suggest": "equipment_bg.png",
    },
    {
        "key": "equipment_guard",
        "title": "Экипировка · Стража Погоста",
        "icon": "🛡",
        "hint": "Тот же экран, но с фоном фракции Стражи.",
        "slots": EQUIPMENT_SLOTS,
        "suggest": "equipment_guard.png",
    },
    {
        "key": "equipment_order",
        "title": "Экипировка · Орден Рассвета",
        "icon": "⚜️",
        "hint": "Тот же экран с фоном Ордена.",
        "slots": EQUIPMENT_SLOTS,
        "suggest": "equipment_order.png",
    },
    {
        "key": "equipment_cult",
        "title": "Экипировка · Культ Пожирателя",
        "icon": "🌑",
        "hint": "Тот же экран с фоном Культа.",
        "slots": EQUIPMENT_SLOTS,
        "suggest": "equipment_cult.png",
    },
    {
        "key": "equipment_scavengers",
        "title": "Экипировка · Гильдия падальщиков",
        "icon": "💰",
        "hint": "Тот же экран с фоном Падальщиков.",
        "slots": EQUIPMENT_SLOTS,
        "suggest": "equipment_scavengers.png",
    },
    {
        "key": "inventory",
        "title": "Сумка",
        "icon": "🎒",
        "hint": "Экран инвентаря: ячейки заполняются предметами по порядку.",
        "slots": bag_slots(),
        "suggest": "inventory_bg.png",
    },
]

SCENE_BY_KEY = {s["key"]: s for s in SCENES}


def scene(key: str) -> dict | None:
    return SCENE_BY_KEY.get((key or "").strip())


def scene_slots(key: str) -> list:
    """Имена слотов, которые ждёт рендер для этой сцены."""
    row = scene(key)
    return list(row["slots"]) if row else []


def known_keys() -> list:
    return [s["key"] for s in SCENES]


# ── галерея фонов ───────────────────────────────────────────

def gallery() -> list:
    """Картинки из admin/static/ui — то, из чего можно выбирать.

    Раньше путь вписывался руками и опечатка обнаруживалась только пустым
    экраном у игрока. Теперь выбор идёт из реально существующих файлов.
    """
    if not UI_DIR.is_dir():
        return []
    out = []
    for name in sorted(os.listdir(UI_DIR)):
        if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        path = UI_DIR / name
        try:
            size_kb = int(path.stat().st_size / 1024)
        except OSError:
            size_kb = 0
        out.append({"name": name, "url": UI_URL_PREFIX + name,
                    "size_kb": size_kb})
    return out


def image_size(url: str) -> tuple | None:
    """Размер картинки в пикселях — нужен, чтобы слоты не уехали за край."""
    from core.assets import local_asset_path

    path = local_asset_path(url)
    if not path or not path.is_file():
        return None
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


# ── пресеты слотов ──────────────────────────────────────────

def preset(key: str, width: int = 0, height: int = 0) -> list:
    """Готовая раскладка слотов для сцены.

    Считается от размера картинки, а не зашита в пикселях: фоны бывают
    разного размера, и раскладка в абсолютных координатах на другом фоне
    оказалась бы за краем.
    """
    slots = scene_slots(key)
    if not slots:
        return []
    width = int(width or 800)
    height = int(height or 800)

    if key.startswith("equipment"):
        # Экипировка: колонка слева, вертикально по центру.
        size = max(48, int(min(width, height) * 0.14))
        gap = int(size * 0.35)
        total = len(slots) * size + (len(slots) - 1) * gap
        top = max(10, (height - total) // 2)
        left = max(10, int(width * 0.08))
        return [
            {"name": s["name"], "x": left, "y": top + i * (size + gap),
             "w": size, "h": size}
            for i, s in enumerate(slots)
        ]

    # Сумка: сетка 4×N по центру.
    cols = 4
    size = max(40, int(width * 0.16))
    gap = int(size * 0.2)
    rows = (len(slots) + cols - 1) // cols
    grid_w = cols * size + (cols - 1) * gap
    grid_h = rows * size + (rows - 1) * gap
    left = max(10, (width - grid_w) // 2)
    top = max(10, (height - grid_h) // 2)
    return [
        {"name": s["name"],
         "x": left + (i % cols) * (size + gap),
         "y": top + (i // cols) * (size + gap),
         "w": size, "h": size}
        for i, s in enumerate(slots)
    ]


# ── проверка разметки ───────────────────────────────────────

def validate(key: str, slots: list, width: int = 0, height: int = 0) -> dict:
    """Что не так с разметкой. Пустые списки = всё в порядке.

    Проверяется то, из-за чего рендер молча ничего не рисовал:
    неизвестное имя слота, пропущенный обязательный слот, дубликаты и
    выход за границы картинки.
    """
    expected = {s["name"] for s in scene_slots(key)}
    names = [str(s.get("name", "")) for s in (slots or [])]

    unknown = sorted({n for n in names if expected and n not in expected})
    missing = sorted(expected - set(names)) if expected else []
    dupes = sorted({n for n in names if names.count(n) > 1})

    outside = []
    if width and height:
        for s in slots or []:
            x, y = int(s.get("x", 0)), int(s.get("y", 0))
            w = int(s.get("w", s.get("size", 0)))
            h = int(s.get("h", s.get("size", 0)))
            if x < 0 or y < 0 or x + w > width or y + h > height:
                outside.append(str(s.get("name", "?")))

    return {
        "ok": not (unknown or missing or dupes or outside),
        "unknown": unknown,      # рендер такие слоты проигнорирует
        "missing": missing,      # эти вещи не отрисуются вообще
        "duplicates": dupes,     # второй слот с тем же именем перекроет первый
        "outside": sorted(set(outside)),
    }
