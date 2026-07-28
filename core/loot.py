"""Генерация уникальных экземпляров предметов и раздача лута.

Каждый предмет, выпавший из моба, сундука или вышедший из-под молота
кузнеца, — это отдельная строка `item_instances` со своим `uid` и
собственными статами, откатанными с небольшим разбросом от шаблона.
Поэтому два «Ржавых меча» никогда не будут одинаковыми.
"""
import random
import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.enums import ItemRarity, ItemSource, ItemType
from core.models import (
    DropEntry, InventoryItem, Item, ItemInstance, Mob, UpgradeRule,
)

# Типы, которые складываются в стопку и не получают уникальных статов
STACKABLE_TYPES = {ItemType.CONSUMABLE, ItemType.MATERIAL}

# Редкость -> (множитель статов, шанс выпасть при перекате редкости)
RARITY_MULTIPLIER = {
    ItemRarity.COMMON: 1.0,
    ItemRarity.UNCOMMON: 1.15,
    ItemRarity.RARE: 1.35,
    ItemRarity.EPIC: 1.6,
    ItemRarity.LEGENDARY: 2.0,
}

RARITY_ORDER = [
    ItemRarity.COMMON, ItemRarity.UNCOMMON, ItemRarity.RARE,
    ItemRarity.EPIC, ItemRarity.LEGENDARY,
]

# Префиксы по качеству экземпляра — сразу видно, повезло или нет
QUALITY_PREFIXES = [
    (70, ["Ржавый", "Треснувший", "Щербатый", "Потёртый"]),
    (90, ["Простой", "Обычный", "Походный"]),
    (110, ["Крепкий", "Добротный", "Выверенный"]),
    (125, ["Закалённый", "Отменный", "Мастерский"]),
    (999, ["Легендарный", "Безупречный", "Проклятый", "Совершенный"]),
]


def new_uid() -> str:
    """Короткий человекочитаемый уникальный ID экземпляра предмета."""
    return "IT-" + secrets.token_hex(4).upper()


def _prefix_for(quality: int) -> str:
    for threshold, names in QUALITY_PREFIXES:
        if quality <= threshold:
            return random.choice(names)
    return ""


def is_stackable(item: Item) -> bool:
    return item.item_type in STACKABLE_TYPES or not item.is_unique_roll


def roll_quality(variance: float, luck: int = 0) -> int:
    """Качество экземпляра в процентах от базы.

    `variance` — доля разброса (0.15 => ±15 %). Удача персонажа слегка
    смещает распределение вверх, но не ломает баланс.
    """
    variance = max(0.0, min(0.6, variance))
    spread = int(round(variance * 100))
    if spread <= 0:
        return 100
    # Треугольное распределение: середина вероятнее краёв
    base = random.triangular(100 - spread, 100 + spread, 100)
    base += min(10, luck * 0.25)
    return max(40, min(200, int(round(base))))


def roll_rarity(base: ItemRarity, luck: int = 0) -> ItemRarity:
    """Небольшой шанс, что экземпляр окажется на ступень лучше шаблона."""
    idx = RARITY_ORDER.index(base) if base in RARITY_ORDER else 0
    upgrade_chance = 0.06 + min(0.10, luck * 0.004)
    if idx < len(RARITY_ORDER) - 1 and random.random() < upgrade_chance:
        idx += 1
    return RARITY_ORDER[idx]


def create_instance(
    item: Item,
    source: str = ItemSource.MOB.value,
    source_detail: str = "",
    extra_variance: float = 0.0,
    luck: int = 0,
    force_quality: int | None = None,
) -> ItemInstance:
    """Катает уникальный экземпляр предмета по шаблону.

    Возвращает несохранённый `ItemInstance` — вызывающий код добавляет его
    в сессию сам (обычно через `grant_item`).
    """
    variance = (item.stat_variance if item.stat_variance is not None else 0.15) + extra_variance
    quality = force_quality if force_quality is not None else roll_quality(variance, luck)
    rarity = roll_rarity(item.rarity or ItemRarity.COMMON, luck)
    mult = RARITY_MULTIPLIER.get(rarity, 1.0) / RARITY_MULTIPLIER.get(
        item.rarity or ItemRarity.COMMON, 1.0
    )

    inst = ItemInstance(
        uid=new_uid(),
        item_id=item.id,
        source=source,
        source_detail=source_detail[:128],
        rarity=rarity,
        quality=quality,
        upgrade_level=0,
        prefix=_prefix_for(quality),
    )

    for field, base in item.base_bonuses().items():
        if not base:
            setattr(inst, field, 0)
            continue
        rolled = base * (quality / 100.0) * mult
        # Небольшой независимый джиттер на каждый стат — «характер» предмета
        rolled *= random.uniform(0.94, 1.06)
        value = int(round(rolled))
        # Стат, который был у шаблона, не должен обнуляться из-за округления
        setattr(inst, field, max(1, value) if base > 0 else min(-1, value))

    # Держим шаблон под рукой, чтобы display_name() не лез в БД лениво
    inst.item = item
    return inst


async def grant_item(
    session,
    character,
    item: Item,
    quantity: int = 1,
    source: str = ItemSource.MOB.value,
    source_detail: str = "",
    extra_variance: float = 0.0,
) -> list[InventoryItem]:
    """Кладёт предмет(ы) в инвентарь.

    Расходники и материалы складываются в стопку, снаряжение создаётся
    отдельными уникальными экземплярами — по одной строке на предмет.
    """
    luck = getattr(character, "luck", 0) or 0
    added: list[InventoryItem] = []

    if is_stackable(item):
        result = await session.execute(
            select(InventoryItem)
            .options(selectinload(InventoryItem.item))
            .where(InventoryItem.character_id == character.id)
            .where(InventoryItem.item_id == item.id)
            .where(InventoryItem.instance_id.is_(None))
        )
        row = result.scalar_one_or_none()
        if row:
            row.quantity = (row.quantity or 0) + quantity
            added.append(row)
        else:
            row = InventoryItem(
                character_id=character.id, item_id=item.id, quantity=quantity
            )
            row.item = item
            session.add(row)
            added.append(row)
        return added

    for _ in range(max(1, quantity)):
        inst = create_instance(
            item, source=source, source_detail=source_detail,
            extra_variance=extra_variance, luck=luck,
        )
        session.add(inst)
        await session.flush()
        row = InventoryItem(
            character_id=character.id, item_id=item.id,
            instance_id=inst.id, quantity=1,
        )
        row.item = item
        row.instance = inst
        session.add(row)
        added.append(row)

    await session.flush()
    return added


async def roll_drops(session, owner_type: str, owner_id: int | None, luck: int = 0):
    """Возвращает список (Item, quantity, variance_bonus) выпавшего лута."""
    query = select(DropEntry).options(selectinload(DropEntry.item)).where(
        DropEntry.owner_type == owner_type
    )
    query = query.where(
        DropEntry.owner_id == owner_id if owner_id is not None
        else DropEntry.owner_id.is_(None)
    )
    result = await session.execute(query)
    entries = result.scalars().all()

    drops = []
    luck_bonus = min(0.15, (luck or 0) * 0.004)
    for entry in entries:
        if entry.item is None:
            continue
        if random.random() > min(1.0, (entry.chance or 0) + luck_bonus):
            continue
        low = max(1, entry.min_quantity or 1)
        high = max(low, entry.max_quantity or low)
        drops.append((entry.item, random.randint(low, high), entry.variance_bonus or 0.0))
    return drops


async def give_mob_loot(session, character, mob: Mob):
    """Выдаёт лут за убийство моба. Возвращает список InventoryItem."""
    drops = await roll_drops(session, "mob", mob.id, luck=character.luck)
    granted = []
    for item, qty, variance in drops:
        granted += await grant_item(
            session, character, item, qty,
            source=ItemSource.MOB.value, source_detail=mob.name,
            extra_variance=variance,
        )
    return granted


async def give_chest_loot(session, character, location_id: int | None = None, tier: int = 1):
    """Лут из сундука: сначала таблица локации, иначе общий пул."""
    drops = await roll_drops(session, "chest", location_id, luck=character.luck)
    if not drops:
        drops = await roll_drops(session, "chest", None, luck=character.luck)

    granted = []
    # Сундуки покруче дают чуть более разбросанные (и потенциально лучшие) статы
    tier_variance = 0.03 * max(0, tier - 1)
    for item, qty, variance in drops:
        granted += await grant_item(
            session, character, item, qty,
            source=ItemSource.CHEST.value, source_detail=f"Сундук ур.{tier}",
            extra_variance=variance + tier_variance,
        )
    return granted


def instance_price(instance: ItemInstance, base_price: int) -> int:
    """Цена уникального экземпляра с учётом качества и заточки."""
    price = base_price * (instance.quality or 100) / 100.0
    price *= RARITY_MULTIPLIER.get(instance.rarity or ItemRarity.COMMON, 1.0)
    price *= 1 + 0.25 * (instance.upgrade_level or 0)
    return max(1, int(round(price)))


async def find_upgrade_rule(session, from_level: int) -> UpgradeRule | None:
    """Правило заточки, покрывающее переход from_level -> from_level + 1."""
    result = await session.execute(
        select(UpgradeRule)
        .options(selectinload(UpgradeRule.material_item))
        .where(UpgradeRule.from_level <= from_level)
        .order_by(UpgradeRule.from_level.desc())
    )
    for rule in result.scalars().all():
        if rule.to_level > from_level:
            return rule
    return None


def apply_upgrade(instance: ItemInstance, item: Item, rule: UpgradeRule) -> dict:
    """Повышает уровень заточки и статы экземпляра. Возвращает прирост."""
    gains = {}
    base = item.base_bonuses()
    for field, base_value in base.items():
        if not base_value:
            continue
        gain = max(
            rule.min_stat_gain or 1,
            int(round(abs(base_value) * (rule.stat_gain_percent or 0.08))),
        )
        gain = gain if base_value > 0 else -gain
        setattr(instance, field, (getattr(instance, field) or 0) + gain)
        gains[field] = gain
    instance.upgrade_level = (instance.upgrade_level or 0) + 1
    return gains
