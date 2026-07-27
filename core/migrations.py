import os
from sqlalchemy import text
from core.database import engine, DATABASE_URL
from core.models import Base


async def run_migrations():
    """Simple migration runner for SQLite."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    async with engine.begin() as conn:
        # Check existing tables
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in result.fetchall()}

        # Add missing columns to characters
        if "characters" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(characters)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "is_vip" not in cols:
                await conn.execute(text("ALTER TABLE characters ADD COLUMN is_vip BOOLEAN DEFAULT 0"))
            if "vip_until" not in cols:
                await conn.execute(text("ALTER TABLE characters ADD COLUMN vip_until DATETIME"))

        # Add missing columns to locations
        if "locations" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(locations)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "world_x" not in cols:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN world_x INTEGER DEFAULT 0"))
            if "world_y" not in cols:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN world_y INTEGER DEFAULT 0"))

        # Add missing columns to cells
        if "cells" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(cells)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "target_location_id" not in cols:
                await conn.execute(text("ALTER TABLE cells ADD COLUMN target_location_id INTEGER"))
            if "target_x" not in cols:
                await conn.execute(text("ALTER TABLE cells ADD COLUMN target_x INTEGER"))
            if "target_y" not in cols:
                await conn.execute(text("ALTER TABLE cells ADD COLUMN target_y INTEGER"))

        # Add missing columns to mobs
        if "mobs" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(mobs)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "spawn_chance" not in cols:
                await conn.execute(text("ALTER TABLE mobs ADD COLUMN spawn_chance FLOAT DEFAULT 0.3"))

        # Create new tables if not exist
        await conn.run_sync(Base.metadata.create_all)
