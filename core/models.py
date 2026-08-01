from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime, Float,
    Boolean, ForeignKey, Text, Enum as SQLEnum, TypeDecorator, func
)
from sqlalchemy.orm import relationship, validates

from core.database import Base
from core.enums import (
    CharacterClass, ItemType, ItemRarity, LocationType, BattleResult, QuestStatus,
    ItemSource, CraftStation, MagicSchool, AffinityGrade, AuctionStatus,
    source_badge, source_label,
)


# Ключи классов пишутся строчными буквами; старые enum-имена были в верхнем
# регистре. Одна точка нормализации на всё приложение.
def _normalize_class_key(value) -> str:
    if isinstance(value, CharacterClass):
        return value.value
    text = str(value).strip()
    return text.lower() if text.isupper() else text


class ClassKey(str):
    """Ключ класса персонажа.

    Ведёт себя как обычная строка (`"warrior"`), но у него есть `.value`,
    поэтому весь старый код вида `character.character_class.value`
    продолжает работать после перехода классов из enum в таблицу БД.
    """

    @property
    def value(self) -> str:
        return str(self)

    @property
    def name(self) -> str:
        return str(self).upper()


class ClassKeyType(TypeDecorator):
    """Хранит класс персонажа строкой, отдаёт `ClassKey`.

    Раньше колонка была `Enum(CharacterClass)` и новые классы нельзя было
    добавить из админки. Теперь список классов ведётся в таблице
    `character_classes`, а тут лежит просто её ключ.
    """
    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _normalize_class_key(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # Старые записи хранили имя enum-члена ("WARRIOR"), а не ключ
        # ("warrior") — SQLAlchemy Enum пишет .name. Нормализуем на чтении,
        # чтобы персонажи из прежних версий находили свой класс.
        return ClassKey(_normalize_class_key(value))


class CharacterClassDef(Base):
    """Класс персонажа, настраиваемый из админки.

    Стартовые статы, множители роста за уровень и описание для экрана
    выбора класса в боте — всё редактируется без правки кода.
    """
    __tablename__ = "character_classes"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(64), nullable=False)
    icon = Column(String(16), default="⚔️")
    description = Column(Text, default="")

    base_strength = Column(Integer, default=10)
    base_agility = Column(Integer, default=10)
    base_intelligence = Column(Integer, default=10)
    base_endurance = Column(Integer, default=10)
    base_luck = Column(Integer, default=10)
    base_hp = Column(Integer, default=100)
    base_mp = Column(Integer, default=50)

    # Прирост за уровень
    growth_strength = Column(Integer, default=1)
    growth_agility = Column(Integer, default=1)
    growth_intelligence = Column(Integer, default=1)
    growth_endurance = Column(Integer, default=1)
    growth_luck = Column(Integer, default=0)
    growth_hp = Column(Integer, default=10)
    growth_mp = Column(Integer, default=5)

    image_url = Column(String(512), nullable=True)
    is_enabled = Column(Boolean, default=True)
    sort_order = Column(Integer, default=100)

    # Шансы получить дар к магии при создании героя (0..1)
    affinity_chance = Column(Float, default=0.5)      # хотя бы одна школа
    dual_affinity_chance = Column(Float, default=0.12)  # сразу две школы
    # Школы, к которым класс склонен, через запятую ("fire,shadow").
    # Пусто — любая из шести равновероятна.
    preferred_schools = Column(Text, default="")

    def preferred_school_list(self) -> list:
        return [s.strip() for s in (self.preferred_schools or "").split(",") if s.strip()]

    def base_stats(self) -> dict:
        return {
            "strength": self.base_strength,
            "agility": self.base_agility,
            "intelligence": self.base_intelligence,
            "endurance": self.base_endurance,
            "luck": self.base_luck,
            "max_hp": self.base_hp,
            "max_mp": self.base_mp,
        }

    def growth(self) -> dict:
        return {
            "strength": self.growth_strength,
            "agility": self.growth_agility,
            "intelligence": self.growth_intelligence,
            "endurance": self.growth_endurance,
            "luck": self.growth_luck,
            "max_hp": self.growth_hp,
            "max_mp": self.growth_mp,
        }


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(128), nullable=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Web admin panel access, grantable per-player from the admin UI
    is_web_admin = Column(Boolean, default=False)
    web_admin_role = Column(String(32), nullable=True)  # viewer/moderator/gamemaster/admin
    web_admin_password_hash = Column(String(128), nullable=True)
    # Plaintext kept so the owner can re-show it and the bot can resend it on
    # demand; rotate with "new password" instead of storing it forever elsewhere.
    web_admin_password = Column(String(64), nullable=True)
    # Comma-separated capability keys; empty => use the rank preset
    web_admin_caps = Column(Text, nullable=True)
    web_admin_granted_at = Column(DateTime(timezone=True), nullable=True)

    character = relationship("Character", back_populates="user", uselist=False)
    messages = relationship("AdminMessage", back_populates="user", order_by="AdminMessage.created_at.desc()")


class Party(Base):
    __tablename__ = "parties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    leader_id = Column(Integer, ForeignKey("characters.id"), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("Character", back_populates="party", foreign_keys="Character.party_id")
    leader = relationship("Character", foreign_keys=[leader_id], overlaps="members")


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    character_class = Column(ClassKeyType, nullable=False)
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    # Три валюты: бронза (мелочь), серебро, золото
    bronze = Column(Integer, default=120)
    silver = Column(Integer, default=8)
    gold = Column(Integer, default=2)

    strength = Column(Integer, default=10)
    agility = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    endurance = Column(Integer, default=10)
    luck = Column(Integer, default=10)

    # === Новые расширенные статы (Gear Score, Ловкость, Криты, Дропы и т.д.) ===
    gear_score = Column(Integer, default=0)
    damage_reduction = Column(Float, default=0.0)
    dexterity = Column(Integer, default=10)           # Ловкость
    crit_chance = Column(Float, default=5.0)
    crit_damage = Column(Float, default=50.0)
    double_hit_chance = Column(Float, default=0.0)
    double_damage_chance = Column(Float, default=0.0)
    dodge_chance = Column(Float, default=0.0)
    block_chance = Column(Float, default=0.0)
    water_conversion = Column(Float, default=0.0)
    poison_conversion = Column(Float, default=0.0)
    life_on_hit = Column(Integer, default=0)
    life_on_kill = Column(Integer, default=0)
    thorns_damage = Column(Integer, default=0)
    pet_damage_mult = Column(Float, default=1.0)
    exp_gain_mult = Column(Float, default=1.0)
    gold_gain_mult = Column(Float, default=1.0)
    item_drop_chance = Column(Float, default=0.0)
    material_drop_chance = Column(Float, default=0.0)
    rune_drop_chance = Column(Float, default=0.0)
    ruby_drop_chance = Column(Float, default=0.0)
    extra_kill_chance = Column(Float, default=0.0)

    # === Дополнительные 7 статов (полный комплект) ===
    attack_damage_min = Column(Integer, default=10)
    attack_damage_max = Column(Integer, default=15)
    effective_drop_mult = Column(Float, default=1.0)
    effective_material_mult = Column(Float, default=1.0)
    effective_rune_mult = Column(Float, default=1.0)
    effective_ruby_mult = Column(Float, default=1.0)
    pet_damage = Column(Integer, default=0)

    max_hp = Column(Integer, default=100)
    current_hp = Column(Integer, default=100)
    max_mp = Column(Integer, default=50)
    current_mp = Column(Integer, default=50)

    location_id = Column(Integer, ForeignKey("locations.id"), default=1)
    cell_id = Column(Integer, ForeignKey("cells.id"), nullable=True)
    floor = Column(Integer, default=0)

    party_id = Column(Integer, ForeignKey("parties.id"), nullable=True)

    weapon_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    armor_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    helmet_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    boots_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    accessory_id = Column(Integer, ForeignKey("items.id"), nullable=True)

    is_vip = Column(Boolean, default=False)
    vip_until = Column(DateTime(timezone=True), nullable=True)
    # VIP may temporarily leave the world while remaining completely immune.
    offline_protected = Column(Boolean, default=False)
    image_url = Column(String(512), nullable=True)

    # Фракции: очки репутации в JSON {"guard": 12, ...} — четыре силы, счёт
    # ведётся так же, как в engine/factions.py.
    reputation = Column(Text, default="")
    # Раны после гибели: до этого времени статы порезаны.
    wounded_until = Column(DateTime(timezone=True), nullable=True)
    # Осмотренные достопримечательности: список ключей "loc:x:y".
    landmarks_seen = Column(Text, default="")

    # Перекат стартовых статов: сколько попыток осталось из выданных при
    # создании героя. Ноль — статы зафиксированы окончательно.
    rerolls_left = Column(Integer, default=0)
    stats_locked = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="character")
    location = relationship("Location", foreign_keys=[location_id])
    cell = relationship("Cell", foreign_keys=[cell_id])
    inventory = relationship("InventoryItem", back_populates="character", cascade="all, delete-orphan")
    battles = relationship("Battle", back_populates="character")
    party = relationship("Party", back_populates="members", foreign_keys=[party_id], overlaps="leader")
    quests = relationship("CharacterQuest", back_populates="character", cascade="all, delete-orphan")
    dungeon_runs = relationship("DungeonRun", back_populates="character", order_by="DungeonRun.created_at.desc()")
    affinities = relationship(
        "CharacterAffinity", back_populates="character", cascade="all, delete-orphan"
    )

    @validates("character_class")
    def _normalize_class(self, key, value):
        """Класс всегда хранится как ClassKey, даже до записи в БД.

        Так `character.character_class.value` работает и сразу после
        присваивания обычной строки, и после чтения из базы.
        """
        if value is None:
            return None
        return ClassKey(_normalize_class_key(value))

    def effective_stats(self):
        return {
            "strength": self.strength,
            "agility": self.agility,
            "intelligence": self.intelligence,
            "endurance": self.endurance,
            "luck": self.luck,
            "max_hp": self.max_hp,
            "max_mp": self.max_mp,
        }


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    location_type = Column(SQLEnum(LocationType), default=LocationType.SAFE)
    min_level = Column(Integer, default=1)
    image_url = Column(String(512), nullable=True)
    grid_size = Column(Integer, default=10)
    floors_count = Column(Integer, default=1)

    # World map coordinates for seamless world (0..9 by default, world is 10x10 locations of 10x10 cells = 100x100)
    world_x = Column(Integer, default=0)
    world_y = Column(Integer, default=0)

    cells = relationship("Cell", back_populates="location", foreign_keys="Cell.location_id", cascade="all, delete-orphan")
    mobs = relationship("Mob", back_populates="location")


class Cell(Base):
    __tablename__ = "cells"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    floor = Column(Integer, default=0)
    name = Column(String(128), default="")
    description = Column(Text, default="")
    image_url = Column(String(512), nullable=True)
    is_passable = Column(Boolean, default=True)

    tile_type = Column(String(32), default="grass")

    mob_id = Column(Integer, ForeignKey("mobs.id"), nullable=True)
    has_npc = Column(Boolean, default=False)
    npc_name = Column(String(128), nullable=True)
    npc_dialogue = Column(Text, nullable=True)
    npc_type = Column(String(32), nullable=True)
    has_chest = Column(Boolean, default=False)
    has_house = Column(Boolean, default=False)
    has_campfire = Column(Boolean, default=False)
    has_tree = Column(Boolean, default=False)
    # Для NPC-ремесленника: какой станок он обслуживает (forge/alchemy/jewelry)
    npc_station = Column(String(16), nullable=True)
    # Когда сундук будет доступен снова (сундуки восстанавливаются)
    chest_respawn_at = Column(DateTime(timezone=True), nullable=True)
    chest_tier = Column(Integer, default=1)

    # Dungeon entrance: stepping on this cell can start a procedural dungeon run
    dungeon_template_id = Column(Integer, ForeignKey("dungeon_templates.id"), nullable=True)

    # Seamless world: links to neighbor locations at borders, or floor transitions (stairs)
    # within the same location (target_location_id == location_id, different target_floor)
    # If set, moving beyond this cell transitions to target_location_id at target_x, target_y, target_floor
    target_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    target_x = Column(Integer, nullable=True)
    target_y = Column(Integer, nullable=True)
    target_floor = Column(Integer, nullable=True)

    location = relationship("Location", back_populates="cells", foreign_keys=[location_id])
    mob = relationship("Mob")
    target_location = relationship("Location", foreign_keys=[target_location_id])
    dungeon_template = relationship("DungeonTemplate", foreign_keys=[dungeon_template_id])


class Mob(Base):
    __tablename__ = "mobs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    level = Column(Integer, default=1)
    hp = Column(Integer, default=30)
    damage = Column(Integer, default=5)
    defense = Column(Integer, default=2)
    gold_reward = Column(Integer, default=10)
    exp_reward = Column(Integer, default=15)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    is_boss = Column(Boolean, default=False)
    drop_items = Column(Text, default="")
    spawn_chance = Column(Float, default=0.3)
    image_url = Column(String(512), nullable=True)
    # Характер: passive / territorial / hunter — см. engine/behavior.py.
    behavior = Column(String(16), default="passive")

    # ── Популяция и передвижение ───────────────────────────
    # Сколько живых экземпляров этого моба одновременно держим в локации.
    # Убили одного — заспавнится новый, но не сверх этого числа.
    population = Column(Integer, default=3)
    respawn_seconds = Column(Integer, default=120)
    # Насколько часто моб делает шаг по карте (0 = стоит на месте)
    move_interval_seconds = Column(Integer, default=45)
    can_roam = Column(Boolean, default=True)
    # Слабый моб может забредать в локации выше уровнем, сильный к слабым — нет.
    # Правило: моб уходит только туда, где min_level >= min_level его дома.
    roam_radius = Column(Integer, default=1)  # на сколько локаций может уйти
    gold_min = Column(Integer, default=0)     # 0 = использовать gold_reward
    gold_max = Column(Integer, default=0)

    location = relationship("Location", back_populates="mobs")
    spawns = relationship(
        "MobSpawn", foreign_keys="MobSpawn.mob_id",
        cascade="all, delete-orphan", back_populates="mob",
    )


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    item_type = Column(SQLEnum(ItemType), nullable=False)
    rarity = Column(SQLEnum(ItemRarity), default=ItemRarity.COMMON)
    level_requirement = Column(Integer, default=1)
    price = Column(Integer, default=0)

    bonus_strength = Column(Integer, default=0)
    bonus_agility = Column(Integer, default=0)
    bonus_intelligence = Column(Integer, default=0)
    bonus_endurance = Column(Integer, default=0)
    bonus_luck = Column(Integer, default=0)
    bonus_hp = Column(Integer, default=0)
    bonus_mp = Column(Integer, default=0)
    bonus_damage = Column(Integer, default=0)
    bonus_defense = Column(Integer, default=0)

    is_sellable = Column(Boolean, default=True)
    icon = Column(String(16), default="⚔️")
    image_url = Column(String(512), nullable=True)

    # ── Уникальность выпадающих предметов ──────────────────
    # Шаблон задаёт «базу», а конкретный экземпляр получает разброс статов
    # в пределах ±stat_variance (доля от базового значения) и может быть
    # улучшен гриндом. Так два одинаковых меча всё равно различаются.
    stat_variance = Column(Float, default=0.15)
    is_unique_roll = Column(Boolean, default=True)   # катать ли статы при дропе
    is_craftable = Column(Boolean, default=False)    # используется ли в крафте как результат
    max_upgrade_level = Column(Integer, default=10)

    # ── Особые предметы ────────────────────────────────────
    # Уникальный: существует ровно в одном экземпляре на весь мир. Как
    # только он кем-то получен, повторно не выпадет и не скрафтится.
    is_one_of_a_kind = Column(Boolean, default=False)
    # Праздничный: выдаётся только когда включено соответствующее событие.
    is_festive = Column(Boolean, default=False)
    festive_event = Column(String(64), default="")   # ключ события, напр. "newyear"
    # Школа магии, которую усиливает предмет (для посохов, амулетов и т.п.)
    magic_school = Column(String(16), nullable=True)
    magic_power = Column(Integer, default=0)

    BONUS_FIELDS = (
        "bonus_strength", "bonus_agility", "bonus_intelligence",
        "bonus_endurance", "bonus_luck", "bonus_hp", "bonus_mp",
        "bonus_damage", "bonus_defense",
    )

    def base_bonuses(self) -> dict:
        return {f: getattr(self, f) or 0 for f in self.BONUS_FIELDS}


class ItemInstance(Base):
    """Уникальный экземпляр предмета.

    У каждого выпавшего/скрафченного предмета свой ID (`uid`, показывается
    игроку) и собственные статы, откатанные с небольшим разбросом от
    шаблона. Улучшение гриндом повышает `upgrade_level` и статы.
    """
    __tablename__ = "item_instances"

    id = Column(Integer, primary_key=True, index=True)
    uid = Column(String(32), unique=True, index=True, nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)

    # Кто и откуда его получил — для истории и админки
    source = Column(String(32), default=ItemSource.MOB.value)
    source_detail = Column(String(128), default="")

    rarity = Column(SQLEnum(ItemRarity), default=ItemRarity.COMMON)
    quality = Column(Integer, default=100)   # 60..140 %, влияет на цену и статы
    upgrade_level = Column(Integer, default=0)
    prefix = Column(String(64), default="")  # «Ржавый», «Закалённый» и т.п.

    bonus_strength = Column(Integer, default=0)
    bonus_agility = Column(Integer, default=0)
    bonus_intelligence = Column(Integer, default=0)
    bonus_endurance = Column(Integer, default=0)
    bonus_luck = Column(Integer, default=0)
    bonus_hp = Column(Integer, default=0)
    bonus_mp = Column(Integer, default=0)
    bonus_damage = Column(Integer, default=0)
    bonus_defense = Column(Integer, default=0)

    # Особые метки экземпляра
    is_one_of_a_kind = Column(Boolean, default=False)
    is_festive = Column(Boolean, default=False)
    festive_event = Column(String(64), default="")
    magic_school = Column(String(16), nullable=True)
    magic_power = Column(Integer, default=0)

    # Сколько раз вещь меняла владельца через аукцион — «намоленность»
    trade_count = Column(Integer, default=0)
    # Текущий владелец (денормализация ради истории и админки)
    owner_character_id = Column(Integer, ForeignKey("characters.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("Item")
    history = relationship(
        "ItemHistory", back_populates="instance",
        cascade="all, delete-orphan", order_by="ItemHistory.created_at",
    )

    BONUS_FIELDS = Item.BONUS_FIELDS

    def bonuses(self) -> dict:
        return {f: getattr(self, f) or 0 for f in self.BONUS_FIELDS}

    def badge(self) -> str:
        """Эмодзи способа получения — печатается перед ID предмета.

        Особые метки важнее исходного источника: единственная в мире вещь
        всегда светится 🌟, праздничная — 🎄, прошедшая через аукцион — 🔁.
        """
        if self.is_one_of_a_kind:
            return source_badge(ItemSource.UNIQUE.value)
        if self.is_festive:
            return source_badge(ItemSource.FESTIVE.value)
        if (self.trade_count or 0) > 0:
            return source_badge(ItemSource.AUCTION.value)
        return source_badge(self.source)

    def tagged_uid(self) -> str:
        """ID предмета со значком источника: «⚔️IT-9AC99E61»."""
        return f"{self.badge()}{self.uid}"

    def source_title(self) -> str:
        return source_label(self.source)

    def display_name(self, item=None) -> str:
        """Имя экземпляра: «Закалённый Стальной меч +3».

        `item` можно передать снаружи, чтобы не дёргать relationship —
        вызывающий код обычно уже держит шаблон загруженным.
        """
        template = item if item is not None else self.__dict__.get("item")
        base = template.name if template is not None else "Предмет"
        name = f"{self.prefix} {base}".strip() if self.prefix else base
        if self.upgrade_level:
            name += f" +{self.upgrade_level}"
        return name


class ItemHistory(Base):
    """Летопись экземпляра: как появился, у кого побывал, что с ним делали.

    Ведётся только для уникальных экземпляров (у ресурсов истории нет).
    Благодаря ей вещь с аукциона приходит к покупателю «с историей».
    """
    __tablename__ = "item_history"

    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("item_instances.id"), nullable=False, index=True)
    # created / looted / crafted / bought / sold / traded / upgraded / gifted
    event = Column(String(32), default="created")
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    actor_name = Column(String(64), default="")     # имя на момент события
    detail = Column(String(256), default="")
    price = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    instance = relationship("ItemInstance", back_populates="history")


class AuctionLot(Base):
    """Лот аукциона: игрок выставляет уникальный экземпляр за золото.

    Купить может другой игрок; если до `expires_at` никто не выкупил, лот
    возвращается продавцу. Скупщик-NPC может выкупить лот сам, чтобы вещь
    не пропадала в мёртвых лотах.
    """
    __tablename__ = "auction_lots"

    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("item_instances.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    seller_name = Column(String(64), default="")
    buyer_id = Column(Integer, ForeignKey("characters.id"), nullable=True)

    price = Column(Integer, default=0)          # цена «купить сразу»
    status = Column(String(16), default=AuctionStatus.ACTIVE.value, index=True)
    is_npc_lot = Column(Boolean, default=False)  # выставлено скупщиком

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    sold_at = Column(DateTime(timezone=True), nullable=True)

    instance = relationship("ItemInstance")
    item = relationship("Item")
    seller = relationship("Character", foreign_keys=[seller_id])
    buyer = relationship("Character", foreign_keys=[buyer_id])


class CharacterAffinity(Base):
    """Предрасположенность героя к школе магии.

    У персонажа от 0 до 2 записей: кто-то рождается вовсе без дара, кто-то
    с искрой одной школы, а редкие счастливчики — с талантом к двум.
    """
    __tablename__ = "character_affinities"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False, index=True)
    school = Column(String(16), nullable=False)
    grade = Column(String(16), default=AffinityGrade.NORMAL.value)

    character = relationship("Character", back_populates="affinities")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    # Уникальный экземпляр: заполнен у снаряжения, пуст у стакающихся
    # расходников и материалов (у них статы не катаются).
    instance_id = Column(Integer, ForeignKey("item_instances.id"), nullable=True)
    quantity = Column(Integer, default=1)
    is_equipped = Column(Boolean, default=False)
    # Защищённый карман: такие вещи не выпадают при гибели. Ячеек мало
    # (см. core/stash.py), поэтому игрок выбирает, что беречь.
    in_stash = Column(Boolean, default=False, index=True)

    character = relationship("Character", back_populates="inventory")
    item = relationship("Item")
    instance = relationship("ItemInstance")

    # Проверяем instance_id перед self.instance: у стакающихся предметов
    # экземпляра нет, и лишнее обращение к relationship вызвало бы ленивую
    # загрузку из async-сессии (MissingGreenlet).
    def _instance(self):
        return self.instance if self.instance_id else None

    def bonuses(self) -> dict:
        """Итоговые бонусы: у уникального экземпляра — свои, иначе шаблонные."""
        inst = self._instance()
        if inst is not None:
            return inst.bonuses()
        return self.item.base_bonuses() if self.item else {}

    def display_name(self) -> str:
        inst = self._instance()
        if inst is not None:
            return inst.display_name(self.item)
        return self.item.name if self.item else "Предмет"

    def uid(self) -> str:
        inst = self._instance()
        return inst.uid if inst is not None else ""


class DropEntry(Base):
    """Строка таблицы лута: что может выпасть из моба или сундука.

    `owner_type` — "mob" (owner_id = mobs.id), "chest" (owner_id = None —
    общий пул для сундуков, либо locations.id для лута конкретной локации)
    или "dungeon" (owner_id = dungeon_templates.id).
    """
    __tablename__ = "drop_entries"

    id = Column(Integer, primary_key=True, index=True)
    owner_type = Column(String(16), default="mob", index=True)
    owner_id = Column(Integer, nullable=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    chance = Column(Float, default=0.2)      # 0..1
    min_quantity = Column(Integer, default=1)
    max_quantity = Column(Integer, default=1)
    # Дополнительный разброс статов именно для этого источника (доля)
    variance_bonus = Column(Float, default=0.0)

    item = relationship("Item")


class CraftRecipe(Base):
    """Рецепт крафта. Доступен у NPC-ремесленника нужного типа."""
    __tablename__ = "craft_recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    station = Column(String(16), default=CraftStation.FORGE.value)
    result_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    result_quantity = Column(Integer, default=1)
    gold_cost = Column(Integer, default=0)
    min_level = Column(Integer, default=1)
    success_chance = Column(Float, default=1.0)
    # Разброс статов результата (доля). Крафт тоже даёт уникальные предметы.
    quality_bonus = Column(Float, default=0.0)
    is_enabled = Column(Boolean, default=True)

    result_item = relationship("Item")
    ingredients = relationship(
        "CraftIngredient", back_populates="recipe", cascade="all, delete-orphan"
    )


class CraftIngredient(Base):
    __tablename__ = "craft_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("craft_recipes.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Integer, default=1)

    recipe = relationship("CraftRecipe", back_populates="ingredients")
    item = relationship("Item")


class UpgradeRule(Base):
    """Правила улучшения предмета гриндом у NPC-ремесленника.

    Одна строка на диапазон уровней заточки: сколько золота и материалов
    нужно, какой шанс успеха и сколько статов добавляется.
    """
    __tablename__ = "upgrade_rules"

    id = Column(Integer, primary_key=True, index=True)
    from_level = Column(Integer, default=0)
    to_level = Column(Integer, default=1)
    gold_cost = Column(Integer, default=50)
    material_item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    material_quantity = Column(Integer, default=1)
    success_chance = Column(Float, default=0.9)
    # На сколько процентов от базовых статов растёт предмет за уровень
    stat_gain_percent = Column(Float, default=0.08)
    # Минимальный абсолютный прирост, чтобы слабые предметы тоже росли
    min_stat_gain = Column(Integer, default=1)

    material_item = relationship("Item")


class MobSpawn(Base):
    """Живой экземпляр моба на карте.

    Каждая локация держит фиксированное число живых мобов: убили одного —
    через `respawn_seconds` появится новый, но сверх лимита никто не
    спавнится. Мобы ходят по клеткам своей локации и могут уходить в
    локации с уровнем не ниже родного.
    """
    __tablename__ = "mob_spawns"

    id = Column(Integer, primary_key=True, index=True)
    mob_id = Column(Integer, ForeignKey("mobs.id"), nullable=False, index=True)
    # Локация, к которой моб «приписан» (лимит считается по ней)
    home_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    # Где он сейчас (может отличаться от домашней при бродяжничестве)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    floor = Column(Integer, default=0)
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)

    current_hp = Column(Integer, default=0)
    is_alive = Column(Boolean, default=True, index=True)
    killed_at = Column(DateTime(timezone=True), nullable=True)
    respawn_at = Column(DateTime(timezone=True), nullable=True)
    last_move_at = Column(DateTime(timezone=True), nullable=True)
    # Кто сейчас в бою с этим мобом (чтобы моб не ушёл посреди боя)
    engaged_by_id = Column(Integer, ForeignKey("characters.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    mob = relationship("Mob", foreign_keys=[mob_id], back_populates="spawns")
    location = relationship("Location", foreign_keys=[location_id])
    home_location = relationship("Location", foreign_keys=[home_location_id])


class Battle(Base):
    __tablename__ = "battles"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    mob_id = Column(Integer, ForeignKey("mobs.id"), nullable=False)
    result = Column(SQLEnum(BattleResult), nullable=True)
    rounds = Column(Integer, default=0)
    damage_dealt = Column(Integer, default=0)
    damage_taken = Column(Integer, default=0)
    gold_earned = Column(Integer, default=0)
    exp_earned = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    character = relationship("Character", back_populates="battles")
    mob = relationship("Mob")


class ShopItem(Base):
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    price = Column(Integer, nullable=False)
    stock = Column(Integer, default=-1)
    refresh_interval = Column(Integer, default=0)

    item = relationship("Item")


class Quest(Base):
    __tablename__ = "quests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    objective_type = Column(String(32), default="kill")  # kill, collect, explore, talk
    objective_target = Column(String(64), default="")  # mob name or item name or npc name
    objective_count = Column(Integer, default=1)
    reward_gold = Column(Integer, default=0)
    reward_exp = Column(Integer, default=0)
    reward_item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    min_level = Column(Integer, default=1)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    npc_name = Column(String(128), nullable=True)
    image_url = Column(String(512), nullable=True)

    reward_item = relationship("Item")


class CharacterQuest(Base):
    __tablename__ = "character_quests"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    quest_id = Column(Integer, ForeignKey("quests.id"), nullable=False)
    status = Column(SQLEnum(QuestStatus), default=QuestStatus.ACTIVE)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    character = relationship("Character", back_populates="quests")
    quest = relationship("Quest")


class VisitedCell(Base):
    """Tracks fog-of-war: which world cells a character has physically visited."""
    __tablename__ = "visited_cells"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    floor = Column(Integer, default=0)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    visited_at = Column(DateTime(timezone=True), server_default=func.now())

    character = relationship("Character")
    location = relationship("Location")


class DungeonTemplate(Base):
    """Admin-configurable procedural dungeon blueprint (standalone, not tied to the 100x100 world grid)."""
    __tablename__ = "dungeon_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    grid_size = Column(Integer, default=25)
    floors_count = Column(Integer, default=1)
    min_level = Column(Integer, default=1)
    wall_chance = Column(Float, default=0.22)
    chest_chance = Column(Float, default=0.06)
    mob_chance = Column(Float, default=0.18)
    mob_level_min = Column(Integer, default=1)
    mob_level_max = Column(Integer, default=5)
    mob_pool = Column(Text, default="")  # comma-separated mob names used for flavor
    image_url = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True)

    # Portal lifecycle: when a portal is opened new entries are allowed; once
    # closed (by admin or automatically after PORTAL_MAX_LIFETIME) no new
    # characters may enter, but anyone already inside keeps playing until
    # they die, leave on their own, or the hard timeout is reached.
    portal_opened_at = Column(DateTime(timezone=True), nullable=True)
    portal_closed_at = Column(DateTime(timezone=True), nullable=True)

    dungeon_runs = relationship("DungeonRun", back_populates="template")


class DungeonRun(Base):
    __tablename__ = "dungeon_runs"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("dungeon_templates.id"), nullable=True)
    dungeon_type = Column(String(32), default="procedural")  # procedural, fixed
    seed = Column(Integer, default=0)
    floor = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    character = relationship("Character", back_populates="dungeon_runs")
    template = relationship("DungeonTemplate", back_populates="dungeon_runs")
    cells = relationship("DungeonCell", back_populates="run", cascade="all, delete-orphan")


class DungeonCell(Base):
    __tablename__ = "dungeon_cells"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("dungeon_runs.id"), nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    name = Column(String(128), default="")
    description = Column(Text, default="")
    is_passable = Column(Boolean, default=True)
    tile_type = Column(String(32), default="cave")
    has_mob = Column(Boolean, default=False)
    mob_name = Column(String(128), nullable=True)
    mob_level = Column(Integer, default=1)
    mob_hp = Column(Integer, default=30)
    mob_damage = Column(Integer, default=5)
    mob_defense = Column(Integer, default=2)
    mob_gold = Column(Integer, default=10)
    mob_exp = Column(Integer, default=15)
    has_chest = Column(Boolean, default=False)
    chest_gold = Column(Integer, default=0)
    has_exit = Column(Boolean, default=False)
    is_visited = Column(Boolean, default=False)

    run = relationship("DungeonRun", back_populates="cells")


class AdminMessage(Base):
    __tablename__ = "admin_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    from_admin = Column(Boolean, default=False)
    text = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="messages")


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, nullable=False)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIGeneration(Base):
    """Черновик AI-мастерской: сгенерированный квест/диалог/лор-запись.

    status: draft (черновик) → bible («библия лора», попадает в контекст
    будущих генераций — это и есть «долгая память» генератора) → applied
    (применён: создан квест или записан диалог NPC).
    """
    __tablename__ = "ai_generations"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(24), nullable=False)        # quest / npc_dialogue / quest_chain / location_desc / lore_note
    title = Column(String(200), default="")           # короткая подпись
    prompt_summary = Column(Text, default="")         # параметры запроса (JSON)
    content = Column(Text, nullable=False, default="")
    status = Column(String(16), default="draft", index=True)
    provider = Column(String(32), default="offline")
    model = Column(String(64), default="")
    target_label = Column(String(200), default="")    # «Тёмный Лес / Торговец Варн»
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WorldEvent(Base):
    """Катаклизм или мировой босс — событие с таймером.

    Одна таблица на оба вида: у них общая природа (живёт по сроку, шлёт
    вести, попадает в летопись), различает поле `kind`.
    """
    __tablename__ = "world_events"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(16), default="cataclysm")   # cataclysm | boss
    key = Column(String(32), nullable=False)         # quake / warden / ...
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    is_global = Column(Boolean, default=False)

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    until = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, index=True)

    # Босс: общее здоровье и фаза. Катаклизм: сколько клеток задето.
    hp = Column(Integer, default=0)
    max_hp = Column(Integer, default=0)
    phase = Column(Integer, default=0)
    cells_touched = Column(Integer, default=0)

    # Слепок изменённых клеток, чтобы вернуть мир как было: JSON
    # {"cell_id": [tile, passable, mob_id, has_chest], ...}
    snapshot = Column(Text, default="")

    location = relationship("Location")
    damage = relationship("WorldEventDamage", back_populates="event",
                          cascade="all, delete-orphan")


class WorldEventDamage(Base):
    """Вклад игрока в мирового босса — награда идёт по нему."""
    __tablename__ = "world_event_damage"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("world_events.id"), nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    damage = Column(Integer, default=0)

    event = relationship("WorldEvent", back_populates="damage")
    character = relationship("Character")


class Grave(Base):
    """Надгробие: золото и вещи ждут хозяина на месте гибели."""
    __tablename__ = "graves"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    owner_name = Column(String(64), default="")
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)
    floor = Column(Integer, default=0)
    gold = Column(Integer, default=0)
    # Индексы предметов, выпавших из сумки: JSON-список item_id.
    items = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    character = relationship("Character")
    location = relationship("Location")


class GameUpdate(Base):
    """Информация об обновлении."""
    __tablename__ = "game_updates"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(128), nullable=False)
    change_type = Column(String(32), default="new")  # "new" (новинка) or "change" (было->стало)
    was_text = Column(Text, nullable=True)            # было
    became_text = Column(Text, nullable=False)        # стало / новинка
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PlayerSuggestion(Base):
    """Пожелания игроков."""
    __tablename__ = "player_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    text = Column(Text, nullable=False)
    status = Column(String(32), default="pending")  # "pending", "taken_in_work", "rejected", "accepted_implemented"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    character = relationship("Character")


class GameSettings(Base):
    """Глобальные настройки игры (в т.ч. курс валют)."""
    __tablename__ = "game_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(Text, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
