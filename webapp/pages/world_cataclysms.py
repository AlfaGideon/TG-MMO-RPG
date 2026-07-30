"""Вкладка «Катаклизмы»: что бушует сейчас, чем ударить, летопись бедствий."""
import time

from engine import cataclysm as C
from engine import data
from engine import worldboss as WB
from webapp.html import esc


def render(ctx):
    return f"""
{_live(ctx)}
{_boss(ctx)}
{_arsenal(ctx)}
{_settings(ctx)}
{_history(ctx)}
"""


def _live(ctx):
    live = C.active(ctx.store, None)
    if not live:
        body = ("<p class='muted'>Сейчас тихо. Мир цел — можно это исправить "
                "кнопкой ниже.</p>")
    else:
        rows = ""
        for e in live:
            k = C.kind(e["kind"]) or {}
            left = max(0, int(e["until"] - time.time()))
            rows += (
                f"<tr><td><b>{esc(C.title(e['kind']))}</b>"
                f"<div class='muted'>{esc(k.get('story', ''))}</div></td>"
                f"<td>{esc(C.place(e['loc']))}</td>"
                f"<td><span class='badge cata-timer' data-until='{int(e['until'])}'>"
                f"{left // 60} мин</span></td>"
                f"<td>{e.get('cells', 0)}</td>"
                f"<td>👾×{k.get('mob_rate', 1):.2f} · 💥×{k.get('damage', 1):.2f}<br>"
                f"📦×{k.get('loot', 1):.2f} · 🪙×{k.get('gold', 1):.2f} · 🏕×{k.get('rest', 1):.2f}<br>"
                f"<span style='color:var(--danger)'>⚡ засада {int(k.get('ambush', 0) * 100)}%"
                f" · ➕ подмога {int(k.get('join', 0) * 100)}%</span></td>"
                f"<td><button class='btn danger sm' data-act='cata-end' "
                f"data-arg='{e['id']}'>🕊 Прекратить</button></td></tr>")
        body = f"""
<div class="scroll"><table>
  <thead><tr><th>Бедствие</th><th>Где</th><th>Осталось</th><th>Клеток</th>
    <th>Множители</th><th></th></tr></thead>
  <tbody>{rows}</tbody>
</table></div>
<div style="margin-top:.8rem">
  <button class="btn" data-act="cata-calm">🕊 Успокоить всё разом</button>
</div>
"""
    return f"""
<div class="card">
  <h2>🔥 Бушует сейчас ({len(live)})</h2>
  <div class="hint">Пока бедствие идёт, тварей <b>вдвое больше</b> обычного, они
     <b>нападают сами</b> из соседних клеток и сбегаются на шум уже идущего боя.
     Когда беда стихает, популяция и поведение возвращаются к норме.<br>
     Клетки правятся со слепком: тайлы, проходимость и сундуки восстанавливаются.
     Клетки под игроками, спавн и швы-переходы не трогаются.</div>
  {body}
</div>
{_timer_script()}
"""


def _boss(ctx):
    """Мировой босс: кто сейчас, кого призвать, чем кончилось прошлое."""
    ev = WB.active(ctx.store)
    if ev is None:
        body = "<p class='muted'>Мировой босс не призван.</p>"
    else:
        b = WB.BOSSES[ev["key"]]
        where = (data.LOCATIONS[ev["loc"]][0]
                 if ev["loc"] < len(data.LOCATIONS) else "?")
        left = max(0, int(ev["until"] - time.time()))
        fighters = ""
        dmg = ev.get("damage") or {}
        total = sum(int(v) for v in dmg.values()) or 1
        for tg_id, dealt in sorted(dmg.items(), key=lambda kv: -int(kv[1]))[:8]:
            q = ctx.store.players.get(int(tg_id))
            name = esc(q.name) if q else f"#{tg_id}"
            fighters += (f"<tr><td>{name}</td><td>{dealt}</td>"
                         f"<td>{int(dealt) / total * 100:.0f}%</td></tr>")
        table = (f"<table><thead><tr><th>Герой</th><th>Урон</th><th>Вклад</th>"
                 f"</tr></thead><tbody>{fighters}</tbody></table>"
                 if fighters else "<p class='muted'>Пока никто не бился.</p>")
        body = f"""
<div class="cata-live">
  <b>{esc(WB.title(ev['key']))}</b> · 📍 {esc(where)}<br>
  ❤️ {ev['hp']}/{ev['max_hp']} · ⏳ <span class="cata-timer"
     data-until="{int(ev['until'])}">{left // 60} мин</span>
  {' · 🔥 вторая фаза' if ev.get('phase') else ''}
</div>
{table}
<div style="margin-top:.8rem">
  <button class="btn danger" data-act="boss-dismiss">🌫 Развеять босса</button>
</div>"""

    cards = ""
    for key in WB.ORDER:
        b = WB.BOSSES[key]
        cards += f"""
<div class="cata-card">
  <div class="ct">{b['icon']} {esc(b['name'])}</div>
  <div class="cd">{esc(b['story'])}<br>❤️ {b['hp']} · ⚔️ ур. {b['level']}+
     · ⏳ ~{b['hours']} ч</div>
  <button class="btn sm primary" data-act="boss-summon" data-arg="{key}"
     {'disabled' if ev is not None else ''}>🏰 Призвать</button>
</div>"""

    log = WB.history(ctx.store, 8)
    rows = ""
    for e in log:
        when = time.strftime("%d.%m %H:%M", time.localtime(e.get("ts", 0)))
        outcome = "🏆 повержен" if e.get("won") else "🌫 ушёл"
        rows += (f"<tr><td class='muted'>{when}</td>"
                 f"<td>{esc(WB.title(e.get('key', '')))}</td>"
                 f"<td>{outcome}</td><td>{e.get('heroes', 0)} героев</td></tr>")
    story = (f"<h3>Летопись сражений</h3><div class='scroll'><table><tbody>"
             f"{rows}</tbody></table></div>") if rows else ""

    return f"""
<div class="card">
  <h2>🏰 Мировой босс</h2>
  <div class="hint">Босс — событие, а не клетка: живёт по таймеру, держит
     общий счётчик урона и раздаёт награду по вкладу. Бить может каждый,
     кто дошёл и дорос уровнем. На половине здоровья призывает свиту.
     Один босс на мир.</div>
  {body}
  <h3 style="margin-top:1rem">Кого призвать</h3>
  <div class="cata-grid">{cards}</div>
  {story}
</div>
"""


def _arsenal(ctx):
    cards = ""
    for key in C.ORDER:
        k = C.KINDS[key]
        cards += f"""
<div class="cata-card">
  <div class="ct">{k['icon']} {esc(k['name'])}</div>
  <div class="cd">{esc(k['story'])}<br>⏳ ~{k['hours']} ч · охват {int(k['spread'] * 100)}%
     · 👾×{k['mob_rate']:.2f} · 📦×{k['loot']:.2f}<br>
     ⚡ засада {int(k['ambush'] * 100)}% · ➕ подмога {int(k['join'] * 100)}%</div>
  <button class="btn sm primary" data-act="cata-form" data-arg="{key}">🌋 Наслать</button>
</div>"""
    return f"""
<div class="card">
  <h2>🌋 Арсенал бедствий ({len(C.ORDER)})</h2>
  <p class="muted" style="margin-bottom:.7rem">Выбери бедствие, укажи локацию
     (или весь мир) и срок — игроки получат весть в боте.</p>
  <div class="cata-grid">{cards}</div>
</div>
"""


def _settings(ctx):
    s = ctx.store.settings
    auto = bool(s.get("cataclysm_auto", True))
    notify = bool(s.get("cataclysm_notify", True))
    return f"""
<div class="card">
  <h2>⚙️ Стихийные бедствия сами по себе</h2>
  <p class="muted">Шанс проверяется на каждом шаге игрока по миру. Сид череды
     бед — <b>🌋 Катаклизмы</b> во вкладке «Локации».</p>
  <div class="row" style="margin-top:.6rem">
    <div><label>Автокатаклизмы</label><select id="cataAuto">
      <option value="1" {'selected' if auto else ''}>включены</option>
      <option value="0" {'selected' if not auto else ''}>выключены</option></select></div>
    <div><label>Шанс на шаг (0–1)</label>
      <input id="cataChance" value="{s.get('cataclysm_chance', 0.02)}"></div>
    <div><label>Максимум разом</label>
      <input id="cataLimit" type="number" min="1" max="8" value="{s.get('cataclysm_limit', 2)}"></div>
    <div><label>Вести игрокам</label><select id="cataNotify">
      <option value="1" {'selected' if notify else ''}>рассылать</option>
      <option value="0" {'selected' if not notify else ''}>молча</option></select></div>
    <div style="flex:0 0 auto"><label>&nbsp;</label>
      <button class="btn primary" data-act="cata-settings">💾 Сохранить</button></div>
  </div>
</div>
"""


def _history(ctx):
    log = C.history(ctx.store, 20)
    if not log:
        rows = "<tr><td colspan='4' class='muted'>Летопись пуста.</td></tr>"
    else:
        rows = ""
        for e in log:
            when = time.strftime("%d.%m %H:%M", time.localtime(e.get("ts", 0)))
            rows += (f"<tr><td class='muted' style='white-space:nowrap'>{when}</td>"
                     f"<td>{esc(C.title(e.get('kind', '')))}</td>"
                     f"<td>{esc(C.place(e.get('loc', -1)))}</td>"
                     f"<td>{esc(e.get('what', ''))} · {e.get('cells', 0)} кл.</td></tr>")
    return f"""
<div class="card">
  <h2>📜 Летопись бедствий</h2>
  <div class="scroll"><table>
    <thead><tr><th>Когда</th><th>Что</th><th>Где</th><th>Итог</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</div>
"""


def _timer_script():
    return """
<script>
(function(){
  function tick(){
    document.querySelectorAll('.cata-timer[data-until]').forEach(function(el){
      var left = parseInt(el.dataset.until, 10) - Math.floor(Date.now() / 1000);
      if (left <= 0) { el.textContent = '🕊 стихает'; return; }
      var h = Math.floor(left / 3600), m = Math.floor((left % 3600) / 60), s = left % 60;
      el.textContent = '⏳ ' + (h ? h + 'ч ' : '') + m + 'м ' + s + 'с';
    });
    setTimeout(tick, 1000);
  }
  tick();
})();
</script>
"""
