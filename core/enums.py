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
    """Откуда взялся конкретный экземпляр предмета.

    Способ получения виден игроку прямо в ID предмета: у каждого источника
    свой эмодзи-значок (см. `SOURCE_BADGES`), поэтому по строке
    `⚔️IT-9AC99E61` сразу понятно, что вещь выбита в бою.
    """
    MOB = "mob"              # выбито в бою
    CHEST = "chest"          # найдено в сундуке/коробке
    DUNGEON = "dungeon"      # добыто в подземелье
    CRAFT = "craft"          # изготовлено ремесленником
    SHOP = "shop"            # куплено в лавке
    AUCTION = "auction"      # прошло через аукцион
    QUEST = "quest"          # награда за задание
    FESTIVE = "festive"      # праздничное/событийное
    UNIQUE = "unique"        # существует в единственном экземпляре
    ADMIN = "admin"          # выдано администратором
    STARTER = "starter"      # стартовый комплект


# Значок способа получения, который печатается перед ID предмета.
# Не применяется к ресурсам и расходникам — у них нет своего ID.
SOURCE_BADGES = {
    ItemSource.MOB.value: "⚔️",
    ItemSource.CHEST.value: "📦",
    ItemSource.DUNGEON.value: "🕳",
    ItemSource.CRAFT.value: "🔨",
    ItemSource.SHOP.value: "🏪",
    ItemSource.AUCTION.value: "🔁",
    ItemSource.QUEST.value: "📜",
    ItemSource.FESTIVE.value: "🎄",
    ItemSource.UNIQUE.value: "🌟",
    ItemSource.ADMIN.value: "🛠",
    ItemSource.STARTER.value: "🎒",
}

SOURCE_LABELS = {
    ItemSource.MOB.value: "Выбито в бою",
    ItemSource.CHEST.value: "Найдено в сундуке",
    ItemSource.DUNGEON.value: "Добыто в подземелье",
    ItemSource.CRAFT.value: "Изготовлено",
    ItemSource.SHOP.value: "Куплено в лавке",
    ItemSource.AUCTION.value: "С аукциона",
    ItemSource.QUEST.value: "Награда за задание",
    ItemSource.FESTIVE.value: "Праздничное",
    ItemSource.UNIQUE.value: "Единственное в мире",
    ItemSource.ADMIN.value: "Выдано администратором",
    ItemSource.STARTER.value: "Стартовое снаряжение",
}


def source_badge(source: str) -> str:
    """Эмодзи способа получения; для незнакомых источников — нейтральный."""
    return SOURCE_BADGES.get(str(source or ""), "🔹")


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(str(source or ""), "Неизвестно")


class MagicSchool(str, Enum):
    """Шесть школ магии. У героя предрасположенность к 0, 1 или 2 из них."""
    FIRE = "fire"          # огонь: чистый урон
    FROST = "frost"        # лёд: замедление и контроль
    STORM = "storm"        # гроза: скорость и криты
    SHADOW = "shadow"      # тьма: проклятия, вытягивание жизни
    NATURE = "nature"      # природа: яды и регенерация
    LIGHT = "light"        # свет: исцеление, урон по нежити


MAGIC_SCHOOLS = {
    MagicSchool.FIRE.value: ("🔥", "Огонь", "Пламя выжигает всё живое. Чистый разрушительный урон."),
    MagicSchool.FROST.value: ("❄️", "Лёд", "Холод сковывает движения. Замедление и контроль."),
    MagicSchool.STORM.value: ("⚡", "Гроза", "Молния бьёт быстрее мысли. Скорость и критические удары."),
    MagicSchool.SHADOW.value: ("🌑", "Тьма", "Проклятия и вытягивание жизни. Цена — собственная кровь."),
    MagicSchool.NATURE.value: ("🌿", "Природа", "Яды, шипы и восстановление. Медленно, но неотвратимо."),
    MagicSchool.LIGHT.value: ("✨", "Свет", "Исцеление союзников и испепеление нежити."),
}


class AffinityGrade(str, Enum):
    """Сила предрасположенности к школе магии."""
    NONE = "none"          # нет дара вовсе
    WEAK = "weak"          # слабая искра
    NORMAL = "normal"      # обычный дар
    STRONG = "strong"      # сильный дар
    GIFTED = "gifted"      # редчайший талант


AFFINITY_GRADES = {
    AffinityGrade.WEAK.value: ("Искра", 0.6, "◦"),
    AffinityGrade.NORMAL.value: ("Дар", 1.0, "•"),
    AffinityGrade.STRONG.value: ("Сильный дар", 1.4, "✦"),
    AffinityGrade.GIFTED.value: ("Талант", 1.8, "✸"),
}


class AuctionStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


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
