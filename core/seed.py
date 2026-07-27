import random
from collections import deque
from sqlalchemy import select
from core.database import async_session
from core.models import Location, Mob, Item, ShopItem, Cell, Quest
from core.enums import LocationType, ItemType, ItemRarity

LOCATION_IMAGES = {
    1: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc1_safe.jpg",
    2: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc2_forest.jpg",
    3: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc3_fortress.jpg",
    4: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc4_dungeon.jpg",
    5: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc5_boss.jpg",
}

CELL_STORIES = [
    ("Тёмная поляна", "Ты выходишь на поляну, где трава почернела от проклятия...", "grass"),
    ("Старый дуб", "Древний дуб, старше самого королевства...", "forest"),
    ("Заросший тропинка", "Едва заметная тропа вьётся между колючими кустами...", "road"),
    ("Болотистая низина", "Воздух здесь густой и тяжёлый...", "water"),
    ("Овраг с туманом", "Глубокий овраг заполнен белым туманом...", "wall"),
    ("Покинутый костёр", "На камнях вокруг кострища — следы когтей...", "grass"),
    ("Чаща терновника", "Колючие ветви переплелись в непроходимую стену...", "forest"),
    ("Каменная гряда", "Груда валунов, похожих на гигантские черепа...", "wall"),
    ("Ручей с мутной водой", "Вода в ручье мутная и тёплая...", "water"),
    ("Поваленное дерево", "Могучий дуб лежит поперёк тропы...", "forest"),
    ("Гнездо воронов", "Сотни ворон сидят на мёртвых деревьях...", "forest"),
    ("Заброшенная телега", "Полуразрушенная телега с грузом гнилых тыкв...", "road"),
    ("Мхи и папоротники", "Здесь всё покрыто толстым слоем мха...", "grass"),
    ("Склеп под корнями", "Между корнями старого дерева видна каменная плита...", "wall"),
    ("Разбитый обоз", "Обломки повозки разбросаны по поляне...", "road"),
    ("Яма с костями", "Неестественно ровная яма, дно которой устлано костями...", "wall"),
    ("Следы копыт", "В мягкой земле отпечатались следы копыт...", "road"),
    ("Виселица у дороги", "Гнилой столб с оборванной верёвкой...", "road"),
    ("Табличка с предупреждением", "Истлевшая деревянная табличка...", "road"),
    ("Заросший колодец", "Колодец зарос плющом...", "water"),
    ("Пещерка в холме", "Небольшой вход в холм, обрамлённый синим мхом...", "wall"),
    ("Скопление грибов", "Поляна усыпана светящимися грибами...", "grass"),
    ("Топкое болото", "Земля здесь ходит ходуном...", "water"),
    ("Каменный идол", "Фигура безликого бога из чёрного базальта...", "wall"),
    ("Разорванный флаг", "Остатки знамени королевской гвардии...", "road"),
    ("Следы битвы", "Выжженная земля, перекошенные деревья...", "grass"),
    ("Заброшенная шахта", "Вход в шахту завален...", "wall"),
    ("Ручей с кристаллами", "Дно ручья усыпано тёмными кристаллами...", "water"),
    ("Древний менгир", "Одинокий стоящий камень, старше цивилизации...", "wall"),
    ("Пепельная зона", "Всё здесь покрыто слоем серого пепла...", "grass"),
    ("Кустарник шиповника", "Шиповник здесь вырос до размеров деревьев...", "forest"),
    ("Тропа следопыта", "Едва заметные метки на деревьях...", "road"),
    ("Воронка от взрыва", "Огромный кратер, как будто упал метеорит...", "wall"),
    ("Заброшенная хижина", "Хижина стоит, но дверь открыта...", "village"),
    ("Мостик через ручей", "Гнилой мостик едва держится...", "road"),
    ("Заросший сад", "Когда-то здесь росли розы...", "forest"),
    ("Кострище гоблинов", "Круг из камней, внутри — зола и кости...", "grass"),
    ("Скала с рунами", "Отвесная скала испещрена светящимися рунами...", "wall"),
    ("Темная заводь", "Вода здесь неподвижна, как зеркало...", "water"),
    ("Поляна с травами", "Редкие лечебные травы растут среди обычных сорняков...", "grass"),
    ("Остатки костра", "Угли ещё теплые...", "grass"),
    ("Заброшенная мельница", "Мельничные жернова крутятся сами по себе...", "village"),
    ("Туннель в зарослях", "Живые изгороди сомкнулись, образуя туннель...", "forest"),
    ("Скопление камней", "Камни сложены в пирамиду...", "wall"),
    ("Ветхая часовня", "Крыша обвалилась, но алтарь цел...", "village"),
    ("Яма с ядом", "Воронка, заполненная бурлящей зелёной жидкостью...", "water"),
    ("Разрушенная стена", "Остатки каменной стены...", "wall"),
    ("Колодец с лозой", "Колодец обвит пурпурной лозой...", "water"),
    ("Перекрёсток троп", "Пять троп сходятся в одной точке...", "road"),
    ("Темный овраг", "Овраг такой глубокий, что дно в вечной тени...", "wall"),
    ("Старый мост", "Каменная арка через бездну...", "road"),
    ("Заросший пруд", "Поверхность пруда покрыта плотной плёнкой...", "water"),
    ("Поваленная статуя", "Гигантская статуя короля лежит лицом вниз...", "wall"),
    ("Костяная куча", "Гора костей разных существ...", "grass"),
    ("Гниющий пень", "Пень размером с дом...", "forest"),
    ("Разорванная сеть", "Огромная паутина между деревьями разорвана...", "forest"),
    ("Скала с гнездом", "На отвесной скале — гнездо из человеческих костей...", "wall"),
    ("Заброшенный колодец", "Колодец засыпан, но из щелей сочётся вода...", "water"),
    ("Тропа в никуда", "Тропа идёт прямо и резко обрывается у пропасти...", "road"),
    ("Пепельный склон", "Склон горы покрыт вулканическим пеплом...", "wall"),
    ("Дупло с сокровищем", "В дупле старого дуба блестит что-то золотое...", "forest"),
    ("Разрушенная башня", "Остатки сторожевой башни...", "wall"),
    ("Заросший канал", "Каменный канал, когда-то ведший в город...", "water"),
    ("Каменный мостик", "Мостик через бездну...", "road"),
    ("Поляна мертвецов", "Все деревья здесь мёртвы, но стоят...", "forest"),
    ("Старый курган", "Холм, искусственно насыпанный тысячи лет назад...", "wall"),
    ("Топь с огоньками", "Болото, где над каждой лужей парит огонёк...", "water"),
    ("Разбитый щит", "Щит королевской гвардии, расколотый пополам...", "road"),
    ("Древний дольмен", "Три камня, поддерживающие четвёртый...", "wall"),
    ("Кусты черники", "Единственное безопасное место...", "grass"),
    ("Овраг с водопадом", "Вода падает с высоты, но звука нет...", "water"),
    ("Заброшенный лагерь", "Палатки стоят, костры потушены...", "grass"),
    ("Следы когтей", "Следы на камне. Камень расколот...", "wall"),
    ("Висельная роща", "Деревья нагружены верёвками...", "forest"),
    ("Костяная арка", "Арка из человеческих костей...", "wall"),
    ("Темная чаща", "Деревья стоят так плотно...", "forest"),
    ("Разрушенная дорога", "Брусчатка вздута корнями...", "road"),
    ("Заросший огород", "Грядки с овощами, но они выросли до неестественных размеров...", "grass"),
    ("Пещера с эхом", "Пещера, где эхо отвечает не твоим голосом...", "wall"),
    ("Каменный столб", "Столб с выбитыми именами...", "wall"),
    ("Болотные огоньки", "Огоньки танцуют над болотом...", "water"),
    ("Старый кладбище", "Надгробия без имён...", "grass"),
    ("Тропа ведьмы", "Тропа, усыпанная странными травами...", "road"),
    ("Разорванная карта", "На земле лежит карта этой местности...", "road"),
    ("Дуб с петлёй", "На ветке висит свежая петля...", "forest"),
    ("Заброшенная тюрьма", "Железные клетки пусты...", "wall"),
    ("Ручей с золотом", "На дне ручая блестит золото...", "water"),
    ("Скала с трещиной", "В трещине скалы видно движение...", "wall"),
    ("Поляна с кострами", "Десятки потухших костров...", "grass"),
    ("Темный туннель", "Туннель ведёт под гору...", "wall"),
    ("Старый маяк", "Маяк стоит посреди леса...", "village"),
    ("Заросший порт", "Каменные причалы, но нет воды...", "water"),
    ("Кораблекрушение", "Разбитый корабль посреди леса...", "water"),
    ("Пляж с костями", "Берег чёрного озера...", "water"),
    ("Скала с гнездом дракона", "На вершине утёса — гнездо...", "wall"),
    ("Вулканический пепел", "Земля горячая под ногами...", "wall"),
]


def _ensure_connectivity(cells):
    """Make sure all passable cells are reachable from spawn (5,5)."""
    passable = {(c.x, c.y): c for c in cells if c.is_passable}
    if not passable:
        return

    start = (5, 5)
    if start not in passable:
        for c in cells:
            if c.x == 5 and c.y == 5:
                c.is_passable = True
                passable[start] = c
                break

    visited = set()
    queue = deque([start])
    visited.add(start)

    while queue:
        x, y = queue.popleft()
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) in passable and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append((nx, ny))

    for (x, y), cell in passable.items():
        if (x, y) not in visited:
            cell.is_passable = False
            cell.tile_type = "wall"


async def seed_database():
    async with async_session() as session:
        result = await session.execute(select(Location))
        if result.scalars().first():
            return

        locations = [
            Location(name="Погост Костров", description="Безопасная деревня среди болот...", location_type=LocationType.SAFE, min_level=1, image_url=LOCATION_IMAGES[1], world_x=0, world_y=0),
            Location(name="Тёмный Лес", description="Старые дубы скрывают глаза нежити...", location_type=LocationType.DANGEROUS, min_level=1, image_url=LOCATION_IMAGES[2], world_x=1, world_y=0),
            Location(name="Заброшенная Крепость", description="Каменные стены помнят времена...", location_type=LocationType.DANGEROUS, min_level=3, image_url=LOCATION_IMAGES[3], world_x=2, world_y=0),
            Location(name="Катакомбы Павших", description="Глубокие подземелья под храмом...", location_type=LocationType.DUNGEON, min_level=5, image_url=LOCATION_IMAGES[4], world_x=3, world_y=0),
            Location(name="Логово Пожирателя", description="Расщелина в скалах...", location_type=LocationType.BOSS, min_level=10, image_url=LOCATION_IMAGES[5], world_x=4, world_y=0),
        ]
        session.add_all(locations)
        await session.flush()

        story_idx = 0
        for loc in locations:
            cells = []
            for x in range(10):
                for y in range(10):
                    is_border = (x == 0 or x == 9 or y == 0 or y == 9)
                    is_wall = is_border or (not is_border and random.random() < 0.15 and (x, y) != (5, 5))

                    name, desc, tile = CELL_STORIES[story_idx % len(CELL_STORIES)]
                    story_idx += 1

                    cell = Cell(
                        location_id=loc.id,
                        x=x,
                        y=y,
                        name=name,
                        description=desc,
                        is_passable=not is_wall,
                        tile_type=tile if not is_wall else "wall",
                        has_tree=(not is_wall and tile == "forest" and random.random() < 0.3),
                        has_campfire=(not is_wall and random.random() < 0.05),
                        has_house=(not is_wall and tile == "village" and random.random() < 0.3),
                    )
                    session.add(cell)
                    cells.append(cell)

            _ensure_connectivity(cells)
            await session.flush()

        # Link locations seamlessly: east-west borders
        # loc1 (0,0) east border -> loc2 (1,0) west border
        for i in range(len(locations) - 1):
            loc_a = locations[i]
            loc_b = locations[i + 1]
            for row in range(1, 9):
                # A's east border (x=row, y=9) -> B's west border (x=row, y=0)
                result = await session.execute(
                    select(Cell).where(Cell.location_id == loc_a.id).where(Cell.x == row).where(Cell.y == 9)
                )
                cell_a = result.scalar_one_or_none()
                result = await session.execute(
                    select(Cell).where(Cell.location_id == loc_b.id).where(Cell.x == row).where(Cell.y == 0)
                )
                cell_b = result.scalar_one_or_none()
                if cell_a and cell_b:
                    cell_a.is_passable = True
                    cell_a.tile_type = "road"
                    cell_a.target_location_id = loc_b.id
                    cell_a.target_x = row
                    cell_a.target_y = 1
                    cell_b.is_passable = True
                    cell_b.tile_type = "road"
                    cell_b.target_location_id = loc_a.id
                    cell_b.target_x = row
                    cell_b.target_y = 8

        # Add NPCs to safe location
        result = await session.execute(
            select(Cell).where(Cell.location_id == 1).where(Cell.is_passable == True)
        )
        safe_cells = result.scalars().all()
        if len(safe_cells) >= 3:
            npcs = [
                ("Старейшина Григор", "Добро пожаловать в Погост, странник...", "storyteller"),
                ("Торговец Варн", "У меня есть всё, что нужно выжившему...", "merchant"),
                ("Лекарь Мира", "Ты ранен? Я могу исцелить...", "quest_giver"),
            ]
            for i, (npc_name, dialogue, npc_type) in enumerate(npcs):
                cell = safe_cells[i * 3]
                cell.has_npc = True
                cell.npc_name = npc_name
                cell.npc_dialogue = dialogue
                cell.npc_type = npc_type

        # Add chests randomly
        result = await session.execute(
            select(Cell).where(Cell.location_id.in_([2, 3, 4])).where(Cell.is_passable == True)
        )
        danger_cells = result.scalars().all()
        for cell in random.sample(danger_cells, min(8, len(danger_cells))):
            cell.has_chest = True

        mobs_data = [
            {"name": "Болотный зомби", "desc": "Медлительный труп...", "level": 1, "hp": 25, "dmg": 4, "def": 1, "gold": 5, "exp": 10, "loc": 2},
            {"name": "Лесной ворг", "desc": "Крупный волк с чёрной шерстью...", "level": 2, "hp": 40, "dmg": 7, "def": 2, "gold": 8, "exp": 18, "loc": 2},
            {"name": "Скелет-воин", "desc": "Ожившие останки павшего солдата...", "level": 3, "hp": 50, "dmg": 8, "def": 3, "gold": 12, "exp": 25, "loc": 3},
            {"name": "Гнолл-грабитель", "desc": "Гибрид человека и гиены...", "level": 4, "hp": 65, "dmg": 10, "def": 3, "gold": 15, "exp": 35, "loc": 3},
            {"name": "Пещерный тролль", "desc": "Громадина с каменной кожей...", "level": 6, "hp": 100, "dmg": 14, "def": 6, "gold": 25, "exp": 60, "loc": 4},
            {"name": "Теневой призрак", "desc": "Нематериальная сущность из кошмаров...", "level": 7, "hp": 80, "dmg": 18, "def": 2, "gold": 30, "exp": 70, "loc": 4},
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

        for mob, loc_id in created_mobs:
            result = await session.execute(
                select(Cell).where(Cell.location_id == loc_id).where(Cell.is_passable == True)
            )
            cells = result.scalars().all()
            if cells:
                target = random.choice(cells)
                target.mob_id = mob.id

        items = [
            Item(name="Ржавый меч", description="Клинок, который видел лучшие дни...", item_type=ItemType.WEAPON, rarity=ItemRarity.COMMON, price=20, bonus_damage=3, icon="🗡"),
            Item(name="Дубинка гнолла", description="Тяжёлая палка с вбитым гвоздём...", item_type=ItemType.WEAPON, rarity=ItemRarity.COMMON, price=35, bonus_damage=5, icon="🏏"),
            Item(name="Кинжал теней", description="Лезвие из метеоритного железа...", item_type=ItemType.WEAPON, rarity=ItemRarity.RARE, price=120, bonus_damage=10, bonus_agility=3, icon="🗡"),
            Item(name="Старая кольчуга", description="Ржавые кольца, но лучше, чем рубаха...", item_type=ItemType.ARMOR, rarity=ItemRarity.COMMON, price=25, bonus_defense=3, bonus_hp=10, icon="🦺"),
            Item(name="Мантия послушника", description="Простая ткань с вышитыми рунами...", item_type=ItemType.ARMOR, rarity=ItemRarity.COMMON, price=25, bonus_defense=2, bonus_mp=15, icon="🥋"),
            Item(name="Шлем изгнанника", description="Железный шлем с зарубкой...", item_type=ItemType.HELMET, rarity=ItemRarity.UNCOMMON, price=40, bonus_defense=2, bonus_endurance=2, icon="🪖"),
            Item(name="Сапоги скитальца", description="Изношенная кожа, но удобные...", item_type=ItemType.BOOTS, rarity=ItemRarity.COMMON, price=15, bonus_agility=1, icon="👢"),
            Item(name="Кольцо удачи", description="Серебряное кольцо с выгравированным клевером...", item_type=ItemType.ACCESSORY, rarity=ItemRarity.UNCOMMON, price=60, bonus_luck=5, icon="💍"),
            Item(name="Зелье здоровья", description="Красная жидкость с запахом трав...", item_type=ItemType.CONSUMABLE, rarity=ItemRarity.COMMON, price=10, icon="🧪"),
            Item(name="Зелье маны", description="Синяя субстанция...", item_type=ItemType.CONSUMABLE, rarity=ItemRarity.COMMON, price=10, icon="🧪"),
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

        # Seed quests
        quests = [
            Quest(name="Первые шаги", description="Убей 3 болотных зомби в Тёмном Лесу.", objective_type="kill", objective_target="Болотный зомби", objective_count=3, reward_gold=50, reward_exp=30, min_level=1, location_id=2),
            Quest(name="Охота на воргов", description="Убей 2 лесных ворга.", objective_type="kill", objective_target="Лесной ворг", objective_count=2, reward_gold=80, reward_exp=50, min_level=2, location_id=2),
            Quest(name="Сбор трав", description="Принеси лекарю 5 лечебных трав.", objective_type="collect", objective_target="Лечебная трава", objective_count=5, reward_gold=30, reward_exp=20, min_level=1, location_id=1, npc_name="Лекарь Мира"),
        ]
        session.add_all(quests)

        await session.commit()
        print("Database seeded with 500 unique cells, quests, and seamless links.")
