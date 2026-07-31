"""Дедуп Telegram-апдейтов: один /start — один ответ.

Симптом в логе (браузерный стек):
  Янгель: /start
  🌑 <b>Теневые Земли</b>
  Янгель: /start          ← тот же апдейт повторно
  🌑 <b>Теневые Земли</b>
  Bad Request: message is not modified

Причины: два poll-loop (зомби после start без await cancel), cors-прокси
отдаёт кэш getUpdates, Telegram ретраит callback. Фикс — LRU по update_id
до dispatch + единственный живой loop.

python3 tests/test_telegram_dedup.py
"""
import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Заглушки браузерных модулей (как в test_transport / test_pages).
fake_js = types.ModuleType("js")
fake_js.encodeURIComponent = lambda s: str(s)
sys.modules.setdefault("js", fake_js)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


# ── чистый LRU (без I/O) ───────────────────────────────────

def test_deduper_unit():
    print("\n— UpdateDeduper: LRU и повтор —")
    from webapp.telegram import UpdateDeduper

    d = UpdateDeduper(maxlen=3)
    check(d.seen_before(10) is False, "первый id — новый")
    check(d.seen_before(10) is True, "повтор того же id — дубль")
    check(d.seen_before(11) is False, "другой id — новый")
    check(d.seen_before(12) is False, "третий id — новый")
    check(d.seen_before(13) is False, "четвёртый вытесняет самый старый")
    # 10 вытеснен — снова «новый», но это ок: offset уже далеко
    check(10 not in d, "вытесненный id больше не в LRU")
    check(d.seen_before(11) is True, "ещё живой id — всё ещё дубль")
    check(d.seen_before("not-int") is False, "мусорный id не валит")
    d.clear()
    check(len(d) == 0, "clear опустошает")


def test_bot_deduper_unit():
    print("\n— aiogram Deduper: тот же контракт —")
    try:
        from bot.middlewares.dedup import UpdateIdDeduper
    except Exception as e:
        print(f"  ⚠ Пропуск (нет aiogram/зависимостей): {e}")
        return
    d = UpdateIdDeduper(maxlen=2)
    check(d.seen_before(1) is False, "bot: первый")
    check(d.seen_before(1) is True, "bot: повтор")
    check(d.seen_before(2) is False, "bot: сосед")
    check(d.seen_before(3) is False, "bot: вытеснение")
    check(1 not in d, "bot: старый вытеснен")


# ── интеграция: dispatch не зовётся на дубль ────────────────

class _FakeReply:
    def __init__(self, text="ok"):
        self.text = text
        self.keyboard = []
        self.alert = None
        self.new_message = False
        self.image_url = None


class _FakeGame:
    def __init__(self):
        self.calls = []

    def handle(self, p, action):
        self.calls.append(action)
        return _FakeReply(text=f"reply:{action}")

    def text_input(self, p, text):
        return None


class _FakeStore:
    def __init__(self):
        self.settings = {}
        self.players = {}
        self.world = {}
        self.saves = 0

    def player(self, tg_id, name):
        if tg_id not in self.players:
            p = types.SimpleNamespace(tg_id=tg_id, name=name, msg_id=None)
            self.players[tg_id] = p
        return self.players[tg_id]

    def save_player(self, p):
        self.saves += 1

    def save(self):
        pass


class _FakeTransport:
    """Эмулирует Telegram. getUpdates по умолчанию пустой (loop не ест
    тестовые апдейты); replay_batches — явная очередь «прокси-дублей».
    """

    def __init__(self):
        self.sent = []
        self.calls = []
        self._polls = 0
        self.replay_batches = []  # list[list[dict]]
        self.sample_update = {
            "update_id": 100,
            "message": {
                "message_id": 1,
                "from": {"id": 42, "first_name": "Янгель"},
                "chat": {"id": 42},
                "text": "/start",
            },
        }

    def arm_proxy_replay(self):
        """Два одинаковых батча — как cors-прокси, отдавший кэш дважды."""
        self.replay_batches = [
            [dict(self.sample_update)],
            [dict(self.sample_update)],
        ]

    async def call(self, token, method, params):
        self.calls.append((method, dict(params or {})))
        if method == "getMe":
            return {"ok": True, "result": {"username": "shadow_bot",
                                           "first_name": "Shadow"}}
        if method == "deleteWebhook":
            return {"ok": True, "result": True}
        if method == "getUpdates":
            self._polls += 1
            if self.replay_batches:
                return {"ok": True, "result": self.replay_batches.pop(0)}
            return {"ok": True, "result": []}
        if method in ("sendMessage", "editMessageText", "sendPhoto",
                      "answerCallbackQuery"):
            self.sent.append((method, dict(params or {})))
            return {"ok": True, "result": {"message_id": 7}}
        return {"ok": True, "result": True}


def _make_bot(transport=None):
    from webapp.telegram import TelegramBot

    logs = []
    store = _FakeStore()
    bot = TelegramBot(store, lambda lvl, msg: logs.append((lvl, msg)))
    bot.game = _FakeGame()
    bot.transport = transport or _FakeTransport()
    return bot, store, logs


async def test_ingest_dedupes_same_update():
    print("\n— _ingest: один update_id → один dispatch —")
    bot, store, logs = _make_bot()
    upd = {
        "update_id": 555,
        "message": {
            "message_id": 1,
            "from": {"id": 7, "first_name": "Янгель"},
            "chat": {"id": 7},
            "text": "/start",
        },
    }
    ok1 = await bot._ingest(upd)
    ok2 = await bot._ingest(upd)
    ok3 = await bot._ingest(dict(upd, update_id=556))  # другой id

    check(ok1 is True, "первый ingest — обработан")
    check(ok2 is False, "повторный ingest — отброшен")
    check(ok3 is True, "другой update_id — обработан")
    check(bot.game.calls == ["start", "start"],
          f"handle вызван ровно 2 раза (не 3): {bot.game.calls}")
    check(bot.counters["dupes"] == 1, f"счётчик dupes=1 ({bot.counters})")
    check(bot.counters["updates"] == 2, f"счётчик updates=2 ({bot.counters})")
    # В логе входящих — только два /start, не три
    ins = [m for lvl, m in logs if lvl == "in"]
    check(len(ins) == 2, f"в лог 'in' попали 2 сообщения: {ins}")


async def test_callback_dedupes():
    print("\n— _ingest: повторный callback_query —")
    bot, store, logs = _make_bot()
    upd = {
        "update_id": 900,
        "callback_query": {
            "id": "cq1",
            "from": {"id": 7, "first_name": "Янгель"},
            "message": {"message_id": 3, "chat": {"id": 7}},
            "data": "help",
        },
    }
    await bot._ingest(upd)
    await bot._ingest(upd)
    check(bot.game.calls == ["help"], f"callback один раз: {bot.game.calls}")
    check(bot.counters["dupes"] == 1, "callback-дубль посчитан")


async def test_concurrent_ingest_same_id():
    print("\n— _ingest: гонка двух одинаковых id —")
    bot, store, logs = _make_bot()

    # Замедляем dispatch, чтобы оба _ingest успели стартовать
    original = bot.dispatch
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_dispatch(upd):
        entered.set()
        await release.wait()
        await original(upd)

    bot.dispatch = slow_dispatch
    upd = {
        "update_id": 42,
        "message": {
            "message_id": 1,
            "from": {"id": 1, "first_name": "A"},
            "chat": {"id": 1},
            "text": "/start",
        },
    }

    t1 = asyncio.create_task(bot._ingest(upd))
    await entered.wait()
    t2 = asyncio.create_task(bot._ingest(upd))
    # Дать t2 дойти до замка
    await asyncio.sleep(0.05)
    release.set()
    r1, r2 = await asyncio.gather(t1, t2)
    check(sorted([r1, r2]) == [False, True],
          f"ровно один победитель гонки: {r1}, {r2}")
    check(bot.game.calls == ["start"], f"handle один раз при гонке: {bot.game.calls}")


async def test_single_poll_loop_on_double_start():
    print("\n— start(): повторный запуск не плодит poll-loop —")
    transport = _FakeTransport()
    bot, store, logs = _make_bot(transport)

    ok1, info1 = await bot.start("123:ABC")
    check(ok1 is True, f"первый start ок ({info1})")
    task1 = bot._task
    check(task1 is not None and not task1.done(), "poll-task жив")
    gen1 = bot._loop_gen

    ok2, info2 = await bot.start("123:ABC")
    check(ok2 is False, f"второй start отказан: {info2}")
    check(bot._task is task1, "тот же task — зомби-loop не создан")
    check(bot._loop_gen == gen1, "поколение loop не сменилось")

    # Жёстко гасим: halt (как при рестарте)
    await bot._halt_loop()
    check(bot.running is False, "halt сбрасывает running")
    check(task1.done() or task1.cancelled(), "старый task завершён")

    ok3, _ = await bot.start("123:ABC")
    check(ok3 is True, "start после halt поднимает заново")
    check(bot._task is not None and bot._task is not task1, "новый task")
    check(bot._loop_gen > gen1, "поколение loop выросло")

    await bot._halt_loop()
    check(bot.running is False, "финальный halt")


async def test_loop_dedupes_proxy_replay():
    print("\n— poll-loop: прокси отдал один апдейт в двух getUpdates —")
    transport = _FakeTransport()
    transport.arm_proxy_replay()
    bot, store, logs = _make_bot(transport)

    # Не крутим бесконечный loop: имитируем два ответа getUpdates вручную
    # через _ingest (тот же путь, что и _loop).
    batch1 = (await transport.call("t", "getUpdates", {})).get("result", [])
    batch2 = (await transport.call("t", "getUpdates", {})).get("result", [])
    for upd in batch1:
        await bot._ingest(upd)
    for upd in batch2:
        await bot._ingest(upd)

    check(transport._polls >= 2, f"было ≥2 getUpdates ({transport._polls})")
    check(bot.game.calls == ["start"],
          f"handle ровно один /start, не два: {bot.game.calls}")
    check(bot.counters["dupes"] >= 1,
          f"дубль пойман счётчиком ({bot.counters})")
    sends = [m for m, _ in transport.sent if m == "sendMessage"]
    check(len(sends) == 1, f"sendMessage ровно 1 раз: {len(sends)}")


async def test_aiogram_middleware_dedup():
    print("\n— DedupUpdateMiddleware: глотает повтор event_update —")
    try:
        from bot.middlewares.dedup import DedupUpdateMiddleware, UpdateIdDeduper
    except Exception as e:
        print(f"  ⚠ Пропуск: {e}")
        return

    mw = DedupUpdateMiddleware(UpdateIdDeduper())
    hits = []

    async def handler(event, data):
        hits.append(data.get("event_update"))
        return "ok"

    class Upd:
        def __init__(self, i):
            self.update_id = i

    class Ev:
        pass

    r1 = await mw(handler, Ev(), {"event_update": Upd(77)})
    r2 = await mw(handler, Ev(), {"event_update": Upd(77)})
    r3 = await mw(handler, Ev(), {"event_update": Upd(78)})
    check(r1 == "ok" and r3 == "ok", "новые апдейты проходят")
    check(r2 is None, "повтор update_id глотается")
    check(len(hits) == 2, f"handler ровно 2 раза: {len(hits)}")


def main():
    test_deduper_unit()
    test_bot_deduper_unit()
    asyncio.run(test_ingest_dedupes_same_update())
    asyncio.run(test_callback_dedupes())
    asyncio.run(test_concurrent_ingest_same_id())
    asyncio.run(test_single_poll_loop_on_double_start())
    asyncio.run(test_loop_dedupes_proxy_replay())
    asyncio.run(test_aiogram_middleware_dedup())

    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}: {', '.join(FAILED)}")
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
