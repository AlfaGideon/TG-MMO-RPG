"""Каталог бедствий: параметры каждого вида катаклизма.

Только данные, без логики — правила читают их через engine.cataclysm.
"""

# Во сколько раз больше тварей, пока бушует бедствие. Держится ровно:
# сколько бы бедствий ни наложилось, итог всё равно ×MOB_MULT от мирного.
MOB_MULT = 2.0

# kind -> параметры. tiles — во что превращается тайл, spread — доля клеток,
# block — шанс завала, chests — шанс находки.
# mob_rate/damage/loot/gold/rest — множители правил, пока беда идёт.
# ambush — шанс, что тварь бросится на игрока сама, join — что подтянется
# к уже идущему бою. В мирное время обе равны нулю: твари ждут на месте.
KINDS = {
    "quake": dict(
        name="Землетрясение", icon="🌋", hours=3, spread=0.40,
        tiles={"grass": "cave", "road": "cave", "village": "cave"},
        block=0.14, chests=0.04,
        mob_rate=1.15, damage=1.10, loot=1.05, gold=1.00, rest=0.80,
        ambush=0.18, join=0.12,
        omen="Гул из-под земли слышен даже в Погосте Костров.",
        story="Земля вспарывается трещинами, тропы обрушиваются в пустоту."),
    "flood": dict(
        name="Великий потоп", icon="🌊", hours=4, spread=0.45,
        tiles={"grass": "water", "road": "water", "village": "water"},
        block=0.10, chests=0.06,
        mob_rate=0.90, damage=1.05, loot=1.10, gold=1.05, rest=0.70,
        ambush=0.14, join=0.10,
        omen="Реки вышли из берегов и идут на низины.",
        story="Мутная вода накрыла дороги; уцелевшие тропы стали островами."),
    "wildfire": dict(
        name="Пожар", icon="🔥", hours=2, spread=0.50,
        tiles={"forest": "grass", "village": "grass", "grass": "road"},
        block=0.08, chests=0.03,
        mob_rate=1.20, damage=1.20, loot=1.00, gold=1.10, rest=0.60,
        ambush=0.22, join=0.16,
        omen="Небо на горизонте стало рыжим от зарева.",
        story="Огонь съедает чащу, оставляя пепел и раскалённые камни."),
    "blizzard": dict(
        name="Ледяная буря", icon="❄️", hours=5, spread=0.55,
        tiles={"water": "wall", "grass": "wall", "road": "road"},
        block=0.06, chests=0.02,
        mob_rate=0.85, damage=1.15, loot=1.00, gold=0.95, rest=0.50,
        ambush=0.12, join=0.08,
        omen="Ветер принёс мороз, которого не помнят старики.",
        story="Снег заносит тропы, вода схватывается коркой чёрного льда."),
    "bloodmoon": dict(
        name="Кровавая луна", icon="🌕", hours=2, spread=0.60,
        tiles={}, block=0.0, chests=0.05,
        mob_rate=1.60, damage=1.25, loot=1.35, gold=1.30, rest=0.75,
        ambush=0.45, join=0.35,
        omen="Луна налилась красным — твари осмелели.",
        story="Нежить лезет отовсюду, зато и добыча стала щедрее."),
    "meteor": dict(
        name="Звездопад", icon="☄️", hours=3, spread=0.30,
        tiles={"grass": "cave", "forest": "cave"},
        block=0.12, chests=0.18,
        mob_rate=1.10, damage=1.05, loot=1.25, gold=1.20, rest=0.85,
        ambush=0.20, join=0.14,
        omen="С неба падают камни, оставляя дымящиеся воронки.",
        story="В кратерах поблёскивает звёздное железо — и что-то шевелится."),
    "plague": dict(
        name="Мор", icon="☠️", hours=6, spread=0.50,
        tiles={"village": "grass"}, block=0.02, chests=0.02,
        mob_rate=1.25, damage=1.10, loot=0.90, gold=0.80, rest=0.40,
        ambush=0.28, join=0.20,
        omen="По деревням идёт болезнь: костры горят даже днём.",
        story="Живые прячутся, мёртвые ходят. Отдых почти не помогает."),
    "voidrift": dict(
        name="Разлом Пустоты", icon="🌀", hours=2, spread=0.25,
        tiles={"grass": "cave", "road": "cave", "wall": "cave"},
        block=0.05, chests=0.10,
        mob_rate=1.45, damage=1.35, loot=1.50, gold=1.40, rest=0.65,
        ambush=0.40, join=0.30,
        omen="Ткань мира треснула — из прорехи тянет холодом.",
        story="Пространство свернулось: за каждым поворотом ждёт чужое."),
}

ORDER = ["quake", "flood", "wildfire", "blizzard", "bloodmoon", "meteor",
         "plague", "voidrift"]
