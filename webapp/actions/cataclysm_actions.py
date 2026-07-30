"""Действия катаклизмов и подземелий: удар, отмена, порталы."""
from engine import adminops, cataclysm as C
from webapp import dom
from webapp.pages import dungeons as page_dungeons
from webapp.pages import world_forms as forms


def register(app, A):
    A("cata-form", lambda arg: _form(app, arg))
    A("cata-strike", lambda arg: _strike(app, arg))
    A("cata-end", lambda arg: _end(app, arg))
    A("cata-calm", lambda _="": _calm(app))
    A("cata-settings", lambda _="": _settings(app))
    A("boss-summon", lambda arg: _boss_summon(app, arg))
    A("boss-dismiss", lambda _="": _boss_dismiss(app))

    A("dungeon-create", lambda _="": _dungeon_create(app))
    A("dungeon-open", lambda arg: _dungeon_open(app, arg))
    A("dungeon-close", lambda arg: _dungeon_close(app, arg))
    A("dungeon-delete", lambda arg: _dungeon_delete(app, arg))
    A("dungeon-focus", lambda arg: _dungeon_focus(app, arg))
    A("portal-loc", lambda arg: _portal_loc(app, arg))


# ── катаклизмы ──────────────────────────────────────────────

def _form(app, kind_key):
    if not C.kind(kind_key):
        dom.toast("Неизвестный катаклизм", "err")
        return
    app.modal(forms.cataclysm_form(app, kind_key))


def _strike(app, kind_key):
    try:
        loc = int(dom.value("#cata_loc", str(C.GLOBAL)))
        hours = float(dom.value("#cata_hours", "0") or 0) or None
    except ValueError:
        dom.toast("Часы — число", "err")
        return
    try:
        _, info = adminops.cataclysm_strike(app.store, app.actor, kind_key,
                                            loc, hours)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    app.log("sys", f"🌋 Катаклизм: {info}")
    app.close_modal()
    dom.toast(f"Обрушено: {info}")
    app.render()
    _flush(app)


def _end(app, event_id):
    try:
        _, info = adminops.cataclysm_end(app.store, app.actor, event_id)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    app.log("sys", f"🕊 Катаклизм прекращён: {info}")
    dom.toast(f"{info} — прекращено, клетки восстановлены")
    app.render()
    _flush(app)


def _calm(app):
    from js import window
    if not window.confirm("Прекратить все катаклизмы и вернуть клетки как было?"):
        return
    try:
        n = adminops.cataclysm_calm(app.store, app.actor)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    dom.toast(f"Успокоено бедствий: {n}" if n else "Бушевать было нечему")
    app.render()
    _flush(app)


def _settings(app):
    s = app.store.settings
    try:
        chance = float(dom.value("#cataChance", "0.02"))
        limit = int(dom.value("#cataLimit", "2"))
    except ValueError:
        dom.toast("Шанс и лимит — числа", "err")
        return
    s["cataclysm_auto"] = dom.value("#cataAuto", "1") == "1"
    s["cataclysm_notify"] = dom.value("#cataNotify", "1") == "1"
    s["cataclysm_chance"] = min(1.0, max(0.0, chance))
    s["cataclysm_limit"] = min(8, max(1, limit))
    app.store.save()
    dom.toast("Настройки катаклизмов сохранены")
    app.render()


# ── мировой босс ────────────────────────────────────────────

def _boss_summon(app, key):
    try:
        _, info = adminops.boss_summon(app.store, app.actor, key)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    app.log("sys", f"🏰 Призван мировой босс: {info}")
    dom.toast(f"Призван: {info}")
    app.render()
    _flush(app)


def _boss_dismiss(app):
    from js import window
    if not window.confirm("Развеять босса? Награды никто не получит."):
        return
    try:
        _, info = adminops.boss_dismiss(app.store, app.actor)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    dom.toast(f"{info} развеян")
    app.render()
    _flush(app)


# ── подземелья ──────────────────────────────────────────────

def _dungeon_create(app):
    name = dom.value("#dg_name").strip()
    desc = dom.value("#dg_desc").strip() or "Загадочные катакомбы."
    if not name:
        dom.toast("Введите название!", "err")
        return
    try:
        min_level = int(dom.value("#dg_level", "1"))
        grid_size = int(dom.value("#dg_size", "10"))
    except ValueError:
        dom.toast("Уровень и размер должны быть числами", "err")
        return
    tpls = app.store.settings.setdefault("dungeon_templates", [])
    new_id = max([t["id"] for t in tpls] + [-1]) + 1
    tpls.append({"id": new_id, "name": name, "desc": desc,
                 "min_level": min_level, "grid_size": grid_size,
                 "portal_cell": None})
    app.store.save()
    dom.toast("Шаблон подземелья создан!")
    app.render()


def _dungeon_open(app, dg_id):
    from engine import adminmenu
    try:
        _, info = adminops.portal_open(app.store, app.actor, dg_id,
                                       adminmenu.pick_cell)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    app.log("sys", f"📢 Портал открыт: {info}")
    dom.toast("Портал успешно открыт!")
    app.render()
    _flush(app)


def _dungeon_close(app, dg_id):
    try:
        adminops.portal_close(app.store, app.actor, dg_id)
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    app.log("sys", "❌ Портал закрыт администратором.")
    dom.toast("Портал закрыт")
    app.render()
    _flush(app)


def _dungeon_delete(app, dg_id):
    from js import window
    if not window.confirm("Удалить этот шаблон подземелья?"):
        return
    _dungeon_close(app, dg_id)
    tpls = app.store.settings.setdefault("dungeon_templates", [])
    app.store.settings["dungeon_templates"] = [t for t in tpls if t["id"] != int(dg_id)]
    app.store.save()
    dom.toast("Шаблон подземелья удалён")
    app.render()


def _dungeon_focus(app, dg_id):
    tpls = app.store.settings.setdefault("dungeon_templates", [])
    dg = next((t for t in tpls if t["id"] == int(dg_id)), None)
    if not dg:
        dom.toast("Шаблон не найден", "err")
        return
    app.modal(page_dungeons.dungeon_form(app, dg))


def _portal_loc(app, idx):
    app.state["world_tab"] = "dungeons"
    app.state["portal_loc"] = int(idx)
    app.render()


def _flush(app):
    if not getattr(app.bot, "running", False):
        return
    import asyncio
    asyncio.ensure_future(app.bot.flush_outbox())
