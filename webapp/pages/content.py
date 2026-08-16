"""Страница: контент игры — мобы, предметы, NPC, классы. Всё редактируемо."""
from engine import bestiary, data, familiars, pets, rules
from webapp.html import esc
from webapp.pages import dungeons as page_dungeons

TITLE = "📦 Контент"
CRUMBS = [("Контент", "content")]

TABS = [("mobs", "👾 Мобы"), ("items", "⚔️ Предметы"),
        ("npcs", "🎭 NPC"), ("classes", "🧙 Классы"),
        ("pets", "🐾 Питомцы"), ("pet_templates", "🥚 Шаблоны питомцев"),
        ("bestiary", "📖 Бестиарий"),
        ("dungeons", "🕳 Подземелья")]


def render(ctx):
    tab = ctx.state.setdefault("content_tab", "mobs")
    buttons = "".join(
        f"<button class='btn {'primary' if tab == key else ''}' "
        f"data-act='content-tab' data-arg='{key}'>{label}</button> "
        for key, label in TABS)

    renderers = {"mobs": _mobs, "items": _items,
                 "npcs": _npcs, "classes": _classes,
                 "pets": _pets, "pet_templates": _pet_templates,
                 "bestiary": _bestiary,
                 "dungeons": page_dungeons.render}
    if tab not in renderers:
        tab = "mobs"
        ctx.state["content_tab"] = tab
    body = renderers[tab](ctx)

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
    labels = ["Имя", "Описание", "Ур.", "HP", "Урон", "Защита", "Золото",
              "Опыт", "Локация", "Нрав"]
    rows = "".join(_row(f"data-act='mob-edit' data-arg='{i}'", [
        f"<b>{esc(m[0])}</b>", f"<span class='muted'>{esc(m[1])}</span>", m[2],
        m[3], m[4], m[5], f"{m[6]} 🪙", f"{m[7]} ⭐",
        esc(data.LOCATIONS[m[8]][0]),
        data.BEHAVIORS.get(m[9] if len(m) > 9 else data.DEFAULT_BEHAVIOR,
                           ("", "", ""))[0]], labels,
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


def _pets(ctx):
    """Каталог фамильяров и то, кого герои себе завели (пункт № 74).

    Каталог — `engine/familiars.FAMILIARS`, тот же, что видит бот и
    серверная админка (`core/familiars.py` его реэкспортирует), поэтому
    цены и бонусы здесь не переписаны руками, а взяты из кода.
    """
    taken = {}
    for p in ctx.store.players.values():
        ftype = getattr(p, "familiar_type", None)
        if ftype:
            taken.setdefault(ftype, []).append(p)

    rows = ""
    for key, f in familiars.FAMILIARS.items():
        owners = taken.get(key, [])
        bonus_bits = []
        if f.get("crit_bonus"):
            bonus_bits.append(f"крит +{f['crit_bonus']}%")
        if f.get("magic_bonus"):
            bonus_bits.append(f"магия +{f['magic_bonus']}%")
        if f.get("gold_to_stash_pct"):
            bonus_bits.append(f"{f['gold_to_stash_pct']}% золота в карман")
        if f.get("vision_bonus"):
            bonus_bits.append(f"обзор +{f['vision_bonus']}")
        if f.get("berserk_bonus"):
            bonus_bits.append(f"берсерк +{f['berserk_bonus']}%")
        if f.get("ambush_shield"):
            bonus_bits.append("предупреждает о засадах")
        rows += (f"<tr><td><b>{f['icon']} {esc(f['name'])}</b></td>"
                 f"<td class='muted'>{esc(f['desc'])}</td>"
                 f"<td>{esc(' · '.join(bonus_bits))}</td>"
                 f"<td>{f['cost']}🟤</td>"
                 f"<td>{len(owners)}</td></tr>")

    owners_rows = ""
    for p in sorted(ctx.store.players.values(), key=lambda pl: pl.name or ""):
        fam = familiars.get_familiar(p)
        if not fam:
            continue
        b = familiars.familiar_bonuses(p)
        owners_rows += (
            f"<tr><td>{esc(p.name)} <span class='muted'>ур. {p.level}</span></td>"
            f"<td>{fam['icon']} {esc(fam['custom_name'])}</td>"
            f"<td>ур. {fam['level']}</td>"
            f"<td class='muted'>крит +{b['crit_bonus']}% · магия +{b['magic_bonus']}%"
            f" · берсерк +{b['berserk_bonus']}%</td></tr>")
    owners_body = (f"<div class='scroll'><table><tr><th>Герой</th><th>Спутник</th>"
                   f"<th>Уровень</th><th>Текущие бонусы</th></tr>{owners_rows}"
                   f"</table></div>") if owners_rows else (
        "<p class='muted'>Пока никто не завёл спутника. "
        "Кнопка приручения — экран «🐾 Фамильяры» в боте.</p>")

    return f"""
<div class="card">
  <h2>🐾 Каталог фамильяров <span class="muted">({len(familiars.FAMILIARS)})</span></h2>
  <p class="muted">Каталог общий для браузера и бота — правится в
     <code>engine/familiars.py</code>, цены в бронзе.</p>
  <div class="scroll"><table>
    <tr><th>Спутник</th><th>Описание</th><th>Бонусы</th><th>Цена</th><th>Хозяев</th></tr>
    {rows}
  </table></div>
</div>
<div class="card">
  <h2>👥 Спутники героев</h2>
  {owners_body}
</div>
"""


def _pet_templates(ctx):
    """Редактор шаблонов питомцев (пункт № 20).

    Паритет с серверной админкой: правила ключа, редкости и разбора
    бонусов — общие (`engine/pets.py`), у сервера они лежат в таблице
    `PetTemplate`, здесь — в `store.settings["pet_templates"]`.
    """
    rows = ""
    for tpl in pets.templates(ctx.store):
        rarity = tpl.get("rarity", "common")
        state = ("<span class='tag'>вкл</span>" if tpl.get("is_active", True)
                 else "<span class='muted'>выкл</span>")
        rows += (
            f"<tr><td data-label='Питомец'><b>{esc(tpl.get('name', ''))}</b>"
            f"<br><code>{esc(tpl.get('key', ''))}</code></td>"
            f"<td data-label='Семейство'>{esc(pets.FAMILY_LABELS.get(tpl.get('family'), '—'))}</td>"
            f"<td data-label='Редкость'>{pets.RARITY_ICONS.get(rarity, '⚪')} "
            f"{esc(pets.RARITY_LABELS.get(rarity, rarity))}</td>"
            f"<td data-label='Бонусы' class='muted'>"
            f"{esc(pets.describe_bonuses(tpl.get('bonuses_json')))}</td>"
            f"<td data-label='Статус'>{state}</td>"
            f"<td data-label=''>"
            f"<button class='btn' data-act='pet-toggle' data-arg=\"{esc(tpl.get('key',''))}\">⏻</button> "
            f"<button class='btn danger' data-act='pet-del' data-arg=\"{esc(tpl.get('key',''))}\">🗑</button>"
            f"</td></tr>")
    if not rows:
        rows = ("<tr><td colspan='6'><div class='empty-state'>"
                "<div class='empty-icon'>🥚</div>"
                "<div>Шаблонов пока нет — заведи первого ниже.</div>"
                "</div></td></tr>")

    families = "".join(f"<option value='{k}'>{esc(v)}</option>"
                       for k, v in pets.FAMILY_LABELS.items())
    rarities = "".join(
        f"<option value='{k}'>{pets.RARITY_ICONS.get(k, '')} {esc(v)}</option>"
        for k, v in pets.RARITY_LABELS.items())

    return f"""
<div class="card">
  <h2>🥚 Шаблоны питомцев <span class="muted">({len(pets.templates(ctx.store))})</span></h2>
  <p class="muted">Каталог будущих видов — то же, что редактор
     <code>/editor/pets</code> в серверной админке. Правила ключа, редкости
     и разбора бонусов общие (<code>engine/pets.py</code>), поэтому шаблон,
     принятый здесь, примет и сервер.</p>
  <div class="scroll"><table>
    <tr><th>Питомец</th><th>Семейство</th><th>Редкость</th><th>Бонусы</th>
        <th>Статус</th><th></th></tr>
    {rows}
  </table></div>
</div>
<div class="card">
  <h2>➕ Новый шаблон</h2>
  <div class="row">
    <div><label>Имя</label><input id="pt_name" placeholder="Слизень Зари"></div>
    <div><label>Ключ (необязательно)</label><input id="pt_key" placeholder="из имени"></div>
    <div><label>Семейство</label><select id="pt_family">{families}</select></div>
    <div><label>Редкость</label><select id="pt_rarity">{rarities}</select></div>
  </div>
  <div class="row" style="margin-top:.5rem">
    <div style="flex:2"><label>Описание</label>
      <input id="pt_desc" placeholder="Чем он примечателен"></div>
    <div><label>Порядок</label><input id="pt_sort" type="number" value="100"></div>
  </div>
  <div style="margin-top:.5rem">
    <label>Бонусы (JSON)</label>
    <input id="pt_bonuses" value="{{}}" placeholder='{{"crit_bonus": 3}}'>
    <div class="hint">Механика читает: {esc(', '.join(pets.KNOWN_BONUSES))}.
       Остальные ключи сохранятся, но пока декоративны.</div>
  </div>
  <div style="margin-top:.8rem">
    <button class="btn primary" data-act="pet-add">➕ Добавить шаблон</button>
  </div>
</div>
"""


def _bestiary(ctx):
    """Бестиарий: справочник тварей + счётчики убийств по серверу (№ 76)."""
    kills = {}
    hunters = {}
    for p in ctx.store.players.values():
        for mob, cnt in bestiary.get_bestiary(p).items():
            kills[mob] = kills.get(mob, 0) + cnt
            if cnt > hunters.get(mob, (0, ""))[0]:
                hunters[mob] = (cnt, p.name)

    rows = ""
    for i, m in enumerate(data.MOBS):
        name = m[0]
        total = kills.get(name, 0)
        best_cnt, best_name = hunters.get(name, (0, ""))
        top = (f"{esc(best_name)} <span class='muted'>× {best_cnt} "
               f"(+{min(bestiary.MAX_BONUS_PCT, best_cnt // bestiary.KILLS_PER_STEP)}%)"
               f"</span>") if best_cnt else "<span class='muted'>—</span>"
        rows += (f"<tr class='clickable' data-act='mob-edit' data-arg='{i}'>"
                 f"<td><b>{esc(name)}</b></td>"
                 f"<td>ур. {m[2]} · ❤️ {m[3]} · ⚔️ {m[4]}</td>"
                 f"<td>{total}</td><td>{top}</td></tr>")

    unknown = sorted(set(kills) - {m[0] for m in data.MOBS})
    extra = ("<div class='hint warn'>Убийства тварей, которых нет в каталоге "
             "(переименованы или удалены): " + esc(", ".join(unknown)) + "</div>") if unknown else ""

    return f"""
<div class="card">
  <h2>📖 Бестиарий <span class="muted">({len(data.MOBS)} видов ·
      {sum(kills.values())} побед всего)</span></h2>
  <p class="muted">Каждые {bestiary.KILLS_PER_STEP} побед над видом дают герою
     +1 % урона по нему, потолок +{bestiary.MAX_BONUS_PCT} % —
     числа из <code>engine/bestiary.py</code>, те же, что в бою.
     Клик по строке открывает карточку твари.</p>
  {extra}
  <div class="scroll"><table>
    <tr><th>Тварь</th><th>Параметры</th><th>Убито на сервере</th><th>Лучший охотник</th></tr>
    {rows}
  </table></div>
</div>
"""


# ── формы ───────────────────────────────────────────────────

def _num(fid, label, val):
    return f"<div><label>{esc(label)}</label><input id='{fid}' type='number' value='{val}'></div>"


def mob_form(ctx, idx):
    new = idx is None
    m = data.MOBS[idx] if not new else ("", "", 1, 30, 5, 2, 10, 15, 0,
                                        data.DEFAULT_BEHAVIOR)
    cur_behavior = m[9] if len(m) > 9 else data.DEFAULT_BEHAVIOR
    behaviors = "".join(
        f"<option value='{k}' {'selected' if k == cur_behavior else ''}>"
        f"{icon} {name} — {hint}</option>"
        for k, (icon, name, hint) in data.BEHAVIORS.items())
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
<div style="margin-top:.5rem"><label>Характер (как ведёт себя вне боя)</label>
  <select id="mf_behavior">{behaviors}</select></div>
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
