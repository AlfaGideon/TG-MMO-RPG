"""Реактивные реплики жителей: мир влияет на то, что говорят NPC.

Паритет с серверным стеком: та же лестница приоритетов и те же тексты,
что в `core/dialogue.py` (осада → катаклизм → караван → карма → покой).
Пороги кармы берутся из `engine/karma.py` — единственного источника
правды, чтобы диалоги не разошлись с самой системой кармы.

Контекст собирается из уже существующих механик движка:
  • катаклизм  — `engine/cataclysm.active(store, loc)`;
  • караван    — `engine/merchant.at(store, loc)` (бродячий торговец);
  • осада      — пока не реализована в браузерном стеке, поле
    зарезервировано, чтобы ветка совпадала с серверной.
"""
from engine import karma


def world_context(store, loc):
    """Что сейчас происходит в локации — для выбора реплики."""
    from engine import cataclysm, merchant

    if store is None:
        return {"has_siege": False, "has_cataclysm": False, "has_caravan": False}
    return {
        # Осады в браузерном стеке ещё нет — ветка сохранена для паритета.
        "has_siege": False,
        "has_cataclysm": bool(cataclysm.active(store, loc)),
        "has_caravan": bool(merchant.at(store, loc)),
    }


def generate_reactive_dialogue(p, npc_name, npc_type="", context=None):
    """Реплика жителя с учётом мировых событий и кармы героя.

    Возвращает готовую строку или пустую строку, если ничего особенного
    не происходит и герой нейтрален — тогда экран показывает обычное
    описание NPC из каталога.
    """
    context = context or {}
    score = getattr(p, "karma_score", 0) or 0
    prefix = f"💬 <b>{npc_name}</b>"

    if context.get("has_siege"):
        return (f"{prefix}:\n— К оружию! Вражеские осадные орудия бьют по "
                f"главным воротам замка! Помоги удержать цитадель!")
    if context.get("has_cataclysm"):
        return (f"{prefix}:\n— Небо почернело... Бушует катаклизм. Будь "
                f"осторожен на открытых трактах, путник!")
    if context.get("has_caravan"):
        return (f"{prefix}:\n— Слыхал? На тракте показался богатый торговый "
                f"обоз. Наёмники начеку, но разбойники уже готовят засаду.")
    if score <= karma.DEFILED_KARMA:
        return (f"{prefix}:\n— Отойди от меня, осквернитель... Твои руки "
                f"пахнут разрытыми могилами.")
    if score >= karma.PIOUS_KARMA:
        return (f"{prefix}:\n— Да пребудет с тобой благословение света, "
                f"благородный странник! Тебе здесь всегда рады.")
    return ""


def line_for(store, p, npc_name, npc_type=""):
    """Готовая строка для экрана NPC ('' — говорить нечего особенного)."""
    if p is None:
        return ""
    loc = getattr(p, "loc", 0)
    return generate_reactive_dialogue(p, npc_name, npc_type,
                                      world_context(store, loc))
