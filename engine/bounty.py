"""Награды за головы: твари, убившие героев, становятся целями охоты.

Титулы убийц и формула куша — общие для обоих стеков (`core/bounty.py`
берёт их отсюда). Хранилище разное: сервер держит счётчик в `MobSpawn`,
браузерный стек — в настройках `store` по ключу клетки.
"""
import random

BOUNTY_KEY = "bounties"

BOUNTY_TITLES = (
    "Палач Забытых",
    "Кровавый Мясник",
    "Бич Странников",
    "Пожиратель Костей",
)

BASE_REWARD = 150        # базовый куш за любую голову
PER_KILL_REWARD = 100    # прибавка за каждую загубленную душу


def reward_for(kills: int) -> int:
    """Размер награды: чем больше жертв, тем дороже голова."""
    return BASE_REWARD + max(1, int(kills or 1)) * PER_KILL_REWARD


def _board(store) -> dict:
    data = store.settings.get(BOUNTY_KEY)
    if not isinstance(data, dict):
        data = {}
        store.settings[BOUNTY_KEY] = data
    return data


def record_kill(store, cell_key: str, mob_index: int, rng=None) -> dict:
    """Тварь убила героя: она получает имя и попадает на доску."""
    rng = rng or random
    data = _board(store)
    row = data.get(cell_key) or {"cell": cell_key, "mob": int(mob_index),
                                 "kills": 0, "title": ""}
    row["kills"] = int(row["kills"]) + 1
    row["mob"] = int(mob_index)
    if not row["title"]:
        row["title"] = rng.choice(BOUNTY_TITLES)
    data[cell_key] = row
    store.settings[BOUNTY_KEY] = data
    store.save()
    return row


def active(store) -> list:
    """Цели охоты, от самых кровавых к остальным."""
    return sorted(_board(store).values(),
                  key=lambda r: -int(r.get("kills", 0)))


def at_cell(store, cell_key: str):
    return _board(store).get(cell_key)


def claim(store, cell_key: str) -> int:
    """Голова сдана: снять контракт и вернуть размер награды."""
    data = _board(store)
    row = data.pop(cell_key, None)
    if row is None:
        return 0
    store.settings[BOUNTY_KEY] = data
    store.save()
    return reward_for(row.get("kills", 1))
