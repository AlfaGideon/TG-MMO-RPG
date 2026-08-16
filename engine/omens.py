"""Знамения: атмосферные предвестия бед для обоих стеков.

Каталог живёт здесь, в `engine/` — единственный источник правды.
Серверный модуль `core/omens.py` реэкспортирует `OMENS` отсюда
(как `core/worldevents.py` берёт каталог бедствий из engine), поэтому
расхождение между стеками невозможно: список один.

Сейчас знамения статичны и показываются:
  • в боте — кнопка «🔮 Знамения» (bot/handlers/world_extra.py);
  • в браузерном движке — пункт меню «🔮 Знамения» (engine/game.do_omens).

Знамение больше не оторвано от мира (IDEAS-100.md № 86): если бедствие
уже бушует, показывается ЕГО предвестие — строка `omen` из
`engine/cataclysm_kinds.KINDS`, которая для каждого вида была написана
давно, но никем не читалась. В спокойное время берётся статичный каталог
ниже.

Админ может дописать свои знамения (IDEAS-100.md № 68): они лежат в
настройках (`store.settings` в браузере, `AppSetting` на сервере) под
ключом `CUSTOM_KEY` и подмешиваются к каталогу — код при этом один.
"""

OMENS = [
    {
        "icon": "🩸",
        "title": "Кровавый туман",
        "desc": "Небо на горизонте затянуло багровой дымкой. Древние предрекают скорое пробуждение Бездны.",
    },
    {
        "icon": "🌪",
        "title": "Пепельный суховей",
        "desc": "Ветер несёт колючую пыль с южных гор. Приближается огненная буря.",
    },
    {
        "icon": "🌑",
        "title": "Шёпот из расщелин",
        "desc": "Земля под ногами глухо вибрирует. Нежить собирается в полчища.",
    },
]


CUSTOM_KEY = "custom_omens"     # ключ настроек: список добавленных админом


def custom_omens(settings=None) -> list:
    """Знамения, добавленные из админки. Битые записи молча отбрасываются."""
    if not settings:
        return []
    raw = settings.get(CUSTOM_KEY)
    if isinstance(raw, str):                 # сервер хранит JSON-строкой
        import json
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    out = []
    for row in raw:
        if not isinstance(row, dict) or not row.get("title"):
            continue
        out.append({
            "icon": str(row.get("icon") or "🔮")[:4],
            "title": str(row["title"])[:64],
            "desc": str(row.get("desc") or "")[:300],
            "custom": True,
        })
    return out


def catalog(settings=None) -> list:
    """Полный каталог: встроенные знамения плюс добавленные админом."""
    return list(OMENS) + custom_omens(settings)


def for_cataclysm(kind_key: str) -> dict | None:
    """Знамение конкретного бедствия: строка `omen` из его описания.

    Поле `omen` есть у каждого вида в `engine/cataclysm_kinds.KINDS`
    («Гул из-под земли слышен даже в Погосте Костров.») — оно было
    написано, но до № 86 не читалось нигде.
    """
    from engine.cataclysm_kinds import KINDS

    k = KINDS.get(kind_key)
    if not k:
        return None
    return {
        "icon": k.get("icon", "🔮"),
        "title": f"Предвестие: {k.get('name', kind_key)}",
        "desc": k.get("omen") or k.get("story", ""),
        "kind": kind_key,
    }


def get_current_omens(settings=None, active_kinds=()) -> list:
    """Текущие знамения.

    Если в мире бушуют бедствия (`active_kinds` — их ключи), первыми идут
    их предвестия: знамение перестаёт быть случайной декорацией и
    указывает на то, что действительно происходит. Дальше — каталог.
    """
    omens = []
    seen = set()
    for key in active_kinds or ():
        row = for_cataclysm(key)
        if row and key not in seen:
            seen.add(key)
            omens.append(row)
    omens.extend(catalog(settings))
    return omens


def omen_banner(settings=None, active_kinds=()) -> str:
    """Баннер знамения. При живом бедствии показывает именно его предвестие."""
    import random

    rows = get_current_omens(settings, active_kinds)
    # Предвестие реального бедствия важнее случайной приметы, поэтому при
    # активном катаклизме берём первую строку, а не случайную.
    omen = rows[0] if active_kinds and rows else random.choice(rows or OMENS)
    return f"{omen['icon']} <b>Знамение: {omen['title']}</b>\n<i>{omen['desc']}</i>"


def omens_lines(settings=None, active_kinds=()) -> list:
    """Строки для экрана: значок, заголовок и описание каждого знамения."""
    out = []
    for o in get_current_omens(settings, active_kinds):
        out.append(f"{o['icon']} <b>{o['title']}</b>")
        out.append(f"<i>{o['desc']}</i>")
    return out


def omens_text(settings=None, active_kinds=()) -> str:
    """Готовый текст экрана «Знамения»."""
    lines = ["🔮 <b>Знамения</b>", "", "<i>Старики в Погосте шепчутся о дурных приметах:</i>", ""]
    lines.extend(omens_lines(settings, active_kinds))
    lines.append("")
    lines.append("<i>Говорят, за знамением всегда приходит беда…</i>")
    return "\n".join(lines)
