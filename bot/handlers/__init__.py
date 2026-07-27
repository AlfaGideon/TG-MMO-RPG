from .start import router as start_router
from .character import router as character_router
from .location import router as location_router
from .battle import router as battle_router
from .inventory import router as inventory_router
from .shop import router as shop_router

routers = [
    start_router,
    character_router,
    location_router,
    battle_router,
    inventory_router,
    shop_router,
]
