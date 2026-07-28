"""Действия вкладки «Контент»: правка мобов, предметов, NPC и классов.

Правки пишутся в engine.data (живой контент) и дублируются в настройки,
чтобы пережить перезагрузку страницы.
"""
from engine import data
from webapp import dom
from webapp.pages import content as page


def register(app, A):
    A("content-tab", lambda arg: _tab(app, arg))

    A("mob-edit", lambda arg: app.modal(page.mob_form(app, int(arg))))
    A("mob-new", lambda _="": app.modal(page.mob_form(app, None)))
    A("mob-save", lambda arg: _mob_save(app, arg))
    A("mob-del", lambda arg: _mob_del(app, arg))
    A("mob-clone", lambda arg: _mob_clone(app, arg))

    A("item-edit", lambda arg: app.modal(page.item_form(app, int(arg))))
    A("item-new", lambda _="": app.modal(page.item_form(app, None)))
    A("item-save", lambda arg: _item_save(app, arg))
    A("item-del", lambda arg: _item_del(app, arg))
    A("item-clone", lambda arg: _item_clone(app, arg))

    A("npc-edit", lambda arg: app.modal(page.npc_form(app, int(arg))))
    A("npc-new", lambda _="": app.modal(page.npc_form(app, None)))
    A("npc-save", lambda arg: _npc_save(app, arg))
    A("npc-del", lambda arg: _npc_del(app, arg))
    A("npc-clone", lambda arg: _npc_clone(app, arg))

    A("class-edit", lambda arg: app.modal(page.class_form(app, arg)))
    A("class-save", lambda arg: _class_save(app, arg))
    A("class-clone", lambda arg: _class_clone(app, arg))


def _tab(app, tab):
    app.state["content_tab"] = tab
    app.render()


def _int(sel, default=0):
    try:
        return int(dom.value(sel, str(default)))
    except (ValueError, TypeError):
        return default


def _persist(app):
    """Сохраняет текущий контент в настройки и обновляет UI."""
    app.store.settings["content"] = {
        "mobs": [list(m) for m in data.MOBS],
        "items": [[i[0], i[1], i[2], i[3], i[4], dict(i[5])] for i in data.ITEMS],
        "npcs": [list(n) for n in data.NPCS],
        "classes": {k: [v[0], v[1], dict(v[2])] for k, v in data.CLASSES.items()},
    }
    app.store.save()
    app.close_modal()
    app.render()


def restore(store):
    """Поднимает сохранённый контент при старте панели."""
    blob = store.settings.get("content")
    if not blob:
        return
    if blob.get("mobs"):
        data.MOBS[:] = [tuple(m) for m in blob["mobs"]]
    if blob.get("items"):
        data.ITEMS[:] = [(i[0], i[1], i[2], i[3], i[4], dict(i[5])) for i in blob["items"]]
    if blob.get("npcs"):
        data.NPCS[:] = [tuple(n) for n in blob["npcs"]]
    for key, val in (blob.get("classes") or {}).items():
        data.CLASSES[key] = (val[0], val[1], dict(val[2]))


# ── мобы ────────────────────────────────────────────────────

def _mob_save(app, arg):
    name = dom.value("#mf_name", "").strip()
    if not name:
        dom.toast("Введите имя моба", "err")
        return
    row = (name, dom.value("#mf_desc", "").strip(), _int("#mf_level", 1),
           _int("#mf_hp", 30), _int("#mf_dmg", 5), _int("#mf_def", 2),
           _int("#mf_gold", 10), _int("#mf_exp", 15), _int("#mf_loc", 0))
    if arg == "new":
        data.MOBS.append(row)
        dom.toast(f"Моб «{name}» создан")
    else:
        data.MOBS[int(arg)] = row
        dom.toast(f"Моб «{name}» сохранён")
    _persist(app)


def _mob_del(app, arg):
    idx = int(arg)
    name = data.MOBS[idx][0]
    data.MOBS.pop(idx)
    for cell in app.store.world.values():
        if cell.mob == idx:
            cell.mob = -1
        elif cell.mob > idx:
            cell.mob -= 1
    dom.toast(f"Моб «{name}» удалён")
    _persist(app)


# ── предметы ────────────────────────────────────────────────

def _parse_bonus(raw):
    out = {}
    for part in raw.split(","):
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        try:
            out[k.strip()] = int(v.strip())
        except ValueError:
            continue
    return out


def _item_save(app, arg):
    name = dom.value("#if_name", "").strip()
    if not name:
        dom.toast("Введите название", "err")
        return
    row = (name, dom.value("#if_type", "weapon"), dom.value("#if_rarity", "common"),
           _int("#if_price", 10), dom.value("#if_icon", "⚔️").strip() or "⚔️",
           _parse_bonus(dom.value("#if_bonus", "")))
    if arg == "new":
        data.ITEMS.append(row)
        dom.toast(f"Предмет «{name}» создан")
    else:
        data.ITEMS[int(arg)] = row
        dom.toast(f"Предмет «{name}» сохранён")
    _persist(app)


def _item_del(app, arg):
    idx = int(arg)
    name = data.ITEMS[idx][0]
    data.ITEMS.pop(idx)
    for p in app.store.players.values():
        p.inventory = [i - 1 if i > idx else i for i in p.inventory if i != idx]
        p.equipped = {s: (i - 1 if i > idx else i)
                      for s, i in p.equipped.items() if i != idx}
    dom.toast(f"Предмет «{name}» удалён")
    _persist(app)


# ── NPC ─────────────────────────────────────────────────────

def _npc_save(app, arg):
    name = dom.value("#nf_name", "").strip()
    if not name:
        dom.toast("Введите имя NPC", "err")
        return
    row = (name, dom.value("#nf_text", "").strip(), dom.value("#nf_kind", "storyteller"))
    if arg == "new":
        data.NPCS.append(row)
        dom.toast(f"NPC «{name}» создан")
    else:
        data.NPCS[int(arg)] = row
        dom.toast(f"NPC «{name}» сохранён")
    _persist(app)


def _npc_del(app, arg):
    idx = int(arg)
    name = data.NPCS[idx][0]
    data.NPCS.pop(idx)
    for cell in app.store.world.values():
        if cell.npc == idx:
            cell.npc = -1
        elif cell.npc > idx:
            cell.npc -= 1
    dom.toast(f"NPC «{name}» удалён")
    _persist(app)


# ── классы ──────────────────────────────────────────────────

def _class_save(app, key):
    old = data.CLASSES.get(key)
    if not old:
        return
    stats = {k: _int(f"#cf_{k}", v) for k, v in old[2].items()}
    data.CLASSES[key] = (dom.value("#cf_title", old[0]).strip() or old[0],
                         dom.value("#cf_desc", old[1]).strip(), stats)
    dom.toast("Класс сохранён")
    _persist(app)


# ── клонирование ────────────────────────────────────────────

def _mob_clone(app, arg):
    idx = int(arg)
    src = list(data.MOBS[idx])
    src[0] = src[0] + " (копия)"
    data.MOBS.append(tuple(src))
    dom.toast(f"Моб «{src[0]}» склонирован")
    _persist(app)


def _item_clone(app, arg):
    idx = int(arg)
    src = list(data.ITEMS[idx])
    src[0] = src[0] + " (копия)"
    data.ITEMS.append(tuple(src))
    dom.toast(f"Предмет «{src[0]}» склонирован")
    _persist(app)


def _npc_clone(app, arg):
    idx = int(arg)
    src = list(data.NPCS[idx])
    src[0] = src[0] + " (копия)"
    data.NPCS.append(tuple(src))
    dom.toast(f"NPC «{src[0]}» склонирован")
    _persist(app)


def _class_clone(app, arg):
    src = data.CLASSES.get(arg)
    if not src:
        return
    new_key = arg + "_copy"
    while new_key in data.CLASSES:
        new_key += "_copy"
    data.CLASSES[new_key] = (src[0] + " (копия)", src[1], dict(src[2]))
    dom.toast(f"Класс «{data.CLASSES[new_key][0]}» склонирован")
    _persist(app)
