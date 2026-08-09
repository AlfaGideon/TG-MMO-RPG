"""Реактивные диалоги жителей мира с учётом мировых событий и кармы."""
from core.models import Character


def generate_reactive_dialogue(character: Character, npc_name: str, npc_type: str, world_context: dict) -> str:
    """Генерирует реплику жителя с учётом активных катаклизмов, осад и кармы."""
    karma = getattr(character, "karma_score", 0) or 0
    active_siege = world_context.get("has_siege")
    active_cataclysm = world_context.get("has_cataclysm")
    active_caravan = world_context.get("has_caravan")

    prefix = f"💬 <b>{npc_name}</b>"

    if active_siege:
        return f"{prefix}:\n— К оружию! Вражеские осадные орудия бьют по главным воротам замка! Помоги удержать цитадель!"
    elif active_cataclysm:
        return f"{prefix}:\n— Небо почернело... Бушует катаклизм. Будь осторожен на открытых трактах, путник!"
    elif active_caravan:
        return f"{prefix}:\n— Слыхал? На тракте показался богатый торговый обоз. Наёмники начеку, но разбойники уже готовят засаду."
    elif karma <= -150:
        return f"{prefix}:\n— Отойди от меня, осквернитель... Твои руки пахнут разрытыми могилами."
    elif karma >= 150:
        return f"{prefix}:\n— Да пребудет с тобой благословение света, благородный странник! Тебе здесь всегда рады."
    else:
        return f"{prefix}:\n— Мир полон тайн и опасностей. Держи клинок наготове, путник."
