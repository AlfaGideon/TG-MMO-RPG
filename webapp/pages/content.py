"""Страница: контент игры — мобы, предметы, NPC, классы. Всё редактируемо."""
from engine import data, rules
from webapp.html import esc

TITLE = "📦 Контент"
CRUMBS = [("Контент", "content")]

TABS = [("mobs", "👾 Мобы"), ("items", "⚔️ Предметы"),
        ("npcs", "🎭 NPC"), ("classes", "🧙 Классы")]


def render(ctx):
    tab = ctx.state.setdefault("content_tab", "mobs")
    buttons = "".join(
        f"<button class='btn {'primary' if tab == key else ''}' "
        f"data-act='content-tab' data-arg='{key}'>{label}</button> "
        for key, label in TABS)

    body = {"mobs": _mobs, "items": _items,
            "npcs": _npcs, "classes": _classes}[tab](ctx)

    return f"""
<div class="card">
  <h2>📦 Контент игры</h2>
  <p class="muted">Клик по строке — редактировать. Изменения сразу видны боту и игрокам.</p>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.6rem">{buttons}</div>
</div>
{body}
"""


def _row(attrs, cols, labels=None, actions="<button class='btn'>✏️</button>"):
    """attrs — готовая строка data-act/data-arg, cols — ячейки."""
    labels = labels or []
    tds = ""
    for i, c in enumerate(cols):
        label = labels[i] if i < len(labels) else ""
        tds += f"<td data-label='{esc(label)}'>{c}</td>"
    return (f"<tr class='clickable' {attrs}>{tds}"
            f"<td data-label='' style='white-space:nowrap'>{actions}</td></tr>")


def _mobs(ctx):
    labels = ["Имя", "Описание", "Ур.", "HP", "Урон", "Защита", "Золото", "Опыт", "Локация"]
    rows = "".join(_row(f"data-act='mob-edit' data-arg='{i}'", [
        f"<b>{esc(m[0])}</b>", f"<span class='muted'>{esc(m[1])}</span>", m[2],
        m[3], m[4], m[5], f"{m[6]} 🪙", f"{m[7]} ⭐",
        esc(data.LOCATIONS[m[8]][0])], labels,
        actions=(f"<button class='btn'>✏️</button> "
                 f"<button class='btn' data-act='mob-drops' data-arg='{i}' title='Что выпадает'>🎁</button> "
                 f"<button class='btn' data-act='mob-clone' data-arg='{i}' title='Клонировать'>📋</button>"))
        for i, m in enumerate(data.MOBS))
    return f"""
<div class="card">
  <h2>👾 Мобы <span class="muted">({len(data.MOBS)})</span>
    <button class="btn primary" style="float:right" data-act="mob-new">➕ Добавить</button></h2>
  <div class="scroll"><table>
    <tr><th>Имя</th><th>Описание</th><th>Ур.</th><th>HP</th><th>Урон</th>
        <th>Защита</th><th>Золото</th><th>Опыт</th><th>Локация</th><th></th></tr>{rows}
  </table></div>
</div>
"""


def _items(ctx):
    labels = ["Предмет", "Тип", "Редкость", "Цена", "Бонусы"]
    rows = ""
    for i in range(len(data.ITEMS)):
        it = rules.item(i)
        bon = ", ".join(f"{k}+{v}" for k, v in it["bonus"].items()) or "—"
        price_form = (f"<form class='inline-form' data-act='item-inline' data-arg='{i}:price' onsubmit='return false'>"
                      f"<input type='number' class='inline-num' value='{it['price']}' min='0' max='999999'></form>")
        rows += _row(f"data-act='item-edit' data-arg='{i}'", [
            f"{it['icon']} <b>{esc(it['name'])}</b>",
            f"<span class='tag'>{it['type']}</span>",
            f"<span class='tag {it['rarity']}'>{it['rarity']}</span>",
            price_form, f"<span class='muted'>{esc(bon)}</span>"], labels,
            actions=f"<button class='btn'>✏️</button> <button class='btn' data-act='item-clone' data-arg='{i}' title='Клонировать'>📋</button>")
    return f"""
<div class="card">
  <h2>⚔️ Предметы <span class="muted">({len(data.ITEMS)})</span>
    <button class="btn primary" style="float:right" data-act="item-new">➕ Добавить</button></h2>
  <div class="scroll"><table>
    <tr><th>Предмет</th><th>Тип</th><th>Редкость</th><th>Цена</th><th>Бонусы</th><th></th></tr>{rows}
  </table></div>
</div>
"""


def _npcs(ctx):
    labels = ["Имя", "Роль", "Реплика"]
    rows = "".join(_row(f"data-act='npc-edit' data-arg='{i}'", [
        f"<b>{esc(n[0])}</b>", f"<span class='tag'>{n[2]}</span>",
        f"<span class='muted'>{esc(n[1])}</span>"], labels,
        actions=f"<button class='btn'>✏️</button> <button class='btn' data-act='npc-clone' data-arg='{i}' title='Клонировать'>📋</button>")
        for i, n in enumerate(data.NPCS))
    return f"""
<div class="card">
  <h2>🎭 NPC <span class="muted">({len(data.NPCS)})</span>
    <button class="btn primary" style="float:right" data-act="npc-new">➕ Добавить</button></h2>
  <div class="scroll"><table>
    <tr><th>Имя</th><th>Роль</th><th>Реплика</th><th></th></tr>{rows}
  </table></div>
</div>
"""


def _classes(ctx):
    labels = ["Класс", "Описание", "Стартовые статы"]
    rows = ""
    for key, (title, desc, st) in data.CLASSES.items():
        stats = " · ".join(f"{k} {v}" for k, v in st.items())
        rows += _row(f"data-act='class-edit' data-arg='{key}'", [
            f"<b>{esc(title)}</b>", f"<span class='muted'>{esc(desc)}</span>",
            f"<span class='muted'>{esc(stats)}</span>"], labels,
            actions=f"<button class='btn'>✏️</button> <button class='btn' data-act='class-clone' data-arg='{key}' title='Клонировать'>📋</button>")
    return f"""
<div class="card">
  <h2>🧙 Классы <span class="muted">({len(data.CLASSES)})</span></h2>
  <div class="scroll"><table>
    <tr><th>Класс</th><th>Описание</th><th>Стартовые статы</th><th></th></tr>{rows}
  </table></div>
</div>
"""


# ── формы ───────────────────────────────────────────────────

def _num(fid, label, val):
    return f"<div><label>{esc(label)}</label><input id='{fid}' type='number' value='{val}'></div>"


def mob_form(ctx, idx):
    new = idx is None
    m = data.MOBS[idx] if not new else ("", "", 1, 30, 5, 2, 10, 15, 0)
    locs = "".join(
        f"<option value='{i}' {'selected' if i == m[8] else ''}>{esc(l[0])}</option>"
        for i, l in enumerate(data.LOCATIONS))
    arg = "new" if new else idx
    return f"""
<h2>{'➕ Новый моб' if new else '👾 ' + esc(m[0])}</h2>
<form data-validate data-autosave>
<div style="margin-top:.6rem"><label>Имя</label><input id="mf_name" value="{esc(m[0])}" required></div>
<div style="margin-top:.5rem"><label>Описание</label><textarea id="mf_desc" rows="2">{esc(m[1])}</textarea></div>
<div style="margin-top:.5rem"><label>Изображение</label><input type="file" accept="image/*" data-preview="#mfPreview"><br><img id="mfPreview" style="max-width:120px;max-height:120px;margin-top:.5rem;border-radius:6px"></div>
<div class="row" style="margin-top:.5rem">
  {_num('mf_level', 'Уровень', m[2])}{_num('mf_hp', 'HP', m[3])}
  {_num('mf_dmg', 'Урон', m[4])}{_num('mf_def', 'Защита', m[5])}
</div>
<div class="row" style="margin-top:.5rem">
  {_num('mf_gold', 'Золото', m[6])}{_num('mf_exp', 'Опыт', m[7])}
  <div><label>Локация</label><select id="mf_loc">{locs}</select></div>
</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="mob-save" data-arg="{arg}">💾 Сохранить</button>
  {"" if new else f'<button class="btn danger" data-act="mob-del" data-arg="{idx}">🗑 Удалить</button>'}
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
</form>
"""


def item_form(ctx, idx):
    new = idx is None
    it = data.ITEMS[idx] if not new else ("", "weapon", "common", 10, "⚔️", {})
    types = ["weapon", "armor", "helmet", "boots", "accessory", "consumable"]
    rarities = ["common", "uncommon", "rare", "epic", "legendary"]
    topts = "".join(f"<option {'selected' if t == it[1] else ''}>{t}</option>" for t in types)
    ropts = "".join(f"<option {'selected' if r == it[2] else ''}>{r}</option>" for r in rarities)
    bon = ", ".join(f"{k}={v}" for k, v in it[5].items())
    arg = "new" if new else idx
    return f"""
<h2>{'➕ Новый предмет' if new else it[4] + ' ' + esc(it[0])}</h2>
<form data-validate data-autosave id="itemForm">
<div class="row" style="margin-top:.6rem">
  <div><label>Название</label><input id="if_name" value="{esc(it[0])}"></div>
  <div style="flex:0 0 90px"><label>Иконка</label><input id="if_icon" value="{esc(it[4])}"></div>
</div>
<div style="margin-top:.5rem"><label>Изображение</label><input type="file" accept="image/*" data-preview="#ifPreview"><br><img id="ifPreview" style="max-width:120px;max-height:120px;margin-top:.5rem;border-radius:6px"></div>
<div class="row" style="margin-top:.5rem">
  <div><label>Тип</label><select id="if_type">{topts}</select></div>
  <div><label>Редкость</label><select id="if_rarity">{ropts}</select></div>
  {_num('if_price', 'Цена', it[3])}
</div>
<div style="margin-top:.5rem">
  <label>Бонусы (через запятую: damage=5, hp=10)</label>
  <input id="if_bonus" value="{esc(bon)}">
</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="item-save" data-arg="{arg}">💾 Сохранить</button>
  {"" if new else f'<button class="btn danger" data-act="item-del" data-arg="{idx}">🗑 Удалить</button>'}
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
</form>
"""


def npc_form(ctx, idx):
    new = idx is None
    n = data.NPCS[idx] if not new else ("", "", "storyteller")
    kinds = ["storyteller", "merchant", "healer"]
    kopts = "".join(f"<option {'selected' if k == n[2] else ''}>{k}</option>" for k in kinds)
    arg = "new" if new else idx
    return f"""
<h2>{'➕ Новый NPC' if new else '🎭 ' + esc(n[0])}</h2>
<form data-validate data-autosave>
<div style="margin-top:.6rem"><label>Имя</label><input id="nf_name" value="{esc(n[0])}" required></div>
<div style="margin-top:.5rem"><label>Изображение</label><input type="file" accept="image/*" data-preview="#nfPreview"><br><img id="nfPreview" style="max-width:120px;max-height:120px;margin-top:.5rem;border-radius:6px"></div>
<div style="margin-top:.5rem"><label>Реплика</label><textarea id="nf_text" rows="3">{esc(n[1])}</textarea></div>
<div class="row" style="margin-top:.5rem">
  <div><label>Роль</label><select id="nf_kind">{kopts}</select></div>
</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="npc-save" data-arg="{arg}">💾 Сохранить</button>
  {"" if new else f'<button class="btn danger" data-act="npc-del" data-arg="{idx}">🗑 Удалить</button>'}
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
</form>
"""


def mob_drops_form(ctx, idx):
    from engine import rules
    m = data.MOBS[idx]
    level = m[2]
    rows = ""
    candidates = []
    for i, it in enumerate(data.ITEMS):
        itd = rules.item(i)
        rarity_score = {"common": 1, "uncommon": 2, "rare": 3, "epic": 4, "legendary": 5}.get(itd["rarity"], 1)
        price_score = itd["price"] // 20
        candidates.append((i, itd, rarity_score + price_score))
    candidates.sort(key=lambda x: x[2], reverse=True)
    for i, itd, _ in candidates[:6]:
        chance = max(5, min(60, 50 - i * 5 + level * 2))
        rows += (f"<div class='drop-preview-row'><span class='drop-name'>{itd['icon']} {esc(itd['name'])}</span>"
                 f"<span class='drop-chance'>{chance}%</span></div>")
    if not rows:
        rows = "<div class='muted'>Нет подходящих предметов.</div>"
    return f"""
<h2>🎁 Что выпадает с «{esc(m[0])}»</h2>
<p class="muted">Уровень моба: {level} · локация: {esc(data.LOCATIONS[m[8]][0])}</p>
<div class="drop-preview-list">{rows}</div>
<div style="margin-top:1rem"><button class="btn" data-act="modal-close">Закрыть</button></div>
"""


def class_form(ctx, key):
    title, desc, st = data.CLASSES[key]
    fields = "".join(_num(f"cf_{k}", k, v) for k, v in st.items())
    return f"""
<h2>🧙 {esc(title)}</h2>
<form data-validate data-autosave>
<div style="margin-top:.6rem"><label>Название</label><input id="cf_title" value="{esc(title)}" required></div>
<div style="margin-top:.5rem"><label>Описание</label><textarea id="cf_desc" rows="2">{esc(desc)}</textarea></div>
<h3>Стартовые статы</h3>
<div class="row">{fields}</div>
<div style="margin-top:1rem;display:flex;gap:.5rem;flex-wrap:wrap">
  <button class="btn primary" data-act="class-save" data-arg="{key}">💾 Сохранить</button>
  <button class="btn" data-act="modal-close">Отмена</button>
</div>
</form>
"""
