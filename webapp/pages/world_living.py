"""Вкладка «Жизнь мира»: респавн тварей и сундуков, обзор заданий."""
from engine import data, quests, respawn
from webapp.html import esc

LOC_TYPES = [("safe", "🛡 Безопасные"), ("dangerous", "⚠️ Опасные"),
             ("dungeon", "💀 Подземелья"), ("boss", "👹 Логова боссов")]


def render(ctx):
    return f"""
{_respawn_settings(ctx)}
{_queue(ctx)}
{_quests(ctx)}
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
