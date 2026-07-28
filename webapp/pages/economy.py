"""Страница: экономика — уникальные предметы, крафт и аукцион.

Здесь видно всё, что добавило обновление 8: реестр именных экземпляров с
их ID и происхождением, летопись каждой вещи, рецепты крафта и живые
лоты аукциона.
"""
from engine import auction, craft, data, items, itemui
from webapp.html import esc

TITLE = "💰 Экономика"
CRUMBS = [("Экономика", "economy")]

TABS = [("instances", "🆔 Экземпляры"), ("auction", "🏛 Аукцион"),
        ("craft", "🔨 Крафт"), ("sources", "🏷 Значки")]


def render(ctx):
    tab = ctx.state.setdefault("eco_tab", "instances")
    buttons = "".join(
        f"<button class='btn {'primary' if tab == key else ''}' "
        f"data-act='eco-tab' data-arg='{key}'>{label}</button> "
        for key, label in TABS)
    body = {"instances": _instances, "auction": _auction,
            "craft": _craft, "sources": _sources}[tab](ctx)
    return f"""
<div class="card">
  <h2>💰 Экономика мира</h2>
  <p class="muted">Уникальные экземпляры предметов, аукцион между игроками и
     крафт у ремесленников. Каждая вещь имеет свой ID, статы и летопись.</p>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.6rem">{buttons}</div>
</div>
{body}
"""


def _tiles(pairs):
    return "".join(f"<div class='stat'><div class='v'>{v}</div>"
                   f"<div class='l'>{esc(k)}</div></div>" for k, v in pairs)


# ── экземпляры ──────────────────────────────────────────────

INST_PER_PAGE = 15


def _instances(ctx):
    st = items.stats(ctx.store)
    grid = _tiles([("Всего вещей", st["total"]), ("🌟 Реликвий", st["unique"]),
                   ("🔁 Торговались", st["traded"]), ("⚡ Заточено", st["upgraded"]),
                   ("У игроков", st["owned"]), ("🎄 Праздничных", st["festive"])])

    page = max(1, ctx.state.get("instances_page", 1))
    all_inst = items.all_instances(ctx.store)
    total = len(all_inst)
    pages = max(1, (total + INST_PER_PAGE - 1) // INST_PER_PAGE)
    page = min(page, pages)
    ctx.state["instances_page"] = page
    start = (page - 1) * INST_PER_PAGE
    slice_inst = all_inst[start:start + INST_PER_PAGE]

    rows = ""
    for inst in slice_inst:
        owner = ctx.store.players.get(int(inst.get("owner") or 0))
        who = esc(owner.name) if owner else "<span class='muted'>ничей</span>"
        rar = inst.get("rarity", "common")
        dot, rare_name = itemui.RARITY.get(rar, ("⚪", rar))
        rows += (
            f"<tr class='clickable' data-act='inst-view' data-arg='{esc(inst['uid'])}'>"
            f"<td><code>{items.badge(inst)}{esc(inst['uid'])}</code></td>"
            f"<td>{esc(inst.get('icon',''))} <b>{esc(items.title(inst))}</b></td>"
            f"<td><span class='tag {esc(rar)}'>{dot} {esc(rare_name)}</span></td>"
            f"<td>{inst.get('quality', 100)} %</td>"
            f"<td class='muted'>{esc(items.source_label(inst))}</td>"
            f"<td>{who}</td><td>{items.price(inst)} 🪙</td>"
            f"<td><button class='btn'>📖</button></td></tr>")
    if not rows:
        rows = ("<tr><td colspan='8'><div class='empty-state'>"
                "<div class='empty-icon'>🆔</div>"
                "<div>Пока ни одной именной вещи.</div>"
                "<span class='muted'>Они появляются, когда игрок выбивает предмет из моба, "
                "открывает сундук или кует вещь в мастерской.</span>"
                "<button class='btn primary' data-act='nav' data-arg='bot'>🤖 Запустить бота</button>"
                "</div></td></tr>")

    pagination = ""
    if pages > 1:
        pagination = '<div class="pagination">'
        if page > 1:
            pagination += f"<button data-act='instances-page' data-arg='{page - 1}'>←</button>"
        else:
            pagination += "<span>←</span>"
        for p in range(1, pages + 1):
            if p == page:
                pagination += f"<span class='current'>{p}</span>"
            elif p == 1 or p == pages or abs(p - page) <= 2:
                pagination += f"<button data-act='instances-page' data-arg='{p}'>{p}</button>"
            elif abs(p - page) == 3:
                pagination += "<span>...</span>"
        if page < pages:
            pagination += f"<button data-act='instances-page' data-arg='{page + 1}'>→</button>"
        else:
            pagination += "<span>→</span>"
        pagination += "</div>"

    return f"""
<div class="card"><h2>🆔 Реестр экземпляров</h2><div class="grid g4">{grid}</div></div>
<div class="card">
  <h2>📦 Именные вещи <span class="muted">({start + 1}–{min(start + INST_PER_PAGE, total)} из {total})</span></h2>
  <p class="muted">Клик по строке — летопись вещи: кто добыл, у кого побывал,
     за сколько ушла.</p>
  <div class="scroll"><table>
    <tr><th>ID</th><th>Предмет</th><th>Редкость</th><th>Качество</th>
        <th>Происхождение</th><th>Владелец</th><th>Оценка</th><th></th></tr>
    {rows}
  </table></div>
  {pagination}
</div>
"""


def instance_form(ctx, uid):
    """Карточка экземпляра с полной летописью."""
    inst = items.get(ctx.store, uid)
    if not inst:
        return "<p>Экземпляр не найден.</p>"
    owner = ctx.store.players.get(int(inst.get("owner") or 0))
    rar = inst.get("rarity", "common")
    dot, rare_name = itemui.RARITY.get(rar, ("⚪", rar))

    stats = "".join(
        f"<span class='chip'>{itemui.BONUS.get(k, ('•', k))[0]} "
        f"{esc(itemui.BONUS.get(k, ('•', k))[1])} +{v}</span>"
        for k, v in (inst.get("stats") or {}).items()
    ) or "<span class='muted'>без бонусов</span>"

    log = items.history(inst)
    story = "".join(f"<div class='logline'>{esc(line)}</div>"
                    for line in reversed(log)) or \
        "<div class='muted'>Летопись пуста.</div>"

    return f"""
<h2>{esc(inst.get('icon',''))} {esc(items.title(inst))}</h2>
<p class="muted"><code>{items.badge(inst)}{esc(inst['uid'])}</code> ·
   <span class="tag {esc(rar)}">{dot} {esc(rare_name)}</span> ·
   качество {inst.get('quality', 100)} % · оценка {items.price(inst)} 🪙</p>
<div class="row" style="margin-top:.6rem">
  <div><label>Происхождение</label><div>{items.badge(inst)} {esc(items.source_label(inst))}</div></div>
  <div><label>Владелец</label><div>{esc(owner.name) if owner else '—'}</div></div>
  <div><label>Сделок</label><div>{inst.get('trades', 0)}</div></div>
  <div><label>Заточка</label><div>+{inst.get('upgrade', 0)}</div></div>
</div>
<h3>Статы экземпляра</h3><div>{stats}</div>
<h3>📖 Летопись</h3>
<div class="story">{story}</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn danger" data-act="inst-del" data-arg="{esc(inst['uid'])}">🗑 Удалить вещь</button>
  <button class="btn" data-act="modal-close">Закрыть</button>
</div>
"""


# ── аукцион ─────────────────────────────────────────────────

def _auction(ctx):
    st = auction.stats(ctx.store)
    grid = _tiles([("Активных лотов", st["active"]), ("Продано", st["sold"]),
                   ("Оборот", f"{st['turnover']} 🪙"), ("Всего лотов", st["total"])])

    rows = ""
    for lot in auction.active(ctx.store):
        inst = items.get(ctx.store, lot["uid"])
        name = f"{esc(inst['icon'])} {esc(items.title(inst))}" if inst else "—"
        tag = f"<code>{items.badge(inst)}{esc(inst['uid'])}</code>" if inst else "—"
        rows += (f"<tr><td>{tag}</td><td>{name}</td>"
                 f"<td>{esc(lot.get('seller_name', '—'))}</td>"
                 f"<td><b>{lot.get('price', 0)}</b> 🪙</td>"
                 f"<td class='muted'>{esc(items.stamp(lot.get('ts', 0)))}</td>"
                 f"<td><button class='btn danger' data-act='lot-del' "
                 f"data-arg='{esc(str(lot.get('id')))}'>🗑</button></td></tr>")
    if not rows:
        rows = ("<tr><td colspan='6' class='muted'>Витрина пуста. Игроки "
                "выставляют вещи через «🏛 Аукцион» в боте.</td></tr>")

    return f"""
<div class="card"><h2>🏛 Торги</h2><div class="grid g4">{grid}</div></div>
<div class="card">
  <h2>🧾 Активные лоты</h2>
  <p class="muted">Комиссия аукциона — {int(auction.COMMISSION * 100)} %.
     Непроданный за сутки лот возвращается владельцу.
     Скупщик «{esc(auction.NPC_NAME)}» берёт вещь сразу
     за {int(auction.NPC_BUY * 100)} % оценки.</p>
  <div class="scroll"><table>
    <tr><th>ID вещи</th><th>Предмет</th><th>Продавец</th><th>Цена</th>
        <th>Выставлен</th><th></th></tr>
    {rows}
  </table></div>
</div>
"""


# ── крафт ───────────────────────────────────────────────────

def _craft(ctx):
    mats = "".join(
        f"<tr><td>{esc(icon)} <b>{esc(name)}</b></td>"
        f"<td><span class='tag {esc(rar)}'>{esc(rar)}</span></td>"
        f"<td>{price} 🪙</td></tr>"
        for name, icon, rar, price in data.MATERIALS)

    recipes = ""
    for i, (name, icon, station, idx, need, price, lvl) in enumerate(data.RECIPES):
        sicon, sname = data.STATIONS.get(station, ("🔨", station))
        parts = " + ".join(
            f"{esc(craft.material(m)[1])} {esc(craft.material(m)[0])} ×{c}"
            for m, c in need.items())
        recipes += (f"<tr><td>{esc(icon)} <b>{esc(name)}</b></td>"
                    f"<td><span class='tag'>{esc(sicon)} {esc(sname)}</span></td>"
                    f"<td class='muted'>{parts}</td>"
                    f"<td>{price} 🪙</td><td>ур. {lvl}</td></tr>")

    ups = "".join(
        f"<tr><td>+{n} → +{n + 1}</td><td>{int(chance * 100)} %</td>"
        f"<td>×{mult} от базы</td></tr>"
        for n, (chance, mult) in enumerate(data.UPGRADE_ODDS))

    return f"""
<div class="card">
  <h2>🔨 Рецепты <span class="muted">({len(data.RECIPES)})</span></h2>
  <p class="muted">Из рецепта выходит именной экземпляр со значком 🔨 и своей
     летописью. Материалы падают с мобов.</p>
  <div class="scroll"><table>
    <tr><th>Что куём</th><th>Станок</th><th>Материалы</th><th>Плата</th><th>Уровень</th></tr>
    {recipes}
  </table></div>
</div>
<div class="card">
  <h2>🔩 Материалы <span class="muted">({len(data.MATERIALS)})</span></h2>
  <div class="scroll"><table>
    <tr><th>Материал</th><th>Редкость</th><th>Цена</th></tr>{mats}
  </table></div>
</div>
<div class="card">
  <h2>⚡ Заточка</h2>
  <p class="muted">Неудача не ломает вещь — теряется только плата.
     Максимум +{data.MAX_UPGRADE}. Каждый успех даёт +10 % к статам.</p>
  <div class="scroll"><table>
    <tr><th>Ступень</th><th>Шанс</th><th>Цена</th></tr>{ups}
  </table></div>
</div>
"""


# ── значки ──────────────────────────────────────────────────

def _sources(ctx):
    rows = "".join(
        f"<tr><td style='font-size:1.3rem'>{icon}</td><td><b>{esc(label)}</b></td>"
        f"<td class='muted'><code>{icon}IT-XXXXXXXX</code></td></tr>"
        for _key, (icon, label) in data.SOURCES.items())
    ev = "".join(
        f"<tr><td style='font-size:1.1rem'>{icon}</td><td>{esc(label)}</td></tr>"
        for _k, (icon, label) in data.EVENTS.items())
    schools = "".join(
        f"<tr><td style='font-size:1.3rem'>{icon}</td><td><b>{esc(name)}</b></td>"
        f"<td class='muted'>{esc(desc)}</td></tr>"
        for _k, (icon, name, desc) in data.MAGIC_SCHOOLS.items())
    grades = "".join(
        f"<tr><td>{mark}</td><td><b>{esc(title)}</b></td><td>×{mult}</td></tr>"
        for _k, (title, mult, mark) in data.AFFINITY_GRADES.items())

    return f"""
<div class="card">
  <h2>🏷 Значки происхождения</h2>
  <p class="muted">Значок печатается перед ID предмета, поэтому происхождение
     вещи видно с одного взгляда. Особые метки важнее исходного источника:
     реликвия всегда 🌟, праздничная вещь — 🎄, торгованная — 🔁.</p>
  <div class="scroll"><table>
    <tr><th>Значок</th><th>Откуда</th><th>Как выглядит</th></tr>{rows}
  </table></div>
</div>
<div class="card">
  <h2>📖 События летописи</h2>
  <div class="scroll"><table><tr><th></th><th>Событие</th></tr>{ev}</table></div>
</div>
<div class="card">
  <h2>✨ Школы магии</h2>
  <p class="muted">У героя от нуля до двух предрасположенностей. Дар умножает
     эффект магических умений.</p>
  <div class="scroll"><table>
    <tr><th></th><th>Школа</th><th>Описание</th></tr>{schools}
  </table></div>
</div>
<div class="card">
  <h2>🎖 Ступени дара</h2>
  <div class="scroll"><table>
    <tr><th>Знак</th><th>Ступень</th><th>Множитель</th></tr>{grades}
  </table></div>
</div>
"""
