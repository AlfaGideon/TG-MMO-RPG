"""Вкладка «Катаклизмы»: что бушует сейчас, чем ударить, летопись бедствий."""
import time

from engine import cataclysm as C
from engine import data
from webapp.html import esc


def render(ctx):
    return f"""
{_live(ctx)}
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
                f"📦×{k.get('loot', 1):.2f} · 🪙×{k.get('gold', 1):.2f} · 🏕×{k.get('rest', 1):.2f}</td>"
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
  <div class="hint">Клетки правятся со слепком: когда бедствие стихает, тайлы,
     проходимость, твари и сундуки возвращаются как были. Клетки под игроками,
     спавн и швы-переходы не трогаются.</div>
  {body}
</div>
{_timer_script()}
"""


def _arsenal(ctx):
    cards = ""
    for key in C.ORDER:
        k = C.KINDS[key]
        cards += f"""
<div class="cata-card">
  <div class="ct">{k['icon']} {esc(k['name'])}</div>
  <div class="cd">{esc(k['story'])}<br>⏳ ~{k['hours']} ч · охват {int(k['spread'] * 100)}%
     · 👾×{k['mob_rate']:.2f} · 📦×{k['loot']:.2f}</div>
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
