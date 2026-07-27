from enum import Enum


class CharacterClass(str, Enum):
    WARRIOR = "warrior"
    MAGE = "mage"
    ROGUE = "rogue"
    CLERIC = "cleric"


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
