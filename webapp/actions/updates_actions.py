"""Действия страницы публикаций и идей игроков."""
from engine import audit
from webapp import dom


def register(app, A):
    A("publish-update", lambda *_: _publish(app))
    A("delete-update", lambda arg="": _delete(app, arg))
    A("suggest-action", lambda arg="": _suggest(app, arg))


def _publish(app):
    title = dom.value("#updTitle").strip()
    became = dom.value("#updBecame").strip()
    if not title or not became:
        dom.toast("Заполни заголовок и описание", "err")
        return
    kind = dom.value("#updType", "new")
    try:
        from js import Date
        now = int(Date.now())
    except Exception:
        import time
        now = int(time.time() * 1000)
    rows = list(app.store.settings.get("updates", []) or [])
    uid = max([int(x.get("id") or 0) for x in rows] + [0]) + 1
    rows.append({"id": uid, "title": title, "change_type": kind,
                 "was_text": dom.value("#updWasText").strip() if kind == "change" else "",
                 "became_text": became, "created_at": str(now)})
    app.store.settings["updates"] = rows
    app.store.save()
    audit.record(app.store, app.actor, "Опубликовал обновление", title, source="panel")
    dom.toast("Обновление опубликовано")
    app.render()


def _delete(app, arg):
    try:
        uid = int(arg)
    except (TypeError, ValueError):
        dom.toast("Неверный ID обновления", "err")
        return
    rows = list(app.store.settings.get("updates", []) or [])
    target = next((x for x in rows if int(x.get("id") or 0) == uid), None)
    if target is None:
        dom.toast("Обновление не найдено", "err")
        return
    app.store.settings["updates"] = [x for x in rows if int(x.get("id") or 0) != uid]
    app.store.save()
    audit.record(app.store, app.actor, "Удалил обновление", target.get("title", ""), source="panel")
    dom.toast("Обновление удалено")
    app.render()


def _suggest(app, arg):
    try:
        sid, action = str(arg).split(":", 1)
        sid = int(sid)
    except (TypeError, ValueError):
        dom.toast("Неверная команда", "err")
        return
    rows = list(app.store.settings.get("suggestions", []) or [])
    row = next((x for x in rows if int(x.get("id") or x.get("created_at") or 0) == sid), None)
    if row is None:
        dom.toast("Идея не найдена", "err")
        return
    statuses = {"take_in_work": "taken_in_work", "complete": "accepted_implemented", "reject": "rejected"}
    if action not in statuses:
        dom.toast("Неизвестный статус", "err")
        return
    row["status"] = statuses[action]
    row["admin_comment"] = dom.value(f"#suggestComment{sid}").strip()
    app.store.settings["suggestions"] = rows
    app.store.save()
    audit.record(app.store, app.actor, "Изменил статус идеи", row.get("text", "")[:80],
                 f"{row['status']}; {row['admin_comment'][:80]}", "panel")
    dom.toast("Статус идеи сохранён")
    app.render()
