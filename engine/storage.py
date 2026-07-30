"""Хранилище состояния. Бэкенд подставляется снаружи (localStorage / файл)."""
import json
import random

from engine import data, world
from engine.models import Cell, Player


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
        # Катаклизмы: живут в настройках, поэтому их видят и бот, и панель.
        self.settings.setdefault("seeds", {})
        self.settings.setdefault("cataclysms", [])
        self.settings.setdefault("cataclysm_auto", True)
        self.settings.setdefault("cataclysm_chance", 0.02)
        self.settings.setdefault("cataclysm_limit", 2)
        self.settings.setdefault("cataclysm_notify", True)

    # ── загрузка/сохранение ─────────────────────────────────
    def load(self):
        raw = self.backend.get("shadowlands")
        if raw:
            try:
                blob = json.loads(raw)
                self.settings.update(blob.get("settings", {}))
                self.players = {int(k): Player.from_dict(v)
                                for k, v in blob.get("players", {}).items()}
                self.world = {k: Cell(**v) for k, v in blob.get("world", {}).items()}
                for c in self.world.values():
                    c.link = tuple(c.link)
            except Exception:
                self.players, self.world = {}, {}
        self.sync_locations()
        # Сетка мира должна существовать до первой генерации, иначе мир
        # соберётся цепочкой, а панель покажет другую раскладку.
        self.settings.setdefault("world_grid", dict(world.DEFAULT_GRID))
        if not self.world:
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
                                    seeds=self.seeds())
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
        batch, _ = world.gen_cells(li, rnd, story_rnd=random.Random(sd["stories"] + li))
        for c in batch:
            self.world[c.key] = c
        report = world.link_new_location(self.world, li, grid)
        if f>1:
            report.append(f"🏢 Подуровней: {f} (визуально стопка на сетке)")
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
        if floors is not None:
            try:
                f = max(1, min(10, int(floors)))
            except (TypeError, ValueError):
                f = 1
            self.settings.setdefault("location_floors", {})[str(li)] = f
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
                p.loc, p.x, p.y = 0, world.SPAWN[0], world.SPAWN[1]
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
                l, x, y = c.link
                if l == li:
                    c.link = ()
                elif l > li:
                    c.link = (l - 1, x, y)
            reborn[c.key] = c
        self.world = reborn

        # сетка мира: убрать удалённую, сдвинуть ключи
        grid = self.settings.setdefault("world_grid", dict(world.DEFAULT_GRID))
        grid.pop(str(li), None)
        self.settings["world_grid"] = {
            str(int(k) - 1 if int(k) > li else k): v for k, v in grid.items()}
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
            "gold": sum(p.gold for p in made),
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
    return dict(loc=c.loc, x=c.x, y=c.y, name=c.name, desc=c.desc, tile=c.tile,
                passable=c.passable, mob=c.mob, npc=c.npc, chest=c.chest,
                link=list(c.link), mob_at=c.mob_at, chest_at=c.chest_at)
