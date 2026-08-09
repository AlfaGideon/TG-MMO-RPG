"""Система гильдий — общий оплот, казна и хранилище предметов (Vault)."""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Table, select, func, DateTime
from sqlalchemy.orm import relationship, selectinload
from core.models import Base, Character, InventoryItem, Item, ItemInstance

guild_members = Table(
    "guild_members",
    Base.metadata,
    Column("guild_id", Integer, ForeignKey("guilds.id")),
    Column("character_id", Integer, ForeignKey("characters.id")),
    Column("role", String(32), default="member"),  # leader / officer / member
)


class Guild(Base):
    __tablename__ = "guilds"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text, default="")
    treasury_bronze = Column(Integer, default=0)
    level = Column(Integer, default=1)
    leader_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("Character", secondary=guild_members, backref="guilds")
    vault_items = relationship("GuildVaultItem", back_populates="guild", cascade="all, delete-orphan")


class GuildVaultItem(Base):
    """Предмет в общем хранилище гильдии."""
    __tablename__ = "guild_vault_items"

    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    instance_id = Column(Integer, ForeignKey("item_instances.id"), nullable=True)
    quantity = Column(Integer, default=1)
    deposited_by_character_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    guild = relationship("Guild", back_populates="vault_items")
    item = relationship("Item")
    instance = relationship("ItemInstance")


async def create_guild(session, character: Character, name: str, description: str = "") -> dict:
    """Создать гильдию."""
    from engine.currency import total_in_bronze, deduct_currency
    from sqlalchemy import insert

    cost = 2000
    if total_in_bronze(character) < cost:
        return {"ok": False, "reason": f"Для основания гильдии требуется {cost}🟤."}

    existing = await session.scalar(select(Guild).where(Guild.name == name))
    if existing:
        return {"ok": False, "reason": "Гильдия с таким именем уже существует."}

    deduct_currency(character, cost)
    guild = Guild(
        name=name,
        description=description or f"Гильдия под предводительством {character.name}",
        leader_id=character.id,
        treasury_bronze=500,
        level=1,
    )
    session.add(guild)
    await session.flush()

    await session.execute(
        insert(guild_members).values(
            guild_id=guild.id,
            character_id=character.id,
            role="leader",
        )
    )
    await session.flush()
    return {"ok": True, "guild": guild}


async def deposit_guild_treasury(session, character: Character, guild: Guild, amount: int) -> dict:
    """Внести средства в общую казну гильдии."""
    from engine.currency import total_in_bronze, deduct_currency
    if amount <= 0 or total_in_bronze(character) < amount:
        return {"ok": False, "reason": "Недостаточно средств."}

    deduct_currency(character, amount)
    guild.treasury_bronze = (guild.treasury_bronze or 0) + amount
    await session.flush()
    return {"ok": True, "treasury": guild.treasury_bronze}


async def deposit_guild_vault(session, character: Character, guild: Guild, inv_item: InventoryItem) -> dict:
    """Положить предмет в хранилище гильдии."""
    if inv_item.is_equipped:
        return {"ok": False, "reason": "Сначала сними экипированный предмет!"}

    vault_entry = GuildVaultItem(
        guild_id=guild.id,
        item_id=inv_item.item_id,
        instance_id=inv_item.instance_id,
        quantity=inv_item.quantity or 1,
        deposited_by_character_id=character.id,
    )
    session.add(vault_entry)
    await session.delete(inv_item)
    await session.flush()
    return {"ok": True, "item_name": inv_item.display_name()}

