import random
from sqlalchemy import select
from core.database import async_session
from core.models import Location, Mob, Item, ShopItem, AppSetting, Cell
from core.enums import LocationType, ItemType, ItemRarity


CELL_NAMES = [
    "Тёмная поляна", "Старый дуб", "Заросший тропинка", "Болотистая низина",
    "Овраг с туманом", "Покинутый костёр", "Чаща терновника", "Каменная гряда",
    "Ручей с мутной водой", "Поваленное дерево", "Гнездо воронов", "Заброшенная телега",
    "Мхи и папоротники", "Склеп под корнями", "Разбитый обоз", "Яма с костями",
    "Следы копыт", "Виселица у дороги", "Табличка с предупреждением", "Заросший колодец",
    "Пещерка в холме", "Скопление грибов", "Топкое болото", "Каменный идол",
    "Разорванный флаг", "Следы битвы", "Заброшенная шахта", "Ручей с кристаллами",
    "Древний менгир", "Пепельная зона", "Кустарник шиповника", "Тропа следопыта",
    "Воронка от взрыва", "Заброшенная хижина", "Мостик через ручей", "Заросший сад",
    "Кострище гоблинов", "Скала с рунами", "Темная заводь", "Поляна с травами",
    "Остатки костра", "Заброшенная мельница", "Туннель в зарослях", "Скопление камней",
    "Ветхая часовня", "Яма с ядом", "Разрушенная стена", "Колодец с лозой",
    "Перекрёсток троп", "Темный овраг", "Старый мост", "Заросший пруд",
    "Поваленная статуя", "Костяная куча", "Гниющий пень", "Разорванная сеть",
    "Скала с гнездом", "Заброшенный колодец", "Тропа в никуда", "Пепельный склон",
    "Дупло с сокровищем", "Разрушенная башня", "Заросший канал", "Каменный мостик",
    "Поляна мертвецов", "Старый курган", "Топь с огоньками", "Разбитый щит",
    "Древний дольмен", "Кусты черники", "Овраг с водопадом", "Заброшенный лагерь",
    "Следы когтей", "Висельная роща", "Костяная арка", "Темная чаща",
    "Разрушенная дорога", "Заросший огород", "Пещера с эхом", "Каменный столб",
    "Болотные огоньки", "Старый кладбище", "Тропа ведьмы", "Разорванная карта",
    "Дуб с петлёй", "Заброшенная тюрьма", "Ручей с золотом", "Скала с трещиной",
    "Поляна с кострами", "Темный туннель", "Старый маяк", "Заросший порт",
    "Кораблекрушение", "Пляж с костями", "Скала с гнездом дракона", "Вулканический пепел",
]

CELL_DESCRIPTIONS = [
    "Вокруг царит гнетущая тишина, нарушаемая лишь шорохом невидимых существ.",
    "Воздух здесь густой и тяжёлый, словно пропитанный древним злом.",
    "Под ногами хрустят сухие ветки, а в кронах деревьев что-то шевелится.",
    "Туман сгущается, скрывая опасности за каждым поворотом.",
    "Здесь когда-то произошла битва. Кости ещё лежат среди травы.",
    "Странный свет просачивается сквозь листву, окрашивая всё в зелёный.",
    "Запах гнили и серы не даёт нормально дышать.",
    "Старые руны выбиты на камне, но их смысл давно утерян.",
    "Вода здесь чёрная и не отражает небо.",
    "Ветер несёт зловещий шёпот с неведомых сторон.",
]


async def seed_database():
    async with async_session() as session:
        result = await session.execute(select(Location))
        if result.scalars().first():
            return

        locations = [
            Location(name="Погост Костров", description="Безопасная деревня среди болот. Здесь торгуют странствующие купцы и изгнанники находят пристанище.", location_type=LocationType.SAFE, min_level=1),
            Location(name="Тёмный Лес", description="Старые дубы скрывают глаза нежити. Шёпот слышен за каждым деревом.", location_type=LocationType.DANGEROUS, min_level=1),
            Location(name="Заброшенная Крепость", description="Каменные стены помнят времена, когда рыцари ещё носили сияющие доспехи. Теперь здесь обитают гноллы и скелеты.", location_type=LocationType.DANGEROUS, min_level=3),
            Location(name="Катакомбы Павших", description="Глубокие подземелья под храмом забытого бога. Легенды гласят, что в самых низах спит древнее зло.", location_type=LocationType.DUNGEON, min_level=5),
            Location(name="Логово Пожирателя", description="Расщелина в скалах, откуда исходит серная вонь. Здесь обитает Пожиратель — древний дракон тьмы.", location_type=LocationType.BOSS, min_level=10),
        ]
        session.add_all(locations)
        await session.flush()

        # Generate 10x10 cells for each location
        for loc in locations:
            for x in range(10):
                for y in range(10):
                    name = random.choice(CELL_NAMES)
                    desc = random.choice(CELL_DESCRIPTIONS)
                    # Border cells are impassable (world edge)
                    is_passable = not (x == 0 or x == 9 or y == 0 or y == 9)
                    cell = Cell(
                        location_id=loc.id,
                        x=x,
                        y=y,
                        name=name,
                        description=desc,
                        is_passable=is_passable,
                    )
                    session.add(cell)
        await session.flush()

        # Assign mobs to random cells in dangerous+ locations
        mobs_data = [
            {"name": "Болотный зомби", "desc": "Медлительный труп, пропитанный ядовитыми испарениями.", "level": 1, "hp": 25, "dmg": 4, "def": 1, "gold": 5, "exp": 10, "loc": 2},
            {"name": "Лесной ворг", "desc": "Крупный волк с чёрной шерстью и светящимися глазами.", "level": 2, "hp": 40, "dmg": 7, "def": 2, "gold": 8, "exp": 18, "loc": 2},
            {"name": "Скелет-воин", "desc": "Ожившие останки павшего солдата. Его кости стучат мерным ритмом.", "level": 3, "hp": 50, "dmg": 8, "def": 3, "gold": 12, "exp": 25, "loc": 3},
            {"name": "Гнолл-грабитель", "desc": "Гибрид человека и гиены. Пахнет тленом и жадностью.", "level": 4, "hp": 65, "dmg": 10, "def": 3, "gold": 15, "exp": 35, "loc": 3},
            {"name": "Пещерный тролль", "desc": "Громадина с каменной кожей. Его шаги заставляют дрожать стены.", "level": 6, "hp": 100, "dmg": 14, "def": 6, "gold": 25, "exp": 60, "loc": 4},
            {"name": "Теневой призрак", "desc": "Нематериальная сущность из кошмаров. Прикасается к разуму, а не к плоти.", "level": 7, "hp": 80, "dmg": 18, "def": 2, "gold": 30, "exp": 70, "loc": 4},
        ]

        created_mobs = []
        for md in mobs_data:
            mob = Mob(
                name=md["name"], description=md["desc"], level=md["level"],
                hp=md["hp"], damage=md["dmg"], defense=md["def"],
                gold_reward=md["gold"], exp_reward=md["exp"],
                location_id=md["loc"],
            )
            session.add(mob)
            created_mobs.append((mob, md["loc"]))
        await session.flush()

        # Assign mobs to random passable cells
        for mob, loc_id in created_mobs:
            result = await session.execute(
                select(Cell).where(Cell.location_id == loc_id).where(Cell.is_passable == True)
            )
            cells = result.scalars().all()
            if cells:
                target = random.choice(cells)
                target.mob_id = mob.id

        items = [
            Item(name="Ржавый меч", description="Клинок, который видел лучшие дни. Всё ещё режет.", item_type=ItemType.WEAPON, rarity=ItemRarity.COMMON, price=20, bonus_damage=3, icon="🗡"),
            Item(name="Дубинка гнолла", description="Тяжёлая палка с вбитым гвоздём. Грубо, но эффективно.", item_type=ItemType.WEAPON, rarity=ItemRarity.COMMON, price=35, bonus_damage=5, icon="🏏"),
            Item(name="Кинжал теней", description="Лезвие из метеоритного железа. Едва заметно в темноте.", item_type=ItemType.WEAPON, rarity=ItemRarity.RARE, price=120, bonus_damage=10, bonus_agility=3, icon="🗡"),
            Item(name="Старая кольчуга", description="Ржавые кольца, но лучше, чем рубаха.", item_type=ItemType.ARMOR, rarity=ItemRarity.COMMON, price=25, bonus_defense=3, bonus_hp=10, icon="🦺"),
            Item(name="Мантия послушника", description="Простая ткань с вышитыми рунами защиты.", item_type=ItemType.ARMOR, rarity=ItemRarity.COMMON, price=25, bonus_defense=2, bonus_mp=15, icon="🥋"),
            Item(name="Шлем изгнанника", description="Железный шлем с зарубкой за каждую пережитую битву.", item_type=ItemType.HELMET, rarity=ItemRarity.UNCOMMON, price=40, bonus_defense=2, bonus_endurance=2, icon="🪖"),
            Item(name="Сапоги скитальца", description="Изношенная кожа, но удобные.", item_type=ItemType.BOOTS, rarity=ItemRarity.COMMON, price=15, bonus_agility=1, icon="👢"),
            Item(name="Кольцо удачи", description="Серебряное кольцо с выгравированным клевером.", item_type=ItemType.ACCESSORY, rarity=ItemRarity.UNCOMMON, price=60, bonus_luck=5, icon="💍"),
            Item(name="Зелье здоровья", description="Красная жидкость с запахом трав. Восстанавливает 30 HP.", item_type=ItemType.CONSUMABLE, rarity=ItemRarity.COMMON, price=10, icon="🧪"),
            Item(name="Зелье маны", description="Синяя субстанция. Восстанавливает 20 MP.", item_type=ItemType.CONSUMABLE, rarity=ItemRarity.COMMON, price=10, icon="🧪"),
        ]
        session.add_all(items)
        await session.flush()

        shop_items = [
            ShopItem(item_id=1, price=20, stock=-1),
            ShopItem(item_id=2, price=35, stock=5),
            ShopItem(item_id=4, price=25, stock=-1),
            ShopItem(item_id=5, price=25, stock=-1),
            ShopItem(item_id=6, price=40, stock=3),
            ShopItem(item_id=7, price=15, stock=-1),
            ShopItem(item_id=8, price=60, stock=1),
            ShopItem(item_id=9, price=10, stock=-1),
            ShopItem(item_id=10, price=10, stock=-1),
        ]
        session.add_all(shop_items)
        await session.commit()
        print("Database seeded with 500 cells.")
