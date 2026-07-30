"""Действия для страницы обновлений и идей."""
from webapp import dom


def register(app, A):
    A("publish-update", lambda *_: _publish_update(app))
    A("delete-update", lambda arg="": _delete_update(app, arg))
    A("suggest-action", lambda arg="": _suggest_action(app, arg))


def _publish_update(app):
    # Read form values via inline JS — this is tricky in pure Python.
    # We'll use a simpler approach: the form submits via data-act,
    # and the handler reads from DOM using the webapp.html module patterns.
    # For simplicity, we'll rely on the form data being accessible through
    # the standard webapp mechanism. Looking at other pages, forms use
    # inline form submission through data-act and the handler reads from
    # the form's parent or uses dom.value on inputs with IDs.

    # Since there's no direct form-data parser in webapp, we'll use
    # a practical approach: read values from DOM by element IDs.
    from js import document
    title = str(document.querySelector('input[name="title"]').value)
    change_type = str(document.querySelector('select[name="change_type"]').value)
    was_text = str(document.querySelector('textarea[name="was_text"]').value)
    became_text = str(document.querySelector('textarea[name="became_text"]').value)

    if not title or not became_text:
        dom.toast("Заполни заголовок и описание", "err")
        return

    updates = list(app.store.settings.get("updates", []) or [])
    up_id = max([int(u.get("id", 0)) for u in updates] + [0]) + 1
    from js import Date
    updates.append({
        "id": up_id,
        "title": title,
        "change_type": change_type,
        "was_text": was_text if change_type == "change" else "",
        "became_text": became_text,
        "created_at": str(int(Date.now())),
    })
    app.store.settings["updates"] = updates
    app.store.save()
    dom.toast("Обновление опубликовано")
    app.render()


def _delete_update(app, arg):
    try:
        up_id = int(arg)
    except (ValueError, TypeError):
        dom.toast("Неверный ID обновления", "err")
        return
    updates = list(app.store.settings.get("updates", []) or [])
    updates = [u for u in updates if int(u.get("id", 0)) != up_id]
    app.store.settings["updates"] = updates
    app.store.save()
    dom.toast("Обновление удалено")
    app.render()


def _suggest_action(app, arg):
    # arg format: "s_id:action" or just action
    try:
        if ":" in str(arg):
            s_id_str, action = str(arg).split(":", 1)
            s_id = int(s_id_str)
        else:
            s_id = int(arg)
            action = ""
    except (ValueError, TypeError):
        dom.toast("Неверный аргумент", "err")
        return

    suggestions = list(app.store.settings.get("suggestions", []) or [])
    for s in suggestions:
        sid = s.get("id", s.get("created_at", 0))
        if int(sid) == s_id:
            if action == "take_in_work":
                s["status"] = "taken_in_work"
            elif action == "reject":
                s["status"] = "rejected"
            elif action == "complete":
                s["status"] = "accepted_implemented"
            # Read comment if present
            from js import document
            comment_el = document.querySelector(f'input[name="comment"][value*="{s_id}"]')
            # Since comments are in hidden inputs within forms, we'll use a simpler approach:
            # For simplicity, no custom comment parsing in this minimal implementation.
            break
    else:
        dom.toast("Предложение не найдено", "err")
        return

    app.store.settings["suggestions"] = suggestions
    app.store.save()
    status_label = {
        "pending": "Ожидает",
        "taken_in_work": "В работе",
        "rejected": "Отклонено",
        "accepted_implemented": "Реализовано",
    }.get(s.get("status", "pending"), s.get("status", "pending"))
    dom.toast(f"Статус изменён: {status_label}")
    app.render()
