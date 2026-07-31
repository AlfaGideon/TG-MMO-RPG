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
            if "offline_protected" not in cols:
                await conn.execute(text("ALTER TABLE characters ADD COLUMN offline_protected BOOLEAN DEFAULT 0"))
            if "image_url" not in cols:
                await conn.execute(text("ALTER TABLE characters ADD COLUMN image_url VARCHAR(512)"))

        # Фракции, раны и найденные диковины у героя.
        if "characters" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(characters)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "reputation" not in cols:
                await conn.execute(text(
                    "ALTER TABLE characters ADD COLUMN reputation TEXT DEFAULT ''"))
            if "wounded_until" not in cols:
                await conn.execute(text(
                    "ALTER TABLE characters ADD COLUMN wounded_until DATETIME"))
            if "landmarks_seen" not in cols:
                await conn.execute(text(
                    "ALTER TABLE characters ADD COLUMN landmarks_seen TEXT DEFAULT ''"))

        # Характер твари: как ведёт себя вне боя.
        if "mobs" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(mobs)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "behavior" not in cols:
                await conn.execute(text(
                    "ALTER TABLE mobs ADD COLUMN behavior VARCHAR(16) DEFAULT 'passive'"))

        # Защищённый карман: вещи, которые переживают гибель героя.
        if "inventory_items" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(inventory_items)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "in_stash" not in cols:
                await conn.execute(text(
                    "ALTER TABLE inventory_items ADD COLUMN in_stash BOOLEAN DEFAULT 0"))

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
            # 💎 донатная валюта: отдельный счётчик, не смешивается с монетами.
            if "premium" not in cols:
                await conn.execute(text(
                    "ALTER TABLE characters ADD COLUMN premium INTEGER DEFAULT 0"))

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

        # Add missing columns to mobs (population / roaming)
        if "mobs" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(mobs)"))
            cols = {row[1] for row in cols_result.fetchall()}
            for col, ddl in (
                ("population", "INTEGER DEFAULT 3"),
                ("respawn_seconds", "INTEGER DEFAULT 120"),
                ("move_interval_seconds", "INTEGER DEFAULT 45"),
                ("can_roam", "BOOLEAN DEFAULT 1"),
                ("roam_radius", "INTEGER DEFAULT 1"),
                ("gold_min", "INTEGER DEFAULT 0"),
                ("gold_max", "INTEGER DEFAULT 0"),
            ):
                if col not in cols:
                    await conn.execute(text(f"ALTER TABLE mobs ADD COLUMN {col} {ddl}"))

        # Add missing columns to items (unique-roll settings)
        if "items" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(items)"))
            cols = {row[1] for row in cols_result.fetchall()}
            for col, ddl in (
                ("stat_variance", "FLOAT DEFAULT 0.15"),
                ("is_unique_roll", "BOOLEAN DEFAULT 1"),
                ("is_craftable", "BOOLEAN DEFAULT 0"),
                ("max_upgrade_level", "INTEGER DEFAULT 10"),
            ):
                if col not in cols:
                    await conn.execute(text(f"ALTER TABLE items ADD COLUMN {col} {ddl}"))

        # Add missing columns to inventory_items (unique instance link)
        if "inventory_items" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(inventory_items)"))
            cols = {row[1] for row in cols_result.fetchall()}
            if "instance_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE inventory_items ADD COLUMN instance_id INTEGER")
                )

        # Add missing columns to cells (craft NPC station, chest respawn)
        if "cells" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(cells)"))
            cols = {row[1] for row in cols_result.fetchall()}
            for col, ddl in (
                ("npc_station", "VARCHAR(16)"),
                ("chest_respawn_at", "DATETIME"),
                ("chest_tier", "INTEGER DEFAULT 1"),
            ):
                if col not in cols:
                    await conn.execute(text(f"ALTER TABLE cells ADD COLUMN {col} {ddl}"))

        # characters.character_class was an ENUM, now a plain string key so new
        # classes can be added from the admin panel. SQLAlchemy's Enum stored
        # the member *name* ("WARRIOR"), while the new class registry keys off
        # the lowercase value ("warrior") — normalise old rows once.
        if "characters" in tables:
            await conn.execute(text(
                "UPDATE characters SET character_class = lower(character_class) "
                "WHERE character_class <> lower(character_class)"
            ))

        # Особые предметы, магия и перекат статов
        if "items" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(items)"))
            cols = {row[1] for row in cols_result.fetchall()}
            for col, ddl in (
                ("is_one_of_a_kind", "BOOLEAN DEFAULT 0"),
                ("is_festive", "BOOLEAN DEFAULT 0"),
                ("festive_event", "VARCHAR(64) DEFAULT ''"),
                ("magic_school", "VARCHAR(16)"),
                ("magic_power", "INTEGER DEFAULT 0"),
            ):
                if col not in cols:
                    await conn.execute(text(f"ALTER TABLE items ADD COLUMN {col} {ddl}"))

        if "item_instances" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(item_instances)"))
            cols = {row[1] for row in cols_result.fetchall()}
            for col, ddl in (
                ("is_one_of_a_kind", "BOOLEAN DEFAULT 0"),
                ("is_festive", "BOOLEAN DEFAULT 0"),
                ("festive_event", "VARCHAR(64) DEFAULT ''"),
                ("magic_school", "VARCHAR(16)"),
                ("magic_power", "INTEGER DEFAULT 0"),
                ("trade_count", "INTEGER DEFAULT 0"),
                ("owner_character_id", "INTEGER"),
            ):
                if col not in cols:
                    await conn.execute(
                        text(f"ALTER TABLE item_instances ADD COLUMN {col} {ddl}")
                    )

        if "characters" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(characters)"))
            cols = {row[1] for row in cols_result.fetchall()}
            # Существующим героям переката не полагается — их статы давно в деле
            if "rerolls_left" not in cols:
                await conn.execute(text(
                    "ALTER TABLE characters ADD COLUMN rerolls_left INTEGER DEFAULT 0"
                ))
            if "stats_locked" not in cols:
                await conn.execute(text(
                    "ALTER TABLE characters ADD COLUMN stats_locked BOOLEAN DEFAULT 1"
                ))

        if "character_classes" in tables:
            cols_result = await conn.execute(text("PRAGMA table_info(character_classes)"))
            cols = {row[1] for row in cols_result.fetchall()}
            for col, ddl in (
                ("affinity_chance", "FLOAT DEFAULT 0.5"),
                ("dual_affinity_chance", "FLOAT DEFAULT 0.12"),
                ("preferred_schools", "TEXT DEFAULT ''"),
            ):
                if col not in cols:
                    await conn.execute(
                        text(f"ALTER TABLE character_classes ADD COLUMN {col} {ddl}")
                    )

        # Create new tables if not exist
        await conn.run_sync(Base.metadata.create_all)
