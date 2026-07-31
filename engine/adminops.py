"""Операции администратора — единственная реализация для бота и панели.

Любое админ-действие проходит через эти функции: они проверяют право,
меняют состояние, пишут запись в журнал (engine.audit) и при необходимости
кладут сообщение игроку в исходящую очередь (outbox), которую разбирает
транспорт бота. Поэтому кнопка в Telegram и кнопка в панели делают ровно
одно и то же и одинаково видны во вкладке «Действия админов».
"""
from engine import audit, data, money, permissions, rules

OUTBOX = "outbox"
MAX_OUTBOX = 200


# ── исходящие сообщения игрокам ─────────────────────────────

def queue(store, chat_id, text):
    """Ставит сообщение в очередь. Отправит тот, кто держит соединение."""
    box = store.settings.get(OUTBOX)
    if not isinstance(box, list):
        box = []
    box.append({"to": int(chat_id), "text": text})
    store.settings[OUTBOX] = box[-MAX_OUTBOX:]
    store.save()


def queue_all(store, text, skip=0):
    for tg_id in list(store.players):
        if skip and int(tg_id) == int(skip):
            continue
        queue(store, tg_id, text)


def drain(store):
    """Забирает и очищает очередь: [(chat_id, text), ...]."""
    box = store.settings.get(OUTBOX) or []
    store.settings[OUTBOX] = []
    if box:
        store.save()
    return [(int(m["to"]), m["text"]) for m in box if m.get("to")]


# ── общая обвязка ───────────────────────────────────────────

class Denied(Exception):
    """Не хватает права на действие."""


def require(actor, cap):
    """actor=None — владелец панели (полный доступ)."""
    if actor is None:
        return True
    if permissions.can(actor, cap):
        return True
    raise Denied(f"Нужно право «{permissions.CAP_LABELS.get(cap, cap)}»")


def allowed(actor, cap):
    try:
        return require(actor, cap)
    except Denied:
        return False


def _done(store, actor, source, action, target="", detail=""):
    audit.record(store, actor, action, target, detail, source)
    return True, detail or action


def _target(store, tg_id):
    p = store.players.get(int(tg_id))
    if not p:
        raise Denied("Игрок не найден")
    return p


def _who(p):
    return f"{p.name} #{p.tg_id}"


# ── игроки ──────────────────────────────────────────────────

def heal(store, actor, tg_id, source="panel"):
    require(actor, "heal_players")
    p = _target(store, tg_id)
    s = rules.stats(p)
    p.hp, p.mp = s["max_hp"], s["max_mp"]
    store.save_player(p)
    queue(store, p.tg_id, "💊 Администратор полностью восстановил твои силы.")
    return _done(store, actor, source, "Исцелил игрока", _who(p),
                 f"HP/MP → {s['max_hp']}/{s['max_mp']}")


def give_item(store, actor, tg_id, item_idx, source="panel"):
    require(actor, "give_items")
    p = _target(store, tg_id)
    idx = int(item_idx)
    if not 0 <= idx < len(data.ITEMS):
        raise Denied("Нет такого предмета")
    p.inventory.append(idx)
    store.save_player(p)
    it = rules.item(idx)
    queue(store, p.tg_id, f"🎁 Тебе выдан предмет: {it['icon']} <b>{it['name']}</b>")
    return _done(store, actor, source, "Выдал предмет", _who(p),
                 f"{it['icon']} {it['name']}")


def add_gold(store, actor, tg_id, amount, source="panel"):
    require(actor, "edit_players")
    p = _target(store, tg_id)
    amount = int(amount)
    p.gold = max(0, money.balance(p) + amount)
    store.save_player(p)
    queue(store, p.tg_id, f"👛 Администратор изменил твой кошелёк: {money.plus(amount)}")
    return _done(store, actor, source, "Изменил золото", _who(p),
                 f"{money.plus(amount)} → {money.fmt(p.gold)}")


def add_level(store, actor, tg_id, delta, source="panel"):
    require(actor, "edit_players")
    p = _target(store, tg_id)
    delta = int(delta)
    old_level = p.level
    new_level = max(1, old_level + delta)
    actual_delta = new_level - old_level
    p.level = new_level
    if actual_delta != 0:
        from engine import hero
        gains = hero.growth(p.cls)
        for key, step in gains.items():
            setattr(p, key, max(0, getattr(p, key, 0) + int(step) * actual_delta))
        p.hp = p.max_hp
    store.save_player(p)
    sign = "+" if delta >= 0 else ""
    queue(store, p.tg_id, f"⭐ Твой уровень изменён администратором: {sign}{delta}")
    return _done(store, actor, source, "Изменил уровень", _who(p),
                 f"{sign}{delta} → ур. {p.level}")


def set_fields(store, actor, tg_id, fields, source="panel"):
    """Пакетная правка статов из формы панели."""
    require(actor, "edit_players")
    p = _target(store, tg_id)
    
    # Check if level changed
    level_val = fields.get("level")
    if level_val is not None:
        try:
            new_level = max(1, int(level_val))
            delta = new_level - p.level
            if delta != 0:
                from engine import hero
                gains = hero.growth(p.cls)
                for stat, step in gains.items():
                    form_val = fields.get(stat)
                    if form_val is not None:
                        try:
                            if int(form_val) == getattr(p, stat, 0):
                                fields[stat] = max(0, int(form_val) + int(step) * delta)
                        except (ValueError, TypeError):
                            pass
                    else:
                        setattr(p, stat, max(0, getattr(p, stat, 0) + int(step) * delta))
        except (ValueError, TypeError):
            pass

    changed = []
    for k, v in fields.items():
        if not hasattr(p, k):
            continue
        old = getattr(p, k)
        if str(old) == str(v):
            continue
        setattr(p, k, v)
        changed.append(f"{k}: {old}→{v}")
    store.save_player(p)
    return _done(store, actor, source, "Правка статов", _who(p),
                 ", ".join(changed) if changed else "без изменений")


def delete_player(store, actor, tg_id, source="panel"):
    require(actor, "del_players")
    p = _target(store, tg_id)
    store.players.pop(int(tg_id), None)
    store.save()
    return _done(store, actor, source, "Удалил игрока", _who(p))


def wipe_players(store, actor, source="panel"):
    require(actor, "del_players")
    n = len(store.players)
    store.wipe_players()
    return _done(store, actor, source, "Удалил всех игроков", "", f"было {n}")


def teleport(store, actor, tg_id, loc, x, y, source="panel"):
    require(actor, "edit_players")
    p = _target(store, tg_id)
    p.loc, p.x, p.y = int(loc), int(x), int(y)
    p.combat = {}
    store.save_player(p)
    where = data.LOCATIONS[p.loc][0] if p.loc < len(data.LOCATIONS) else "?"
    queue(store, p.tg_id, f"🌀 Тебя переместили: <b>{where}</b> [{p.x},{p.y}]")
    return _done(store, actor, source, "Телепорт", _who(p), f"{where} [{p.x},{p.y}]")


# ── доступы ─────────────────────────────────────────────────

def grant(store, actor, tg_id, rank="viewer", caps=None, source="panel"):
    require(actor, "grant_admin")
    from engine import adminbot
    p = _target(store, tg_id)
    keep = bool(p.web_admin_password)
    text = adminbot.grant(store, p, rank, caps, reset_password=not keep)
    queue(store, p.tg_id, text)
    _done(store, actor, source, "Выдал доступ", _who(p),
          permissions.rank_title(p.web_admin_role))
    return True, text


def revoke(store, actor, tg_id, source="panel"):
    require(actor, "grant_admin")
    from engine import adminbot
    p = _target(store, tg_id)
    text = adminbot.revoke(store, p)
    queue(store, p.tg_id, text)
    _done(store, actor, source, "Отозвал доступ", _who(p))
    return True, text


def new_password(store, actor, tg_id, source="panel"):
    require(actor, "grant_admin")
    p = _target(store, tg_id)
    p.web_admin_password = permissions.new_password()
    store.save_player(p)
    queue(store, p.tg_id,
          f"🔑 Новый пароль от панели: <code>{p.web_admin_password}</code>")
    return _done(store, actor, source, "Сменил пароль доступа", _who(p))


# ── рассылка и мир ──────────────────────────────────────────

def broadcast(store, actor, text, source="panel"):
    require(actor, "broadcast")
    body = (text or "").strip()
    if not body:
        raise Denied("Пустое сообщение")
    skip = getattr(actor, "tg_id", 0) if actor is not None else 0
    queue_all(store, f"📣 <b>Объявление</b>\n\n{body}", skip=skip)
    n = len(store.players) - (1 if skip in store.players else 0)
    _done(store, actor, source, "Рассылка", f"{max(n, 0)} игрокам", body[:120])
    return True, max(n, 0)


def portal_open(store, actor, tpl_id, pick, source="panel"):
    """pick(store) -> ключ клетки для портала (выбор делает вызывающий)."""
    require(actor, "dungeons")
    tpl = _tpl(store, tpl_id)
    if tpl.get("portal_cell"):
        raise Denied("Портал уже открыт")
    key = pick(store)
    if not key:
        raise Denied("Нет подходящей клетки")
    c = store.world[key]
    c.name = f"🌀 Портал: {tpl['name']}"
    c.desc = (f"Врата сияют мистической энергией. Ведут в '{tpl['name']}' "
              f"(мин. уровень {tpl.get('min_level', 1)}).")
    c.tile = "cave"
    tpl["portal_cell"] = key
    import time
    tpl["opened_at"] = time.time()
    store.save()
    where = data.LOCATIONS[c.loc][0] if c.loc < len(data.LOCATIONS) else "?"
    queue_all(store, f"🌀 <b>Открылся портал!</b>\n\n{tpl['name']}\n"
                     f"📍 {where} [{c.x},{c.y}]")
    return _done(store, actor, source, "Открыл портал", tpl["name"],
                 f"{where} [{c.x},{c.y}]")


def portal_close(store, actor, tpl_id, source="panel"):
    require(actor, "dungeons")
    tpl = _tpl(store, tpl_id)
    key = tpl.get("portal_cell")
    if key:
        c = store.world.get(key)
        if c:
            c.name = "Заросшая поляна"
            c.desc = "Трава и кустарники. Здесь когда-то сиял портал."
            c.tile = "grass"
    tpl["portal_cell"] = None
    store.save()
    queue_all(store, f"🚪 Портал <b>{tpl['name']}</b> закрылся.")
    return _done(store, actor, source, "Закрыл портал", tpl["name"])


def _tpl(store, tpl_id):
    for t in store.settings.get("dungeon_templates", []) or []:
        if int(t["id"]) == int(tpl_id):
            return t
    raise Denied("Шаблон не найден")


def templates(store):
    return store.settings.get("dungeon_templates", []) or []


# ── операции над миром ──────────────────────────────────────
# Реализация переехала в engine/adminworld.py, но вызывать привычно
# через adminops — поэтому здесь тонкие делегаты.

def cataclysm_strike(store, actor, kind_key, loc=-1, hours=None, source="panel"):
    from engine import adminworld
    return adminworld.cataclysm_strike(store, actor, kind_key, loc, hours, source)


def cataclysm_end(store, actor, event_id, source="panel"):
    from engine import adminworld
    return adminworld.cataclysm_end(store, actor, event_id, source)


def cataclysm_calm(store, actor, source="panel"):
    from engine import adminworld
    return adminworld.cataclysm_calm(store, actor, source)


def boss_summon(store, actor, key, loc=None, hours=None, source="panel"):
    from engine import adminworld
    return adminworld.boss_summon(store, actor, key, loc, hours, source)


def boss_dismiss(store, actor, source="panel"):
    from engine import adminworld
    return adminworld.boss_dismiss(store, actor, source)
