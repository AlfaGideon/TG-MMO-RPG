"""Единый журнал действий администраторов.

И бот, и веб-панель пишут сюда через один и тот же Store, поэтому запись,
сделанная кнопкой в Telegram, тут же видна во вкладке «Действия админов»
и наоборот. Никаких браузерных зависимостей — только stdlib.
"""
import time

KEY = "audit"
LIMIT = 400                       # сколько последних записей храним

SOURCES = {"bot": "🤖 Бот", "panel": "🖥 Панель"}
OWNER = "Владелец"


def _log(store):
    lst = store.settings.get(KEY)
    if not isinstance(lst, list):
        lst = []
        store.settings[KEY] = lst
    return lst


def record(store, actor, action, target="", detail="", source="panel"):
    """actor: Player | строка-имя | None (владелец панели без входа)."""
    who, name = 0, OWNER
    if actor is None:
        pass
    elif isinstance(actor, str):
        name = actor or OWNER
    else:
        who = int(getattr(actor, "tg_id", 0) or 0)
        name = getattr(actor, "name", "") or f"#{who}"

    entry = {
        "ts": int(time.time()),
        "who": who,
        "name": name,
        "act": str(action),
        "target": str(target),
        "detail": str(detail),
        "src": source if source in SOURCES else "panel",
    }
    lst = _log(store)
    lst.append(entry)
    if len(lst) > LIMIT:
        del lst[:-LIMIT]
    store.settings[KEY] = lst
    try:
        store.save()
    except Exception:                                     # pragma: no cover
        pass
    return entry


def entries(store, source="", who=0, limit=LIMIT):
    """Записи от новых к старым, с необязательными фильтрами."""
    out = []
    for e in _log(store):
        if source and e.get("src") != source:
            continue
        if who and int(e.get("who") or 0) != int(who):
            continue
        out.append(e)
    out.reverse()
    return out[:limit]


def count(store, source=""):
    return len(entries(store, source=source))


def clear(store):
    store.settings[KEY] = []
    store.save()


def stamp(entry, fmt="%d.%m %H:%M"):
    try:
        return time.strftime(fmt, time.localtime(int(entry.get("ts", 0))))
    except Exception:                                     # pragma: no cover
        return "—"


def line(entry):
    """Одна запись журнала строкой для сообщения в боте."""
    src = SOURCES.get(entry.get("src"), "")
    target = f" → <code>{entry.get('target')}</code>" if entry.get("target") else ""
    detail = f"\n   <i>{entry.get('detail')}</i>" if entry.get("detail") else ""
    return (f"{stamp(entry)} · {src}\n"
            f"   <b>{entry.get('name')}</b>: {entry.get('act')}{target}{detail}")
