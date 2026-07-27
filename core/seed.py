from sqlalchemy import select
from core.database import async_session
from core.models import Location, Mob, Item, ShopItem, AppSetting
from core.enums import LocationType, ItemType, ItemRarity


async def seed_database():
    async with async_session() as session:
        # Seed locations
        result = await session.execute(select(Location))
        if result.scalars().first():
            return

        locations = [
            Location(name="Погост Костров", description="Безопасная деревня среди болот. Здесь торгуют странствующие купцы и изгнанники находят пристанище.", location_type=LocationType.SAFE, min_level=1),
            Location(name="Тёмный Лес", description="Старые дубы скрывают глаза нежити. Шёпот слышен за каждым деревом.", location_type=LocationType.DANGEROUS, min_level=1),
            Location(name="Заброшенная Крепость", description="Каменные стены помнят времена, когда рыцари ещё носили сияющие доспехи. Теперь здесь обитают гноллы и скелеты.", location_type=LocationType.DANGEROUS, min_level=3),
            Location(name="Катакомбы Павших", description="Глубокие подземелья под храмом забытого бога. Легенды гласят, что в самых низах спит древнее зло.", location_type=LocationType.DUNGEON, min_level=5),
            Location(name="Логово Пожирателя", description="Расщелина в скалах, откуда исходит серная вонь. Здесь обитает Пожиратель — древний дракон тьмы.", location_type=LocationType.BOSS, min_level=10),
        ]
        session.add_all(locations)
        await session.flush()

        mobs = [
            Mob(name="Болотный зомби", description="Медлительный труп, пропитанный ядовитыми испарениями.", level=1, hp=25, damage=4, defense=1, gold_reward=5, exp_reward=10, location_id=2),
            Mob(name="Лесной ворг", description="Крупный волк с чёрной шерстью и светящимися глазами.", level=2, hp=40, damage=7, defense=2, gold_reward=8, exp_reward=18, location_id=2),
            Mob(name="Скелет-воин", description="Ожившие останки павшего солдата. Его кости стучат мерным ритмом.", level=3, hp=50, damage=8, defense=3, gold_reward=12, exp_reward=25, location_id=3),
            Mob(name="Гнолл-грабитель", description="Гибрид человека и гиены. Пахнет тленом и жадностью.", level=4, hp=65, damage=10, defense=3, gold_reward=15, exp_reward=35, location_id=3),
            Mob(name="Пещерный тролль", description="Громадина с каменной кожей. Его шаги заставляют дрожать стены.", level=6, hp=100, damage=14, defense=6, gold_reward=25, exp_reward=60, location_id=4),
            Mob(name="Теневой призрак", description="Нематериальная сущность из кошмаров. Прикасается к разуму, а не к плоти.", level=7, hp=80, damage=18, defense=2, gold_reward=30, exp_reward=70, location_id=4),
        ]
        session.add_all(mobs)

        items = [
            Item(name="Ржавый меч", description="Клинок, который видел лучшие дни. Всё ещё режет.", item_type=ItemType.WEAPON, rarity=ItemRarity.COMMON, price=20, bonus_damage=3, icon="🗡"),
            Item(name="Дубинка гнолла", description="Тяжёлая палка с вбитым гвоздём. Грубо, но эффективно.", item_type=ItemType.WEAPON, rarity=ItemRarity.COMMON, price=35, bonus_damage=5, icon="🏏"),
            Item(name="Кинжал теней", description="Лезвие из метеоритного железа. Едва заметно в темноте.", item_type=ItemType.WEAPON, rarity=ItemRarity.RARE, price=120, bonus_damage=10, bonus_agility=3, icon="🗡"),
            Item(name="Старая кольчуга", description="Ржавые кольца, но лучше, чем рубаха.", item_type=ItemType.ARMOR, rarity=ItemRarity.COMMON, price=25, bonus_defense=3, bonus_hp=10, icon="🦺"),
            Item(name="Мантия послушника", description="Простая ткань с вышитыми рунами защиты.", item_type=ItemType.ARMOR, rarity=ItemRarity.COMMON, price=25, bonus_defense=2, bonus_mp=15, icon="🥋"),
            Item(name="Шлем изгнанника", description="Железный шлем с зарубкой за каждую пережитую битву.", item_type=ItemType.HELMET, rarity=ItemRarity.UNCOMMON, price=40, bonus_defense=2, bonus_endurance=2, icon="🪖"),
            Item(name="Сапоги скитальца", description="Изношенная кожа, но удобные.", item_type=ItemType.BOOTS, rarity=ItemRarity.COMMON, price=15, bonus_agility=1, icon="👢"),
            Item(name="Кольцо удачи", description="Серебряное кольцо с выгравированным клевером.", item_type=ItemType.ACCESSORY, rarity=ItemRarity.UNCOMMON, price=60, bonus_luck=5, icon="💍"),
            Item(name="Зелье здоровья", description="Красная жидкость с запахом трав. Восстанавливает 30 HP.", item_type=ItemType.CONSUMABLE, rarity=ItemRarity.COMMON, price=10, icon="🧪"),
            Item(name="Зелье маны", description="Синяя субстанция. Восстанавливает 20 MP.", item_type=ItemType.CONSUMABLE, rarity=ItemRarity.COMMON, price=10, icon="🧪"),
        ]
        session.add_all(items)
        await session.flush()

        shop_items = [
            ShopItem(item_id=1, price=20, stock=-1),
            ShopItem(item_id=2, price=35, stock=5),
            ShopItem(item_id=4, price=25, stock=-1),
            ShopItem(item_id=5, price=25, stock=-1),
            ShopItem(item_id=6, price=40, stock=3),
            ShopItem(item_id=7, price=15, stock=-1),
            ShopItem(item_id=8, price=60, stock=1),
            ShopItem(item_id=9, price=10, stock=-1),
            ShopItem(item_id=10, price=10, stock=-1),
        ]
        session.add_all(shop_items)
        await session.commit()
        print("Database seeded.")
