"""Вкладка «Валюты»: разряды монет, кошельки игроков и премиум.

Отдельным модулем, а не внутри `economy.py`: та страница уже у предела
длины, а деньги — самостоятельный раздел с собственными настройками.
"""
from engine import money
from webapp.html import esc

PER_PAGE = 15


def render(ctx):
    return f"{_summary(ctx)}{_settings(ctx)}{_wallets(ctx)}"


def _tiles(pairs):
    return "".join(f"<div class='stat'><div class='v'>{v}</div>"
                   f"<div class='l'>{esc(k)}</div></div>" for k, v in pairs)


def _summary(ctx):
    players = [p for p in ctx.store.players.values() if p.created_char]
    coins = sum(money.balance(p) for p in players)
    gems = sum(money.premium(p) for p in players)
    richest = max(players, key=money.balance, default=None)
    avg = coins // len(players) if players else 0

    rows = "".join(
        f"<tr><td>{icon}</td><td><b>{esc(name.capitalize())}</b></td>"
        f"<td class='muted'>{nominal} 🥉</td>"
        f"<td>{sum(1 for p in players if money.balance(p) >= nominal)}</td></tr>"
        for nominal, icon, name in money.COINS)

    return f"""
<div class="card">
  <h2>🪙 Деньги мира</h2>
  <p class="muted">Кошелёк героя хранится в бронзе, а разряды считаются на лету:
     {esc(money.coin_line())}. Премиум-валюта
     «{esc(money.PREMIUM_NAME)}» {money.PREMIUM_ICON} живёт отдельным счётчиком и
     не смешивается с монетами.</p>
  <div class="grid g4">{_tiles([
      ("Монет в мире", money.fmt(coins)),
      ("В среднем", money.fmt(avg)),
      (f"{money.PREMIUM_ICON} Кристаллов", gems),
      ("Богатейший", esc(richest.name) if richest else "—"),
  ])}</div>
  <div class="scroll" style="margin-top:.9rem"><table>
    <tr><th></th><th>Разряд</th><th>Номинал</th><th>Кому по карману</th></tr>
    {rows}
  </table></div>
</div>
"""


def _settings(ctx):
    fields = ""
    for key, (default, label, about) in money.TUNABLES.items():
        val = money.tune(ctx.store, key)
        own = "своё значение" if ctx.store.settings.get(key) not in (None, "") else "по умолчанию"
        fields += (f"<div><label>{label} <span class='muted'>· {own}</span></label>"
                   f"<input id='money_{key}' type='number' min='0' value='{val}'>"
                   f"<div class='muted' style='font-size:.7rem;margin-top:.15rem'>"
                   f"{esc(about)} · умолчание {default}</div></div>")
    rate = money.tune(ctx.store, "premium_rate")
    return f"""
<div class="card">
  <h2>{money.PREMIUM_ICON} Премиум-валюта</h2>
  <div class="hint">Кристаллы выдаются только админом или за донат: их нельзя
     выбить из моба, найти в сундуке или потерять в могиле. Обмен работает в
     одну сторону — {money.PREMIUM_ICON} → монеты, сейчас
     1{money.PREMIUM_ICON} = {money.fmt(rate)}. Обратный обмен не
     предусмотрен намеренно: иначе донат стал бы способом вывода.</div>
  <div class="row" style="margin-top:.7rem">{fields}</div>
  <div style="margin-top:.9rem">
    <button class="btn primary" data-act="money-save">💾 Сохранить настройки валют</button>
  </div>
</div>
"""


def _wallets(ctx):
    players = sorted((p for p in ctx.store.players.values() if p.created_char),
                     key=money.balance, reverse=True)
    page = max(1, int(ctx.state.get("money_page", 1)))
    pages = max(1, (len(players) + PER_PAGE - 1) // PER_PAGE)
    page = min(page, pages)
    ctx.state["money_page"] = page
    chunk = players[(page - 1) * PER_PAGE:(page - 1) * PER_PAGE + PER_PAGE]

    rows = ""
    for p in chunk:
        g, s, b = money.split(money.balance(p))
        rows += (
            f"<tr><td data-label='Герой'><b>{esc(p.name)}</b> "
            f"<span class='muted'>ур.{p.level}</span></td>"
            f"<td data-label='Кошелёк'>{money.fmt(money.balance(p))}</td>"
            f"<td data-label='{money.GOLD_ICON}'>{g}</td>"
            f"<td data-label='{money.SILVER_ICON}'>{s}</td>"
            f"<td data-label='{money.BRONZE_ICON}'>{b}</td>"
            f"<td data-label='Премиум'>{money.premium(p)}{money.PREMIUM_ICON}</td>"
            f"<td data-label='Выдать'>"
            f"<button class='btn sm' data-act='money-gem' data-arg='{p.tg_id}:10' "
            f"title='Выдать 10 кристаллов'>+10{money.PREMIUM_ICON}</button> "
            f"<button class='btn sm' data-act='money-gem' data-arg='{p.tg_id}:-10' "
            f"title='Списать 10 кристаллов'>−10{money.PREMIUM_ICON}</button>"
            f"</td></tr>")
    if not rows:
        rows = ("<tr><td colspan='7'><div class='empty-state'>"
                "<div class='empty-icon'>👛</div>"
                "<div>Кошельков пока нет — герои ещё не созданы.</div>"
                "</div></td></tr>")

    pagination = ""
    if pages > 1:
        pagination = '<div class="pagination">'
        for n in range(1, pages + 1):
            pagination += (f"<span class='current'>{n}</span>" if n == page else
                           f"<button data-act='money-page' data-arg='{n}'>{n}</button>")
        pagination += "</div>"

    return f"""
<div class="card">
  <h2>👛 Кошельки героев <span class="muted">({len(players)})</span></h2>
  <p class="muted">Монеты правятся на вкладке «Игроки» — там поле указано в
     бронзе. Здесь видно, как та же сумма выглядит разрядами, и выдаются
     кристаллы.</p>
  <div class="scroll"><table>
    <tr><th>Герой</th><th>Кошелёк</th><th>{money.GOLD_ICON}</th>
        <th>{money.SILVER_ICON}</th><th>{money.BRONZE_ICON}</th>
        <th>{money.PREMIUM_ICON}</th><th>Выдать</th></tr>
    {rows}
  </table></div>
  {pagination}
</div>
"""
