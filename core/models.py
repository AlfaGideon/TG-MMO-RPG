from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime, Float,
    Boolean, ForeignKey, Text, Enum as SQLEnum, func
)
from sqlalchemy.orm import relationship

from core.database import Base
from core.enums import CharacterClass, ItemType, ItemRarity, LocationType, BattleResult


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

    character = relationship("Character", back_populates="user", uselist=False)


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    character_class = Column(SQLEnum(CharacterClass), nullable=False)
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    gold = Column(Integer, default=50)

    # Stats
    strength = Column(Integer, default=10)
    agility = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    endurance = Column(Integer, default=10)
    luck = Column(Integer, default=10)

    # Combat
    max_hp = Column(Integer, default=100)
    current_hp = Column(Integer, default=100)
    max_mp = Column(Integer, default=50)
    current_mp = Column(Integer, default=50)

    # Location & Cell (open world grid)
    location_id = Column(Integer, ForeignKey("locations.id"), default=1)
    cell_id = Column(Integer, ForeignKey("cells.id"), nullable=True)

    # Equipment
    weapon_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    armor_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    helmet_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    boots_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    accessory_id = Column(Integer, ForeignKey("items.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="character")
    location = relationship("Location", foreign_keys=[location_id])
    cell = relationship("Cell", foreign_keys=[cell_id])
    inventory = relationship("InventoryItem", back_populates="character", cascade="all, delete-orphan")
    battles = relationship("Battle", back_populates="character")

    def effective_stats(self):
        stats = {
            "strength": self.strength,
            "agility": self.agility,
            "intelligence": self.intelligence,
            "endurance": self.endurance,
            "luck": self.luck,
            "max_hp": self.max_hp,
            "max_mp": self.max_mp,
        }
        return stats


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    location_type = Column(SQLEnum(LocationType), default=LocationType.SAFE)
    min_level = Column(Integer, default=1)
    image_url = Column(String(512), nullable=True)
    grid_size = Column(Integer, default=10)  # 10x10

    cells = relationship("Cell", back_populates="location", cascade="all, delete-orphan")
    mobs = relationship("Mob", back_populates="location")


class Cell(Base):
    __tablename__ = "cells"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    name = Column(String(128), default="")
    description = Column(Text, default="")
    image_url = Column(String(512), nullable=True)
    is_passable = Column(Boolean, default=True)
    mob_id = Column(Integer, ForeignKey("mobs.id"), nullable=True)

    location = relationship("Location", back_populates="cells")
    mob = relationship("Mob")


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


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(128), unique=True, nullable=False)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
