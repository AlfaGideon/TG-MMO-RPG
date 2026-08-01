from .start import router as start_router
from .help_book import router as help_book_router
from .updates_book import router as updates_book_router
from .character import router as character_router
from .location import router as location_router
from .battle import router as battle_router
from .inventory import router as inventory_router
from .shop import router as shop_router
from .party import router as party_router
from .dungeon import router as dungeon_router
from .craft import router as craft_router
from .auction import router as auction_router
from .merchant import router as merchant_router
from .admin import router as admin_router
from .world_extra import router as world_extra_router

routers = [
    start_router,
    help_book_router,
    updates_book_router,
    character_router,
    location_router,
    battle_router,
    inventory_router,
    shop_router,
    party_router,
    dungeon_router,
    craft_router,
    auction_router,
    merchant_router,
    admin_router,
    world_extra_router,
]
