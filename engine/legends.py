"""Зал Славы: первопроходцы сервера.

Тексты и правило «рекорд фиксируется один раз» — общие для обоих стеков.
Различается хранилище: сервер пишет строки в таблицу `ServerRecord`,
браузерный стек — список в `store.settings` (таблиц там нет).

Рекорд именной и неизменяемый: кто первым убил босса или дошёл до дна
подземелья, тот и остаётся в летописи навсегда — поэтому повторная
запись того же ключа отклоняется.
"""
import time

KEY = "legends"      # ключ списка в store.settings
MAX_RECORDS = 50     # летопись не растёт бесконечно
SHOWN = 8            # столько записей показываем на экране


def _records(store):
    lst = store.settings.get(KEY)
    if not isinstance(lst, list):
        lst = []
        store.settings[KEY] = lst
    return lst


def all_records(store) -> list:
    """Записи от новых к старым."""
    return list(reversed(_records(store)))


def has_record(store, record_key: str) -> bool:
    return any(r.get("key") == record_key for r in _records(store))


def record_first(store, record_key: str, title: str, p, detail: str = "") -> bool:
    """Зафиксировать первопроходство. False — рекорд уже занят."""
    if has_record(store, record_key):
        return False
    lst = _records(store)
    lst.append({
        "key": record_key,
        "title": title,
        "holder": getattr(p, "name", "?"),
        "holder_id": int(getattr(p, "tg_id", 0) or 0),
        "detail": detail,
        "ts": int(time.time()),
    })
    store.settings[KEY] = lst[-MAX_RECORDS:]
    store.save()
    return True


def stamp(ts) -> str:
    try:
        return time.strftime("%d.%m.%Y", time.localtime(int(ts)))
    except (ValueError, TypeError, OSError):
        return "—"


def hall_text(records: list) -> str:
    """Экран Зала Славы. Принимает список словарей (движок) либо строк БД.

    Имя героя и заголовок экранируются: экран выводится с parse_mode="HTML"
    и в боте, и в браузерной панели, а имя — ввод игрока. Без `escape`
    имя вида `<b href=…>` испортило бы разметку (и это же stored-XSS в
    панели). Обёртки <b> добавляем уже после экранирования.
    """
    from html import escape

    def _h(text):
        return escape(str(text or ""), quote=False)

    if not records:
        return (
            "🏆 <b>Глобальный Зал Славы (Server Legends)</b>\n\n"
            "Летопись мира пока пуста. Соверши великий подвиг, чтобы твоё "
            "имя навеки вошло в историю!"
        )
    lines = ["🏆 <b>Глобальный Зал Славы Теневых Земель</b>\n"]
    for r in records[:SHOWN]:
        if isinstance(r, dict):
            title, holder, when = _h(r.get("title", "?")), _h(r.get("holder", "?")), stamp(r.get("ts"))
        else:                                   # строка ServerRecord с сервера
            title = _h(r.title)
            holder = _h(r.holder_character_name)
            when = r.achieved_at.strftime("%d.%m.%Y") if r.achieved_at else "—"
        lines.append(f"⭐ <b>{title}</b>\n   Первопроходец: <b>{holder}</b> ({when})\n")
    return "\n".join(lines)
