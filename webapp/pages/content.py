"""Страница: справочник контента — мобы, предметы, NPC, классы."""
from engine import data, rules
from webapp.html import esc

TITLE = "📦 Контент"


def render(ctx):
    mobs = "".join(
        f"<tr><td>{esc(m[0])}</td><td class='muted'>{esc(m[1])}</td><td>{m[2]}</td>"
        f"<td>{m[3]}</td><td>{m[4]}</td><td>{m[5]}</td><td>{m[6]} 🪙</td><td>{m[7]} ⭐</td>"
        f"<td>{esc(data.LOCATIONS[m[8]][0])}</td></tr>" for m in data.MOBS)

    items = ""
    for i in range(len(data.ITEMS)):
        it = rules.item(i)
        bon = ", ".join(f"{k}+{v}" for k, v in it["bonus"].items()) or "—"
        items += (f"<tr><td>{it['icon']} {esc(it['name'])}</td><td><span class='tag'>{it['type']}</span></td>"
                  f"<td><span class='tag {it['rarity']}'>{it['rarity']}</span></td>"
                  f"<td>{it['price']} 🪙</td><td class='muted'>{esc(bon)}</td></tr>")

    npcs = "".join(f"<tr><td>{esc(n[0])}</td><td><span class='tag'>{n[2]}</span></td>"
                   f"<td class='muted'>{esc(n[1])}</td></tr>" for n in data.NPCS)

    classes = ""
    for key, (title, desc, st) in data.CLASSES.items():
        stats = " · ".join(f"{k} {v}" for k, v in st.items())
        classes += (f"<tr><td>{esc(title)}</td><td class='muted'>{esc(desc)}</td>"
                    f"<td class='muted'>{esc(stats)}</td></tr>")

    return f"""
<div class="card">
  <h2>👾 Мобы <span class="muted">({len(data.MOBS)})</span></h2>
  <div class="scroll"><table>
    <tr><th>Имя</th><th>Описание</th><th>Ур.</th><th>HP</th><th>Урон</th>
        <th>Защита</th><th>Золото</th><th>Опыт</th><th>Локация</th></tr>{mobs}
  </table></div>
</div>

<div class="card">
  <h2>⚔️ Предметы <span class="muted">({len(data.ITEMS)})</span></h2>
  <div class="scroll"><table>
    <tr><th>Предмет</th><th>Тип</th><th>Редкость</th><th>Цена</th><th>Бонусы</th></tr>{items}
  </table></div>
</div>

<div class="card">
  <h2>🎭 NPC</h2>
  <div class="scroll"><table><tr><th>Имя</th><th>Роль</th><th>Реплика</th></tr>{npcs}</table></div>
</div>

<div class="card">
  <h2>🧙 Классы</h2>
  <div class="scroll"><table><tr><th>Класс</th><th>Описание</th><th>Стартовые статы</th></tr>{classes}</table></div>
</div>

<div class="card">
  <div class="hint">Контент задан в <code>engine/data.py</code>. Правь этот файл —
    и бот, и панель подхватят изменения (для мобов и клеток нужна перегенерация мира).</div>
</div>
"""
