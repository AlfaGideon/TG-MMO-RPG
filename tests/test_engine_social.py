"""Перенос в браузерный стек: арена, гильдии, наставничество, награды.

Запуск: python3 tests/test_engine_social.py

Раздел 2 `IDEAS-100.md` (пункты 26–31) — последняя группа. Здесь главная
сложность в том, что механики про **отношения между игроками**, а в
браузерном стеке нет сервера, сводящего двоих в реальном времени.

Решение: арена работает по «теням» — слепкам чужих героев, поэтому
соперник не обязан быть онлайн. Гильдии и наставничество живут в общем
`store`, где все игроки уже видны друг другу.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import arena, bounty, currency, guilds, illusions
from engine.game import Game
from engine.storage import Store
from webapp.backend import MemoryStorage

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _hero(store, game, tg_id, name, cls="warrior", level=1, money=0):
    p = store.player(tg_id, name)
    game.handle(p, f"make:{cls}")
    p.level = level
    if money:
        currency.earn(p, money)
    return p


def main():
    random.seed(12)
    store = Store(MemoryStorage())
    game = Game(store)

    print("\n— Арена: бой с тенью, соперник не обязан быть онлайн —")
    a = _hero(store, game, 1, "Гидеон", level=12)
    b = _hero(store, game, 2, "Мара", "mage", level=11)
    check(not arena.opponents(store, a), "теней ещё нет")

    arena.update_shadow(store, b)
    foes = arena.opponents(store, a)
    check(len(foes) == 1 and foes[0]["name"] == "Мара", "чужая тень появилась")
    check(all(int(f["owner"]) != a.tg_id for f in arena.opponents(store, a)),
          "своей тени среди соперников нет")

    # Свой слепок появляется при заходе на арену — только после этого
    # осмысленно проверять запрет драться с самим собой.
    game.handle(a, "arena")
    r = game.handle(a, f"arenago:{a.tg_id}")
    check("своей тенью" in (r.alert or "").lower(), "с собой драться нельзя")
    check(game.handle(a, "arenago:99999").alert is not None,
          "несуществующая тень отклонена")

    rating_before = a.arena_rating
    res = arena.duel(store, a, arena.find_shadow(store, b.tg_id))
    check(res["rounds"] >= 1 and res["log"], "бой прошёл и записан в лог")
    check(a.gladiator_tokens > 0, "жетоны начислены в любом случае")
    if res["victory"]:
        check(a.arena_rating == rating_before + arena.WIN_RATING,
              f"рейтинг вырос: {rating_before} → {a.arena_rating}")
    else:
        check(a.arena_rating == rating_before + arena.LOSS_RATING,
              f"рейтинг снизился: {rating_before} → {a.arena_rating}")

    # Рейтинг не падает ниже пола — иначе новичка невозможно догнать.
    loser = _hero(store, game, 3, "Слабак", level=1)
    loser.arena_rating = arena.MIN_RATING
    for _ in range(5):
        arena.duel(store, loser, arena.find_shadow(store, b.tg_id))
    check(loser.arena_rating >= arena.MIN_RATING,
          f"рейтинг не ушёл ниже {arena.MIN_RATING}")

    print("\n— Гильдия: основание, вступление, казна —")
    founder = _hero(store, game, 4, "Основатель", level=10, money=100)
    r = game.handle(founder, "guildnew")
    check("хватает" in (r.alert or "").lower(), "без денег гильдию не основать")
    check(guilds.guild_of(store, founder)[0] is None, "гильдия не создана")

    currency.earn(founder, guilds.CREATE_COST)
    money_before = currency.total(founder)
    game.handle(founder, "guildnew")
    g, role = guilds.guild_of(store, founder)
    check(g is not None and role == "leader", "основатель стал главой")
    check(currency.total(founder) == money_before - guilds.CREATE_COST,
          "деньги списаны ровно по цене")
    check(g["treasury"] == guilds.START_TREASURY, "казна получила стартовый взнос")

    r = game.handle(founder, "guildnew")
    check("уже состоишь" in (r.alert or "").lower(), "второй гильдии не бывает")

    member = _hero(store, game, 5, "Соратник", level=6, money=1000)
    game.handle(member, f"guildjoin:{g['id']}")
    g, _ = guilds.guild_of(store, member)
    check(len(g["members"]) == 2, "участник вступил")

    treasury_before = g["treasury"]
    game.handle(member, "guilddep:100")
    g, _ = guilds.guild_of(store, member)
    check(g["treasury"] == treasury_before + 100, "взнос дошёл до казны")
    check(game.handle(member, "guilddep:777").alert is not None,
          "подделанная сумма взноса отклонена")

    print("\n— Наставничество: пороги уровней —")
    veteran = _hero(store, game, 6, "Ветеран", level=guilds.MENTOR_MIN_LEVEL)
    rookie = _hero(store, game, 7, "Новичок", level=2)
    weak = _hero(store, game, 8, "Слабый", level=3)

    ok, _why = guilds.can_mentor(weak, rookie)
    check(ok is False, "низкоуровневый не может быть наставником")
    ok, _why = guilds.can_mentor(veteran, veteran)
    check(ok is False, "сам себе наставником не станешь")

    r = game.handle(rookie, f"mentorgo:{veteran.tg_id}")
    check(rookie.mentor_id == veteran.tg_id, "наставник привязан")
    check(guilds.mentor_bonuses(rookie)["exp_bonus_pct"]
          == guilds.MENTOR_EXP_BONUS_PCT, "ученик получил бонус опыта")
    check(game.handle(rookie, f"mentorgo:{veteran.tg_id}").alert is not None,
          "второго наставника не взять")

    honor = guilds.reward_mentor(store, rookie)
    check(honor == guilds.HONOR_PER_PROGRESS, "наставнику начислены очки чести")
    check(veteran.honor_points == honor, "очки записаны ветерану")
    check(guilds.reward_mentor(store, veteran) == 0,
          "без наставника очки никому не идут")

    print("\n— Награды за головы —")
    fresh = Store(MemoryStorage())
    check(not bounty.active(fresh), "доска пуста")
    row = bounty.record_kill(fresh, "1:3:3", 5)
    check(row["kills"] == 1 and row["title"], "убийца получил имя")
    check(bounty.active(fresh), "цель попала на доску")

    first = bounty.reward_for(1)
    bounty.record_kill(fresh, "1:3:3", 5)
    check(bounty.reward_for(2) > first, "чем больше жертв, тем дороже голова")
    check(bounty.at_cell(fresh, "1:3:3")["kills"] == 2, "счётчик растёт")

    paid = bounty.claim(fresh, "1:3:3")
    check(paid == bounty.reward_for(2), f"выплачено {paid}🟤")
    check(not bounty.at_cell(fresh, "1:3:3"), "контракт снят после сдачи")
    check(bounty.claim(fresh, "1:3:3") == 0, "дважды за одну голову не платят")

    print("\n— Иллюзии: тексты общие —")
    check(illusions.REVEAL_EXP > 0 and illusions.GROTTO_NAME,
          "награда и название грота заданы")

    print("\n— Экраны и меню —")
    datas = [d for row in game.menu(a).keyboard for _l, d in row]
    for cb in ("arena", "guild", "mentor"):
        check(cb in datas, f"в меню есть «{cb}»")
    check("Колизей" in game.handle(a, "arena").text, "экран арены открывается")
    check("Гильд" in game.handle(a, "guild").text, "экран гильдий открывается")
    check("Наставнич" in game.handle(rookie, "mentor").text,
          "экран наставничества открывается")

    print("\n— Правила общие с сервером —")
    try:
        from core import arena as c_arena
        from core import bounty as c_bounty
        from core import illusions as c_ill
        from core import mentorship as c_ment
        check(c_arena.A is arena, "арена сервера берёт правила отсюда")
        check(c_bounty.B is bounty, "награды за головы — общий модуль")
        check(c_ment.G is guilds, "наставничество берёт пороги отсюда")
        check(c_ill.I is illusions, "тексты иллюзий общие")
    except ImportError as e:
        check(True, f"серверный стек недоступен, пропуск ({e})")

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
