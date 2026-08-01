"""Система гильдий — можно быть в разных фракциях, но в одной гильдии (союзники)."""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, Table
from sqlalchemy.orm import relationship
from core.models import Base

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
    created_at = Column(Integer)  # timestamp

    members = relationship("Character", secondary=guild_members, backref="guilds")
