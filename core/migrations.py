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
            if "image_url" not in cols:
                await conn.execute(text("ALTER TABLE characters ADD COLUMN image_url VARCHAR(512)"))

        # Add missing columns to users
        if "users" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(users)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "is_web_admin" not in cols:
                await conn.execute(text("ALTER TABLE users ADD COLUMN is_web_admin BOOLEAN DEFAULT 0"))
            if "web_admin_role" not in cols:
                await conn.execute(text("ALTER TABLE users ADD COLUMN web_admin_role VARCHAR(32)"))
            if "web_admin_password_hash" not in cols:
                await conn.execute(text("ALTER TABLE users ADD COLUMN web_admin_password_hash VARCHAR(128)"))
            if "web_admin_granted_at" not in cols:
                await conn.execute(text("ALTER TABLE users ADD COLUMN web_admin_granted_at DATETIME"))
            if "web_admin_password" not in cols:
                await conn.execute(text("ALTER TABLE users ADD COLUMN web_admin_password VARCHAR(64)"))
            if "web_admin_caps" not in cols:
                await conn.execute(text("ALTER TABLE users ADD COLUMN web_admin_caps TEXT"))

        # Add missing columns to locations
        if "locations" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(locations)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "world_x" not in cols:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN world_x INTEGER DEFAULT 0"))
            if "world_y" not in cols:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN world_y INTEGER DEFAULT 0"))
            if "image_url" not in cols:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN image_url VARCHAR(512)"))
            if "floors_count" not in cols:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN floors_count INTEGER DEFAULT 1"))

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
            if "target_floor" not in cols:
                await conn.execute(text("ALTER TABLE cells ADD COLUMN target_floor INTEGER"))
            if "image_url" not in cols:
                await conn.execute(text("ALTER TABLE cells ADD COLUMN image_url VARCHAR(512)"))
            if "floor" not in cols:
                await conn.execute(text("ALTER TABLE cells ADD COLUMN floor INTEGER DEFAULT 0"))
            if "dungeon_template_id" not in cols:
                await conn.execute(text("ALTER TABLE cells ADD COLUMN dungeon_template_id INTEGER"))

        # Add missing columns to characters (floor)
        if "characters" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(characters)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "floor" not in cols:
                await conn.execute(text("ALTER TABLE characters ADD COLUMN floor INTEGER DEFAULT 0"))

        # Add missing columns to dungeon_runs
        if "dungeon_runs" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(dungeon_runs)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "template_id" not in cols:
                await conn.execute(text("ALTER TABLE dungeon_runs ADD COLUMN template_id INTEGER"))

        # Add missing columns to mobs
        if "mobs" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(mobs)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "spawn_chance" not in cols:
                await conn.execute(text("ALTER TABLE mobs ADD COLUMN spawn_chance FLOAT DEFAULT 0.3"))
            if "image_url" not in cols:
                await conn.execute(text("ALTER TABLE mobs ADD COLUMN image_url VARCHAR(512)"))

        # Add missing columns to items
        if "items" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(items)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "image_url" not in cols:
                await conn.execute(text("ALTER TABLE items ADD COLUMN image_url VARCHAR(512)"))

        # Add missing columns to quests
        if "quests" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(quests)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "image_url" not in cols:
                await conn.execute(text("ALTER TABLE quests ADD COLUMN image_url VARCHAR(512)"))

        # Add missing columns to dungeon_templates
        if "dungeon_templates" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(dungeon_templates)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "portal_opened_at" not in cols:
                await conn.execute(text("ALTER TABLE dungeon_templates ADD COLUMN portal_opened_at DATETIME"))
            if "portal_closed_at" not in cols:
                await conn.execute(text("ALTER TABLE dungeon_templates ADD COLUMN portal_closed_at DATETIME"))

        # Create new tables if not exist
        await conn.run_sync(Base.metadata.create_all)
