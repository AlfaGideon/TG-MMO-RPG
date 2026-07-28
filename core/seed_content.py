"""Идемпотентное наполнение нового контента: классы, материалы, лут, крафт.

Вызывается при каждом старте — в отличие от `core.seed.seed_database`,
который отрабатывает только на пустой базе. Здесь всё проверяется по
имени/ключу, поэтому повторный запуск ничего не ломает и не дублирует.
"""
from sqlalchemy import select, func

from core.classes import seed_default_classes
from core.enums import CraftStation, ItemRarity, ItemType
from core.models import (
    AppSetting, Cell, Character, CharacterAffinity, CraftIngredient,
    CraftRecipe, DropEntry, Item, Mob, UpgradeRule,
)

# Кому уже бросали дар при апгрейде — чтобы не бросать повторно
AFFINITY_SEEDED_KEY = "affinity_seeded_ids"

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
    # ── Алхимические реагенты ──────────────────────────────
    ("Уголь саламандры", "Не гаснет под дождём. Основа огненных зелий.", ItemRarity.UNCOMMON, 20, "🔥"),
    ("Вечный лёд", "Не тает в ладони. Наоборот — обжигает холодом.", ItemRarity.UNCOMMON, 20, "❄️"),
    ("Громовая соль", "Потрескивает и щиплет пальцы. Пахнет грозой.", ItemRarity.UNCOMMON, 22, "⚡"),
    ("Слеза тьмы", "Капля густой черноты, застывшая в стекле.", ItemRarity.RARE, 55, "🌑"),
    ("Корень мандрагоры", "Кричит, когда его вырывают. Мощный реагент.", ItemRarity.UNCOMMON, 24, "🌱"),
    ("Пыльца рассвета", "Светится золотом. Собирается только на восходе.", ItemRarity.RARE, 58, "✨"),
    ("Пустой флакон", "Толстое стекло с притёртой пробкой. Держит что угодно.", ItemRarity.COMMON, 3, "🫙"),
    ("Дистиллят", "Прозрачная основа для любого зелья. Без вкуса и запаха.", ItemRarity.COMMON, 8, "💧"),
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

    # ── Алхимия: эликсиры со стойкими бонусами ─────────────
    ("Эликсир силы", "Мышцы каменеют, в глазах темнеет. Ненадолго — но как же мощно.",
     ItemType.CONSUMABLE, ItemRarity.UNCOMMON, 45, 3, "🧪", dict(bonus_strength=5)),
    ("Эликсир ловкости", "Мир замедляется. Ты — нет.",
     ItemType.CONSUMABLE, ItemRarity.UNCOMMON, 45, 3, "🧪", dict(bonus_agility=5)),
    ("Эликсир прозрения", "Буквы в старых книгах вдруг складываются в смысл.",
     ItemType.CONSUMABLE, ItemRarity.UNCOMMON, 45, 3, "🧪", dict(bonus_intelligence=5)),
    ("Эликсир стойкости", "Боль становится далёкой и чужой.",
     ItemType.CONSUMABLE, ItemRarity.UNCOMMON, 45, 3, "🧪", dict(bonus_endurance=5)),
    ("Эликсир удачи", "Монета падает нужной стороной. Каждый раз.",
     ItemType.CONSUMABLE, ItemRarity.RARE, 90, 5, "🍀", dict(bonus_luck=8)),
    ("Настой полного исцеления", "Раны затягиваются на глазах, с шипением.",
     ItemType.CONSUMABLE, ItemRarity.RARE, 120, 6, "❤️‍🩹", dict(bonus_hp=400)),
    ("Философский раствор", "Говорят, алхимики варили его веками. Ты сварил за вечер.",
     ItemType.CONSUMABLE, ItemRarity.EPIC, 260, 10, "⚗️",
     dict(bonus_hp=250, bonus_mp=250, bonus_luck=3)),
]

# ── Магические фокусы: усиливают конкретную школу ──────────
# (name, desc, type, rarity, price, lvl, icon, school, power, bonuses)
MAGIC_ITEMS = [
    ("Жезл пламени", "Навершие тлеет даже в снегу.",
     ItemType.WEAPON, ItemRarity.RARE, 250, 6, "🔥", "fire", 6,
     dict(bonus_damage=11, bonus_intelligence=6, bonus_mp=20)),
    ("Посох инея", "Дерево покрыто вечной изморозью.",
     ItemType.WEAPON, ItemRarity.RARE, 250, 6, "❄️", "frost", 6,
     dict(bonus_damage=9, bonus_intelligence=7, bonus_endurance=2, bonus_mp=25)),
    ("Скипетр грозы", "В навершии заперта молния. Она недовольна.",
     ItemType.WEAPON, ItemRarity.RARE, 265, 7, "⚡", "storm", 7,
     dict(bonus_damage=12, bonus_agility=4, bonus_intelligence=5)),
    ("Посох увядания", "Трава чернеет там, где он касается земли.",
     ItemType.WEAPON, ItemRarity.RARE, 270, 7, "🌑", "shadow", 7,
     dict(bonus_damage=13, bonus_intelligence=6, bonus_luck=2)),
    ("Ветвь древа", "Живая ветка, которая не желает засыхать.",
     ItemType.WEAPON, ItemRarity.RARE, 245, 6, "🌿", "nature", 6,
     dict(bonus_damage=8, bonus_intelligence=6, bonus_hp=40, bonus_mp=20)),
    ("Скипетр зари", "Тёплый на ощупь. В темноте светит сам.",
     ItemType.WEAPON, ItemRarity.RARE, 255, 6, "✨", "light", 6,
     dict(bonus_damage=9, bonus_intelligence=7, bonus_hp=30, bonus_mp=25)),
    ("Амулет стихии", "Шесть граней, и каждая холоднее предыдущей.",
     ItemType.ACCESSORY, ItemRarity.EPIC, 420, 9, "🔮", None, 5,
     dict(bonus_intelligence=9, bonus_mp=60, bonus_luck=3)),
]

# ── Праздничные предметы: падают только при включённом событии ──
# (name, desc, type, rarity, price, lvl, icon, event, bonuses)
FESTIVE_ITEMS = [
    ("Ледяной клинок Стужи", "Выкован в самую длинную ночь года. Дышит холодом.",
     ItemType.WEAPON, ItemRarity.EPIC, 500, 8, "🎄", "winter",
     dict(bonus_damage=18, bonus_intelligence=5, bonus_agility=3)),
    ("Плащ полуночи", "Расшит серебром. В нём не мёрзнут даже в стужу.",
     ItemType.ARMOR, ItemRarity.EPIC, 480, 8, "🎁", "winter",
     dict(bonus_defense=14, bonus_hp=60, bonus_luck=4)),
    ("Венок жатвы", "Пахнет сеном и дымом костров.",
     ItemType.HELMET, ItemRarity.RARE, 300, 5, "🍂", "harvest",
     dict(bonus_endurance=6, bonus_hp=45, bonus_luck=3)),
    ("Фонарь духов", "Внутри мечется что-то, похожее на светлячка. Или на лицо.",
     ItemType.ACCESSORY, ItemRarity.EPIC, 460, 7, "🏮", "spirits",
     dict(bonus_intelligence=7, bonus_luck=7, bonus_mp=45)),
]

# ── Единственные в мире: выпадают ровно один раз за всю игру ──
# (name, desc, type, rarity, price, lvl, icon, bonuses)
UNIQUE_ITEMS = [
    ("Пожиратель, клинок павшего короля",
     "Последний король держал его, когда пала столица. Клинок помнит.",
     ItemType.WEAPON, ItemRarity.LEGENDARY, 5000, 12, "🌟",
     dict(bonus_damage=40, bonus_strength=12, bonus_luck=6, bonus_hp=80)),
    ("Корона Безымянного",
     "Её носил тот, чьё имя стёрли из всех хроник. Она всё ещё тёплая.",
     ItemType.HELMET, ItemRarity.LEGENDARY, 4200, 12, "👑",
     dict(bonus_defense=22, bonus_intelligence=14, bonus_mp=90, bonus_luck=5)),
    ("Сердце Пожирателя",
     "Оно до сих пор бьётся. Раз в минуту, гулко и медленно.",
     ItemType.ACCESSORY, ItemRarity.LEGENDARY, 6000, 15, "🫀",
     dict(bonus_hp=200, bonus_endurance=15, bonus_strength=8, bonus_defense=10)),
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

    # ── Алхимия ────────────────────────────────────────────
    ("Перегонка дистиллята", CraftStation.ALCHEMY, "Дистиллят", 2, 1, 1.0,
     [("Лечебная трава", 1), ("Пустой флакон", 1)]),
    ("Эликсир силы", CraftStation.ALCHEMY, "Эликсир силы", 30, 3, 0.95,
     [("Дистиллят", 1), ("Корень мандрагоры", 2), ("Кость павшего", 1)]),
    ("Эликсир ловкости", CraftStation.ALCHEMY, "Эликсир ловкости", 30, 3, 0.95,
     [("Дистиллят", 1), ("Корень мандрагоры", 2), ("Обрывок шкуры", 2)]),
    ("Эликсир прозрения", CraftStation.ALCHEMY, "Эликсир прозрения", 30, 3, 0.95,
     [("Дистиллят", 1), ("Лунный цвет", 2)]),
    ("Эликсир стойкости", CraftStation.ALCHEMY, "Эликсир стойкости", 30, 3, 0.95,
     [("Дистиллят", 1), ("Корень мандрагоры", 1), ("Стальной слиток", 1)]),
    ("Эликсир удачи", CraftStation.ALCHEMY, "Эликсир удачи", 70, 5, 0.85,
     [("Дистиллят", 2), ("Пыльца рассвета", 1), ("Лунный цвет", 2)]),
    ("Настой полного исцеления", CraftStation.ALCHEMY, "Настой полного исцеления", 90, 6, 0.85,
     [("Дистиллят", 2), ("Лечебная трава", 6), ("Пыльца рассвета", 1)]),
    ("Философский раствор", CraftStation.ALCHEMY, "Философский раствор", 220, 10, 0.6,
     [("Дистиллят", 3), ("Осколок души", 1), ("Пыльца рассвета", 2), ("Слеза тьмы", 1)]),

    # ── Магические фокусы ──────────────────────────────────
    ("Жезл пламени", CraftStation.JEWELRY, "Жезл пламени", 200, 6, 0.8,
     [("Уголь саламандры", 3), ("Стальной слиток", 2), ("Теневой кристалл", 1)]),
    ("Посох инея", CraftStation.JEWELRY, "Посох инея", 200, 6, 0.8,
     [("Вечный лёд", 3), ("Лунный цвет", 2), ("Теневой кристалл", 1)]),
    ("Скипетр грозы", CraftStation.JEWELRY, "Скипетр грозы", 215, 7, 0.78,
     [("Громовая соль", 3), ("Стальной слиток", 2), ("Теневой кристалл", 1)]),
    ("Посох увядания", CraftStation.JEWELRY, "Посох увядания", 220, 7, 0.75,
     [("Слеза тьмы", 2), ("Кость павшего", 5), ("Осколок души", 1)]),
    ("Ветвь древа", CraftStation.JEWELRY, "Ветвь древа", 195, 6, 0.8,
     [("Корень мандрагоры", 4), ("Лечебная трава", 5), ("Лунный цвет", 2)]),
    ("Скипетр зари", CraftStation.JEWELRY, "Скипетр зари", 205, 6, 0.8,
     [("Пыльца рассвета", 3), ("Стальной слиток", 2), ("Лунный цвет", 2)]),
    ("Амулет стихии", CraftStation.JEWELRY, "Амулет стихии", 380, 9, 0.6,
     [("Уголь саламандры", 2), ("Вечный лёд", 2), ("Громовая соль", 2),
      ("Слеза тьмы", 1), ("Пыльца рассвета", 1), ("Осколок души", 1)]),
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
        ("Слеза тьмы", 0.18, 1, 1),
    ],
}

# Алхимические реагенты сыплются понемногу со всех — их нужно много
ALCHEMY_DROPS = {
    "Болотный зомби": [("Пустой флакон", 0.2, 1, 2), ("Корень мандрагоры", 0.12, 1, 1)],
    "Лесной ворг": [("Корень мандрагоры", 0.18, 1, 2), ("Пустой флакон", 0.15, 1, 1)],
    "Скелет-воин": [("Пустой флакон", 0.2, 1, 2), ("Громовая соль", 0.1, 1, 1)],
    "Гнолл-грабитель": [("Уголь саламандры", 0.15, 1, 1), ("Пустой флакон", 0.18, 1, 2)],
    "Пещерный тролль": [("Уголь саламандры", 0.2, 1, 2), ("Вечный лёд", 0.18, 1, 2)],
    "Теневой призрак": [("Пыльца рассвета", 0.12, 1, 1), ("Вечный лёд", 0.15, 1, 1)],
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
    ("Пустой флакон", 0.3, 1, 3),
    ("Дистиллят", 0.15, 1, 2),
    ("Корень мандрагоры", 0.18, 1, 2),
    ("Уголь саламандры", 0.12, 1, 2),
    ("Вечный лёд", 0.12, 1, 2),
    ("Громовая соль", 0.12, 1, 2),
    ("Пыльца рассвета", 0.06, 1, 1),
    ("Слеза тьмы", 0.05, 1, 1),
]

# Единственные в мире вещи привязаны к боссам и глубоким сундукам
UNIQUE_DROPS = [
    ("mob", "Теневой призрак", "Пожиратель, клинок павшего короля", 0.02),
    ("mob", "Пещерный тролль", "Сердце Пожирателя", 0.02),
    ("chest", None, "Корона Безымянного", 0.01),
]

# Праздничные трофеи: падают только когда событие включено в настройках
FESTIVE_DROPS = [
    ("mob", "Пещерный тролль", "Ледяной клинок Стужи", 0.08),
    ("mob", "Теневой призрак", "Плащ полуночи", 0.08),
    ("chest", None, "Венок жатвы", 0.06),
    ("chest", None, "Фонарь духов", 0.05),
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

# Скупщик и аукционист — отдельный NPC, не привязан к станку
AUCTION_NPC = (
    "Скупщик Молчун",
    "Он не поднимает глаз от гроссбуха. — Выставляй, если не спешишь. "
    "Или продай мне — сразу и дешевле. Всё честно записано, вон, гляди.",
)


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

    # Магические фокусы: усиливают конкретную школу магии
    for name, desc, itype, rarity, price, lvl, icon, school, power, bonuses in MAGIC_ITEMS:
        if name in existing:
            continue
        session.add(Item(
            name=name, description=desc, item_type=itype, rarity=rarity,
            price=price, level_requirement=lvl, icon=icon,
            is_craftable=True, stat_variance=0.18, is_unique_roll=True,
            magic_school=school, magic_power=power, **bonuses,
        ))
        added += 1

    # Праздничные трофеи
    for name, desc, itype, rarity, price, lvl, icon, event, bonuses in FESTIVE_ITEMS:
        if name in existing:
            continue
        session.add(Item(
            name=name, description=desc, item_type=itype, rarity=rarity,
            price=price, level_requirement=lvl, icon=icon,
            stat_variance=0.12, is_unique_roll=True,
            is_festive=True, festive_event=event, **bonuses,
        ))
        added += 1

    # Единственные в мире реликвии
    for name, desc, itype, rarity, price, lvl, icon, bonuses in UNIQUE_ITEMS:
        if name in existing:
            continue
        session.add(Item(
            name=name, description=desc, item_type=itype, rarity=rarity,
            price=price, level_requirement=lvl, icon=icon,
            # У реликвии статы почти не гуляют — она и так одна такая
            stat_variance=0.05, is_unique_roll=True,
            is_one_of_a_kind=True, max_upgrade_level=15, **bonuses,
        ))
        added += 1

    if added:
        await session.flush()
    return added


async def ensure_drop_tables(session) -> int:
    """Досыпает недостающие строки лута.

    Проверяет каждую пару «источник + предмет» отдельно, поэтому новые
    таблицы лута (алхимия, реликвии, праздники) появляются и на уже
    работающей базе, а руками добавленные строки не дублируются.
    """
    items = await _items_by_name(session)
    result = await session.execute(select(Mob))
    mobs = {m.name: m for m in result.scalars().all()}

    # Что уже прописано: (owner_type, owner_id, item_id)
    result = await session.execute(
        select(DropEntry.owner_type, DropEntry.owner_id, DropEntry.item_id)
    )
    existing_drops = {tuple(row) for row in result.all()}

    def is_new(owner_type, owner_id, item_id) -> bool:
        return (owner_type, owner_id, item_id) not in existing_drops

    added = 0
    for mob_name, drops in MOB_DROPS.items():
        mob = mobs.get(mob_name)
        if mob is None:
            continue
        for item_name, chance, lo, hi in drops:
            item = items.get(item_name)
            if item is None or not is_new("mob", mob.id, item.id):
                continue
            session.add(DropEntry(
                owner_type="mob", owner_id=mob.id, item_id=item.id,
                chance=chance, min_quantity=lo, max_quantity=hi,
            ))
            added += 1

    for mob_name, drops in ALCHEMY_DROPS.items():
        mob = mobs.get(mob_name)
        if mob is None:
            continue
        for item_name, chance, lo, hi in drops:
            item = items.get(item_name)
            if item is None or not is_new("mob", mob.id, item.id):
                continue
            session.add(DropEntry(
                owner_type="mob", owner_id=mob.id, item_id=item.id,
                chance=chance, min_quantity=lo, max_quantity=hi,
            ))
            added += 1

    for item_name, chance, lo, hi in CHEST_DROPS:
        item = items.get(item_name)
        if item is None or not is_new("chest", None, item.id):
            continue
        session.add(DropEntry(
            owner_type="chest", owner_id=None, item_id=item.id,
            chance=chance, min_quantity=lo, max_quantity=hi,
        ))
        added += 1

    # Уникальные и праздничные — редкие строки лута. Движок сам следит,
    # чтобы уникальное выпало один раз, а праздничное — только в событие.
    for owner_type, owner_name, item_name, chance in UNIQUE_DROPS + FESTIVE_DROPS:
        item = items.get(item_name)
        if item is None:
            continue
        owner_id = None
        if owner_name is not None:
            mob = mobs.get(owner_name)
            if mob is None:
                continue
            owner_id = mob.id
        if not is_new(owner_type, owner_id, item.id):
            continue
        session.add(DropEntry(
            owner_type=owner_type, owner_id=owner_id, item_id=item.id,
            chance=chance, min_quantity=1, max_quantity=1,
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


async def ensure_auction_npc(session) -> int:
    """Ставит скупщика-аукциониста в стартовой локации."""
    result = await session.execute(
        select(Cell).where(Cell.npc_type == "auctioneer")
    )
    if result.scalars().first():
        return 0

    result = await session.execute(
        select(Cell)
        .where(Cell.location_id == 1)
        .where(Cell.is_passable == True)  # noqa: E712
        .where(Cell.has_npc == False)  # noqa: E712
        .where(Cell.dungeon_template_id.is_(None))
        .order_by(Cell.x.desc(), Cell.y.desc())
    )
    cell = result.scalars().first()
    if cell is None:
        return 0

    name, dialogue = AUCTION_NPC
    cell.has_npc = True
    cell.npc_name = name
    cell.npc_type = "auctioneer"
    cell.npc_dialogue = dialogue
    await session.flush()
    return 1


async def ensure_affinities(session) -> int:
    """Бросает магический дар героям, созданным до появления системы.

    Иначе старые персонажи навсегда остались бы без магии, а новые её
    получали бы — нечестно.
    """
    from core.classes import get_class
    from core.magic import roll_affinities, set_affinities

    result = await session.execute(
        select(Character.id)
        .outerjoin(CharacterAffinity, CharacterAffinity.character_id == Character.id)
        .where(CharacterAffinity.id.is_(None))
    )
    orphan_ids = [row[0] for row in result.all()]
    if not orphan_ids:
        return 0

    # Метка в настройках: дар раздаём один раз, иначе бездарные герои
    # получали бы новый бросок при каждом запуске.
    marker = await session.scalar(
        select(AppSetting.value).where(AppSetting.key == AFFINITY_SEEDED_KEY)
    )
    seeded = {int(x) for x in (marker or "").split(",") if x.strip().isdigit()}
    todo = [cid for cid in orphan_ids if cid not in seeded]
    if not todo:
        return 0

    granted = 0
    for char_id in todo:
        character = await session.get(Character, char_id)
        if character is None:
            continue
        cls_def = await get_class(session, character.character_class)
        pairs = roll_affinities(cls_def)
        if pairs:
            await set_affinities(session, character, pairs)
            granted += 1

    row = (await session.execute(
        select(AppSetting).where(AppSetting.key == AFFINITY_SEEDED_KEY)
    )).scalar_one_or_none()
    value = ",".join(str(x) for x in sorted(seeded | set(todo)))
    if row:
        row.value = value
    else:
        session.add(AppSetting(key=AFFINITY_SEEDED_KEY, value=value))
    await session.flush()
    return granted


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
    stats["auction_npc"] = await ensure_auction_npc(session)
    stats["affinities"] = await ensure_affinities(session)
    stats["mobs"] = await ensure_mob_defaults(session)
    await session.commit()
    return stats
