"""Лунно-солнечные циклы мира Shadow Lands: влияние фаз на монстров и магию."""
import time

PHASES = [
    {
        "key": "full_moon",
        "name": "🌕 Полнолуние",
        "desc": "Монстры впадают в неистовство (+30% спавн мобов, +25% дроп материалов).",
        "mob_mult": 1.30,
        "material_mult": 1.25,
        "magic_dark_mult": 1.0,
    },
    {
        "key": "waning_moon",
        "name": "🌘 Убывающая Луна",
        "desc": "Время затишья: жители спокойны, торговцы дают −10% скидки.",
        "mob_mult": 0.85,
        "material_mult": 1.0,
        "magic_dark_mult": 1.0,
    },
    {
        "key": "new_moon",
        "name": "🌑 Новолуние (Тёмная Луна)",
        "desc": "Врата бездны приоткрыты: магия тьмы усилена на +25%, нежить восстаёт быстрее.",
        "mob_mult": 1.15,
        "material_mult": 1.0,
        "magic_dark_mult": 1.25,
    },
    {
        "key": "waxing_moon",
        "name": "🌓 Растущая Луна",
        "desc": "Прилив жизненных сил: шанс критического удара всех героев увеличен на +10%.",
        "mob_mult": 1.0,
        "material_mult": 1.10,
        "magic_dark_mult": 1.0,
    },
]

CYCLE_DURATION_HOURS = 24  # Полный цикл за сутки


def get_current_lunar_phase(timestamp: float | None = None) -> dict:
    """Определяет текущую фазу луны по серверному времени."""
    t = time.time() if timestamp is None else timestamp
    # 4 фазы по 6 часов
    hours = (t / 3600) % CYCLE_DURATION_HOURS
    phase_idx = int(hours // (CYCLE_DURATION_HOURS / len(PHASES)))
    return PHASES[phase_idx % len(PHASES)]


def lunar_phase_banner() -> str:
    phase = get_current_lunar_phase()
    return f"{phase['name']}\n<i>{phase['desc']}</i>"
