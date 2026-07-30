"""Экраны подземелья: комната, кнопки перемещения, карта этажа.

Отделено от engine/dungeon.py, где живут правила: генерация клеток,
перемещение и содержимое. Здесь только сборка Reply.
"""
from engine import rules
from engine.dungeon import (ARROWS, DIRS, EXIT, _passable, cell, leave,
                            run_of, size_of, template)
from engine.models import Reply


def view(store, p):
    """Главный экран подземелья: где стоишь, что вокруг, куда идти."""
    run = run_of(p)
    if run is None:
        return Reply(alert="Ты не в подземелье.")
    tpl = template(store, run["tpl"]) or {"name": "Подземелье"}
    c = cell(store, p)
    if c is None:
        return leave(store, p, "Подземелье схлопнулось за спиной.")

    lines = [f"🕳 <b>{tpl['name']}</b> · этаж {run['floor']}",
             f"📍 [{c['x']},{c['y']}] · <i>{c['name']}</i>", "",
             c["desc"], ""]
    here = []
    if c["exit"]:
        here.append("🚪 Выход наружу")
    if c["mob"]:
        here.append(f"👾 Обитатель (ур. {c['mob_level']})")
    if c["chest"]:
        here.append("📦 Сундук")
    if c["stairs"]:
        here.append("⬇️ Спуск глубже")
    lines.append("\n".join(here) if here else "<i>Пусто.</i>")
    lines.append(f"\n❤️ {p.hp}/{rules.stats(p, store)['max_hp']}  🪙 {p.gold}")

    rows = []
    nav = []
    for d in ("n", "s", "w", "e"):
        dx, dy = DIRS[d]
        if _passable(store, p, run["x"] + dx, run["y"] + dy):
            nav.append((ARROWS[d], f"dgo:{d}"))
        else:
            nav.append(("⬛", "dwall"))
    rows.append(nav)

    act = []
    if c["mob"]:
        act.append(("⚔️ Атаковать", "dfight"))
    if c["chest"]:
        act.append(("📦 Открыть", "dchest"))
    if act:
        rows.append(act)
    deep = []
    if c["stairs"]:
        deep.append(("⬇️ Спуститься", "ddown"))
    if c["exit"]:
        deep.append(("🚪 Выйти", "dexit"))
    if deep:
        rows.append(deep)
    rows.append([("🗺 Карта", "dmap"), ("🎒 Сумка", "bag")])
    return Reply(text="\n".join(lines), keyboard=rows)


def minimap(store, p):
    """Карта этажа: показываем только пройденное."""
    run = run_of(p)
    if run is None:
        return Reply(alert="Ты не в подземелье.")
    tpl = template(store, run["tpl"]) or {}
    size = size_of(tpl)
    seen = set(run.get("seen") or [])
    seen.add(f"{run['floor']}:{run['x']}:{run['y']}")

    rows = []
    for x in range(size):
        line = ""
        for y in range(size):
            key = f"{run['floor']}:{x}:{y}"
            if (x, y) == (run["x"], run["y"]):
                line += "🔴"
                continue
            if key not in seen:
                line += "⬜"
                continue
            c = cell(store, p, x, y)
            if c is None or c["wall"]:
                line += "⬛"
            elif c["exit"]:
                line += "🚪"
            elif c["mob"]:
                line += "👾"
            elif c["chest"]:
                line += "📦"
            elif c["stairs"]:
                line += "⬇️"
            else:
                line += "🟫"
        rows.append(line)

    text = (f"🗺 <b>Этаж {run['floor']}</b> · изучено "
            f"{len(seen)}/{size * size}\n\n" + "\n".join(rows)
            + "\n\n🔴 ты · ⬜ тьма · ⬛ стена · 🚪 выход · ⬇️ спуск")
    return Reply(text=text, keyboard=[[("◀️ Назад", "dview")]])
