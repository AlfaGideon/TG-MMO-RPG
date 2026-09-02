"""Хранилище состояния. Бэкенд подставляется снаружи (localStorage / файл)."""
import json
import random

from engine import data, world
from engine.models import Cell, Player


def _wallet_total(p):
    from engine import currency
    return currency.total(p)


def _unify_floor_stairs(cells, floors=None, sizes=None):
    """Миграция старого мира: две лестничные клетки → одна площадка."""
    floors, sizes = floors or {}, sizes or {}
    changed = False
    for raw_li, raw_count in floors.items():
        li, count = int(raw_li), max(1, int(raw_count or 1))
        if count < 2:
            continue
        size = world._size_of(sizes, li)
        sx, sy = size // 2, size // 2
        for lower in range(count - 1):
            old_y = sy + lower
            for floor in (lower, lower + 1):
                old = world.cell_at(cells, li, sx, old_y, floor)
                if (old and old.link and len(old.link) >= 4
                        and old.link[0] == li and old.link[3] != floor):
                    old.link = ()
                    changed = True
        for floor in range(count):
            stair = world.cell_at(cells, li, sx, sy, floor)
            if stair is None:
                continue
            links = []
            if floor > 0:
                links.append((li, sx, sy, floor - 1))
            if floor + 1 < count:
                links.append((li, sx, sy, floor + 1))
            desired = tuple(links)
            if tuple(stair.floor_links or ()) != desired:
                stair.floor_links, changed = desired, True
            if stair.link:
                stair.link, changed = (), True
            for attr, value in (("name", "Лестничная площадка"),
                                ("desc", "Отсюда можно перейти на соседний этаж."),
                                ("tile", "road"), ("passable", True)):
                if getattr(stair, attr) != value:
                    setattr(stair, attr, value)
                    changed = True
    return changed


def _repair_corner_castles(cells, grid=None, sizes=None):
    """Миграция localStorage со старой схемы четырёх замков."""
    grid, sizes = grid or world.DEFAULT_GRID, sizes or world.DEFAULT_SIZES
    fixed = 0
    for li in range(len(data.LOCATIONS)):
        if not world.is_castle(data.LOCATIONS, li):
            continue
        size = world._size_of(sizes, li, 25)
        wx, wy = grid.get(str(li), [0, 0])
        corner = ("ne" if wx >= 5 and wy < 5 else "sw" if wx < 5 and wy >= 5
                  else "se" if wx >= 5 and wy >= 5 else "nw")
        x0, y0 = {"nw": (0, 0), "ne": (0, size - 10),
                  "sw": (size - 10, 0), "se": (size - 10, size - 10)}[corner]
        positions = {int(k): tuple(v) for k, v in grid.items()}
        wx, wy = positions.get(li, [wx, wy])
        neighbours = {"w": (wx - 1, wy) in positions.values(),
                      "e": (wx + 1, wy) in positions.values(),
                      "n": (wx, wy - 1) in positions.values(),
                      "s": (wx, wy + 1) in positions.values()}
        changed = False
        for cell in cells.values():
            if cell.loc != li:
                continue
            inside = x0 <= cell.x < x0 + 10 and y0 <= cell.y < y0 + 10
            if inside and (cell.tile != "village" or not cell.passable):
                cell.tile, cell.passable, changed = "village", True, True
            elif not inside:
                if cell.tile == "village":
                    cell.tile, changed = "grass", True
                if cell.npc >= 0:
                    cell.npc, changed = -1, True
            if cell.x in (0, size - 1) or cell.y in (0, size - 1):
                door = ((cell.y == 0 and cell.x == size // 2 and neighbours["w"]) or
                        (cell.y == size - 1 and cell.x == size // 2 and neighbours["e"]) or
                        (cell.x == 0 and cell.y == size // 2 and neighbours["n"]) or
                        (cell.x == size - 1 and cell.y == size // 2 and neighbours["s"]))
                wanted = "road" if door else "wall"
                if cell.tile != wanted or cell.passable != door:
                    cell.tile, cell.passable, changed = wanted, door, True
        fixed += int(changed)
    return fixed


class Store:
    def __init__(self, backend):
        self.backend = backend        # объект с get(key)/set(key, value)
        self.players = {}             # {tg_id: Player}
        self.world = {}               # {cellkey: Cell}
        self.settings = {"token": "", "seed": 1337, "welcome_bonus": 50,
                         "proxy_mode": "direct", "proxy_url": ""}
        self.load()
        # Шаблоны подземелий нужны и боту, и панели — заводим их здесь,
        # а не при рендере страницы, иначе бот их не увидит.
        self.settings.setdefault("dungeon_templates", default_dungeons())
        self.settings.setdefault("world_grid", dict(world.DEFAULT_GRID))
        # Размеры сеток локаций (угловые замки 25×25) — хранятся рядом с сеткой.
        self.settings.setdefault("world_sizes", dict(world.DEFAULT_SIZES))
        # Катаклизмы: живут в настройках, поэтому их видят и бот, и панель.
        self.settings.setdefault("seeds", {})
        self.settings.setdefault("cataclysms", [])
        self.settings.setdefault("cataclysm_auto", True)
        self.settings.setdefault("cataclysm_chance", 0.02)
        self.settings.setdefault("cataclysm_limit", 2)
        self.settings.setdefault("cataclysm_notify", True)
        # Осады: свои события в настройках — видны и боту, и панели (паритет
        # с серверной таблицей WorldEvent kind="siege").
        self.settings.setdefault("sieges", [])
        self.settings.setdefault("siege_auto", True)
        self.settings.setdefault("siege_chance", 0.012)
        # Обновления и предложения игроков — для паритета с серверным стеком
        self.settings.setdefault("updates", [])
        self.settings.setdefault("suggestions", [])

    # ── загрузка/сохранение ─────────────────────────────────
    def load(self):
        raw = self.backend.get("shadowlands")
        if raw:
            try:
                blob = json.loads(raw)
                self.settings.update(blob.get("settings", {}))
                # Кошелёк старых сейвов переносится в бронзу до создания
                # Player: см. engine/currency.migrate_raw (идемпотентно).
                from engine import currency as _currency
                self.players = {int(k): Player.from_dict(_currency.migrate_raw(v))
                                for k, v in blob.get("players", {}).items()}
                self.world = {k: Cell(**v) for k, v in blob.get("world", {}).items()}
                for c in self.world.values():
                    c.link = tuple(c.link)
                    c.floor_links = tuple(tuple(link) for link in c.floor_links)
            except Exception:
                self.players, self.world = {}, {}
        self.sync_locations()
        # Миграция старых localStorage: раньше каждый 25×25 замок рисовал
        # четыре village-квартала. Исправляем сохранённые клетки без сброса
        # игроков и ручных правок.
        if self.world:
            repaired = _repair_corner_castles(
                self.world, self.settings.get("world_grid"),
                self.settings.get("world_sizes"))
            if repaired:
                self.save()
        # Сетка мира должна существовать до первой генерации, иначе мир
        # соберётся цепочкой, а панель покажет другую раскладку. То же для
        # размеров сеток локаций (угловые замки 25×25).
        self.settings.setdefault("world_grid", dict(world.DEFAULT_GRID))
        self.settings.setdefault("world_sizes", dict(world.DEFAULT_SIZES))
        expected_floors = self.settings.get("location_floors", {}) or {}
        if self.world and _unify_floor_stairs(
                self.world, expected_floors, self.settings.get("world_sizes")):
            self.save()
        missing_floor = any(
            int(n or 1) > 1 and not any(
                c.loc == int(li) and c.floor == 1 for c in self.world.values()
            )
            for li, n in expected_floors.items()
        )
        if not self.world or missing_floor:
            self.regen_world()

    def sync_locations(self):
        """Список локаций — из настроек; data.LOCATIONS становится живым.

        Все потребители читают data.LOCATIONS через атрибут модуля, поэтому
        подмена содержимого видна сразу всему движку и панели.
        """
        saved = self.settings.get("locations")
        if saved:
            data.LOCATIONS[:] = [tuple(l) for l in saved]

    def _persist_locations(self):
        self.settings["locations"] = [list(l) for l in data.LOCATIONS]

    def save(self):
        blob = {
            "settings": self.settings,
            "players": {str(k): v.to_dict() for k, v in self.players.items()},
            "world": {k: _cell_dict(c) for k, c in self.world.items()},
        }
        self.backend.set("shadowlands", json.dumps(blob, ensure_ascii=False))

    def save_player(self, p):
        self.players[p.tg_id] = p
        self.save()

    # ── операции ────────────────────────────────────────────
    def seeds(self):
        """Все сиды мира: рельеф, тексты, мобы, сундуки, NPC, катаклизмы."""
        return world.seeds_of(self.settings)

    def set_seeds(self, values):
        """Сохранить частные сиды. Пустое/0 — вернуть к выводу из базового."""
        saved = self.settings.setdefault("seeds", {})
        for key in world.SEED_KEYS:
            if key not in values:
                continue
            try:
                val = int(values[key])
            except (TypeError, ValueError):
                val = 0
            if val:
                saved[key] = val
            else:
                saved.pop(key, None)
        self.save()
        return self.seeds()

    def regen_world(self, seed=None):
        if seed is not None:
            self.settings["seed"] = int(seed)
        grid = self.settings.get("world_grid")
        self.settings["cataclysms"] = []      # бедствия старого мира не переносим
        self.world = world.generate(self.settings["seed"], grid=grid,
                                    seeds=self.seeds(),
                                    floors=self.settings.get("location_floors", {}),
                                    sizes=self.settings.get("world_sizes", {}))
        self.save()

    def add_location(self, name, desc, ltype, min_level, wx, wy, floors=1):
        """Добавить локацию: достроить её клетки и вшить в швы сетки мира (одна дверь).

        Подуровни хранятся в settings['location_floors'] — визуально как стопка 🏢×N.
        Существующие локации и ручные правки их клеток не трогаются.
        Возвращает (индекс, отчёт о связывании с соседями).
        """
        li = len(data.LOCATIONS)
        data.LOCATIONS.append((name, desc, ltype, int(min_level)))
        self._persist_locations()
        grid = self.settings.setdefault("world_grid", dict(world.DEFAULT_GRID))
        grid[str(li)] = [int(wx), int(wy)]
        # подуровни
        try:
            f = int(floors)
        except Exception:
            f = 1
        f = max(1, min(10, f))
        self.settings.setdefault("location_floors", {})[str(li)] = f
        sd = self.seeds()
        rnd = random.Random(sd["terrain"] + li * 7919)
        sizes = self.settings.setdefault("world_sizes", dict(world.DEFAULT_SIZES))
        if world.is_castle(data.LOCATIONS, li):
            sizes[str(li)] = 25
            corner = ("ne" if wx >= 5 and wy < 5 else
                      "sw" if wx < 5 and wy >= 5 else
                      "se" if wx >= 5 and wy >= 5 else "nw")
            batch, _ = world.gen_castle_cells(
                li, rnd, 25, story_rnd=random.Random(sd["stories"] + li),
                castle_corner=corner)
        else:
            batch, _ = world.gen_cells(li, rnd,
                                       story_rnd=random.Random(sd["stories"] + li))
        for c in batch:
            self.world[c.key] = c
        report = world.link_new_location(self.world, li, grid, sizes)
        if f > 1:
            # Пересобираем только при создании многоэтажной локации: так
            # лестницы появляются сразу, а обычное добавление сохраняет
            # прежний щадящий путь.
            self.regen_world()
            report.append(f"🪜 Лестницы между этажами созданы: {f}")
        else:
            self.save()
        return li, report

    def update_location(self, li, name, desc, ltype, min_level, floors=None):
        """Правка свойств существующей локации.

        Клетки и швы не трогаем: меняются только имя, описание, тип, порог
        уровня и число этажей. Индекс локации сохраняется, поэтому ссылки
        из клеток, порталов и позиций игроков остаются валидными.
        """
        li = int(li)
        if not (0 <= li < len(data.LOCATIONS)):
            return "Локация не найдена."
        old = data.LOCATIONS[li]
        name = (name or "").strip() or old[0]
        desc = (desc or "").strip() or old[1]
        ltype = ltype if ltype in ("safe", "dangerous", "dungeon", "boss") else old[2]
        try:
            lvl = max(1, int(min_level))
        except (TypeError, ValueError):
            lvl = old[3]
        data.LOCATIONS[li] = (name, desc, ltype, lvl)
        self._persist_locations()
        floors_changed = False
        if floors is not None:
            try:
                f = max(1, min(10, int(floors)))
            except (TypeError, ValueError):
                f = 1
            floors_map = self.settings.setdefault("location_floors", {})
            floors_changed = int(floors_map.get(str(li), 1) or 1) != f
            floors_map[str(li)] = f
        # Сетка существующей локации не пересобирается при обычной правке:
        # это сохраняет ручные клетки и швы. Новые этажи применяются при
        # следующей полной генерации мира (кнопка «Пересобрать мир»).
        self.save()
        changed = [w for w, a, b in (("название", old[0], name),
                                     ("описание", old[1], desc),
                                     ("тип", old[2], ltype),
                                     ("уровень", old[3], lvl)) if a != b]
        return (f"Локация «{name}» обновлена"
                + (f": {', '.join(changed)}." if changed else " (без изменений)."))

    def remove_location(self, li):
        """Удалить локацию: реиндексация клеток/игроков/швов/порталов.

        Ручные правки остальных локаций сохраняются. Игроки из удалённой
        локации переносятся на спавн нулевой. Возвращает текст отчёта.
        """
        if li < 0 or li >= len(data.LOCATIONS):
            return "Локация не найдена."
        if len(data.LOCATIONS) <= 1:
            return "Нельзя удалить последнюю локацию мира."
        name = data.LOCATIONS[li][0]

        # Бедствия держат слепки клеток по старым индексам — гасим до сдвига.
        from engine import cataclysm
        for ev in list(cataclysm.active(self, None)):
            cataclysm.end(self, ev["id"], revert=True, actor="Система")

        # игроки: из удаляемой — на спавн, из следующих — сдвиг индекса
        moved = 0
        for p in self.players.values():
            if p.loc == li:
                p.loc, p.floor, p.x, p.y = 0, 0, world.SPAWN[0], world.SPAWN[1]
                moved += 1
            elif p.loc > li:
                p.loc -= 1

        # клетки и швы
        reborn = {}
        for c in self.world.values():
            if c.loc == li:
                continue
            if c.loc > li:
                c.loc -= 1
            if c.link:
                l, x, y = c.link[:3]
                tail = c.link[3:]
                if l == li:
                    c.link = ()
                elif l > li:
                    c.link = (l - 1, x, y, *tail)
            shifted_floor_links = []
            for link in c.floor_links:
                l, x, y, floor = link[:4]
                if l == li:
                    continue
                shifted_floor_links.append(
                    (l - 1 if l > li else l, x, y, floor)
                )
            c.floor_links = tuple(shifted_floor_links)
            reborn[c.key] = c
        self.world = reborn

        # сетка мира: убрать удалённую, сдвинуть ключи
        grid = self.settings.setdefault("world_grid", dict(world.DEFAULT_GRID))
        grid.pop(str(li), None)
        self.settings["world_grid"] = {
            str(int(k) - 1 if int(k) > li else k): v for k, v in grid.items()}
        # размеры сеток (угловые замки) — реиндексация как у сетки
        sizes_map = self.settings.get("world_sizes", {})
        sizes_map.pop(str(li), None)
        self.settings["world_sizes"] = {
            str(int(k) - 1 if int(k) > li else k): v for k, v in sizes_map.items()}
        # подуровни
        floors_map = self.settings.get("location_floors", {})
        floors_map.pop(str(li), None)
        self.settings["location_floors"] = {
            str(int(k) - 1 if int(k) > li else k): v for k, v in floors_map.items()}

        # порталы подземелий, открытые в удалённой локации, закрываем
        for t in self.settings.get("dungeon_templates", []):
            key = t.get("portal_cell")
            if key:
                l = int(key.split(":")[0])
                if l == li:
                    t["portal_cell"] = None
                elif l > li:
                    t["portal_cell"] = f"{l - 1}:{key.split(':', 1)[1]}"

        data.LOCATIONS.pop(li)
        self._persist_locations()
        self.save()
        note = f" Игроки перенесены на спавн: {moved}." if moved else ""
        return f"Локация «{name}» удалена, мир переиндексирован.{note}"

    def player(self, tg_id, name=""):
        p = self.players.get(tg_id)
        if not p:
            p = Player(tg_id=tg_id, name=name or f"Герой{tg_id % 1000}")
            self.players[tg_id] = p
        elif name and p.name.startswith("Герой"):
            p.name = name
        return p

    def wipe_players(self):
        self.players = {}
        self.save()

    def stats(self):
        ps = list(self.players.values())
        made = [p for p in ps if p.created_char]
        return {
            "players": len(ps),
            "heroes": len(made),
            # Богатство сервера — в бронзе: поле gold теперь лишь старший
            # разряд кошелька, суммировать только его было бы неверно.
            "gold": sum(_wallet_total(p) for p in made),
            "kills": sum(p.kills for p in made),
            "avg_level": round(sum(p.level for p in made) / len(made), 1) if made else 0,
            "cells": len(self.world),
        }


def default_dungeons():
    return [
        {"id": 0, "name": "🔥 Огненная Преисподняя",
         "desc": "Пещеры, заполненные лавой и демонами.",
         "min_level": 5, "grid_size": 15, "portal_cell": None},
        {"id": 1, "name": "🕸 Забытый Склеп Пауков",
         "desc": "Гробница древнего короля, затянутая густой паутиной.",
         "min_level": 3, "grid_size": 12, "portal_cell": None},
    ]


def _cell_dict(c):
    return dict(loc=c.loc, floor=c.floor, x=c.x, y=c.y, name=c.name, desc=c.desc, tile=c.tile,
                passable=c.passable, mob=c.mob, npc=c.npc, chest=c.chest,
                link=list(c.link), floor_links=[list(link) for link in c.floor_links],
                mob_at=c.mob_at, chest_at=c.chest_at)
