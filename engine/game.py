"""Роутер бота: команда/callback -> Reply. Не знает ничего про Telegram."""
import random

from engine import (adminbot, adminroute, combat, data, hero, inventory,
                    items, mapview, rules, shop, texts, trade, world)
from engine.models import Reply


class Game:
    def __init__(self, store):
        self.store = store          # engine.storage.Store
        self.world = store.world    # {key: Cell}

    # ── вход ────────────────────────────────────────────────
    def handle(self, p, action):
        if action in ("start", "menu"):
            return self.menu(p)
        head, _, arg = action.partition(":")
        if trade.handles(head):            # мастерская, заточка, аукцион
            return trade.route(self.store, p, head, arg)
        fn = getattr(self, f"do_{head}", None)
        if fn is None:
            return Reply(alert="Неизвестная команда.")
        return fn(p, arg) if arg or ":" in action else fn(p)

    # ── меню и персонаж ─────────────────────────────────────
    def menu(self, p):
        if not p.created_char:
            return Reply(text=texts.WELCOME, keyboard=[
                [("⚔️ Создать героя", "new")], [("❓ Помощь", "help")]])
        rows = [
            [("🧭 В мир", "world"), ("🧙 Профиль", "profile")],
            [("🎒 Инвентарь", "bag"), ("🏪 Лавка", "shop")],
            [("🔨 Мастерская", "craft"), ("🏛 Аукцион", "auc:0")],
            [("🏆 Топ", "top"), ("❓ Помощь", "help")],
        ]
        if p.is_web_admin:
            rows.insert(0, [("🛠 Админка", "admin")])
        return Reply(text=texts.WELCOME + f"\n\n👤 {p.name}, ур. {p.level}", keyboard=rows)

    # ── админский доступ внутри бота ────────────────────────
    def do_admin(self, p, arg=""):
        return adminbot.panel(p, self.store)

    def do_adminpass(self, p, arg=""):
        return adminbot.password(p, self.store)

    def do_adm(self, p, arg=""):
        """Все админ-кнопки бота: adm:<команда>[:аргументы]."""
        return adminroute.handle(p, self.store, arg)

    def text_input(self, p, text):
        """Свободный ввод текста. Сейчас нужен только для рассылки."""
        return adminroute.text_input(p, self.store, text)

    def do_help(self, p, arg=""):
        return Reply(text=texts.HELP, keyboard=[[("◀️ Меню", "menu")]])

    def do_new(self, p, arg=""):
        if p.created_char:
            return Reply(alert="У тебя уже есть герой!")
        rows = [[(data.CLASSES[c][0], f"pick:{c}")] for c in data.CLASSES]
        rows.append([("◀️ Назад", "menu")])
        return Reply(text="Выбери класс своего героя:", keyboard=rows)

    def do_pick(self, p, cls):
        """Выбран класс — сразу катаем стартовые статы и дар к магии."""
        if cls not in data.CLASSES:
            return Reply(alert="Нет такого класса.")
        p.rolls = hero.DEFAULT_REROLLS
        return self._roll(p, cls)

    def do_reroll(self, p, cls):
        """Перекат статов: тратим попытку, пока они есть."""
        if p.created_char:
            return Reply(alert="Герой уже создан!")
        if int(getattr(p, "rolls", 0) or 0) <= 0:
            return Reply(alert="Попытки переката кончились.")
        p.rolls = int(p.rolls) - 1
        return self._roll(p, cls)

    def _roll(self, p, cls):
        """Новый бросок статов и магии, показ карточки предпросмотра."""
        rolled = hero.roll_stats(cls)
        magic = hero.roll_magic(cls)
        p.roll_state = {"cls": cls, "stats": rolled, "magic": magic}
        self.store.save_player(p)
        return Reply(text=texts.roll_view(p, cls, rolled, magic),
                     keyboard=self._roll_keys(p, cls))

    @staticmethod
    def _roll_keys(p, cls):
        left = int(getattr(p, "rolls", 0) or 0)
        rows = [[("✅ Принять судьбу", f"make:{cls}")]]
        if left > 0:
            rows.append([(f"🎲 Перекатить ({left})", f"reroll:{cls}")])
        rows.append([("◀️ Другой класс", "new")])
        return rows

    def do_make(self, p, cls):
        if p.created_char:
            return Reply(alert="Герой уже создан!")
        if cls not in data.CLASSES:
            return Reply(alert="Нет такого класса.")
        state = getattr(p, "roll_state", None) or {}
        if state.get("cls") != cls:
            # Прямой заход мимо переката (тесты, админ-выдача): берём базу
            # класса как есть — без случайности, чтобы результат был предсказуем.
            state = {"stats": hero.base_stats(cls), "magic": hero.roll_magic(cls)}
        hero.apply(p, cls, state.get("stats") or {}, state.get("magic") or [])
        mapview.mark_visited(p)
        self.store.save_player(p)
        return Reply(text=texts.hero_created(p, cls),
                     keyboard=[[("🧭 В мир", "world")], [("◀️ Меню", "menu")]])

    def do_profile(self, p, arg=""):
        if not p.created_char:
            return Reply(alert="Сначала создай героя!")
        return Reply(text=texts.profile(p, self.store), keyboard=[
            [("🎒 Инвентарь", "bag"), ("🧭 В мир", "world")], [("◀️ Меню", "menu")]])

    # ── мир ─────────────────────────────────────────────────
    def _cell(self, p):
        return world.cell_at(self.world, p.loc, p.x, p.y)

    def do_world(self, p, arg=""):
        if not p.created_char:
            return Reply(alert="Сначала создай героя!")
        if p.combat:
            return combat.view(p)
        cell = self._cell(p)
        if not cell:
            p.loc, p.x, p.y = 0, 5, 5
            cell = self._cell(p)
        mapview.mark_visited(p)
        ok = world.neighbours(self.world, p.loc, p.x, p.y)
        rows = []
        for line in (("nw", "n", "ne"), ("w", None, "e"), ("sw", "s", "se")):
            row = []
            for d in line:
                if d is None:
                    row.append(("🔍", "look"))
                elif ok.get(d):
                    row.append((world.ARROWS[d], f"go:{d}"))
                else:
                    row.append(("⬛", "wall"))
            rows.append(row)
        rows.append([("🏕 Отдых", "rest"), ("🎒 Инвентарь", "bag")])
        rows.append([("🗺 Карта", "map"), ("◀️ Меню", "menu")])
        return Reply(text=texts.cell_view(p, cell), keyboard=rows)

    def do_wall(self, p, arg=""):
        return Reply(alert="Туда нельзя пройти.")

    def do_go(self, p, d):
        if p.combat:
            return Reply(alert="Сначала закончи бой!")
        dx, dy = world.DIRS.get(d, (0, 0))
        target = world.cell_at(self.world, p.loc, p.x + dx, p.y + dy)
        if not target or not target.passable:
            return Reply(alert="Туда нельзя пройти!")
        if target.link:
            p.loc, p.x, p.y = target.link
        else:
            p.x, p.y = target.x, target.y
        mapview.mark_visited(p)
        cell = self._cell(p)
        if cell.mob >= 0 and random.random() < 0.75:
            return combat.start(p, cell.mob)
        return self.do_world(p)

    def do_map(self, p, arg=""):
        mapview.mark_visited(p)
        self.store.save_player(p)
        return mapview.render(p, self.world, self.store)

    def do_look(self, p, arg=""):
        cell = self._cell(p)
        found, rows = [], []
        if cell.mob >= 0:
            found.append(f"👾 Враг: {data.MOBS[cell.mob][0]} (ур. {data.MOBS[cell.mob][2]})")
            rows.append([("⚔️ Атаковать", f"hunt:{cell.mob}")])
        if cell.npc >= 0:
            n = data.NPCS[cell.npc]
            found.append(f"💬 {n[0]}")
            rows.append([("💬 Поговорить", f"talk:{cell.npc}")])
        if cell.chest:
            found.append("📦 Сундук!")
            rows.append([("📦 Открыть", "chest")])
        body = "\n".join(found) if found else f"<i>{random.choice(data.EMPTY_LOOK)}</i>"
        rows.append([("◀️ Назад", "world")])
        return Reply(text=f"🔍 <b>Осмотр [{cell.x},{cell.y}]</b>\n<i>{cell.name}</i>\n\n"
                          f"{cell.desc}\n\n{body}", keyboard=rows)

    def do_hunt(self, p, arg):
        cell = self._cell(p)
        if cell.mob < 0:
            return Reply(alert="Враг уже мёртв.")
        return combat.start(p, cell.mob)

    def do_fight(self, p, what):
        return combat.action(p, what, self.world, self.store)

    def do_talk(self, p, arg):
        n = data.NPCS[int(arg)]
        rows = []
        if n[2] == "merchant":
            rows.append([("🛒 Торговать", "shop")])
        if n[2] == "healer":
            rows.append([("💊 Исцелиться", "heal")])
        rows.append([("◀️ Назад", "world")])
        return Reply(text=f"💬 <b>{n[0]}</b>\n\n<i>{n[1]}</i>", keyboard=rows)

    def do_heal(self, p, arg=""):
        s = rules.stats(p)
        p.hp, p.mp = s["max_hp"], s["max_mp"]
        return Reply(text="💊 Лекарь Мира кладёт ладонь тебе на лоб.\n\n"
                          "❤️ Здоровье и мана полностью восстановлены.",
                     keyboard=[[("◀️ В мир", "world")]])

    def do_chest(self, p, arg=""):
        cell = self._cell(p)
        if not cell.chest:
            return Reply(alert="Сундук уже пуст.")
        cell.chest = False
        gold = random.randint(10, 45)
        p.gold += gold
        lines = [f"📦 <b>Сундук открыт!</b>\n\nВнутри: {gold} 🪙"]
        if random.random() < 0.5:
            idx = random.randrange(len(data.ITEMS))
            p.inventory.append(idx)
            inst = items.create(self.store, idx, source="chest", owner=p.tg_id,
                                luck=p.luck, detail="сундук")
            if inst is not None:
                lines.append(f"И ещё: {inst['icon']} <b>{items.title(inst)}</b>")
                lines.append(f"   <code>{items.tag(inst)}</code> · {items.stats_line(inst)}")
            else:
                it = rules.item(idx)
                lines.append(f"И ещё: {it['icon']} {it['name']}")
        return Reply(text="\n".join(lines), keyboard=[[("◀️ В мир", "world")]])

    def do_rest(self, p, arg=""):
        s = rules.stats(p)
        hp = max(1, s["max_hp"] // 3)
        mp = max(1, s["max_mp"] // 3)
        p.hp = min(s["max_hp"], p.hp + hp)
        p.mp = min(s["max_mp"], p.mp + mp)
        return Reply(text=(f"🏕 <b>Привал</b>\n\nТы отдохнул у костра.\n"
                           f"❤️ +{hp} HP · 💙 +{mp} MP\n\n"
                           f"Сейчас: {p.hp}/{s['max_hp']} HP"),
                     keyboard=[[("◀️ В мир", "world")]])

    # ── инвентарь (реализация в engine/inventory.py) ────────
    def do_bag(self, p, arg=""):
        return inventory.bag(p, 0)

    def do_bagp(self, p, arg="0"):
        return inventory.bag(p, arg or 0)

    def do_it(self, p, arg):
        return inventory.card(p, arg)

    def do_on(self, p, arg):
        return inventory.equip(p, arg)

    def do_off(self, p, arg):
        return inventory.unequip(p, arg)

    def do_use(self, p, arg):
        return inventory.use(p, arg)

    def do_sell(self, p, arg):
        return inventory.sell(p, arg)

    def do_toss(self, p, arg):
        return inventory.toss(p, arg)

    # ── лавка (реализация в engine/shop.py) ─────────────────
    def do_shop(self, p, arg="0"):
        return shop.shop(p, arg or 0)

    def do_buyc(self, p, arg):
        return shop.buy_card(p, arg)

    def do_buy(self, p, arg):
        return shop.buy(p, arg)

    def do_sellbag(self, p, arg="0"):
        return shop.sell_list(p, arg or 0)

    def do_sellc(self, p, arg):
        return shop.sell_card(p, arg)

    def do_sells(self, p, arg):
        return shop.sell_here(p, arg)

    def do_noop(self, p, arg=""):
        return Reply(alert="")

    # ── топ ─────────────────────────────────────────────────
    def do_top(self, p, arg=""):
        rows = sorted(self.store.players.values(),
                      key=lambda q: (q.level, q.exp), reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
        lines = ["🏆 <b>Топ героев</b>\n"]
        for i, q in enumerate(rows):
            lines.append(f"{medals[i]} {q.name} — ур. {q.level} · {q.gold}🪙")
        if len(lines) == 1:
            lines.append("<i>Пока пусто.</i>")
        return Reply(text="\n".join(lines), keyboard=[[("◀️ Меню", "menu")]])
