"""Экипировка по конкретному предмету, а не «по такому же».

Долг A из `AUDIT-BUGS.md`. `p.inventory` хранит индексы шаблонов, и
`p.equipped[slot]` тоже хранил индекс — поэтому две одинаковые вещи были
неразличимы, и из этого росло семейство багов:

  * продажа/прятание **второй копии** надетой вещи снимала экипировку:
    код сравнивал `p.equipped.get(тип) == idx`, а idx у копий одинаков;
  * дубликат надетой вещи **не выпадал в надгробие** при смерти:
    `drop_on_death` считал «надетым» любой предмет с тем же индексом.

Полный переход сумки на uid затронул бы 13 модулей (бой, лавка, аукцион,
крафт, задания, подземелья, торговец…) и был бы рискованным. Здесь решение
аддитивное: рядом с `p.equipped` ведётся `p.equipped_pos` — **позиция**
надетой вещи в `p.inventory`. Позиция однозначно указывает на конкретный
экземпляр, а формат сохранений не меняется: старые сейвы без нового поля
просто восстанавливают позицию по индексу (`sync_positions`).

Все изменения сумки должны идти через `take_at()` / `append_item()`,
иначе позиции разъедутся. Инварианты стережёт `tests/test_slot_identity.py`.
"""

POS_ATTR = "equipped_pos"


def positions(p):
    """{slot: позиция в inventory} с ленивой инициализацией."""
    pos = getattr(p, POS_ATTR, None)
    if not isinstance(pos, dict):
        pos = {}
        setattr(p, POS_ATTR, pos)
    return pos


def sync_positions(p):
    """Восстановить позиции для старых сохранений (одна вещь на слот).

    В сейвах до этого рефакторинга позиций нет — берём первый предмет
    с подходящим индексом. Неоднозначность возможна только для копий,
    но дальше позиции ведутся честно.
    """
    pos = positions(p)
    for slot, idx in list(p.equipped.items()):
        known = pos.get(slot)
        if (isinstance(known, int) and 0 <= known < len(p.inventory)
                and p.inventory[known] == idx):
            continue                      # позиция уже корректна
        try:
            pos[slot] = p.inventory.index(idx)
        except ValueError:
            # Надетой вещи нет в сумке (потерялась/продана) — снимаем слот,
            # иначе бонусы считались бы от вещи, которой нет.
            p.equipped.pop(slot, None)
            pos.pop(slot, None)
            (getattr(p, "worn", None) or {}).pop(slot, None)
    return pos


def equipped_positions(p):
    """Множество позиций надетых вещей — то, что нельзя терять и продавать."""
    return {v for v in sync_positions(p).values() if isinstance(v, int)}


def is_equipped_at(p, pos):
    """Надета ли ИМЕННО эта вещь (а не «такая же»)."""
    return int(pos) in equipped_positions(p)


def equip_at(p, pos, slot, uid=None):
    """Надеть вещь, стоящую на позиции `pos`."""
    pos = int(pos)
    p.equipped[slot] = p.inventory[pos]
    positions(p)[slot] = pos
    if uid:
        worn = getattr(p, "worn", None)
        if isinstance(worn, dict):
            worn[slot] = uid


def unequip_slot(p, slot):
    """Снять слот целиком (и забыть позицию с uid экземпляра)."""
    p.equipped.pop(slot, None)
    positions(p).pop(slot, None)
    worn = getattr(p, "worn", None)
    if isinstance(worn, dict):
        worn.pop(slot, None)


def _shift_after_removal(p, removed_pos):
    """Сдвинуть позиции после удаления элемента и снять надетое, если ушло оно."""
    pos_map = positions(p)
    for slot, pos in list(pos_map.items()):
        if not isinstance(pos, int):
            continue
        if pos == removed_pos:
            unequip_slot(p, slot)         # надетую вещь убрали из сумки
        elif pos > removed_pos:
            pos_map[slot] = pos - 1       # всё, что было правее, съехало влево


def take_at(p, pos):
    """Единственный правильный способ убрать вещь из сумки.

    Возвращает индекс шаблона. Экипировка снимается, только если ушла
    **та самая** вещь; позиции остальных слотов корректируются.
    """
    pos = int(pos)
    sync_positions(p)
    idx = p.inventory.pop(pos)
    _shift_after_removal(p, pos)
    return idx


def append_item(p, idx):
    """Положить вещь в конец сумки. Позиции слотов не затрагиваются."""
    p.inventory.append(int(idx))
    return len(p.inventory) - 1


def take_first_unequipped(p, idx):
    """Убрать из сумки одну вещь шаблона `idx`, по возможности не надетую.

    Замена `p.inventory.remove(idx)`: голый `remove` брал первое совпадение
    (могло оказаться надетым) и не поправлял позиции слотов. Возвращает
    позицию, откуда забрали, или None, если такой вещи нет.
    """
    idx = int(idx)
    sync_positions(p)
    worn_at = equipped_positions(p)
    candidates = [i for i, cur in enumerate(p.inventory) if int(cur) == idx]
    if not candidates:
        return None
    free = [i for i in candidates if i not in worn_at]
    pos = free[0] if free else candidates[0]
    take_at(p, pos)
    return pos
