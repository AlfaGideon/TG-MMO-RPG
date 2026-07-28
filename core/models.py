from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime, Float,
    Boolean, ForeignKey, Text, Enum as SQLEnum, func
)
from sqlalchemy.orm import relationship

from core.database import Base
from core.enums import CharacterClass, ItemType, ItemRarity, LocationType, BattleResult, QuestStatus


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
    character_class = Column(SQLEnum(CharacterClass), nullable=False)
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    gold = Column(Integer, default=50)

    strength = Column(Integer, default=10)
    agility = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    endurance = Column(Integer, default=10)
    luck = Column(Integer, default=10)

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
    image_url = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="character")
    location = relationship("Location", foreign_keys=[location_id])
    cell = relationship("Cell", foreign_keys=[cell_id])
    inventory = relationship("InventoryItem", back_populates="character", cascade="all, delete-orphan")
    battles = relationship("Battle", back_populates="character")
    party = relationship("Party", back_populates="members", foreign_keys=[party_id], overlaps="leader")
    quests = relationship("CharacterQuest", back_populates="character", cascade="all, delete-orphan")
    dungeon_runs = relationship("DungeonRun", back_populates="character", order_by="DungeonRun.created_at.desc()")

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

    location = relationship("Location", back_populates="mobs")


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


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Integer, default=1)
    is_equipped = Column(Boolean, default=False)

    character = relationship("Character", back_populates="inventory")
    item = relationship("Item")


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
