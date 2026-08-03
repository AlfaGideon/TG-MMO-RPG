"""Классы персонажей, редактируемые из админки.

Раньше список классов был захардкожен в `CharacterClass`. Теперь он живёт
в таблице `character_classes`: админ добавляет новый класс с любыми
стартовыми статами и приростом за уровень, и он сразу появляется в боте
на экране выбора класса.
"""
from sqlalchemy import select

from core.models import CharacterClassDef

# Классы, которыми наполняется пустая таблица при первом запуске.
DEFAULT_CLASSES = [
    dict(
        key="warrior",
        affinity_chance=0.18, dual_affinity_chance=0.03,
        preferred_schools="", name="Воин", icon="🛡", sort_order=10,
        description=(
            "Тяжёлые доспехи, мечи и щиты — твоя вера. Воины выдерживают удары, "
            "которые убили бы любого другого, и сокрушают врагов мощью."
        ),
        base_strength=15, base_agility=8, base_intelligence=5,
        base_endurance=14, base_luck=8, base_hp=140, base_mp=30,
        growth_strength=2, growth_agility=1, growth_intelligence=0,
        growth_endurance=2, growth_luck=0, growth_hp=14, growth_mp=3,
    ),
    dict(
        key="mage",
        affinity_chance=1.0, dual_affinity_chance=0.35,
        preferred_schools="fire,frost,storm", name="Маг", icon="🔮", sort_order=20,
        description=(
            "Ты познал запретные знания. Пламя и молнии срываются с кончиков "
            "пальцев, а враги превращаются в пепел до того, как успеют крикнуть."
        ),
        base_strength=5, base_agility=8, base_intelligence=16,
        base_endurance=8, base_luck=10, base_hp=80, base_mp=120,
        growth_strength=0, growth_agility=1, growth_intelligence=3,
        growth_endurance=1, growth_luck=1, growth_hp=7, growth_mp=12,
    ),
    dict(
        key="rogue",
        affinity_chance=0.35, dual_affinity_chance=0.06,
        preferred_schools="shadow,storm", name="Разбойник", icon="🗡", sort_order=30,
        description=(
            "Тени — твой дом. Ты бьёшь туда, где брони нет, и исчезаешь прежде, "
            "чем враг поймёт, что произошло."
        ),
        base_strength=10, base_agility=16, base_intelligence=8,
        base_endurance=8, base_luck=14, base_hp=100, base_mp=50,
        growth_strength=1, growth_agility=3, growth_intelligence=1,
        growth_endurance=1, growth_luck=2, growth_hp=9, growth_mp=5,
    ),
    dict(
        key="cleric",
        affinity_chance=0.95, dual_affinity_chance=0.25,
        preferred_schools="light,nature", name="Жрец", icon="✨", sort_order=40,
        description=(
            "Последний свет в тёмном мире. Твоё слово исцеляет раны союзников "
            "и обжигает нежить священным сиянием."
        ),
        base_strength=8, base_agility=8, base_intelligence=14,
        base_endurance=12, base_luck=10, base_hp=110, base_mp=90,
        growth_strength=1, growth_agility=1, growth_intelligence=2,
        growth_endurance=2, growth_luck=1, growth_hp=11, growth_mp=9,
    ),
    dict(
        key="paladin",
        affinity_chance=0.7, dual_affinity_chance=0.12,
        preferred_schools="light", name="Паладин", icon="⚜️", sort_order=50,
        description=(
            "Латы, молот и клятва. Ты стоишь между тьмой и теми, кто ещё жив, "
            "и не отступаешь, пока держат ноги."
        ),
        base_strength=13, base_agility=7, base_intelligence=10,
        base_endurance=15, base_luck=9, base_hp=150, base_mp=60,
        growth_strength=2, growth_agility=1, growth_intelligence=1,
        growth_endurance=3, growth_luck=0, growth_hp=15, growth_mp=6,
    ),
    dict(
        key="ranger",
        affinity_chance=0.5, dual_affinity_chance=0.1,
        preferred_schools="nature,storm", name="Следопыт", icon="🏹", sort_order=60,
        description=(
            "Лес читается тобой как книга. Стрела находит горло раньше, чем "
            "зверь успевает почуять человека."
        ),
        base_strength=11, base_agility=15, base_intelligence=9,
        base_endurance=11, base_luck=12, base_hp=110, base_mp=60,
        growth_strength=1, growth_agility=3, growth_intelligence=1,
        growth_endurance=2, growth_luck=1, growth_hp=11, growth_mp=6,
    ),
    dict(
        key="necromancer",
        affinity_chance=1.0, dual_affinity_chance=0.4,
        preferred_schools="shadow", name="Некромант", icon="💀", sort_order=70,
        description=(
            "Смерть — не конец, а материал. Ты поднимаешь павших и вытягиваешь "
            "жизнь из живых, платя за это собственным телом."
        ),
        base_strength=6, base_agility=8, base_intelligence=17,
        base_endurance=7, base_luck=11, base_hp=75, base_mp=130,
        growth_strength=0, growth_agility=1, growth_intelligence=3,
        growth_endurance=1, growth_luck=1, growth_hp=6, growth_mp=13,
    ),
    dict(
        key="berserker",
        affinity_chance=0.12, dual_affinity_chance=0.02,
        preferred_schools="fire", name="Берсерк", icon="🪓", sort_order=80,
        description=(
            "Боли нет — есть только ярость. Чем меньше здоровья, тем страшнее "
            "твой удар. Броня — для трусов."
        ),
        base_strength=18, base_agility=11, base_intelligence=4,
        base_endurance=10, base_luck=7, base_hp=130, base_mp=20,
        growth_strength=3, growth_agility=2, growth_intelligence=0,
        growth_endurance=1, growth_luck=0, growth_hp=13, growth_mp=2,
    ),
    dict(
        key="druid",
        affinity_chance=0.95, dual_affinity_chance=0.3,
        preferred_schools="nature,frost", name="Друид", icon="🌿", sort_order=90,
        description=(
            "Ты слышишь, как шепчут корни. Природа мстит за выжженные земли "
            "твоими руками."
        ),
        base_strength=9, base_agility=11, base_intelligence=14,
        base_endurance=12, base_luck=11, base_hp=115, base_mp=95,
        growth_strength=1, growth_agility=2, growth_intelligence=2,
        growth_endurance=2, growth_luck=1, growth_hp=11, growth_mp=9,
    ),
    dict(
        key="assassin",
        affinity_chance=0.3, dual_affinity_chance=0.05,
        preferred_schools="shadow", name="Убийца", icon="🩸", sort_order=100,
        description=(
            "Один удар — один труп. Ты не сражаешься, ты выполняешь работу и "
            "растворяешься в темноте."
        ),
        base_strength=12, base_agility=18, base_intelligence=9,
        base_endurance=7, base_luck=16, base_hp=95, base_mp=45,
        growth_strength=2, growth_agility=3, growth_intelligence=1,
        growth_endurance=1, growth_luck=2, growth_hp=8, growth_mp=4,
    ),
]


async def all_classes(session, only_enabled: bool = True):
    query = select(CharacterClassDef).order_by(
        CharacterClassDef.sort_order, CharacterClassDef.id
    )
    if only_enabled:
        query = query.where(CharacterClassDef.is_enabled == True)  # noqa: E712
    result = await session.execute(query)
    return result.scalars().all()


async def get_class(session, key: str) -> CharacterClassDef | None:
    if not key:
        return None
    result = await session.execute(
        select(CharacterClassDef).where(CharacterClassDef.key == str(key))
    )
    return result.scalar_one_or_none()


# ── портреты героя по фракциям ──────────────────────────────

# Сгенерированные портреты 1×1 класса на стороне каждой фракции лежат в
# статике админки по шаблону ниже; admin — корень статики панели, а бот
# читает /static/... как admin/static/... (bot.utils.photos).
CLASS_FACTION_IMAGE_TEMPLATE = "/static/classes/{class_key}_{faction}.png"


def faction_images(cls_def) -> dict:
    """Разбор JSON-колонки faction_images: {фракция: url}, без мусора."""
    import json

    raw = getattr(cls_def, "faction_images", "") or ""
    try:
        data = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {str(k): str(v) for k, v in data.items() if v}


def save_faction_image(cls_def, faction: str, url: str) -> None:
    """Поставить/убрать портрет фракции у класса (пустой url — удалить)."""
    import json

    images = faction_images(cls_def)
    if url:
        images[faction] = url
    else:
        images.pop(faction, None)
    cls_def.faction_images = json.dumps(images, ensure_ascii=False)


def default_faction_image(class_key: str, faction: str) -> str:
    """Файловый путь сгенерированного портрета фракции (если файл есть)."""
    import os

    url = CLASS_FACTION_IMAGE_TEMPLATE.format(
        class_key=class_key, faction=faction)
    # Бот и админка стартуют из корня репозитория: /static/... = admin/static/...
    if url.startswith("/static/") and os.path.isfile("admin" + url):
        return url
    return ""


def class_image(cls_def, faction: str | None = None) -> str:
    """Портрет героя для экранов: сторона игрока → базовое фото класса.

    Игрок может сменить фракцию по ходу игры — профиль всегда берёт
    портрет его ТЕКУЩЕЙ стороны; без портрета стороны откатываемся на
    общую картинку класса.
    """
    if cls_def is None:
        return ""
    if faction:
        custom = faction_images(cls_def).get(faction, "")
        if custom:
            return custom
        generated = default_faction_image(str(cls_def.key), faction)
        if generated:
            return generated
    return (cls_def.image_url or "").strip()


# Поля, которые появились позже и которые надо один раз проставить
# уже существующим классам (иначе у них останутся дефолты миграции).
BACKFILL_FIELDS = ("affinity_chance", "dual_affinity_chance", "preferred_schools")


async def seed_default_classes(session) -> int:
    """Наполняет таблицу классов дефолтами, не трогая уже существующие.

    Для классов, которые уже есть в базе, разово проставляет настройки
    магической предрасположенности — на старых установках колонки завелись
    миграцией с нейтральными значениями.
    """
    result = await session.execute(select(CharacterClassDef))
    existing = {cls.key: cls for cls in result.scalars().all()}
    added = 0
    touched = False

    for payload in DEFAULT_CLASSES:
        current = existing.get(payload["key"])
        if current is None:
            session.add(CharacterClassDef(**payload))
            added += 1
            continue

        # Класс уже есть: доливаем только незаполненную магию, чтобы не
        # затирать ручные правки администратора.
        if not (current.preferred_schools or "").strip():
            for field in BACKFILL_FIELDS:
                if field in payload:
                    setattr(current, field, payload[field])
            touched = True

    if added or touched:
        await session.flush()
    return added


def class_icon(cls_def: CharacterClassDef | None) -> str:
    return (cls_def.icon if cls_def and cls_def.icon else "👤")


def affinity_hint(cls_def) -> str:
    """Строка для экрана выбора класса: насколько вероятен магический дар."""
    from core.magic import school_icon, school_name

    chance = cls_def.affinity_chance if cls_def else 0.5
    if chance >= 0.9:
        base = "Дар к магии почти наверняка"
    elif chance >= 0.6:
        base = "Дар к магии вероятен"
    elif chance >= 0.3:
        base = "Дар к магии редок"
    else:
        base = "Магия — не твой путь"

    schools = cls_def.preferred_school_list() if cls_def else []
    if schools:
        names = ", ".join(
            f"{school_icon(s)} {school_name(s)}" for s in schools
        )
        return f"{base}. Склонность: {names}"
    return f"{base}. Школа — какая выпадет"


def level_up_gains(cls_def: CharacterClassDef | None) -> dict:
    """Прирост статов за уровень. Без класса — старые дефолты движка."""
    if cls_def is None:
        return {
            "strength": 1, "agility": 1, "intelligence": 0,
            "endurance": 1, "luck": 0, "max_hp": 10, "max_mp": 5,
        }
    return cls_def.growth()
