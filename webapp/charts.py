"""Простые SVG-графики для дашборда Pyodide-админки."""


def _bar(title, data, color="#8b5cf6", height=140):
    """data: [(label, value), ...]"""
    if not data:
        return f"<div class='chart-wrap'><h4>{title}</h4><p class='muted'>Нет данных</p></div>"
    max_v = max(v for _, v in data) or 1
    width = 280
    bar_w = max(12, (width - 40) // len(data) - 4)
    bars = ""
    for i, (label, val) in enumerate(data):
        h = max(4, int(val / max_v * (height - 40)))
        x = 30 + i * (bar_w + 4)
        y = height - 20 - h
        bars += (f"<rect x='{x}' y='{y}' width='{bar_w}' height='{h}' fill='{color}' rx='3'/>"
                 f"<text x='{x + bar_w/2}' y='{height - 5}' text-anchor='middle' font-size='9' fill='currentColor'>{label}</text>")
    return f"""
<div class="chart-wrap">
  <h4 style="margin-bottom:.5rem;color:var(--text-muted)">{title}</h4>
  <svg viewBox="0 0 {width} {height}" style="width:100%;max-width:{width}px">
    <line x1="25" y1="{height-20}" x2="{width-10}" y2="{height-20}" stroke="var(--border)" stroke-width="1"/>
    {bars}
  </svg>
</div>
"""


def _pie(title, data, height=140):
    """data: [(label, value, color), ...]"""
    if not data:
        return f"<div class='chart-wrap'><h4>{title}</h4><p class='muted'>Нет данных</p></div>"
    total = sum(v for _, v, _ in data) or 1
    cx, cy, r = 70, height / 2, 50
    start = -90
    slices = ""
    legend = ""
    for label, val, color in data:
        angle = val / total * 360
        end = start + angle
        x1 = cx + r * __import__("math").cos(__import__("math").radians(start))
        y1 = cy + r * __import__("math").sin(__import__("math").radians(start))
        x2 = cx + r * __import__("math").cos(__import__("math").radians(end))
        y2 = cy + r * __import__("math").sin(__import__("math").radians(end))
        large = 1 if angle > 180 else 0
        path = f"M {cx} {cy} L {x1} {y1} A {r} {r} 0 {large} 1 {x2} {y2} Z"
        slices += f"<path d='{path}' fill='{color}' stroke='var(--bg-card)' stroke-width='2'/>"
        legend += f"<span style='display:flex;align-items:center;gap:.3rem;font-size:.75rem'><i style='width:10px;height:10px;border-radius:3px;background:{color}'></i>{label} {val}</span>"
        start = end
    return f"""
<div class="chart-wrap">
  <h4 style="margin-bottom:.5rem;color:var(--text-muted)">{title}</h4>
  <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
    <svg viewBox="0 0 140 {height}" style="width:140px;height:{height}px">{slices}</svg>
    <div style="display:flex;flex-direction:column;gap:.3rem">{legend}</div>
  </div>
</div>
"""


def render_dashboard_charts(ctx):
    from collections import Counter
    from engine import data
    made = [p for p in ctx.store.players.values() if p.created_char]

    # levels distribution
    levels = Counter(p.level for p in made)
    level_data = [(str(l), levels.get(l, 0)) for l in range(1, max(levels.keys() or [1]) + 1)]

    # gold by location
    gold_by_loc = Counter()
    for p in made:
        gold_by_loc[p.loc] += p.gold
    loc_data = [(data.LOCATIONS[i][0][:8], gold_by_loc.get(i, 0)) for i in range(len(data.LOCATIONS))]

    # rarity of items in inventory
    from engine import rules
    rarity_counts = Counter()
    for p in made:
        for idx in p.inventory:
            rarity_counts[rules.item(idx)["rarity"]] += 1
    rarity_order = ["common", "uncommon", "rare", "epic", "legendary"]
    rarity_colors = {"common": "#94a3b8", "uncommon": "#22c55e", "rare": "#3b82f6", "epic": "#a855f7", "legendary": "#f59e0b"}
    rarity_data = [(r, rarity_counts.get(r, 0), rarity_colors[r]) for r in rarity_order if rarity_counts.get(r, 0) > 0]

    # battle results (mock from recent logs)
    wins = sum(1 for line in ctx.log_lines if "побед" in line[2].lower() or "выиграл" in line[2].lower())
    losses = sum(1 for line in ctx.log_lines if "пораж" in line[2].lower() or "убит" in line[2].lower())
    if wins == 0 and losses == 0:
        wins, losses = 1, 0
    battle_data = [("Победы", wins, "#22c55e"), ("Поражения", losses, "#ef4444")]

    return f"""
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem">
  {_bar("Распределение уровней", level_data)}
  {_bar("Золото по локациям", loc_data, color="#f59e0b")}
  {_pie("Предметы по редкости", rarity_data)}
  {_pie("Итоги боёв", battle_data)}
</div>
"""
