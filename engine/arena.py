"""Колизей Теней: асинхронные дуэли со слепками других героев.

Почему «тени», а не живые игроки: соперник не обязан быть онлайн — с ним
дерётся его слепок (последние статы). Это единственный способ дать PvP в
браузерном стеке, где нет сервера, сводящего двоих в реальном времени.

Правила боя и награды — **единственный источник правды** для обоих
стеков: `core/arena.py` берёт числа отсюда. Хранилище разное: сервер
держит `CharacterShadow` в таблице, браузерный стек — слепки в
`store.settings`.
"""
import random
import time

SHADOWS_KEY = "arena_shadows"

START_RATING = 1000      # рейтинг новичка
MIN_RATING = 100         # ниже не падаем: иначе новичка невозможно догнать
WIN_RATING = 20
LOSS_RATING = -10
WIN_TOKENS = 25          # жетоны гладиатора за победу
LOSS_TOKENS = 5          # проигравшему тоже платят — иначе не станут пробовать
MAX_ROUNDS = 15          # ничья по раундам, чтобы бой не был бесконечным


def _shadows(store) -> dict:
    data = store.settings.get(SHADOWS_KEY)
    if not isinstance(data, dict):
        data = {}
        store.settings[SHADOWS_KEY] = data
    return data


def snapshot(p, store=None) -> dict:
    """Слепок героя: то, с чем будут драться в его отсутствие."""
    from engine import rules

    s = rules.stats(p, store)
    return {
        "owner": int(getattr(p, "tg_id", 0) or 0),
        "name": getattr(p, "name", "?"),
        "cls": getattr(p, "cls", ""),
        "level": int(getattr(p, "level", 1) or 1),
        "max_hp": int(s["max_hp"]),
        "damage": max(10, int(s["strength"]) * 2),
        "defense": max(5, int(s["endurance"])),
        "rating": int(getattr(p, "arena_rating", 0) or START_RATING),
        "ts": int(time.time()),
    }


def update_shadow(store, p) -> dict:
    """Обновить свой слепок — зовётся при каждом заходе на арену."""
    data = _shadows(store)
    shadow = snapshot(p, store)
    data[str(shadow["owner"])] = shadow
    store.settings[SHADOWS_KEY] = data
    return shadow


def opponents(store, p, limit: int = 4) -> list:
    """Соперники: чужие тени, ближайшие по рейтингу."""
    mine = int(getattr(p, "tg_id", 0) or 0)
    my_rating = int(getattr(p, "arena_rating", 0) or START_RATING)
    others = [s for s in _shadows(store).values()
              if int(s.get("owner", 0)) != mine]
    # Ближайшие по рейтингу — честнее, чем просто «сильнейшие»: иначе
    # новичок всегда получал бы соперника, которого не победить.
    others.sort(key=lambda s: abs(int(s.get("rating", START_RATING)) - my_rating))
    return others[:limit]


def find_shadow(store, owner_id):
    return _shadows(store).get(str(owner_id))


def duel(store, p, shadow: dict, rng=None) -> dict:
    """Бой с тенью. Возвращает исход, награды и лог раундов."""
    from engine import rules

    rng = rng or random
    s = rules.stats(p, store)
    char_hp = s["max_hp"]
    shadow_hp = int(shadow["max_hp"])
    log = []
    rounds = 0

    while char_hp > 0 and shadow_hp > 0 and rounds < MAX_ROUNDS:
        rounds += 1
        hit, _crit = rules.attack_roll(p, int(shadow["defense"]), store)
        shadow_hp -= hit
        log.append(f"Раунд {rounds}: ты нанёс {hit} урона тени {shadow['name']}.")
        if shadow_hp <= 0:
            break
        back = max(3, int(shadow["damage"]) - s["defense"] // 2 + rng.randint(-2, 3))
        char_hp -= back
        log.append(f"Раунд {rounds}: тень {shadow['name']} ответила на {back}.")

    victory = shadow_hp <= 0
    tokens = WIN_TOKENS if victory else LOSS_TOKENS
    delta = WIN_RATING if victory else LOSS_RATING

    p.arena_rating = max(MIN_RATING,
                         int(getattr(p, "arena_rating", 0) or START_RATING) + delta)
    p.gladiator_tokens = int(getattr(p, "gladiator_tokens", 0) or 0) + tokens
    update_shadow(store, p)          # свежий слепок для чужих боёв
    if store is not None:
        store.save_player(p)
        store.save()

    return {
        "victory": victory,
        "rounds": rounds,
        "tokens": tokens,
        "rating_change": delta,
        "new_rating": p.arena_rating,
        "log": log,
    }
