"""Звуковой эмбиент локаций: профили для Web Audio.

Каталог общий для обоих стеков — `core/ambient.py` реэкспортирует его
отсюда. Браузерному стеку профиль нужен напрямую (звук играет там же),
серверному — чтобы отдавать его мини-приложению.
"""

AMBIENT_PROFILES = {
    "safe": {
        "name": "Погост и Лагерь",
        "soundscape": "campfire_crackles",
        "description": "Уютное потрескивание костра и тихий перезвон церковных колоколов вдали.",
        "reverb": 0.2,
        "base_freq": 120,
    },
    "dangerous": {
        "name": "Опасные пустоши",
        "soundscape": "wind_howl",
        "description": "Протяжный вой пепельного ветра и шелест сухой травы.",
        "reverb": 0.5,
        "base_freq": 80,
    },
    "dungeon": {
        "name": "Катакомбы и подземелья",
        "soundscape": "water_drips_echo",
        "description": "Эхо падающих капель воды, далёкий скрежет цепей и гул бездны.",
        "reverb": 0.8,
        "base_freq": 45,
    },
    "boss": {
        "name": "Логово чудовища",
        "soundscape": "heartbeat_drone",
        "description": "Тяжёлый низкочастотный гул и тревожный ритм биения древнего сердца.",
        "reverb": 0.9,
        "base_freq": 35,
    },
}


def get_ambient_profile(location_type: str = "dangerous") -> dict:
    """Возвращает параметры эмбиент-генератора для типа локации."""
    return AMBIENT_PROFILES.get(location_type, AMBIENT_PROFILES["dangerous"])
