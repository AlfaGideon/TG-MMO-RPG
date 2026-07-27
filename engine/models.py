"""Модели состояния игры (dataclasses, сериализуемые в dict)."""
from dataclasses import dataclass, field, asdict


@dataclass
class Cell:
    loc: int
    x: int
    y: int
    name: str = ""
    desc: str = ""
    tile: str = "grass"
    passable: bool = True
    mob: int = -1            # индекс в data.MOBS, -1 = нет
    npc: int = -1            # индекс в data.NPCS
    chest: bool = False
    link: tuple = ()         # (loc, x, y) — бесшовный переход

    @property
    def key(self):
        return f"{self.loc}:{self.x}:{self.y}"


@dataclass
class Player:
    tg_id: int
    name: str = "Изгнанник"
    cls: str = ""
    level: int = 1
    exp: int = 0
    gold: int = 50
    strength: int = 10
    agility: int = 10
    intelligence: int = 10
    endurance: int = 10
    luck: int = 10
    max_hp: int = 100
    hp: int = 100
    max_mp: int = 50
    mp: int = 50
    loc: int = 0
    x: int = 5
    y: int = 5
    inventory: list = field(default_factory=list)   # [item_index, ...]
    equipped: dict = field(default_factory=dict)    # {slot: item_index}
    kills: int = 0
    combat: dict = field(default_factory=dict)      # активный бой
    msg_id: int = 0                                 # id сообщения для edit
    created: str = ""

    @property
    def created_char(self):
        return bool(self.cls)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Reply:
    """Ответ движка: что показать игроку."""
    text: str = ""
    keyboard: list = field(default_factory=list)   # [[(label, data), ...], ...]
    alert: str = ""                                # всплывающее уведомление
    new_message: bool = False                      # отправить новым сообщением
