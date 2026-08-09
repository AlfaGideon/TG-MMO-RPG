"""Знамения и предвестники бедствий мира Shadow Lands."""

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


def get_current_omens() -> list[dict]:
    return OMENS


def omen_banner() -> str:
    import random
    omen = random.choice(OMENS)
    return f"{omen['icon']} <b>Знамение: {omen['title']}</b>\n<i>{omen['desc']}</i>"
