"""Вкладка «Жизнь мира»: респавн, характеры тварей, могилы, отряды, задания."""
import time

from engine import behavior, data, death, party, quests, respawn
from webapp.html import esc

LOC_TYPES = [("safe", "🛡 Безопасные"), ("dangerous", "⚠️ Опасные"),
             ("dungeon", "💀 Подземелья"), ("boss", "👹 Логова боссов")]


def render(ctx):
    return f"""
{_respawn_settings(ctx)}
{_behavior(ctx)}
{_queue(ctx)}
{_graves(ctx)}
{_parties(ctx)}
{_quests(ctx)}
"""


def _behavior(ctx):
    """Кто как себя ведёт и выключатели брожения/охоты."""
    census = behavior.census(ctx.store)
    cards = ""
    for key, (icon, name, hint) in data.BEHAVIORS.items():
        cards += (f"<div class='cata-card'><div class='ct'>{icon} {esc(name)}</div>"
                  f"<div class='cd'>{esc(hint)}<br>сейчас в мире: "
                  f"<b>{census.get(key, 0)}</b></div></div>")
    wander_on = behavior.enabled(ctx.store, behavior.WANDER_SETTING)
    hunt_on = behavior.enabled(ctx.store, behavior.HUNT_SETTING)
    return f"""
<div class="card">
  <h2>👣 Характеры тварей</h2>
  <div class="hint">Раньше все мобы стояли на местах и ждали, пока на них
     наступят. Теперь нрав задаётся у каждого вида в разделе «Контент → Мобы»:
     охотники бродят и сами идут на игрока, территориальные бросаются
     вплотную, пассивные ждут. Катаклизм добавляет злости всем сверху.</div>
  <div class="cata-grid">{cards}</div>
  <div class="row" style="margin-top:.8rem">
    <div><label>Брожение (охотники ходят)</label><select id="behWander">
      <option value="1" {'selected' if wander_on else ''}>включено</option>
      <option value="0" {'selected' if not wander_on else ''}>выключено</option></select></div>
    <div><label>Твари нападают сами</label><select id="behHunt">
      <option value="1" {'selected' if hunt_on else ''}>включено</option>
      <option value="0" {'selected' if not hunt_on else ''}>выключено</option></select></div>
    <div style="flex:0 0 auto"><label>&nbsp;</label>
      <button class="btn primary" data-act="behavior-save">💾 Сохранить</button></div>
  </div>
</div>
"""


def _graves(ctx):
    """Надгробия павших героев."""
    graves = ctx.store.settings.get(death.GRAVES) or []
    if not graves:
        body = "<p class='muted'>Могил нет — либо все живы, либо всё уже забрали.</p>"
    else:
        rows = ""
        for g in sorted(graves, key=lambda x: -x.get("at", 0))[:15]:
            where = (data.LOCATIONS[g["loc"]][0]
                     if g["loc"] < len(data.LOCATIONS) else "?")
            age = int((time.time() - float(g.get("at", 0))) // 60)
            rows += (f"<tr><td>{esc(g.get('name', '?'))}</td>"
                     f"<td>{esc(where)} [{g['x']},{g['y']}]</td>"
                     f"<td>{g.get('gold', 0)} 🪙</td><td>{age} мин назад</td></tr>")
        body = (f"<div class='scroll'><table><thead><tr><th>Герой</th><th>Где</th>"
                f"<th>Золото</th><th>Когда</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></div>")
    return f"""
<div class="card">
  <h2>🪦 Надгробия ({len(graves)})</h2>
  <div class="hint">Потерянное при гибели золото не исчезает, а ждёт хозяина
     на месте смерти: дошёл — вернул всё, погиб по дороге — потерял. Чужую
     могилу тоже можно обчистить, но половина рассыпается прахом.
     Бесхозные истлевают за {death.GRAVE_HOURS} ч.</div>
  {body}
</div>
"""


def _parties(ctx):
    """Кто с кем ходит."""
    parties = ctx.store.settings.get(party.PARTIES) or []
    if not parties:
        body = "<p class='muted'>Отрядов нет — все странствуют поодиночке.</p>"
    else:
        rows = ""
        for pt in parties:
            names = []
            for tg_id in pt.get("members", []):
                q = ctx.store.players.get(int(tg_id))
                if q is None:
                    continue
                crown = "👑 " if int(pt.get("leader", 0)) == int(tg_id) else ""
                names.append(f"{crown}{esc(q.name)} (ур. {q.level})")
            locs = {ctx.store.players[int(m)].loc
                    for m in pt.get("members", [])
                    if int(m) in ctx.store.players}
            together = "вместе" if len(locs) == 1 else "врозь"
            rows += (f"<tr><td>{', '.join(names)}</td>"
                     f"<td>{len(pt.get('members', []))}/{party.MAX_SIZE}</td>"
                     f"<td>{together}</td></tr>")
        body = (f"<div class='scroll'><table><thead><tr><th>Состав</th>"
                f"<th>Размер</th><th>Где</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></div>")
    return f"""
<div class="card">
  <h2>🤝 Отряды ({len(parties)})</h2>
  <div class="hint">До {party.MAX_SIZE} героев. Опыт и золото получают все,
     кто в одной локации: фонд отряда растёт до ×{party.MAX_TOTAL:g}, но доля
     каждого меньше сольной — вместе выгоднее, чем врозь, и при этом не станок
     по печати денег. Зовут командой <code>/invite Имя</code>.</div>
  {body}
</div>
"""


def _respawn_settings(ctx):
    store = ctx.store
    on = respawn.enabled(store)
    mobs = sum(1 for c in store.world.values() if c.mob >= 0)
    chests = sum(1 for c in store.world.values() if c.chest)

    rows = ""
    for key, label in LOC_TYPES:
        loc = respawn._first_loc_of(key)
        m = respawn._minutes(store, "mob", loc)
        c = respawn._minutes(store, "chest", loc)
        rows += (f"<tr><td>{label}</td>"
                 f"<td><input id='rsp_mob_{key}' type='number' min='0' step='1'"
                 f" value='{m:g}' style='max-width:110px'></td>"
                 f"<td><input id='rsp_chest_{key}' type='number' min='0' step='1'"
                 f" value='{c:g}' style='max-width:110px'></td></tr>")

    return f"""
<div class="card">
  <h2>♻️ Возвращение тварей и сундуков</h2>
  <div class="hint">Без респавна мир одноразовый: выбитые твари и вскрытые
     сундуки не возвращались никогда. Теперь убитая тварь появляется на своей
     клетке через заданное время, а сундук — на случайной клетке той же
     локации, чтобы игроки не заучивали точки.<br>
     <b>0 минут — не возвращать.</b> В безопасных землях это норма.</div>
  <p class="muted">Сейчас в мире: 👾 тварей <b>{mobs}</b> · 📦 сундуков <b>{chests}</b></p>
  <div class="row" style="margin:.6rem 0">
    <div><label>Респавн</label><select id="rspOn">
      <option value="1" {'selected' if on else ''}>включён</option>
      <option value="0" {'selected' if not on else ''}>выключен</option></select></div>
  </div>
  <table style="width:100%;max-width:520px">
    <thead><tr><th>Тип локации</th><th>👾 Твари, мин</th><th>📦 Сундуки, мин</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div style="margin-top:.8rem;display:flex;gap:.5rem;flex-wrap:wrap">
    <button class="btn primary" data-act="respawn-save">💾 Сохранить</button>
    <button class="btn" data-act="respawn-now">⚡ Вернуть всё сейчас</button>
  </div>
</div>
"""


def _queue(ctx):
    waiting = respawn.pending(ctx.store)[:12]
    if not waiting:
        body = "<p class='muted'>Очередь пуста — мир населён полностью.</p>"
    else:
        rows = ""
        for cell, kind, left in waiting:
            icon = "👾 Тварь" if kind == "mob" else "📦 Сундук"
            where = (data.LOCATIONS[cell.loc][0]
                     if cell.loc < len(data.LOCATIONS) else "?")
            rows += (f"<tr><td>{icon}</td><td>{esc(where)} [{cell.x},{cell.y}]</td>"
                     f"<td>{left // 60} мин {left % 60} с</td></tr>")
        body = (f"<div class='scroll'><table><thead><tr><th>Что</th><th>Где</th>"
                f"<th>Осталось</th></tr></thead><tbody>{rows}</tbody></table></div>")
    total = len(respawn.pending(ctx.store))
    return f"""
<div class="card">
  <h2>⏳ Ждут возвращения ({total})</h2>
  <p class="muted">Таймеры тикают на шагах игроков, фоновых задач нет.
     Клетка под игроком пропускается: тварь не появится под ногами.</p>
  {body}
</div>
"""


def _quests(ctx):
    counts = {}
    for p in ctx.store.players.values():
        for qid, rec in (getattr(p, "quests", None) or {}).items():
            slot = counts.setdefault(qid, {"active": 0, "done": 0})
            slot["done" if rec.get("done") else "active"] += 1

    rows = ""
    for q in data.QUESTS:
        f = quests.fields(q)
        npc = data.NPCS[f["npc"]][0] if f["npc"] < len(data.NPCS) else "?"
        if f["kind"] == "hunt":
            goal = (f"⚔️ {data.MOBS[f['target']][0]}" if f["target"] >= 0
                    else "⚔️ любые твари")
            goal += f" ×{f['need']}"
        elif f["kind"] == "reach":
            where = (data.LOCATIONS[f["target"]][0]
                     if f["target"] < len(data.LOCATIONS) else "?")
            goal = f"🧭 {esc(where)}"
        else:
            it = data.ITEMS[f["target"]]
            goal = f"🎒 {it[4]} {esc(it[0])} ×{f['need']}"
        c = counts.get(str(f["id"]), {})
        prize = f"🪙 {f['gold']} · ⭐ {f['exp']}"
        if f["item"] >= 0:
            prize += f" · {data.ITEMS[f['item']][4]}"
        daily = "<span class='tag'>🔄 ежедневное</span>" if f["daily"] else ""
        rows += (f"<tr><td><b>{esc(f['name'])}</b> {daily}"
                 f"<div class='muted' style='font-size:.72rem'>{esc(f['text'])}</div></td>"
                 f"<td>{esc(npc)}</td><td>{goal}</td><td>{f['level']}+</td>"
                 f"<td>{prize}</td>"
                 f"<td>▫️ {c.get('active', 0)} · ✅ {c.get('done', 0)}</td></tr>")

    return f"""
<div class="card">
  <h2>📜 Задания ({len(data.QUESTS)})</h2>
  <div class="hint">Задания выдают жители в диалоге и проверяются по тому, что
     уже считает игра: убийства, туман войны и содержимое сумки. Ежедневные
     (🔄) сбрасываются раз в сутки — это причина зайти в игру завтра.</div>
  <div class="scroll"><table>
    <thead><tr><th>Задание</th><th>Заказчик</th><th>Цель</th><th>Ур.</th>
      <th>Награда</th><th>Взято · Сдано</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</div>
"""
