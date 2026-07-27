"""Хранилище состояния. Бэкенд подставляется снаружи (localStorage / файл)."""
import json

from engine import world
from engine.models import Cell, Player


class Store:
    def __init__(self, backend):
        self.backend = backend        # объект с get(key)/set(key, value)
        self.players = {}             # {tg_id: Player}
        self.world = {}               # {cellkey: Cell}
        self.settings = {"token": "", "seed": 1337, "welcome_bonus": 50,
                         "proxy_mode": "direct", "proxy_url": ""}
        self.load()

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
        if not self.world:
            self.regen_world()

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
    def regen_world(self, seed=None):
        if seed is not None:
            self.settings["seed"] = int(seed)
        self.world = world.generate(self.settings["seed"])
        self.save()

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


def _cell_dict(c):
    return dict(loc=c.loc, x=c.x, y=c.y, name=c.name, desc=c.desc, tile=c.tile,
                passable=c.passable, mob=c.mob, npc=c.npc, chest=c.chest,
                link=list(c.link))
