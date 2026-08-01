import random
from collections import deque
from sqlalchemy import select
from core.database import async_session
from core.models import Location, Mob, Item, ShopItem, Cell, Quest
from core.enums import LocationType, ItemType, ItemRarity
from core import worldgen as W

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


def _ensure_connectivity(cells, grid_size: int = 10):
    """Все проходимые клетки должны быть досягаемы из центра.

    Логика общая с админкой и ботом — живёт в `core/worldgen.py`.
    """
    W.ensure_connectivity(cells, grid_size)


# Жители угловых замков: по два на цитадель (см. build_corner_castle).
# Используется сидом и админкой при создании замка вручную.
CASTLE_NPCS = [
    [("Кастелян Одо", "Свет Ордена держит эти стены...", "storyteller"),
     ("Сестра Люция", "Раненых лечат здесь, не на поле боя...", "healer")],
    [("Тенелов Вирд", "Мы смотрим на ту сторону, откуда приходит тьма...", "storyteller"),
     ("Старый капрал", "Служил ещё при королях. Держи меч остриём к врагу...", "storyteller")],
    [("Хранитель ключей", "Ниже — склепы старше этого форта...", "storyteller"),
     ("Глубинная ведьма", "Я слышу, как вода поёт под нами...", "healer")],
    [("Мастер золы", "Пепел — это память. Мы её храним...", "storyteller"),
     ("Знаменосец Пепла", "Знамя изношено, но не брошено...", "storyteller")],
]


async def seed_database():
    async with async_session() as session:
        result = await session.execute(select(Location))
        if result.scalars().first():
            return

        # Мир: карта 10×10, по краям 36 локаций — 4 угловых замка 25×25
        # (внутри — четыре замка 10×10 по углам) и 32 опасных тракта между
        # ними; внутри кольца — стартовые земли и Логово Пожирателя.
        # Координаты совпадают с engine/world.py DEFAULT_GRID.
        # Мировая карта 10×10: по краям 36 локаций — 4 угловых замка 25×25
        # (внутри — четыре замка 10×10 по углам) и 32 опасных тракта между
        # ними; внутри кольца — стартовые земли и Логово Пожирателя.
        # Координаты совпадают с engine/world.py DEFAULT_GRID.
        LOCATIONS_PLAN = [
            # (имя, описание, тип, мин.уровень, wx, wy, grid_size, картинка)
            # ── стартовые земли (внутри кольца) ──
            ("Погост Костров", "Безопасная деревня среди болот...", LocationType.SAFE, 1, 4, 4, 10, LOCATION_IMAGES[1]),
            ("Тёмный Лес", "Старые дубы скрывают глаза нежити...", LocationType.DANGEROUS, 1, 5, 4, 10, LOCATION_IMAGES[2]),
            ("Заброшенная Крепость", "Каменные стены помнят времена...", LocationType.DANGEROUS, 3, 5, 5, 10, LOCATION_IMAGES[3]),
            ("Катакомбы Павших", "Глубокие подземелья под храмом...", LocationType.DUNGEON, 5, 4, 5, 10, LOCATION_IMAGES[4]),
            ("Логово Пожирателя", "Расщелина в скалах...", LocationType.BOSS, 10, 3, 4, 10, LOCATION_IMAGES[5]),
            # ── угловые замки 25×25 по углам мировой карты ──
            ("Замок Рассвета", "Белые башни Ордена на северо-западе. Безопасная зона с NPC.", LocationType.SAFE, 1, 0, 0, 25, None),
            ("Замок Теней", "Чёрные шпили на северо-востоке. Безопасная зона с NPC.", LocationType.SAFE, 1, 9, 0, 25, None),
            ("Замок Глубин", "Древний форт на юго-западе. Безопасная зона с NPC.", LocationType.SAFE, 1, 0, 9, 25, None),
            ("Замок Пепла", "Обожжённые стены на юго-востоке. Безопасная зона с NPC.", LocationType.SAFE, 1, 9, 9, 25, None),
        ]
        # ── опасные тракты по краям карты: 8 на каждую сторону ──
        _TRAKT_DESC = {
            "Северного": "Мёрзлые пустоши северного края. Снег скрывает тропы...",
            "Восточного": "Пепельные земли, где ветер носит золу...",
            "Южного": "Топи и гнилые болота южного предела...",
            "Западного": "Скалистые осыпи западного края...",
        }
        _NORTH = [(1 + i, 0) for i in range(8)]
        _EAST = [(9, 1 + i) for i in range(8)]
        _SOUTH = [(8 - i, 9) for i in range(8)]
        _WEST = [(0, 8 - i) for i in range(8)]
        for (edge, desc), coords in zip(_TRAKT_DESC.items(),
                                        (_NORTH, _EAST, _SOUTH, _WEST)):
            for i, (wx, wy) in enumerate(coords, start=1):
                LOCATIONS_PLAN.append(
                    (f"Тракт {edge} Предела {i}", desc,
                     LocationType.DANGEROUS, 3, wx, wy, 10, None))
        locations = [
            Location(name=name, description=desc, location_type=lt, min_level=ml,
                     image_url=img, world_x=wx, world_y=wy, grid_size=gs)
            for name, desc, lt, ml, wx, wy, gs, img in LOCATIONS_PLAN
        ]
        session.add_all(locations)
        await session.flush()

        castle_idx = 0
        for loc in locations:
            if loc.name.startswith("Замок"):
                await W.build_corner_castle(session, loc, CELL_STORIES,
                                            rng=random.Random(42 + loc.id),
                                            npcs=CASTLE_NPCS[castle_idx % len(CASTLE_NPCS)])
                castle_idx += 1
            else:
                await W.build_cells(session, loc, CELL_STORIES)

        # Бесшовные швы: пересборка по фактическому соседству на мировой
        # карте (общие функции — в worldgen; одна дверь на границу).
        await W.relink_all(session)

        # Жители деревни — заказчики заданий и торговец.
        result = await session.execute(
            select(Cell).where(Cell.location_id == locations[0].id).where(Cell.is_passable == True)
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

        # Сундуки — в опасных землях: стартовые (2-4) и тракты (10-13).
        danger_ids = [locations[i].id for i in (1, 2, 3, 9, 10, 11, 12)]
        result = await session.execute(
            select(Cell).where(Cell.location_id.in_(danger_ids)).where(Cell.is_passable == True)
        )
        danger_cells = result.scalars().all()
        for cell in random.sample(danger_cells, min(12, len(danger_cells))):
            cell.has_chest = True

        # Мобы: стартовые земли + опасные тракты (локации 2-4 и 10-13).
        mobs_data = [
            {"name": "Помойная крыса", "desc": "Размером с собаку и вдвое наглее...", "level": 1, "hp": 18, "dmg": 3, "def": 0, "gold": 3, "exp": 6, "loc": locations[0].id},
            {"name": "Болотный зомби", "desc": "Медлительный труп...", "level": 1, "hp": 25, "dmg": 4, "def": 1, "gold": 5, "exp": 10, "loc": locations[1].id},
            {"name": "Лесной ворг", "desc": "Крупный волк с чёрной шерстью...", "level": 2, "hp": 40, "dmg": 7, "def": 2, "gold": 8, "exp": 18, "loc": locations[1].id},
            {"name": "Скелет-воин", "desc": "Ожившие останки павшего солдата...", "level": 3, "hp": 50, "dmg": 8, "def": 3, "gold": 12, "exp": 25, "loc": locations[2].id},
            {"name": "Гнолл-грабитель", "desc": "Гибрид человека и гиены...", "level": 4, "hp": 65, "dmg": 10, "def": 3, "gold": 15, "exp": 35, "loc": locations[2].id},
            {"name": "Пещерный тролль", "desc": "Громадина с каменной кожей...", "level": 6, "hp": 100, "dmg": 14, "def": 6, "gold": 25, "exp": 60, "loc": locations[3].id},
            {"name": "Теневой призрак", "desc": "Нематериальная сущность из кошмаров...", "level": 7, "hp": 80, "dmg": 18, "def": 2, "gold": 30, "exp": 70, "loc": locations[3].id},
            {"name": "Культист Бездны", "desc": "Ждал этого дня всю жизнь...", "level": 9, "hp": 95, "dmg": 22, "def": 4, "gold": 45, "exp": 110, "loc": locations[4].id},
            {"name": "Порождение бездны", "desc": "У него слишком много суставов...", "level": 10, "hp": 130, "dmg": 24, "def": 6, "gold": 55, "exp": 130, "loc": locations[4].id},
            {"name": "Страж расщелины", "desc": "Стоит здесь дольше, чем существует королевство...", "level": 11, "hp": 180, "dmg": 23, "def": 12, "gold": 70, "exp": 160, "loc": locations[4].id},
            {"name": "Разбойник с большой дороги", "desc": "Считает путников кормовой базой...", "level": 4, "hp": 60, "dmg": 9, "def": 3, "gold": 14, "exp": 30, "loc": locations[9].id},
            {"name": "Северный канюк", "desc": "Кружит над трактом в ожидании добычи...", "level": 5, "hp": 70, "dmg": 12, "def": 2, "gold": 17, "exp": 36, "loc": locations[10].id},
            {"name": "Скальный хищник", "desc": "Гнездится в осыпях вдоль дороги...", "level": 5, "hp": 75, "dmg": 11, "def": 5, "gold": 16, "exp": 34, "loc": locations[33].id},
            {"name": "Тёмный следопыт", "desc": "Идёт по следу тише, чем думает жертва...", "level": 6, "hp": 85, "dmg": 14, "def": 3, "gold": 19, "exp": 40, "loc": locations[34].id},
            {"name": "Пепельный волк", "desc": "Шерсть серая, как зола...", "level": 6, "hp": 80, "dmg": 13, "def": 3, "gold": 18, "exp": 38, "loc": locations[17].id},
            {"name": "Чернокнижник пепла", "desc": "Поднимает пепельных духов над кострищами...", "level": 7, "hp": 90, "dmg": 16, "def": 5, "gold": 22, "exp": 46, "loc": locations[18].id},
            {"name": "Могильный страж", "desc": "Держит меч даже после смерти...", "level": 7, "hp": 110, "dmg": 15, "def": 8, "gold": 24, "exp": 50, "loc": locations[25].id},
            {"name": "Гниющий великан", "desc": "Каждый шаг оставляет яму...", "level": 8, "hp": 130, "dmg": 18, "def": 7, "gold": 28, "exp": 60, "loc": locations[26].id},
            # ── остальные тракты по краям мировой карты ──
            {"name": "Ледяной падальщик", "desc": "Обедает тем, что замёрзло до него...", "level": 4, "hp": 62, "dmg": 10, "def": 3, "gold": 15, "exp": 32, "loc": locations[11].id},
            {"name": "Вьюжный призрак", "desc": "Появляется из метели...", "level": 5, "hp": 72, "dmg": 12, "def": 2, "gold": 17, "exp": 36, "loc": locations[12].id},
            {"name": "Мёрзлый зомби", "desc": "Тело промёрзло насквозь...", "level": 4, "hp": 68, "dmg": 9, "def": 4, "gold": 14, "exp": 30, "loc": locations[13].id},
            {"name": "Снежный волк", "desc": "Шерсть белая, глаза — льдинки...", "level": 5, "hp": 78, "dmg": 13, "def": 3, "gold": 18, "exp": 38, "loc": locations[14].id},
            {"name": "Костяной странник", "desc": "Идёт по северному тракту без остановки...", "level": 6, "hp": 95, "dmg": 15, "def": 5, "gold": 21, "exp": 44, "loc": locations[15].id},
            {"name": "Северный упырь", "desc": "Согревается чужой кровью...", "level": 6, "hp": 88, "dmg": 16, "def": 4, "gold": 22, "exp": 46, "loc": locations[16].id},
            {"name": "Пепельный хищник", "desc": "Затаивается в золе...", "level": 5, "hp": 74, "dmg": 12, "def": 3, "gold": 17, "exp": 36, "loc": locations[19].id},
            {"name": "Зольный дух", "desc": "Клубок пепла с углями вместо глаз...", "level": 6, "hp": 82, "dmg": 15, "def": 3, "gold": 20, "exp": 42, "loc": locations[20].id},
            {"name": "Обожжённый скелет", "desc": "Кости оплавились, но держатся...", "level": 4, "hp": 66, "dmg": 11, "def": 3, "gold": 14, "exp": 30, "loc": locations[21].id},
            {"name": "Гарпия-падальщица", "desc": "Кружит над трактом, высматривая слабых...", "level": 5, "hp": 70, "dmg": 14, "def": 2, "gold": 18, "exp": 38, "loc": locations[22].id},
            {"name": "Чернокнижник золы", "desc": "Читает судьбы по пеплу...", "level": 7, "hp": 92, "dmg": 17, "def": 5, "gold": 23, "exp": 48, "loc": locations[23].id},
            {"name": "Пепельный страж", "desc": "Стоит на перекрёстке с тех пор, как сгорел город...", "level": 6, "hp": 100, "dmg": 14, "def": 7, "gold": 21, "exp": 44, "loc": locations[24].id},
            {"name": "Топяной змей", "desc": "Скользит по болоту так, что рябь не расходится...", "level": 5, "hp": 76, "dmg": 12, "def": 3, "gold": 17, "exp": 36, "loc": locations[27].id},
            {"name": "Болотный упырь", "desc": "Живёт в трясине и пахнет ею...", "level": 6, "hp": 90, "dmg": 15, "def": 5, "gold": 21, "exp": 44, "loc": locations[28].id},
            {"name": "Трясинный голем", "desc": "Слеплен из грязи, корней и костей...", "level": 7, "hp": 120, "dmg": 16, "def": 8, "gold": 25, "exp": 52, "loc": locations[29].id},
            {"name": "Цапля-мертвяк", "desc": "Стоит на одной ноге, пока жертва не подойдёт...", "level": 5, "hp": 68, "dmg": 13, "def": 2, "gold": 17, "exp": 36, "loc": locations[30].id},
            {"name": "Гнилой латник", "desc": "Броня держит форму лучше, чем владелец...", "level": 6, "hp": 105, "dmg": 14, "def": 7, "gold": 21, "exp": 44, "loc": locations[31].id},
            {"name": "Южный кровосос", "desc": "Пьёт у спящих у костра...", "level": 7, "hp": 85, "dmg": 18, "def": 3, "gold": 24, "exp": 50, "loc": locations[32].id},
            {"name": "Скальный копейщик", "desc": "Обороняет осыпь, которой никто не грозит...", "level": 5, "hp": 80, "dmg": 12, "def": 6, "gold": 17, "exp": 36, "loc": locations[35].id},
            {"name": "Осыпной голем", "desc": "Собран из камней, что падали и не разбились...", "level": 6, "hp": 110, "dmg": 15, "def": 8, "gold": 21, "exp": 44, "loc": locations[36].id},
            {"name": "Горный тролль-одиночка", "desc": "Изгнан из стаи за уродство...", "level": 7, "hp": 130, "dmg": 17, "def": 8, "gold": 26, "exp": 54, "loc": locations[37].id},
            {"name": "Пещерный паук", "desc": "Сеть натянута поперёк ущелья...", "level": 4, "hp": 58, "dmg": 10, "def": 2, "gold": 13, "exp": 28, "loc": locations[38].id},
            {"name": "Западный разбойник", "desc": "Грабит караваны, которых давно не было...", "level": 5, "hp": 72, "dmg": 11, "def": 3, "gold": 16, "exp": 34, "loc": locations[39].id},
            {"name": "Камнекожий страж", "desc": "Кожа вросла в камень...", "level": 6, "hp": 115, "dmg": 13, "def": 9, "gold": 22, "exp": 46, "loc": locations[40].id},
            # Угловые замки: пустоши между замками 10×10 кишат тварью
            {"name": "Обезумевший паломник", "desc": "Шёл к свету — дошёл не туда...", "level": 3, "hp": 50, "dmg": 8, "def": 2, "gold": 11, "exp": 22, "loc": locations[5].id},
            {"name": "Тварь из замкового рва", "desc": "Вода в рвах давно не вода...", "level": 4, "hp": 65, "dmg": 10, "def": 4, "gold": 14, "exp": 30, "loc": locations[5].id},
            {"name": "Чёрный ворон", "desc": "Крупнее орла и умнее, чем кажется...", "level": 3, "hp": 45, "dmg": 9, "def": 1, "gold": 10, "exp": 21, "loc": locations[6].id},
            {"name": "Теневой прислужник", "desc": "Слуга, которого тьма забрала целиком...", "level": 4, "hp": 60, "dmg": 11, "def": 3, "gold": 13, "exp": 28, "loc": locations[6].id},
            {"name": "Глубинная тварь", "desc": "Выползла из склепов под замком...", "level": 4, "hp": 70, "dmg": 10, "def": 5, "gold": 15, "exp": 32, "loc": locations[7].id},
            {"name": "Плесневелый страж", "desc": "Доспех пророс грибницей насквозь...", "level": 5, "hp": 85, "dmg": 12, "def": 6, "gold": 17, "exp": 36, "loc": locations[7].id},
            {"name": "Пепельный голем", "desc": "Слеплен из золы и злобы...", "level": 5, "hp": 95, "dmg": 13, "def": 7, "gold": 18, "exp": 38, "loc": locations[8].id},
            {"name": "Гарпия пепла", "desc": "Её крик слышен за стенами цитадели...", "level": 6, "hp": 80, "dmg": 15, "def": 3, "gold": 20, "exp": 42, "loc": locations[8].id},
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
            # Награда — в единой валюте (gold), как у остальных квестов и
            # всего движка: 120 бронзы + 8 серебра + 2 золота новой системы
            # ≈ 2 золотых; основная награда тут — опыт.
            Quest(name="Первые шаги", description="Убей 3 болотных зомби в Тёмном Лесу.", objective_type="kill", objective_target="Болотный зомби", objective_count=3, reward_gold=2, reward_exp=30, min_level=1, location_id=2),
            Quest(name="Охота на воргов", description="Убей 2 лесных ворга.", objective_type="kill", objective_target="Лесной ворг", objective_count=2, reward_gold=80, reward_exp=50, min_level=2, location_id=2),
            Quest(name="Сбор трав", description="Принеси лекарю 5 лечебных трав.", objective_type="collect", objective_target="Лечебная трава", objective_count=5, reward_gold=30, reward_exp=20, min_level=1, location_id=1, npc_name="Лекарь Мира"),
        ]
        session.add_all(quests)

        await session.commit()
        print("Database seeded: 41 locations (36 on the map rim, corner "
              "castles 25×25), quests, and seamless links.")
