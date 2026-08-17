"""Призрачный торговец у древних могил: прах предков вместо монет.

Каталог товаров и цены в прахе — общие для обоих стеков
(`core/spectral.py` их реэкспортирует). Прах нельзя купить за золото:
его собирают, почтив память павших, поэтому это отдельная «валюта»
поверх обычного кошелька.
"""
ASH_PER_GRAVE = 25          # сколько праха даёт одна почтённая могила

SPECTRAL_WARES = [
    {
        "key": "spec_wound_heal",
        "name": "📜 Свиток Очищения Ран",
        "desc": "Мгновенно исцеляет любые кровоточащие раны после смерти.",
        "cost_ash": 30,
    },
    {
        "key": "spec_ethereal_blade",
        "name": "🗡 Эфирный клинок",
        "desc": "Призрачное оружие: +25 урона, игнорирующего броню.",
        "cost_ash": 75,
    },
    {
        "key": "spec_ancestor_tear",
        "name": "💧 Слеза предков",
        "desc": "Навсегда увеличивает максимальный запас маны на +10.",
        "cost_ash": 50,
    },
]

TEAR_MANA_BONUS = 10        # прибавка маны от «Слезы предков»


def get_spectral_wares() -> list:
    return SPECTRAL_WARES


def ware_by_key(key: str):
    return next((w for w in SPECTRAL_WARES if w["key"] == key), None)


def ash_of(p) -> int:
    return int(getattr(p, "soul_ash", 0) or 0)


def harvest_ash(p) -> dict:
    """Почтить память павшего и собрать прах."""
    p.soul_ash = ash_of(p) + ASH_PER_GRAVE
    return {"ok": True, "gained": ASH_PER_GRAVE, "total_ash": p.soul_ash}


def can_afford(p, key: str) -> bool:
    ware = ware_by_key(key)
    return ware is not None and ash_of(p) >= ware["cost_ash"]


def buy_text(ware: dict, key: str) -> str:
    """Что призрак говорит после сделки — одинаково в обоих стеках."""
    if key == "spec_wound_heal":
        return "Призрачный свет окутал тебя. Все раны мгновенно затянулись!"
    if key == "spec_ancestor_tear":
        return (f"Ты испил слезу предков. Максимальная мана увеличена "
                f"на +{TEAR_MANA_BONUS} навсегда!")
    return (f"Ты приобрёл {ware['name']} у призрачного торговца "
            f"за {ware['cost_ash']} 🕯 Праха предков!")
