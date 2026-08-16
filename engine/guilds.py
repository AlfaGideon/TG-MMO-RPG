"""Гильдии и наставничество: союзы между героями.

Правила — **единственный источник правды** для обоих стеков: цена
основания, взносы, пороги наставничества и бонус ученика берутся отсюда
и серверными модулями тоже. Хранилище различается: сервер держит таблицы
`guilds`/`guild_members`, браузерный стек — записи в `store.settings`.
"""
import time

GUILDS_KEY = "guilds"

CREATE_COST = 2000       # основание гильдии — заметная трата, не спонтанная
START_TREASURY = 500     # часть взноса сразу ложится в казну
MENTOR_MIN_LEVEL = 8     # с этого уровня можно вести ученика
APPRENTICE_MAX_LEVEL = 5  # до этого уровня героя ещё считают новичком
MENTOR_EXP_BONUS_PCT = 25
HONOR_PER_PROGRESS = 25   # очки чести наставнику за успехи ученика


def _guilds(store) -> dict:
    data = store.settings.get(GUILDS_KEY)
    if not isinstance(data, dict):
        data = {}
        store.settings[GUILDS_KEY] = data
    return data


def all_guilds(store) -> list:
    return sorted(_guilds(store).values(),
                  key=lambda g: (-int(g.get("level", 1)), g.get("name", "")))


def guild_of(store, p):
    """Гильдия героя и его роль в ней, либо (None, "")."""
    mine = int(getattr(p, "tg_id", 0) or 0)
    for g in _guilds(store).values():
        for m in g.get("members", []):
            if int(m.get("id", 0)) == mine:
                return g, m.get("role", "member")
    return None, ""


def create(store, p, name: str) -> dict:
    """Основать гильдию. Деньги списывает вызывающий код."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "reason": "У гильдии должно быть имя."}
    if any(g.get("name") == name for g in _guilds(store).values()):
        return {"ok": False, "reason": "Гильдия с таким именем уже существует."}

    data = _guilds(store)
    gid = str(int(time.time() * 1000) % 10_000_000)
    data[gid] = {
        "id": gid,
        "name": name,
        "desc": f"Гильдия под предводительством {p.name}",
        "level": 1,
        "treasury": START_TREASURY,
        "leader": int(p.tg_id),
        "members": [{"id": int(p.tg_id), "name": p.name, "role": "leader"}],
    }
    store.settings[GUILDS_KEY] = data
    store.save()
    return {"ok": True, "guild": data[gid]}


def join(store, p, guild_id: str) -> dict:
    """Вступить в гильдию."""
    existing, _role = guild_of(store, p)
    if existing is not None:
        return {"ok": False, "reason": "Ты уже состоишь в гильдии."}
    g = _guilds(store).get(str(guild_id))
    if g is None:
        return {"ok": False, "reason": "Такой гильдии больше нет."}
    g.setdefault("members", []).append(
        {"id": int(p.tg_id), "name": p.name, "role": "member"})
    store.save()
    return {"ok": True, "guild": g}


def deposit(store, guild: dict, amount: int) -> int:
    """Внести взнос в казну. Деньги списывает вызывающий код."""
    guild["treasury"] = int(guild.get("treasury", 0)) + int(amount)
    store.save()
    return guild["treasury"]


# ── наставничество ──────────────────────────────────────────

def can_mentor(mentor, apprentice) -> tuple:
    """(можно ли, причина отказа) — правила те же, что в core/mentorship."""
    if int(getattr(mentor, "tg_id", 0)) == int(getattr(apprentice, "tg_id", 0)):
        return False, "Нельзя стать наставником самому себе."
    if (mentor.level or 1) < MENTOR_MIN_LEVEL:
        return False, (f"Стать наставником может лишь опытный воин "
                       f"({MENTOR_MIN_LEVEL}+ уровень).")
    if (apprentice.level or 1) > APPRENTICE_MAX_LEVEL:
        return False, (f"Учеником может стать только начинающий путник "
                       f"(1–{APPRENTICE_MAX_LEVEL} уровень).")
    if getattr(apprentice, "mentor_id", 0):
        return False, "У этого героя уже есть наставник."
    return True, ""


def bind_mentor(store, apprentice, mentor) -> dict:
    ok, reason = can_mentor(mentor, apprentice)
    if not ok:
        return {"ok": False, "reason": reason}
    apprentice.mentor_id = int(mentor.tg_id)
    store.save_player(apprentice)
    return {"ok": True, "mentor_name": mentor.name}


def mentor_bonuses(p) -> dict:
    has = bool(getattr(p, "mentor_id", 0))
    return {
        "has_mentor": has,
        "exp_bonus_pct": MENTOR_EXP_BONUS_PCT if has else 0,
        "honor_points": int(getattr(p, "honor_points", 0) or 0),
    }


def reward_mentor(store, apprentice) -> int:
    """Начислить наставнику очки чести за успехи ученика."""
    mentor_id = int(getattr(apprentice, "mentor_id", 0) or 0)
    if not mentor_id:
        return 0
    mentor = store.players.get(mentor_id)
    if mentor is None:
        return 0
    mentor.honor_points = int(getattr(mentor, "honor_points", 0) or 0) + HONOR_PER_PROGRESS
    store.save_player(mentor)
    return HONOR_PER_PROGRESS
