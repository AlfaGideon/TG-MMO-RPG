import random
from collections import deque
from sqlalchemy import select, delete
from core.database import async_session
from core.models import Location, Mob, Item, ShopItem, Cell, Quest, AppSetting
from core.enums import LocationType, ItemType, ItemRarity
from core import worldgen as W

LOCATION_IMAGES = {
    1: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc1_safe.jpg",
    2: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc2_forest.jpg",
    3: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc3_fortress.jpg",
    4: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc4_dungeon.jpg",
    5: "https://raw.githubusercontent.com/AlfaGideon/TG-MMO-RPG/main/admin/static/loc5_boss.jpg",
}

# Образ сгенерированной локации по её типу.
LOC_IMAGE_BY_TYPE = {
    LocationType.SAFE: LOCATION_IMAGES[1],
    LocationType.DANGEROUS: LOCATION_IMAGES[2],
    LocationType.DUNGEON: LOCATION_IMAGES[4],
    LocationType.BOSS: LOCATION_IMAGES[5],
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
    ("Поляна мертвецов", "Все деревья здесь мёртвые, но стоят...", "forest"),
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


# ════════════════════════════════════════════════════════════════
# Процедурная генерация «живого мира»
#
# На мировой карте 10×10 захардкоржены только четыре угловые клетки:
#   (0,0) (9,0) (0,9) (9,9) — четыре замка-цитадели.
# Остальные 32 локации генерируются свободно по сиду: позиции, имена,
# тип и уровень. Сид тоже подбирается свободно (случайно), а понравившийся
# можно сохранить в админке и переиспользовать.
# ════════════════════════════════════════════════════════════════

# Угловые замки-цитадели: (имя, описание, x, y). Только они зафиксированы.
CORNER_CASTLES = [
    ("Замок Рассвета", "Белые башни Ордена на северо-западе. Безопасная зона с NPC.", 0, 0),
    ("Замок Теней", "Чёрные шпили на северо-востоке. Безопасная зона с NPC.", 9, 0),
    ("Замок Глубин", "Древний форт на юго-западе. Безопасная зона с NPC.", 0, 9),
    ("Замок Пепла", "Обожжённые стены на юго-востоке. Безопасная зона с NPC.", 9, 9),
]
CORNER_NAMES = {name for name, *_ in CORNER_CASTLES}
CORNER_CELLS = {(x, y) for _, _, x, y in CORNER_CASTLES}

# Сколько свободных локаций генерировать (помимо 4 угловых замков).
FREE_LOCATIONS = 32
WORLD_GRID = 10
_CENTER = (WORLD_GRID - 1) / 2.0  # 4.5

# Имена свободных локаций: корень (номинатив) + определение (генитив).
# Так имя остаётся грамматически чистым при любом роде корня:
# «Болото Тумана», «Курган Костей», «Развалины Теней».
_NAME_ROOTS = [
    "Болото", "Лес", "Бор", "Чаща", "Пуща", "Топь", "Пустошь", "Развалины",
    "Форпост", "Острог", "Крепость", "Сторожка", "Рудник", "Шахта", "Катакомбы",
    "Склеп", "Грот", "Пещера", "Ущелье", "Овраг", "Урочище", "Перевал", "Курган",
    "Могильник", "Погост", "Кладбище", "Озеро", "Заводь", "Пруд", "Источник",
    "Гряда", "Утёс", "Плато", "Низина", "Долина", "Падь", "Дол", "Перекрёсток",
    "Тропа", "Брод", "Мыс", "Остров", "Холм", "Гать", "Яр", "Вершь",
]
_NAME_MODIFIERS = [
    "Тумана", "Теней", "Костей", "Пепла", "Эха", "Ветров", "Отчаяния", "Шёпотов",
    "Памяти", "Тьмы", "Льда", "Крови", "Погибели", "Забвения", "Скорби", "Гнева",
    "Пустоты", "Молчания", "Снов", "Бездны", "Воронов", "Волков", "Пауков", "Червей",
    "Рассвета", "Полуночи", "Слёз", "Обета", "Пепелища", "Грозы", "Золы", "Грибов",
    "Колдовства", "Стужи", "Проклятых", "Забытых", "Древних", "Упавших", "Седых",
    "Багровых", "Молчащих", "Спящих",
]

# Атмосферные подписи по типу локации — короткая «душа» места.
_DESC_BY_TYPE = {
    LocationType.SAFE: [
        "Здесь ещё можно перевести дух: дымок над крышами, голоса, тепло очага.",
        "Редкий угол, где тьма пока не добралась. Люди живут, как умеют.",
        "Тихое место среди погибшего мира. Сторожа не спят, но и не нападают.",
    ],
    LocationType.DANGEROUS: [
        "Тропы здесь помнят крики. Каждый шаг — за чьим-то вниманием.",
        "Земля дышит опасностью: следы, шорохи, чужие глаза в кустах.",
        "Сюда заходят за добычей и не все возвращаются. Будь начеку.",
    ],
    LocationType.DUNGEON: [
        "Под ногами — тьма и камень. Где-то внизу ждёт то, что не любит свет.",
        "Сырые своды хранят старое зло. Факел чадит, эхо чужое.",
        "Глубокое нутро земли, полное костей и забытой жажды.",
    ],
    LocationType.BOSS: [
        "Воздух здесь тяжёлый и чужой. Дальше дороги нет — только бой.",
        "Это логово чего-то древнего и голодного. Назад пути не будет.",
        "Земля дрожит под ногами: здесь гнездится беда всего мира.",
    ],
}


def _gen_name(rng: random.Random, used: set) -> str:
    """Уникальное название из корня и генитива. Без нумерации «Тракт 1, 2…»."""
    for _ in range(300):
        name = f"{rng.choice(_NAME_ROOTS)} {rng.choice(_NAME_MODIFIERS)}"
        if name not in used:
            used.add(name)
            return name
    # Исчерпали комбинации — добавляем уточняющий корень.
    base = rng.choice(_NAME_ROOTS)
    extra = rng.choice(_NAME_ROOTS)
    candidate = f"{base} {extra}"
    while candidate in used:
        candidate = f"{base} у {extra}"
        extra = rng.choice(_NAME_ROOTS)
    used.add(candidate)
    return candidate


def _dist_to_center(x: int, y: int) -> float:
    """Расстояние Чебышёва от центра карты — мера «глубины» локации."""
    return max(abs(x - _CENTER), abs(y - _CENTER))


def _tier_for_cell(x: int, y: int, rng: random.Random):
    """Тип и мин. уровень локации по удалённости от центра.

    В центре — безопасные стартовые земли, к краям — всё злее и глубже,
    на самых обочинах — подземелья и логова боссов. Так мир живой:
    новичку есть куда прийти, а эндгейм — на окраинах.
    """
    d = _dist_to_center(x, y)
    if d <= 1.5:
        return LocationType.SAFE, 1
    if d <= 2.5:
        return LocationType.DANGEROUS, rng.randint(1, 3)
    if d <= 3.5:
        lt = LocationType.DUNGEON if rng.random() < 0.4 else LocationType.DANGEROUS
        return lt, rng.randint(4, 6)
    # край карты — глубокие подземелья и редкие логова боссов
    lt = LocationType.BOSS if rng.random() < 0.25 else LocationType.DUNGEON
    return lt, rng.randint(7, 10)


async def seed_database():
    """Засеять мир с нуля.

    4 угловых замка захардкоржены, 32 локации генерируются свободно по сиду.
    Сид берётся из настроек, а если его нет — подбирается случайно
    (а не зашитое число): мир каждый раз новый, пока не понравится.
    """
    async with async_session() as session:
        result = await session.execute(select(Location))
        if result.scalars().first():
            return

        # ── Сид: из настроек или случайный (раньше был зашит 1337) ──
        seed_row = await session.scalar(select(AppSetting).where(AppSetting.key == "seed"))
        if not seed_row or not (seed_row.value or "").strip():
            seed = random.randint(1, 2_000_000_000)
            if seed_row:
                seed_row.value = str(seed)
            else:
                session.add(AppSetting(key="seed", value=str(seed)))
                await session.flush()
        else:
            seed = int(seed_row.value)
        rng = random.Random(seed)

        # ── 32 свободные локации на случайных клетках (кроме углов) ──
        free_cells = [(x, y) for x in range(WORLD_GRID) for y in range(WORLD_GRID)
                      if (x, y) not in CORNER_CELLS]
        rng.shuffle(free_cells)
        chosen = free_cells[:FREE_LOCATIONS]

        used_names = set()
        generated = []
        for (x, y) in chosen:
            lt, ml = _tier_for_cell(x, y, rng)
            generated.append({
                "x": x, "y": y, "type": lt, "min_level": ml,
                "name": _gen_name(rng, used_names),
            })

        # Стартовая земля = ближайшая к центру из сгенерированных.
        # Принудительно безопасная, 1 уровень — туда приходят новички
        # (location_id=1, клетка 5×5 — см. bot/handlers/start.py).
        spawn_gen = min(generated, key=lambda g: _dist_to_center(g["x"], g["y"]))
        spawn_gen["type"] = LocationType.SAFE
        spawn_gen["min_level"] = 1

        # ── Сборка объектов: СНАЧАЛА стартовая (id=1), затем замки, затем остальные ──
        def _desc(g):
            return rng.choice(_DESC_BY_TYPE.get(g["type"], _DESC_BY_TYPE[LocationType.DANGEROUS]))

        locations = []
        spawn_loc = Location(
            name=spawn_gen["name"], description=_desc(spawn_gen),
            location_type=LocationType.SAFE, min_level=1,
            world_x=spawn_gen["x"], world_y=spawn_gen["y"],
            grid_size=10, floors_count=1,
            image_url=LOC_IMAGE_BY_TYPE[LocationType.SAFE],
        )
        locations.append(spawn_loc)

        corner_locs = []
        for cname, cdesc, cx, cy in CORNER_CASTLES:
            loc = Location(
                name=cname, description=cdesc, location_type=LocationType.SAFE,
                min_level=1, world_x=cx, world_y=cy, grid_size=25, floors_count=2,
            )
            locations.append(loc)
            corner_locs.append(loc)

        gen_locs = []
        for g in generated:
            if g is spawn_gen:
                continue
            loc = Location(
                name=g["name"], description=_desc(g), location_type=g["type"],
                min_level=g["min_level"], world_x=g["x"], world_y=g["y"],
                grid_size=10, floors_count=1,
                image_url=LOC_IMAGE_BY_TYPE.get(g["type"]),
            )
            locations.append(loc)
            gen_locs.append(loc)

        session.add_all(locations)
        await session.flush()

        # ── Клетки локаций ──
        for loc in locations:
            if loc.name in CORNER_NAMES:
                await W.build_corner_castle(session, loc, CELL_STORIES,
                                            rng=random.Random(seed + loc.id), npcs=None)
                await W.ensure_stairs(session, loc)
            else:
                await W.build_cells(session, loc, CELL_STORIES,
                                    rng=random.Random(seed + loc.id))

        # ── NPC угловых замков (по имени, как и раньше) ──
        CASTLE_NPCS_MAP = {
            "Замок Рассвета": [
                ("Инквизитор Эдуард", "Свет Рассвета рассеет любую тьму. Веришь ли ты в спасение?", "storyteller"),
                ("Интендант Бенедикт", "Орден снабжает верных рыцарей всем необходимым. Покупай добротную экипировку.", "merchant"),
                ("Оружейник Рауль", "Молот Ордена куёт праведную сталь. Я улучшу твой клинок.", "crafter"),
                ("Писарь Иеремия", "Мы ведём учёт трофеев и помогаем обмениваться вещами. Загляни в гроссбух.", "auctioneer"),
            ],
            "Замок Теней": [
                ("Лорд Малакар", "Бездна поглотит всё. Мы лишь готовим мир к её пришествию...", "storyteller"),
                ("Торговец шёпотом Ксавьер", "Тёмные товары для тёмных дел. Бронза не пахнет, верно?", "merchant"),
                ("Кузнец скверны Кром", "Я закаляю сталь в пламени бездны. Она будет резать глубже.", "crafter"),
                ("Ростовщик Теневой секты", "Теневой рынок всегда открыт. Мы задокументируем любую сделку.", "auctioneer"),
            ],
            "Замок Глубин": [
                ("Главарь банды Грюм", "В Глубинах выживает сильнейший. Мёртвым золото ни к чему, а нам пригодится.", "storyteller"),
                ("Скупщик краденого Барни", "Товары со всего мира — дешевле, чем у честных купцов! Бери, пока горячо.", "merchant"),
                ("Оружейник Глубин Шрам", "Ковка из ржавого лома и заточка клинков — моё ремесло. Было бы золото.", "crafter"),
                ("Оценщик Гильдии Клык", "Скупщик Молчун оставил тут свои контакты. Покупай и выставляй лоты.", "auctioneer"),
            ],
            "Замок Пепла": [
                ("Капитан Радклифф", "Мы — Стража Погоста. Пока стоит частокол — живые спят спокойно.", "storyteller"),
                ("Лавочник Кормак", "Походные припасы и броня для защитников рубежей. Всё честно и без обмана.", "merchant"),
                ("Оружейник Торвальд", "Наковальня Стражи куёт лучшую защиту от когтей нежити. Давай сталь.", "crafter"),
                ("Летописец Пепла Морган", "Всё, что добыто на поле боя, записывается здесь. Мы проводим честные аукционы.", "auctioneer"),
            ],
        }
        for loc in corner_locs:
            npc_list = CASTLE_NPCS_MAP.get(loc.name)
            if not npc_list:
                continue
            result = await session.execute(
                select(Cell).where(Cell.location_id == loc.id).where(Cell.floor == 0)
                .where(Cell.is_passable == True).where(Cell.tile_type == "village")
            )
            safe_cells = result.scalars().all()
            cell_rng = random.Random(seed + loc.id)
            cell_rng.shuffle(safe_cells)
            for i, (npc_name, dialogue, npc_type) in enumerate(npc_list):
                if i >= len(safe_cells):
                    break
                cell = safe_cells[i]
                cell.has_npc = True
                cell.npc_name = npc_name
                cell.npc_dialogue = dialogue
                cell.npc_type = npc_type

        # ── Бесшовные швы по фактическому соседству на карте ──
        await W.relink_all(session)

        # ── Жители стартовой деревни: заказчики заданий и торговец ──
        result = await session.execute(
            select(Cell).where(Cell.location_id == spawn_loc.id).where(Cell.is_passable == True)
        )
        spawn_cells = result.scalars().all()
        if len(spawn_cells) >= 3:
            starters = [
                ("Старейшина Григор", "Добро пожаловать, странник. Тут мы ещё держимся.", "storyteller"),
                ("Торговец Варн", "У меня есть всё, что нужно выжившему. Золото при тебе?", "merchant"),
                ("Лекарь Мира", "Ты ранен? Я могу исцелить — было бы чем заплатить.", "quest_giver"),
            ]
            for i, (npc_name, dialogue, npc_type) in enumerate(starters):
                cell = spawn_cells[i * 3]
                cell.has_npc = True
                cell.npc_name = npc_name
                cell.npc_dialogue = dialogue
                cell.npc_type = npc_type

        # ── Опасные земли (для сундуков и бместа мобов) ──
        danger_locs = [l for l in gen_locs
                       if l.location_type in (LocationType.DANGEROUS, LocationType.DUNGEON, LocationType.BOSS)]
        danger_ids = [l.id for l in danger_locs]

        # Сундуки — в опасных землях.
        if danger_ids:
            result = await session.execute(
                select(Cell).where(Cell.location_id.in_(danger_ids)).where(Cell.is_passable == True)
            )
            danger_cells = result.scalars().all()
            for cell in rng.sample(danger_cells, min(12, len(danger_cells))):
                cell.has_chest = True

        # ── Мобы: распределяем по локациям согласно уровню (без привязки к индексам) ──
        mobs_data = [
            {"name": "Помойная крыса", "desc": "Размером с собаку и вдвое наглее...", "level": 1, "hp": 18, "dmg": 3, "def": 0, "gold": 3, "exp": 6},
            {"name": "Болотный зомби", "desc": "Медлительный труп...", "level": 1, "hp": 25, "dmg": 4, "def": 1, "gold": 5, "exp": 10},
            {"name": "Лесной ворг", "desc": "Крупный волк с чёрной шерстью...", "level": 2, "hp": 40, "dmg": 7, "def": 2, "gold": 8, "exp": 18},
            {"name": "Скелет-воин", "desc": "Ожившие останки павшего солдата...", "level": 3, "hp": 50, "dmg": 8, "def": 3, "gold": 12, "exp": 25},
            {"name": "Гнолл-грабитель", "desc": "Гибрид человека и гиены...", "level": 4, "hp": 65, "dmg": 10, "def": 3, "gold": 15, "exp": 35},
            {"name": "Разбойник с большой дороги", "desc": "Считает путников кормовой базой...", "level": 4, "hp": 60, "dmg": 9, "def": 3, "gold": 14, "exp": 30},
            {"name": "Ледяной падальщик", "desc": "Обедает тем, что замёрзло до него...", "level": 4, "hp": 62, "dmg": 10, "def": 3, "gold": 15, "exp": 32},
            {"name": "Северный канюк", "desc": "Кружит в ожидании добычи...", "level": 5, "hp": 70, "dmg": 12, "def": 2, "gold": 17, "exp": 36},
            {"name": "Снежный волк", "desc": "Шерсть белая, глаза — льдинки...", "level": 5, "hp": 78, "dmg": 13, "def": 3, "gold": 18, "exp": 38},
            {"name": "Гарпия-падальщица", "desc": "Кружит, высматривая слабых...", "level": 5, "hp": 70, "dmg": 14, "def": 2, "gold": 18, "exp": 38},
            {"name": "Топяной змей", "desc": "Скользит так, что рябь не расходится...", "level": 5, "hp": 76, "dmg": 12, "def": 3, "gold": 17, "exp": 36},
            {"name": "Тёмный следопыт", "desc": "Идёт по следу тише, чем думает жертва...", "level": 6, "hp": 85, "dmg": 14, "def": 3, "gold": 19, "exp": 40},
            {"name": "Пещерный тролль", "desc": "Громадина с каменной кожей...", "level": 6, "hp": 100, "dmg": 14, "def": 6, "gold": 25, "exp": 60},
            {"name": "Костяной странник", "desc": "Идёт без остановки к неведомой цели...", "level": 6, "hp": 95, "dmg": 15, "def": 5, "gold": 21, "exp": 44},
            {"name": "Могильный страж", "desc": "Держит меч даже после смерти...", "level": 7, "hp": 110, "dmg": 15, "def": 8, "gold": 24, "exp": 50},
            {"name": "Теневой призрак", "desc": "Нематериальная сущность из кошмаров...", "level": 7, "hp": 80, "dmg": 18, "def": 2, "gold": 30, "exp": 70},
            {"name": "Чернокнижник пепла", "desc": "Поднимает пепельных духов над кострищами...", "level": 7, "hp": 92, "dmg": 17, "def": 5, "gold": 23, "exp": 48},
            {"name": "Гниющий великан", "desc": "Каждый шаг оставляет яму...", "level": 8, "hp": 130, "dmg": 18, "def": 7, "gold": 28, "exp": 60},
            {"name": "Трясинный голем", "desc": "Слеплен из грязи, корней и костей...", "level": 7, "hp": 120, "dmg": 16, "def": 8, "gold": 25, "exp": 52},
            {"name": "Культист Бездны", "desc": "Ждал этого дня всю жизнь...", "level": 9, "hp": 95, "dmg": 22, "def": 4, "gold": 45, "exp": 110},
            {"name": "Порождение бездны", "desc": "У него слишком много суставов...", "level": 10, "hp": 130, "dmg": 24, "def": 6, "gold": 55, "exp": 130},
            {"name": "Камнекожий страж", "desc": "Кожа вросла в камень...", "level": 6, "hp": 115, "dmg": 13, "def": 9, "gold": 22, "exp": 46},
            {"name": "Горный тролль-одиночка", "desc": "Изгнан из стаи за уродство...", "level": 7, "hp": 130, "dmg": 17, "def": 8, "gold": 26, "exp": 54},
            {"name": "Страж расщелины", "desc": "Стоит здесь дольше, чем существует королевство...", "level": 11, "hp": 180, "dmg": 23, "def": 12, "gold": 70, "exp": 160},
        ]

        def _loc_for_level(lvl: int):
            """Локация под моба данного уровня: близкая по мин. уровню."""
            if not danger_locs:
                return spawn_loc
            cands = [l for l in danger_locs if l.min_level - 1 <= lvl <= l.min_level + 2]
            if not cands:
                cands = danger_locs
            return rng.choice(cands)

        created_mobs = []
        for md in mobs_data:
            loc = _loc_for_level(md["level"])
            mob = Mob(
                name=md["name"], description=md["desc"], level=md["level"],
                hp=md["hp"], damage=md["dmg"], defense=md["def"],
                gold_reward=md["gold"], exp_reward=md["exp"],
                location_id=loc.id,
            )
            session.add(mob)
            created_mobs.append((mob, loc.id))
        await session.flush()

        # Расставить мобов по клеткам их локаций.
        for mob, loc_id in created_mobs:
            result = await session.execute(
                select(Cell).where(Cell.location_id == loc_id).where(Cell.is_passable == True)
            )
            cells = result.scalars().all()
            if cells:
                random.Random(seed + mob.id).choice(cells).mob_id = mob.id

        # ── Предметы и лавка (без привязки к локациям) ──
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

        # ── Задания: привязка к реальным локациям по месту мобов ──
        # Кого убивать — туда и ведёт задание (не к зашитому индексу).
        mob_loc = {mob.name: loc_id for mob, loc_id in created_mobs}
        kill_loc_id = mob_loc.get("Болотный зомби") or mob_loc.get("Лесной ворг")
        if not kill_loc_id:
            kill_loc_id = (sorted(danger_locs, key=lambda l: (l.min_level, l.id))[0].id
                           if danger_locs else spawn_loc.id)

        quests = [
            Quest(name="Первые шаги", description="Убей 3 болотных зомби в ближайших опасных землях.",
                  objective_type="kill", objective_target="Болотный зомби", objective_count=3,
                  reward_gold=2, reward_exp=30, min_level=1, location_id=kill_loc_id),
            Quest(name="Охота на воргов", description="Убей 2 лесных воргов.",
                  objective_type="kill", objective_target="Лесной ворг", objective_count=2,
                  reward_gold=80, reward_exp=50, min_level=2, location_id=mob_loc.get("Лесной ворг", kill_loc_id)),
            Quest(name="Сбор трав", description="Принеси лекарю 5 лечебных трав.",
                  objective_type="collect", objective_target="Лечебная трава", objective_count=5,
                  reward_gold=30, reward_exp=20, min_level=1, location_id=spawn_loc.id, npc_name="Лекарь Мира"),
        ]
        session.add_all(quests)

        await session.commit()
        print(f"Database seeded: {len(locations)} locations "
              f"(4 corner castles + {FREE_LOCATIONS} procedurally generated, "
              f"seed {seed}), quests, items and seamless links.")


SAVED_SEEDS_KEY = "saved_seeds"


async def get_saved_seeds(session=None) -> list:
    """Сохранённые «любимые» сиды: [{'seed','label','saved_at'}]."""
    import json
    own = session is None
    if own:
        async with async_session() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == SAVED_SEEDS_KEY))
    else:
        row = await session.scalar(select(AppSetting).where(AppSetting.key == SAVED_SEEDS_KEY))
    try:
        return json.loads(row.value) if row and row.value else []
    except (ValueError, TypeError):
        return []


async def add_saved_seed(seed: int, label: str = "") -> list:
    import json
    from datetime import datetime
    label = (label or "").strip()[:64]
    async with async_session() as session:
        seeds = await get_saved_seeds(session)
        # Не дублируем один и тот же сид — обновляем подпись.
        seeds = [s for s in seeds if int(s.get("seed")) != int(seed)]
        seeds.insert(0, {"seed": int(seed), "label": label,
                         "saved_at": datetime.utcnow().isoformat(timespec="seconds")})
        seeds = seeds[:50]  # лимит архива
        row = await session.scalar(select(AppSetting).where(AppSetting.key == SAVED_SEEDS_KEY))
        if row:
            row.value = json.dumps(seeds, ensure_ascii=False)
        else:
            session.add(AppSetting(key=SAVED_SEEDS_KEY,
                                   value=json.dumps(seeds, ensure_ascii=False)))
        await session.commit()
        return seeds


async def delete_saved_seed(seed: int) -> list:
    import json
    async with async_session() as session:
        seeds = await get_saved_seeds(session)
        seeds = [s for s in seeds if int(s.get("seed")) != int(seed)]
        row = await session.scalar(select(AppSetting).where(AppSetting.key == SAVED_SEEDS_KEY))
        if row:
            row.value = json.dumps(seeds, ensure_ascii=False)
        else:
            session.add(AppSetting(key=SAVED_SEEDS_KEY,
                                   value=json.dumps(seeds, ensure_ascii=False)))
        await session.commit()
        return seeds


async def recreate_world_on_server(seed=None):
    """Полностью пересоздать мир по новому сиду.

    seed=None — подобрать случайно («живой мир», без ручного числа).
    seed=int — пересоздать под конкретный (например, из сохранённых).
    """
    from core.models import Grave, DungeonRun, MobSpawn, Cell, Location, Character
    from sqlalchemy import update

    if seed is None:
        seed = random.randint(1, 2_000_000_000)
    seed = int(seed)

    async with async_session() as session:
        seed_row = await session.scalar(select(AppSetting).where(AppSetting.key == "seed"))
        if not seed_row:
            seed_row = AppSetting(key="seed", value=str(seed))
            session.add(seed_row)
        else:
            seed_row.value = str(seed)
        await session.flush()

        # Очищаем мир
        await session.execute(delete(Grave))
        await session.execute(delete(DungeonRun))
        await session.execute(delete(MobSpawn))
        await session.execute(delete(Cell))
        await session.execute(delete(Location))
        await session.flush()

        # Сбрасываем игроков на спавн (location_id=1 — стартовая земля)
        await session.execute(
            update(Character)
            .values(location_id=1, cell_id=None, floor=0)
        )
        await session.flush()
        await session.commit()

    # Заново сеем мир — locations теперь пусто, seed_database отработает.
    await seed_database()
