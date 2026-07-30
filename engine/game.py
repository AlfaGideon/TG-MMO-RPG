"""Роутер бота: команда/callback -> Reply. Не знает ничего про Telegram."""
import random

from engine import (adminbot, adminroute, behavior, cataclysm, combat, data,
                    explore, hero, inventory, items, mapview, respawn, rules,
                    shop, social, texts, trade, world)
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
            [("📜 Задания", "quests"), ("🤝 Отряд", "party")],
            [("🧭 Репутация", "rep")],
            [("🔨 Мастерская", "craft"), ("🏛 Аукцион", "auc:0")],
            [("🏆 Топ", "top"), ("❓ Помощь", "help")],
        ]
        if social.boss_alive(self.store):
            rows.insert(0, [("🏰 Мировой босс!", "boss")])
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
        if social.in_dungeon(p):          # внутри подземелья свой мир
            return social.dungeon_view(self.store, p)
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
        alarm = cataclysm.banner(self.store, p.loc)
        if alarm:
            rows.insert(0, [("🌋 Что происходит?", "disaster")])
        here = mapview.others_here(self.store, p, p.loc, p.x, p.y)
        return Reply(text=texts.cell_view(p, cell, alarm, here), keyboard=rows)

    do_wall = lambda self, p, arg="": Reply(alert="Туда нельзя пройти.")

    def do_go(self, p, d):
        if p.combat:
            return Reply(alert="Сначала закончи бой!")
        dx, dy = world.DIRS.get(d, (0, 0))
        target = world.cell_at(self.world, p.loc, p.x + dx, p.y + dy)
        if not target or not target.passable:
            return Reply(alert="Туда нельзя пройти!")
        warn = ""
        if target.link:
            # Предупреждение по min_level: вход разрешён, но игрок видит alert.
            dest = data.LOCATIONS[target.link[0]] if target.link[0] < len(data.LOCATIONS) else None
            if dest and dest[3] > p.level:
                warn = (f"⚠️ {dest[0]} — опасно! Рекомендуется {dest[3]}+ уровень, "
                        f"у тебя {p.level}. Ты входишь на свой страх и риск…")
            p.loc, p.x, p.y = target.link
            social.on_enter(p, p.loc)        # разведка засчитана
        else:
            p.x, p.y = target.x, target.y
        mapview.mark_visited(p)
        cataclysm.auto(self.store)           # мир может тряхнуть на ходу
        respawn.tick(self.store)             # твари и сундуки возвращаются
        cell = self._cell(p)
        rate = min(0.98, 0.75 * cataclysm.effects(self.store, p.loc)["mob_rate"])
        # Твари живут своей жизнью: бродят и сами решают напасть. В беду
        # к этому добавляется засада орды.
        ambusher = behavior.tick(self.store, p)
        if ambusher is None:
            ambusher = cataclysm.prowl(self.store, p)
        if ambusher is not None:             # тварь бросилась сама
            r = combat.start(p, ambusher, ambush=True, store=self.store)
        elif cell.mob >= 0 and random.random() < rate:
            r = combat.start(p, cell.mob)
        else:
            r = self.do_world(p)
        if warn and not r.alert:
            r.alert = warn
        return r

    # ── отряд, могилы, задания ──────────────────────────────
    # Экраны живут в engine/social.py; здесь только имена команд, чтобы
    # роутер оставался оглавлением, а не свалкой логики.
    do_party = lambda self, p, arg="": social.party_card(self.store, p)
    do_pnew = lambda self, p, arg="": social.party_new(self.store, p)
    do_pjoin = lambda self, p, arg="": social.party_join(self.store, p)
    do_pno = lambda self, p, arg="": social.party_no(self.store, p)
    do_pleave = lambda self, p, arg="": social.party_leave(self.store, p)
    do_pnoop = lambda self, p, arg="": social.party_hint()
    do_invite = lambda self, p, arg="": social.party_invite(self.store, p, arg)
    do_grave = lambda self, p, arg="": social.grave(self.store, p)
    do_claim = lambda self, p, arg="": social.claim(self.store, p)
    do_quests = lambda self, p, arg="": social.journal(p)
    do_qtake = lambda self, p, arg: social.quest_take(self.store, p, arg)
    do_qdrop = lambda self, p, arg: social.quest_drop(self.store, p, arg)
    do_qdone = lambda self, p, arg: social.quest_done(self.store, p, arg)
    do_qcard = lambda self, p, arg: social.quest_card(p, arg)

    def do_disaster(self, p, arg=""):
        """Карточка бедствий, накрывших землю под ногами игрока."""
        return cataclysm.card(self.store, p.loc)

    def do_map(self, p, arg=""):
        mapview.mark_visited(p)
        self.store.save_player(p)
        return mapview.render(p, self.world, self.store)

    def do_look(self, p, arg=""):
        return explore.look(p, self._cell(p), self.store)

    def do_hunt(self, p, arg):
        cell = self._cell(p)
        if cell.mob < 0:
            return Reply(alert="Враг уже мёртв.")
        return combat.start(p, cell.mob)

    def do_fight(self, p, what):
        return combat.action(p, what, self.world, self.store)

    def do_talk(self, p, arg):
        return explore.talk(arg, p)

    def do_heal(self, p, arg=""):
        return explore.heal(p)

    def do_chest(self, p, arg=""):
        return explore.chest(p, self._cell(p), self.store)

    def do_rest(self, p, arg=""):
        return explore.rest(p, self.store)

    # ── инвентарь (реализация в engine/inventory.py) ────────
    # Сумка и экипировка: обёртки над engine/inventory.py.
    do_bag = lambda self, p, arg="": inventory.bag(p, 0, self.store)
    do_bagp = lambda self, p, arg="0": inventory.bag(p, arg or 0, self.store)
    do_it = lambda self, p, arg: inventory.card(p, arg, self.store)
    do_on = lambda self, p, arg: inventory.equip(p, arg)
    do_off = lambda self, p, arg: inventory.unequip(p, arg)
    do_use = lambda self, p, arg: inventory.use(p, arg)
    do_sell = lambda self, p, arg: inventory.sell(p, arg)
    do_toss = lambda self, p, arg: inventory.toss(p, arg)

    # ── подземелья ──────────────────────────────────────────
    do_denter = lambda self, p, arg="": social.dungeon_enter(self.store, p)
    do_dview = lambda self, p, arg="": social.dungeon_view(self.store, p)
    do_dgo = lambda self, p, arg: social.dungeon_move(self.store, p, arg)
    do_dfight = lambda self, p, arg="": social.dungeon_fight(self.store, p)
    do_dchest = lambda self, p, arg="": social.dungeon_chest(self.store, p)
    do_ddown = lambda self, p, arg="": social.dungeon_down(self.store, p)
    do_dexit = lambda self, p, arg="": social.dungeon_exit(self.store, p)
    do_dmap = lambda self, p, arg="": social.dungeon_map(self.store, p)
    do_dwall = lambda self, p, arg="": Reply(alert="Там глухая стена.")

    do_rep = lambda self, p, arg="": social.reputation(self.store, p)
    do_boss = lambda self, p, arg="": social.boss(self.store, p)
    do_bosshit = lambda self, p, arg="": social.boss_hit(self.store, p)
    do_study = lambda self, p, arg="": social.study(self.store, p, self._cell(p))

    # ── защищённый карман ───────────────────────────────────
    def do_stash(self, p, arg=""):
        return social.stash_view(self.store, p)

    def do_stput(self, p, arg):
        return social.stash_put(self.store, p, arg)

    def do_stake(self, p, arg):
        return social.stash_take(self.store, p, arg)

    # ── лавка (реализация в engine/shop.py) ─────────────────
    # Лавка и скупка: обёртки над engine/shop.py.
    do_shop = lambda self, p, arg="0": shop.shop(p, arg or 0)
    do_buyc = lambda self, p, arg: shop.buy_card(p, arg)
    do_buy = lambda self, p, arg: shop.buy(p, arg)
    do_sellbag = lambda self, p, arg="0": shop.sell_list(p, arg or 0)
    do_sellc = lambda self, p, arg: shop.sell_card(p, arg)
    do_sells = lambda self, p, arg: shop.sell_here(p, arg)
    do_noop = lambda self, p, arg="": Reply(alert="")

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
