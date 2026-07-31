"""Telegram Bot API клиент на Python + long polling из браузера."""
import asyncio
from collections import OrderedDict

from engine.game import Game
from webapp.transport import Transport

# Сколько последних update_id помним. Telegram не переиспользует id в
# разумных пределах; 4k хватает с запасом на ретраи прокси и рестарты.
_SEEN_MAX = 4000


class UpdateDeduper:
    """Идемпотентность по update_id.

    Telegram (и cors-прокси) могут отдать один апдейт дважды: два poll-loop
    (две вкладки / гонка start), кэш прокси, повтор getUpdates с тем же
    offset. Без дедупа /start и колбэки обрабатываются дважды — два ответа
    и «message is not modified» на повторном edit.
    """

    def __init__(self, maxlen: int = _SEEN_MAX):
        self._seen: OrderedDict[int, bool] = OrderedDict()
        self._maxlen = max(1, int(maxlen))

    def seen_before(self, update_id: int) -> bool:
        """True = уже обрабатывали (дубль). False = новый, помечен как виденный."""
        try:
            uid = int(update_id)
        except (TypeError, ValueError):
            return False
        if uid in self._seen:
            # refresh LRU-порядок
            self._seen.move_to_end(uid)
            return True
        self._seen[uid] = True
        while len(self._seen) > self._maxlen:
            self._seen.popitem(last=False)
        return False

    def clear(self) -> None:
        self._seen.clear()

    def __contains__(self, update_id: int) -> bool:
        try:
            return int(update_id) in self._seen
        except (TypeError, ValueError):
            return False

    def __len__(self) -> int:
        return len(self._seen)


class TelegramBot:
    def __init__(self, store, log):
        self.store = store
        self.log = log                # callable(level, text)
        self.token = ""
        self.me = None
        self.running = False
        self.offset = 0
        self.last_update_id = -1
        self._task = None
        self._loop_gen = 0            # поколение poll-loop: старый loop умирает
        self.game = Game(store)
        self.transport = Transport(store.settings)
        self.counters = {"updates": 0, "sent": 0, "errors": 0, "dupes": 0}
        self.deduper = UpdateDeduper()
        # Замок на «отметить + обработать», чтобы два concurrent dispatch
        # одного id не прошли оба между проверкой и записью.
        self._dedup_lock = asyncio.Lock()

    # ── HTTP ────────────────────────────────────────────────
    async def call(self, method, **params):
        data = await self.transport.call(self.token, method, params)
        if not data.get("ok"):
            self.counters["errors"] += 1
            self.log("err", f"{method}: {data.get('description', '?')}")
        return data

    # ── жизненный цикл ──────────────────────────────────────
    async def start(self, token):
        if self.running and self._task is not None and not self._task.done():
            return False, "Бот уже запущен"
        # Гасим предыдущий loop полностью (cancel без await оставлял
        # зомби-поллер, и два getUpdates ели один и тот же апдейт).
        await self._halt_loop()
        self.token = token.strip()
        data = await self.call("getMe")
        if not data.get("ok"):
            if data.get("network"):
                return False, ("Telegram недоступен напрямую из браузера. "
                               "Включи прокси в разделе «Бот» → Транспорт.")
            return False, data.get("description", "Неверный токен")
        self.me = data["result"]
        self.running = True
        self.store.settings["token"] = self.token
        self.store.save()
        await self.call("deleteWebhook", drop_pending_updates=False)
        self._loop_gen += 1
        gen = self._loop_gen
        self._task = asyncio.ensure_future(self._loop(gen))
        self.log("sys", f"Бот @{self.me['username']} запущен")
        return True, self.me["username"]

    def stop(self):
        """Синхронная остановка из UI. Полный await — через _halt_loop."""
        self.running = False
        self._loop_gen += 1
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
        self.log("sys", "Бот остановлен")

    async def _halt_loop(self):
        """Отменяет poll-loop и дожидается его выхода."""
        self.running = False
        self._loop_gen += 1
        task = self._task
        self._task = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        # shield: CancelledError от task не должен отменить вызывающий
        # корутин (start / тесты). wait с timeout — страховка от зависания.
        try:
            await asyncio.wait({task}, timeout=2.0)
        except Exception:
            pass

    async def _loop(self, gen: int):
        try:
            while self.running and gen == self._loop_gen:
                try:
                    data = await self.call(
                        "getUpdates", offset=self.offset, timeout=25,
                        allowed_updates=["message", "callback_query"],
                    )
                    if not self.running or gen != self._loop_gen:
                        return
                    for upd in data.get("result", []) or []:
                        if not self.running or gen != self._loop_gen:
                            return
                        await self._ingest(upd)
                    try:
                        await self.flush_outbox()
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        self.log("err", f"outbox: {e}")
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    if not self.running or gen != self._loop_gen:
                        return
                    self.counters["errors"] += 1
                    self.log("err", f"poll: {e}")
                    try:
                        await asyncio.sleep(3)
                    except asyncio.CancelledError:
                        return
        except asyncio.CancelledError:
            return

    async def _ingest(self, upd: dict) -> bool:
        """Принять один апдейт: дедуп → offset → dispatch.

        Возвращает True, если апдейт реально обработан (не дубль).
        """
        upd_id = upd.get("update_id", 0)
        try:
            upd_id = int(upd_id)
        except (TypeError, ValueError):
            upd_id = 0

        async with self._dedup_lock:
            if self.deduper.seen_before(upd_id):
                self.counters["dupes"] += 1
                # Всё равно двигаем offset, чтобы Telegram не слал снова.
                if upd_id >= self.offset:
                    self.offset = upd_id + 1
                if upd_id > self.last_update_id:
                    self.last_update_id = upd_id
                return False
            if upd_id <= self.last_update_id:
                # Поясной ремень: id меньше последнего, но не в LRU —
                # считаем дублем по монотонности.
                self.counters["dupes"] += 1
                if upd_id >= self.offset:
                    self.offset = upd_id + 1
                return False
            self.last_update_id = upd_id
            self.offset = upd_id + 1
            self.counters["updates"] += 1

        try:
            await self.dispatch(upd)
        except Exception as e:
            self.log("err", f"handler: {e}")
        return True

    # ── обработка апдейтов ──────────────────────────────────
    async def dispatch(self, upd):
        if "message" in upd:
            msg = upd["message"]
            frm = msg.get("from", {})
            chat = msg["chat"]["id"]
            text = msg.get("text", "")
            self.log("in", f"{frm.get('first_name','?')}: {text}")
            p = self._player(frm)

            # Админ ждёт свободный ввод (например, текст рассылки).
            pending = self.game.text_input(p, text) if not text.startswith("/") else None
            if pending is not None:
                self.store.save_player(p)
                await self.send(chat, p, pending, force_new=True)
                await self.flush_outbox()
                return

            if text.startswith("/invite"):       # /invite Имя героя
                action = "invite:" + text[len("/invite"):].strip()
            elif text.startswith("/party"):
                action = "party"
            else:
                action = "start" if text.startswith("/start") else \
                         "help" if text.startswith("/help") else \
                         "profile" if text.startswith("/profile") else \
                         "admin" if text.startswith("/admin") else "menu"
            reply = self.game.handle(p, action)
            self.store.save_player(p)
            await self.send(chat, p, reply, force_new=True)

        elif "callback_query" in upd:
            cq = upd["callback_query"]
            frm = cq["from"]
            chat = cq["message"]["chat"]["id"]
            p = self._player(frm)
            p.msg_id = cq["message"]["message_id"]
            self.log("in", f"{frm.get('first_name','?')} → {cq['data']}")
            reply = self.game.handle(p, cq["data"])
            self.store.save_player(p)
            await self.call("answerCallbackQuery", callback_query_id=cq["id"],
                            text=reply.alert or None, show_alert=bool(reply.alert))
            if reply.text:
                await self.send(chat, p, reply)
            await self.flush_outbox()

    def _player(self, frm):
        name = frm.get("first_name") or frm.get("username") or "Изгнанник"
        return self.store.player(frm["id"], name)

    # ── отправка ────────────────────────────────────────────
    @staticmethod
    def _button(text, target):
        """target: строка -> callback_data, {"url": ...} -> кнопка-ссылка."""
        if isinstance(target, dict) and target.get("url"):
            return {"text": text, "url": target["url"]}
        return {"text": text, "callback_data": target}

    async def send(self, chat, p, reply, force_new=False):
        kb = {"inline_keyboard": [[self._button(t, d) for t, d in row]
                                  for row in reply.keyboard]}
        self.counters["sent"] += 1

        if getattr(reply, "image_url", None) and reply.image_url.startswith(("http://", "https://")):
            photo_args = dict(chat_id=chat, photo=reply.image_url, caption=reply.text, parse_mode="HTML", reply_markup=kb)
            res = await self.call("sendPhoto", **photo_args)
            if res.get("ok"):
                p.msg_id = res["result"]["message_id"]
                self.store.save_player(p)
                self.log("out", reply.text.splitlines()[0][:60])
                return

        args = dict(chat_id=chat, text=reply.text, parse_mode="HTML",
                    reply_markup=kb)
        if p.msg_id and not force_new and not reply.new_message:
            res = await self.call("editMessageText", message_id=p.msg_id, **args)
            if res.get("ok"):
                self.log("out", reply.text.splitlines()[0][:60])
                return
            desc = (res.get("description") or "").lower()
            if "message is not modified" in desc:
                return
        res = await self.call("sendMessage", **args)
        if res.get("ok"):
            p.msg_id = res["result"]["message_id"]
            self.store.save_player(p)
            self.log("out", reply.text.splitlines()[0][:60])

    async def broadcast(self, text):
        sent = 0
        for tg_id in list(self.store.players):
            r = await self.call("sendMessage", chat_id=tg_id, text=text, parse_mode="HTML")
            sent += 1 if r.get("ok") else 0
        self.log("sys", f"Рассылка: доставлено {sent}")
        return sent

    async def flush_outbox(self):
        """Разбирает очередь сообщений, наполненную админ-действиями.

        В очередь пишут и панель, и бот (engine.adminops), поэтому уведомления
        игрокам уходят одинаково, кто бы ни нажал кнопку.
        """
        from engine import adminops

        pending = adminops.drain(self.store)
        sent = 0
        for chat_id, text in pending:
            r = await self.call("sendMessage", chat_id=chat_id, text=text,
                                parse_mode="HTML")
            sent += 1 if r.get("ok") else 0
        if pending:
            self.log("out", f"Уведомления игрокам: {sent}/{len(pending)}")
        return sent
