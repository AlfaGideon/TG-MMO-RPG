"""Блок «Фракции и репутация» для вкладки «Жизнь мира»."""
from engine import factions
from webapp.html import esc


def render(ctx):
    """Расклад сил: кто за кого и как это влияет на мир."""
    store = ctx.store
    heroes = [p for p in store.players.values() if p.created_char]
    sides = {k: 0 for k in factions.FACTIONS}
    totals = {k: 0 for k in factions.FACTIONS}
    for p in heroes:
        side = factions.allegiance(p)
        if side:
            sides[side] += 1
        for k in factions.FACTIONS:
            totals[k] += max(0, factions.value(p, k))

    cards = ""
    for key in factions.ORDER:
        icon, name, motto, foe = factions.FACTIONS[key]
        cards += (f"<div class='cata-card'><div class='ct'>{icon} {esc(name)}</div>"
                  f"<div class='cd'>{esc(motto)}<br>"
                  f"👥 сторонников: <b>{sides[key]}</b> · "
                  f"очков в мире: <b>{totals[key]}</b><br>"
                  f"соперник: {factions.FACTIONS[foe][0]} "
                  f"{esc(factions.FACTIONS[foe][1])}</div></div>")

    mult = factions.cataclysm_mult(store)
    if mult > 1:
        mood = (f"🌑 Культ перевешивает — бедствия случаются "
                f"<b>в {mult:g}× чаще</b>.")
    elif mult < 1:
        mood = (f"🛡 Стража держит порядок — бедствия "
                f"<b>в {1 / mult:.1f}× реже</b>.")
    else:
        mood = "⚖️ Силы уравновешены, беды приходят своим чередом."

    rows = ""
    for p in sorted(heroes, key=lambda q: -max(
            factions.value(q, k) for k in factions.FACTIONS))[:12]:
        side = factions.allegiance(p)
        badge = (f"{factions.FACTIONS[side][0]} {esc(factions.FACTIONS[side][1])}"
                 if side else "<span class='muted'>сам по себе</span>")
        cells = " · ".join(
            f"{factions.FACTIONS[k][0]} {factions.value(p, k)}"
            for k in factions.ORDER)
        rows += (f"<tr><td>{esc(p.name)}</td><td>{badge}</td>"
                 f"<td>{cells}</td>"
                 f"<td>−{int(factions.discount(p) * 100)}%</td></tr>")
    table = (f"<div class='scroll'><table><thead><tr><th>Герой</th>"
             f"<th>Сторона</th><th>Репутация</th><th>Скидка</th></tr></thead>"
             f"<tbody>{rows}</tbody></table></div>") if rows else (
        "<p class='muted'>Героев пока нет.</p>")

    return f"""
<div class="card">
  <h2>🧭 Фракции и репутация</h2>
  <div class="hint">Три силы с противоположными интересами: помощь одной
     злит её соперника, поэтому своим для всех не станешь. Репутация даёт
     скидку у торговцев (со звания «Знакомый»), меняет реплики жителей, а
     враг фракции получает от её людей отказ.<br>{mood}</div>
  <div class="cata-grid">{cards}</div>
  <h3 style="margin-top:1rem">Кто за кого</h3>
  {table}
</div>
"""
