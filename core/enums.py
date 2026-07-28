from enum import Enum


class CharacterClass(str, Enum):
    """Легаси-перечисление стартовых классов.

    Классы теперь живут в таблице `character_classes` и добавляются из
    админки, поэтому в БД хранится строковый ключ класса. Этот enum
    оставлен для совместимости со старым кодом и как источник дефолтов.
    """
    WARRIOR = "warrior"
    MAGE = "mage"
    ROGUE = "rogue"
    CLERIC = "cleric"
    PALADIN = "paladin"
    RANGER = "ranger"
    NECROMANCER = "necromancer"
    BERSERKER = "berserker"
    DRUID = "druid"
    ASSASSIN = "assassin"


class ItemSource(str, Enum):
    """Откуда взялся конкретный экземпляр предмета."""
    MOB = "mob"
    CHEST = "chest"
    DUNGEON = "dungeon"
    CRAFT = "craft"
    SHOP = "shop"
    QUEST = "quest"
    ADMIN = "admin"
    STARTER = "starter"


class CraftStation(str, Enum):
    """Тип верстака/NPC, у которого доступен рецепт."""
    FORGE = "forge"          # кузница: оружие и броня
    ALCHEMY = "alchemy"      # алхимия: зелья
    JEWELRY = "jewelry"      # ювелир: аксессуары
    ANY = "any"


class ItemType(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    HELMET = "helmet"
    BOOTS = "boots"
    ACCESSORY = "accessory"
    CONSUMABLE = "consumable"
    MATERIAL = "material"


class ItemRarity(str, Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class LocationType(str, Enum):
    SAFE = "safe"
    DANGEROUS = "dangerous"
    DUNGEON = "dungeon"
    BOSS = "boss"


class BattleResult(str, Enum):
    VICTORY = "victory"
    DEFEAT = "defeat"
    ESCAPE = "escape"


class QuestStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
