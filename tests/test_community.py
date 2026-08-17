"""Структурированное сообщество: каналы, права, мост в Telegram.

python3 tests/test_community.py

Что это за подсистема. Чата между игроками в проекте не было вообще: ни
модели, ни хендлера, ни страницы — только односторонние рассылки
(`bot/broadcast.py`) и WS-шина событий для админки (`core/realtime.py`).
Здесь появляется сообщество: каналы (как разделы форума), журнал сообщений
в БД игры и мост в супергруппу с форум-темами.

Ключевое архитектурное решение, которое проверяют тесты: **источник правды
— игра, а не Telegram**. Права на гильдейский канал считаются по членству
в `core/guilds.py`, а не по составу темы; сообщения живут в БД, потому что
Bot API не отдаёт историю чата задним числом.

Отдельно проверяется найденная по дороге коллизия: `bot/handlers/start.py`
ловил `@router.message(F.text)` без фильтров и первым в списке роутеров —
в группе это складывало бы каждую реплику игроков в `AdminMessage` как
личные письма админу, а в личке съедало бы ввод чужих FSM.
"""
import asyncio
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Грейсфул-скип (пункт № 4): без серверного стека набор пропускается.
from _deps import require  # noqa: E402

require("sqlalchemy", "aiosqlite", "aiogram")

# Детерминизм (пункт № 5).
from _seed import pin, unique_id  # noqa: E402

pin(118)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


# ── заглушки Telegram ───────────────────────────────────────

class FakeTopic:
    def __init__(self, tid):
        self.message_thread_id = tid


class FakeSent:
    def __init__(self, mid):
        self.message_id = mid


class FakeBot:
    """Бот, который считает вызовы вместо похода в Telegram."""

    def __init__(self, fail_send_once=False, fail_topics=False):
        self.topics = []
        self.sent = []
        self._thread = 100
        self._msg = 1000
        self.fail_send_once = fail_send_once
        self.fail_topics = fail_topics

    async def create_forum_topic(self, chat_id, name, icon_color=None):
        if self.fail_topics:
            raise RuntimeError("not enough rights to manage topics")
        self._thread += 1
        self.topics.append((str(chat_id), name, self._thread))
        return FakeTopic(self._thread)

    async def send_message(self, chat_id, text, message_thread_id=None,
                           parse_mode=None):
        if self.fail_send_once:
            self.fail_send_once = False
            raise RuntimeError("message thread not found")
        self._msg += 1
        self.sent.append((message_thread_id, text))
        return FakeSent(self._msg)


def fake_group_message(chat_id, thread_id, text, tg_user_id, message_id):
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(id=chat_id, type="supergroup"),
        message_thread_id=thread_id,
        text=text,
        message_id=message_id,
        from_user=types.SimpleNamespace(id=tg_user_id, full_name="Гость"),
    )


# ── сценарий ────────────────────────────────────────────────

async def scenario():
    from core import community as C
    from core.database import async_session
    from core.guilds import Guild, guild_members
    from core.migrations import run_migrations
    from core.models import Character, User

    await run_migrations()

    print("\n— Каталог каналов —")
    async with async_session() as s:
        created = await C.ensure_default_channels(s)
        check(len(created) == len(C.DEFAULT_CHANNELS),
              f"фиксированные каналы заведены ({len(created)})")
        again = await C.ensure_default_channels(s)
        check(again == [], "повторный вызов ничего не дублирует")
        await s.commit()

    # Герои: член гильдии, чужак и присягнувший фракции.
    async with async_session() as s:
        u1 = User(telegram_id=unique_id(), username="a")
        u2 = User(telegram_id=unique_id(), username="b")
        s.add_all([u1, u2])
        await s.flush()
        hero = Character(user_id=u1.id, name="Гидеон",
                         character_class="mage", level=6)
        stranger = Character(user_id=u2.id, name="Чужак",
                             character_class="warrior", level=4)
        s.add_all([hero, stranger])
        await s.flush()
        guild = Guild(name=f"Дом Пепла {unique_id()}", leader_id=hero.id)
        s.add(guild)
        await s.flush()
        await s.execute(guild_members.insert().values(
            guild_id=guild.id, character_id=hero.id))
        await s.commit()
        hero_id, stranger_id, guild_id = hero.id, stranger.id, guild.id
        hero_tg = u1.telegram_id

    print("\n— Права: считаются по игре, а не по составу темы —")
    async with async_session() as s:
        hero = await s.get(Character, hero_id)
        stranger = await s.get(Character, stranger_id)
        guild = await s.get(Guild, guild_id)

        gch = await C.ensure_guild_channel(s, guild)
        check(gch.kind == C.ChannelKind.GUILD.value, "канал гильдии создан")
        check(await C.can_read(s, gch, hero), "участник гильдии читает канал")
        check(not await C.can_read(s, gch, stranger),
              "чужак в гильдейский канал не попадает")
        check(not await C.can_read(s, gch, None),
              "аноним в закрытый канал не попадает")

        general = await C.get_channel(s, "general")
        world = await C.get_channel(s, "world")
        check(await C.can_read(s, general, stranger), "общий канал открыт всем")
        check(await C.can_read(s, world, stranger),
              "ленту мира читают все")
        check(not await C.can_write(s, world, hero),
              "в ленту мира игрок писать не может (только игра)")

        # Канал фракции: доступ по присяге.
        from core import factions as core_factions

        core_factions.save(hero, {"guard": 200, "scavengers": 0,
                                  "cult": 0, "order": 0})
        fch = await C.ensure_faction_channel(s, "guard")
        check(fch is not None and fch.faction_key == "guard",
              "канал фракции создан из каталога core/factions")
        check(await C.can_read(s, fch, hero), "присягнувший читает канал силы")
        check(not await C.can_read(s, fch, stranger),
              "не присягнувший канал силы не видит")
        check(await C.ensure_faction_channel(s, "нет_такой") is None,
              "несуществующая фракция канал не создаёт")

        vis_hero = {c.key for c in await C.visible_channels(s, hero)}
        vis_other = {c.key for c in await C.visible_channels(s, stranger)}
        check(gch.key in vis_hero and gch.key not in vis_other,
              "меню каналов у героев разное и зависит от членства")
        await s.commit()

    print("\n— Журнал сообщений —")
    async with async_session() as s:
        hero = await s.get(Character, hero_id)
        general = await C.get_channel(s, "general")

        await C.post(s, general, "Всем привет!", character=hero, source="bot")
        check(await C.post(s, general, "   ", character=hero) is None,
              "пустое сообщение не записывается")
        long_text = "х" * (C.MESSAGE_LIMIT + 500)
        big = await C.post(s, general, long_text, character=hero)
        check(len(big.text) == C.MESSAGE_LIMIT,
              f"длинное сообщение обрезано до {C.MESSAGE_LIMIT}")

        first = await C.post(s, general, "эхо", source="telegram",
                             tg_message_id=4242)
        dup = await C.post(s, general, "эхо ещё раз", source="telegram",
                           tg_message_id=4242)
        check(first.id == dup.id,
              "повтор по tg_message_id не создаёт вторую строку")

        rows = await C.recent(s, general)
        check([r.text for r in rows][0] == "Всем привет!",
              "порядок хронологический, а не обратный")

        await C.delete_message(s, first.id)
        rows_after = await C.recent(s, general)
        check(all(r.id != first.id for r in rows_after),
              "мягко удалённое сообщение исчезает из выдачи")
        check(await s.get(C.CommunityMessage, first.id) is not None,
              "но строка остаётся в базе для истории модерации")
        await s.commit()

    print("\n— Мост в Telegram —")
    from bot import community_bridge as bridge

    check(not await bridge.is_enabled(),
          "без настроенной группы мост выключен")

    async with async_session() as s:
        hero = await s.get(Character, hero_id)
    res = await bridge.relay_from_game(hero, "general", "без моста")
    check(res["ok"] and not res["delivered"],
          "при выключенном мосте сообщение всё равно попадает в журнал")

    chat_id = "-1001234567890"
    await bridge.set_chat_id(chat_id)
    check(await bridge.is_enabled(), "мост включается после ввода ID группы")

    bot = FakeBot()
    res = await bridge.relay_from_game(hero, "general", "с мостом", bot=bot)
    check(res["delivered"], "сообщение доставлено в тему")
    check(len(bot.topics) == 1, "тема создана лениво, при первой надобности")
    check(bot.sent and "Гидеон" in bot.sent[0][1],
          "в группу уходит игровое имя, а не ник Telegram")

    res2 = await bridge.relay_from_game(hero, "general", "второе", bot=bot)
    check(len(bot.topics) == 1, "повторная отправка новую тему не плодит")
    check(res2["delivered"], "второе сообщение тоже доставлено")

    broken = FakeBot(fail_send_once=True)
    res3 = await bridge.relay_from_game(hero, "general", "после удаления темы",
                                        bot=broken)
    check(res3["delivered"], "после удаления темы мост пересоздаёт её и шлёт")
    check(len(broken.topics) == 1, "пересоздана ровно одна тема")

    hopeless = FakeBot(fail_topics=True)
    res4 = await bridge.relay_from_game(hero, "trade", "нет прав", bot=hopeless)
    check(res4["ok"] and not res4["delivered"],
          "без прав на темы сообщение остаётся в игре, ошибки нет")

    denied = await bridge.relay_from_game(hero, "world", "нельзя", bot=bot)
    check(not denied["ok"], "в READONLY-канал мост писать не даёт")
    check(await bridge.announce("world", "🌀 Портал открыт!", bot=bot),
          "объявление от имени мира в ленту проходит")

    print("\n— Приём из группы —")
    async with async_session() as s:
        general = await C.get_channel(s, "general")
        thread_id = general.thread_id
    check(thread_id is not None, "канал привязан к теме")

    got = await bridge.relay_from_telegram(
        fake_group_message(int(chat_id), thread_id, "реплика из темы",
                           hero_tg, 5001))
    check(got is not None and got["author"] == "Гидеон",
          "автор найден по telegram_id и подписан игровым именем")

    same = await bridge.relay_from_telegram(
        fake_group_message(int(chat_id), thread_id, "реплика из темы",
                           hero_tg, 5001))
    check(same is not None, "повтор обрабатывается без ошибки")
    async with async_session() as s:
        general = await C.get_channel(s, "general")
        texts = [m.text for m in await C.recent(s, general, limit=50)]
        check(texts.count("реплика из темы") == 1,
              "и не создаёт второй записи (дубль отсечён)")

    check(await bridge.relay_from_telegram(
        fake_group_message(-100999999, thread_id, "чужой чат", hero_tg, 6001)
    ) is None, "сообщение из чужого чата игнорируется")
    check(await bridge.relay_from_telegram(
        fake_group_message(int(chat_id), None, "не в теме", hero_tg, 6002)
    ) is None, "сообщение вне темы игнорируется")
    check(await bridge.relay_from_telegram(
        fake_group_message(int(chat_id), 999999, "чужая тема", hero_tg, 6003)
    ) is None, "непривязанная тема игнорируется")

    unknown = await bridge.relay_from_telegram(
        fake_group_message(int(chat_id), thread_id, "я без героя",
                           unique_id(), 6004))
    check(unknown is not None and unknown["author"] is None,
          "человек без персонажа пишет под ником Telegram")

    print("\n— Лента мира подписана на шину событий —")
    from bot.community_feed import FEED_EVENTS, world_feed

    check("player_move" not in FEED_EVENTS,
          "рутина вроде player_move в общий чат не транслируется")
    check("portal_opened" in FEED_EVENTS and "boss_defeated" in FEED_EVENTS,
          "события мира транслируются")
    check(not world_feed.running, "лента не запущена сама по себе")

    async with async_session() as s:
        info = await C.stats(s)
        check(info["channels"] >= len(C.DEFAULT_CHANNELS) + 2,
              f"каналов в статистике: {info['channels']}")
        check(info["linked"] >= 1, "привязанные темы посчитаны")


def test_handlers_are_scoped():
    """Коллизия роутеров: обработчики личики не должны ловить группу."""
    print("\n— Роутеры разведены по типу чата —")
    with open(os.path.join(ROOT, "bot", "handlers", "start.py"),
              encoding="utf-8") as fh:
        start_src = fh.read()

    check('@router.message(F.text, F.chat.type == "private"' in start_src,
          "handle_text ограничен личкой (иначе съедал бы чат группы)")
    check("StateFilter(None, IdeaForm.waiting_for_text)" in start_src,
          "handle_text не перехватывает ввод чужих FSM")
    check('@router.message(CommandStart(), F.chat.type == "private")'
          in start_src, "/start обрабатывается только в личке")

    with open(os.path.join(ROOT, "bot", "handlers", "community_group.py"),
              encoding="utf-8") as fh:
        group_src = fh.read()
    check("F.chat.type.in_(GROUP_TYPES)" in group_src,
          "роутер группы работает только в группах")

    from bot.handlers import routers
    from bot.handlers.community_group import router as group_router

    check(routers[-1] is group_router,
          "роутер группы подключён последним: он ловит остаток")


def test_bot_menu_has_chat():
    """Кнопка сообщества есть в главном меню и у неё есть обработчик."""
    print("\n— Точка входа в боте —")
    from bot.handlers.community import router
    from bot.keyboards.inline import main_menu_keyboard

    markup = main_menu_keyboard(has_character=True)
    labels = [b.text for row in markup.inline_keyboard for b in row]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    check(any("Сообщество" in l for l in labels), "кнопка есть в меню")
    check("chat_menu" in datas, "у кнопки правильный callback")

    # Реальное сопоставление magic-фильтров, как в test_partial_items_done.
    class Probe:
        def __init__(self, data):
            self.data = data

    def has_handler(callback_data):
        probe = Probe(callback_data)
        for handler in router.callback_query.handlers:
            for flt in handler.filters or []:
                try:
                    if flt.callback(probe):
                        return True
                except Exception:
                    continue
        return False

    for cb in ("chat_menu", "chat_open:general", "chat_write:general",
               "chat_cancel:general"):
        check(has_handler(cb), f"обработчик {cb} зарегистрирован")
    check(not has_handler("chat_nonexistent_action"),
          "негативная проверка: несуществующий колбэк никем не ловится")


def main():
    asyncio.run(scenario())
    test_handlers_are_scoped()
    test_bot_menu_has_chat()

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ Сообщество: каналы, права, мост и приём из группы работают")
    return 0


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="shadowlands-community-")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp}/test.db"
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        code = main()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(code)
