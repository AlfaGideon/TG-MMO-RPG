"""Идемпотентное наполнение нового контента: классы, материалы, лут, крафт.

Вызывается при каждом старте — в отличие от `core.seed.seed_database`,
который отрабатывает только на пустой базе. Здесь всё проверяется по
имени/ключу, поэтому повторный запуск ничего не ломает и не дублирует.
"""
from sqlalchemy import select, func

from core.classes import seed_default_classes
from core.enums import CraftStation, ItemRarity, ItemType
from core.models import (
    Cell, CraftIngredient, CraftRecipe, DropEntry, Item, Mob, UpgradeRule,
)

# ── Материалы для крафта и заточки ─────────────────────────
# (name, description, rarity, price, icon)
MATERIALS = [
    ("Ржавый лом", "Кусок железа, снятый с трупа. Годится в переплавку.", ItemRarity.COMMON, 4, "🔩"),
    ("Обрывок шкуры", "Грубая шкура, ещё пахнет зверем.", ItemRarity.COMMON, 5, "🟫"),
    ("Кость павшего", "Прочная кость. Некроманты платят за такие втридорога.", ItemRarity.COMMON, 6, "🦴"),
    ("Стальной слиток", "Переплавленное железо. Основа любого клинка.", ItemRarity.UNCOMMON, 18, "🧱"),
    ("Дублёная кожа", "Выделанная кожа для доспехов и сапог.", ItemRarity.UNCOMMON, 15, "🟤"),
    ("Лечебная трава", "Горькая на вкус, но затягивает раны.", ItemRarity.COMMON, 7, "🌿"),
    ("Лунный цвет", "Цветёт только в тумане. Основа маны.", ItemRarity.UNCOMMON, 16, "🌸"),
    ("Теневой кристалл", "Внутри клубится темнота. Тёплый на ощупь.", ItemRarity.RARE, 60, "💠"),
    ("Камень заточки", "Точильный камень с вырезанной руной.", ItemRarity.UNCOMMON, 25, "🪨"),
    ("Осколок души", "Тускло светится. Лучше не держать долго в руках.", ItemRarity.EPIC, 140, "🔮"),
]

# ── Крафтовые результаты, которых нет в базовом сиде ───────
# (name, description, type, rarity, price, level_req, icon, bonuses)
CRAFT_ITEMS = [
    ("Стальной меч", "Ровный клинок из хорошего слитка. Без изысков, но надёжен.",
     ItemType.WEAPON, ItemRarity.UNCOMMON, 90, 3, "⚔️", dict(bonus_damage=8, bonus_strength=2)),
    ("Клинок теней", "Металл почти не отражает свет. Режет тихо.",
     ItemType.WEAPON, ItemRarity.RARE, 260, 6, "🗡", dict(bonus_damage=15, bonus_agility=4, bonus_luck=2)),
    ("Костяной посох", "Посох из позвонков. Шепчет на выдохе.",
     ItemType.WEAPON, ItemRarity.RARE, 240, 6, "🪄", dict(bonus_damage=9, bonus_intelligence=7, bonus_mp=25)),
    ("Кожаный доспех", "Прошитая кожа. Не остановит топор, но спасёт от когтей.",
     ItemType.ARMOR, ItemRarity.UNCOMMON, 80, 3, "🦺", dict(bonus_defense=6, bonus_hp=20, bonus_agility=1)),
    ("Стальная кираса", "Тяжёлая, но за ней можно пережить встречу с троллем.",
     ItemType.ARMOR, ItemRarity.RARE, 230, 6, "🛡", dict(bonus_defense=12, bonus_hp=45, bonus_endurance=3)),
    ("Шлем стража", "Забрало опускается со скрежетом. Зато голова цела.",
     ItemType.HELMET, ItemRarity.UNCOMMON, 70, 3, "🪖", dict(bonus_defense=4, bonus_endurance=3, bonus_hp=15)),
    ("Сапоги следопыта", "Мягкая подошва — шаг не слышно даже на гравии.",
     ItemType.BOOTS, ItemRarity.UNCOMMON, 65, 3, "👢", dict(bonus_agility=4, bonus_defense=2)),
    ("Амулет теней", "Тёплый камень в оправе. Ночью светится.",
     ItemType.ACCESSORY, ItemRarity.RARE, 200, 5, "📿", dict(bonus_luck=6, bonus_intelligence=3, bonus_mp=20)),
    ("Кольцо стойкости", "Простое железное кольцо, но носящий его не падает.",
     ItemType.ACCESSORY, ItemRarity.UNCOMMON, 110, 4, "💍", dict(bonus_endurance=5, bonus_hp=30)),
    ("Большое зелье здоровья", "Густое, почти чёрное. Ставит на ноги даже умирающего.",
     ItemType.CONSUMABLE, ItemRarity.UNCOMMON, 35, 1, "🧪", {}),
    ("Большое зелье маны", "Пахнет грозой. Наполняет голову звоном.",
     ItemType.CONSUMABLE, ItemRarity.UNCOMMON, 35, 1, "🧪", {}),
]

# ── Рецепты: (название, станок, результат, золото, ур., шанс, [(материал, кол-во)]) ──
RECIPES = [
    ("Ковка стального меча", CraftStation.FORGE, "Стальной меч", 60, 3, 1.0,
     [("Стальной слиток", 3), ("Ржавый лом", 2)]),
    ("Ковка стальной кирасы", CraftStation.FORGE, "Стальная кираса", 160, 6, 0.9,
     [("Стальной слиток", 6), ("Дублёная кожа", 2)]),
    ("Ковка кожаного доспеха", CraftStation.FORGE, "Кожаный доспех", 50, 3, 1.0,
     [("Дублёная кожа", 3), ("Обрывок шкуры", 4)]),
    ("Ковка шлема стража", CraftStation.FORGE, "Шлем стража", 45, 3, 1.0,
     [("Стальной слиток", 2), ("Обрывок шкуры", 2)]),
    ("Пошив сапог следопыта", CraftStation.FORGE, "Сапоги следопыта", 40, 3, 1.0,
     [("Дублёная кожа", 2), ("Обрывок шкуры", 3)]),
    ("Ковка клинка теней", CraftStation.FORGE, "Клинок теней", 220, 6, 0.75,
     [("Стальной слиток", 4), ("Теневой кристалл", 2), ("Осколок души", 1)]),
    ("Резьба костяного посоха", CraftStation.FORGE, "Костяной посох", 200, 6, 0.8,
     [("Кость павшего", 6), ("Теневой кристалл", 1)]),
    ("Варка большого зелья здоровья", CraftStation.ALCHEMY, "Большое зелье здоровья", 15, 1, 1.0,
     [("Лечебная трава", 3)]),
    ("Варка большого зелья маны", CraftStation.ALCHEMY, "Большое зелье маны", 15, 1, 1.0,
     [("Лунный цвет", 3)]),
    ("Переплавка лома в слиток", CraftStation.FORGE, "Стальной слиток", 5, 1, 1.0,
     [("Ржавый лом", 4)]),
    ("Выделка кожи", CraftStation.FORGE, "Дублёная кожа", 5, 1, 1.0,
     [("Обрывок шкуры", 4)]),
    ("Амулет теней", CraftStation.JEWELRY, "Амулет теней", 180, 5, 0.85,
     [("Теневой кристалл", 2), ("Лунный цвет", 2)]),
    ("Кольцо стойкости", CraftStation.JEWELRY, "Кольцо стойкости", 90, 4, 0.95,
     [("Стальной слиток", 2), ("Кость павшего", 3)]),
]

# ── Заточка: (от, до, золото, материал, кол-во, шанс, прирост%) ──
UPGRADE_RULES = [
    (0, 3, 40, "Камень заточки", 1, 0.95, 0.10),
    (3, 6, 150, "Камень заточки", 2, 0.80, 0.09),
    (6, 8, 400, "Теневой кристалл", 2, 0.65, 0.08),
    (8, 10, 900, "Осколок души", 1, 0.50, 0.08),
]

# Кто что роняет: имя моба -> [(предмет, шанс, мин, макс)]
MOB_DROPS = {
    "Болотный зомби": [
        ("Ржавый лом", 0.45, 1, 2), ("Кость павшего", 0.35, 1, 2),
        ("Лечебная трава", 0.25, 1, 1), ("Ржавый меч", 0.06, 1, 1),
    ],
    "Лесной ворг": [
        ("Обрывок шкуры", 0.55, 1, 3), ("Лечебная трава", 0.2, 1, 2),
        ("Сапоги скитальца", 0.07, 1, 1),
    ],
    "Скелет-воин": [
        ("Кость павшего", 0.6, 1, 3), ("Ржавый лом", 0.35, 1, 2),
        ("Камень заточки", 0.15, 1, 1), ("Старая кольчуга", 0.07, 1, 1),
    ],
    "Гнолл-грабитель": [
        ("Обрывок шкуры", 0.5, 1, 2), ("Стальной слиток", 0.2, 1, 1),
        ("Камень заточки", 0.15, 1, 1), ("Дубинка гнолла", 0.08, 1, 1),
    ],
    "Пещерный тролль": [
        ("Стальной слиток", 0.4, 1, 3), ("Дублёная кожа", 0.3, 1, 2),
        ("Камень заточки", 0.25, 1, 2), ("Теневой кристалл", 0.1, 1, 1),
    ],
    "Теневой призрак": [
        ("Теневой кристалл", 0.35, 1, 2), ("Лунный цвет", 0.3, 1, 2),
        ("Осколок души", 0.08, 1, 1), ("Кинжал теней", 0.05, 1, 1),
    ],
}

# Общий пул сундуков (owner_id = None)
CHEST_DROPS = [
    ("Зелье здоровья", 0.5, 1, 2),
    ("Зелье маны", 0.4, 1, 2),
    ("Ржавый лом", 0.4, 1, 3),
    ("Обрывок шкуры", 0.35, 1, 3),
    ("Лечебная трава", 0.35, 1, 3),
    ("Стальной слиток", 0.25, 1, 2),
    ("Камень заточки", 0.2, 1, 1),
    ("Дублёная кожа", 0.2, 1, 2),
    ("Лунный цвет", 0.18, 1, 2),
    ("Кольцо удачи", 0.08, 1, 1),
    ("Шлем изгнанника", 0.08, 1, 1),
    ("Теневой кристалл", 0.07, 1, 1),
    ("Кинжал теней", 0.03, 1, 1),
    ("Осколок души", 0.02, 1, 1),
]

# NPC-ремесленники, которых подсаживаем в стартовую деревню
CRAFT_NPCS = [
    ("Кузнец Дорн", CraftStation.FORGE.value,
     "Молот стучит, не переставая. — Принёс железо? Тогда поговорим. "
     "Кую снаряжение и точу то, что ты уже носишь."),
    ("Травница Эльса", CraftStation.ALCHEMY.value,
     "Пахнет полынью и чем-то кислым. — Травы есть? Сварю тебе то, "
     "что удержит душу в теле ещё на один бой."),
    ("Ювелир Кассий", CraftStation.JEWELRY.value,
     "Тонкие пальцы, лупа в глазу. — Кристаллы, камни, кости... "
     "Принеси материал — сделаю вещь, за которую будут убивать."),
]


async def _items_by_name(session) -> dict:
    result = await session.execute(select(Item))
    return {item.name: item for item in result.scalars().all()}


async def ensure_materials(session) -> int:
    """Добавляет материалы и крафтовые предметы, если их ещё нет."""
    existing = await _items_by_name(session)
    added = 0

    for name, desc, rarity, price, icon in MATERIALS:
        if name in existing:
            continue
        session.add(Item(
            name=name, description=desc, item_type=ItemType.MATERIAL,
            rarity=rarity, price=price, icon=icon,
            stat_variance=0.0, is_unique_roll=False, max_upgrade_level=0,
        ))
        added += 1

    for name, desc, itype, rarity, price, lvl, icon, bonuses in CRAFT_ITEMS:
        if name in existing:
            continue
        session.add(Item(
            name=name, description=desc, item_type=itype, rarity=rarity,
            price=price, level_requirement=lvl, icon=icon,
            is_craftable=True,
            stat_variance=0.0 if itype == ItemType.CONSUMABLE else 0.18,
            is_unique_roll=itype != ItemType.CONSUMABLE,
            **bonuses,
        ))
        added += 1

    if added:
        await session.flush()
    return added


async def ensure_drop_tables(session) -> int:
    """Заполняет таблицы лута мобов и сундуков (только если пусто)."""
    have = await session.scalar(select(func.count(DropEntry.id))) or 0
    if have:
        return 0

    items = await _items_by_name(session)
    result = await session.execute(select(Mob))
    mobs = {m.name: m for m in result.scalars().all()}

    added = 0
    for mob_name, drops in MOB_DROPS.items():
        mob = mobs.get(mob_name)
        if mob is None:
            continue
        for item_name, chance, lo, hi in drops:
            item = items.get(item_name)
            if item is None:
                continue
            session.add(DropEntry(
                owner_type="mob", owner_id=mob.id, item_id=item.id,
                chance=chance, min_quantity=lo, max_quantity=hi,
            ))
            added += 1

    for item_name, chance, lo, hi in CHEST_DROPS:
        item = items.get(item_name)
        if item is None:
            continue
        session.add(DropEntry(
            owner_type="chest", owner_id=None, item_id=item.id,
            chance=chance, min_quantity=lo, max_quantity=hi,
        ))
        added += 1

    if added:
        await session.flush()
    return added


async def ensure_recipes(session) -> int:
    """Добавляет рецепты крафта, которых ещё нет (по названию)."""
    items = await _items_by_name(session)
    result = await session.execute(select(CraftRecipe.name))
    existing = {row[0] for row in result.all()}

    added = 0
    for name, station, result_name, gold, lvl, chance, ingredients in RECIPES:
        if name in existing:
            continue
        target = items.get(result_name)
        if target is None:
            continue
        recipe = CraftRecipe(
            name=name, station=station.value, result_item_id=target.id,
            result_quantity=1, gold_cost=gold, min_level=lvl,
            success_chance=chance, quality_bonus=0.05,
            description=f"Изготовление: {result_name}",
        )
        session.add(recipe)
        await session.flush()
        for mat_name, qty in ingredients:
            mat = items.get(mat_name)
            if mat is None:
                continue
            session.add(CraftIngredient(
                recipe_id=recipe.id, item_id=mat.id, quantity=qty,
            ))
        added += 1

    if added:
        await session.flush()
    return added


async def ensure_upgrade_rules(session) -> int:
    have = await session.scalar(select(func.count(UpgradeRule.id))) or 0
    if have:
        return 0

    items = await _items_by_name(session)
    added = 0
    for lo, hi, gold, mat_name, qty, chance, gain in UPGRADE_RULES:
        mat = items.get(mat_name)
        session.add(UpgradeRule(
            from_level=lo, to_level=hi, gold_cost=gold,
            material_item_id=mat.id if mat else None,
            material_quantity=qty, success_chance=chance,
            stat_gain_percent=gain, min_stat_gain=1,
        ))
        added += 1
    if added:
        await session.flush()
    return added


async def ensure_craft_npcs(session) -> int:
    """Ставит ремесленников в стартовой (безопасной) локации."""
    result = await session.execute(
        select(Cell).where(Cell.npc_station.isnot(None))
    )
    if result.scalars().first():
        return 0

    result = await session.execute(
        select(Cell)
        .where(Cell.location_id == 1)
        .where(Cell.is_passable == True)  # noqa: E712
        .where(Cell.has_npc == False)  # noqa: E712
        .where(Cell.dungeon_template_id.is_(None))
        .order_by(Cell.x, Cell.y)
    )
    free = result.scalars().all()
    if not free:
        return 0

    added = 0
    for idx, (name, station, dialogue) in enumerate(CRAFT_NPCS):
        step = max(1, len(free) // (len(CRAFT_NPCS) + 1))
        cell = free[min(len(free) - 1, idx * step + 1)]
        if cell.has_npc:
            continue
        cell.has_npc = True
        cell.npc_name = name
        cell.npc_type = "crafter"
        cell.npc_station = station
        cell.npc_dialogue = dialogue
        added += 1

    if added:
        await session.flush()
    return added


async def ensure_mob_defaults(session) -> int:
    """Проставляет мобам популяцию/респавн, если поля пустые (старая база)."""
    result = await session.execute(select(Mob))
    changed = 0
    for mob in result.scalars().all():
        if mob.population is None:
            mob.population = 1 if mob.is_boss else 3
            changed += 1
        if mob.respawn_seconds is None:
            mob.respawn_seconds = 600 if mob.is_boss else 120
            changed += 1
        if mob.move_interval_seconds is None:
            mob.move_interval_seconds = 0 if mob.is_boss else 45
            changed += 1
        if mob.can_roam is None:
            mob.can_roam = not mob.is_boss
            changed += 1
        if mob.roam_radius is None:
            mob.roam_radius = 0 if mob.is_boss else 1
            changed += 1
    if changed:
        await session.flush()
    return changed


async def seed_content(session) -> dict:
    """Полный проход. Безопасно вызывать при каждом старте."""
    stats = {
        "classes": await seed_default_classes(session),
        "materials": await ensure_materials(session),
        "recipes": 0, "drops": 0, "upgrades": 0, "npcs": 0, "mobs": 0,
    }
    stats["recipes"] = await ensure_recipes(session)
    stats["drops"] = await ensure_drop_tables(session)
    stats["upgrades"] = await ensure_upgrade_rules(session)
    stats["npcs"] = await ensure_craft_npcs(session)
    stats["mobs"] = await ensure_mob_defaults(session)
    await session.commit()
    return stats
