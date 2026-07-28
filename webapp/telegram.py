"""Telegram Bot API клиент на Python + long polling из браузера."""
import asyncio

from engine.game import Game
from webapp.transport import Transport


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
        self.game = Game(store)
        self.transport = Transport(store.settings)
        self.counters = {"updates": 0, "sent": 0, "errors": 0}

    # ── HTTP ────────────────────────────────────────────────
    async def call(self, method, **params):
        data = await self.transport.call(self.token, method, params)
        if not data.get("ok"):
            self.counters["errors"] += 1
            self.log("err", f"{method}: {data.get('description', '?')}")
        return data

    # ── жизненный цикл ──────────────────────────────────────
    async def start(self, token):
        if self.running:
            return False, "Бот уже запущен"
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
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
        self._task = asyncio.ensure_future(self._loop())
        self.log("sys", f"Бот @{self.me['username']} запущен")
        return True, self.me["username"]

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self.log("sys", "Бот остановлен")

    async def _loop(self):
        while self.running:
            try:
                data = await self.call("getUpdates", offset=self.offset,
                                       timeout=25, allowed_updates=["message", "callback_query"])
                for upd in data.get("result", []):
                    upd_id = upd.get("update_id", 0)
                    if upd_id <= self.last_update_id:
                        continue
                    self.last_update_id = upd_id
                    self.offset = upd_id + 1
                    self.counters["updates"] += 1
                    try:
                        await self.dispatch(upd)
                    except Exception as e:
                        self.log("err", f"handler: {e}")
                try:
                    await self.flush_outbox()      # уведомления из панели
                except Exception as e:
                    self.log("err", f"outbox: {e}")
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.counters["errors"] += 1
                self.log("err", f"poll: {e}")
                await asyncio.sleep(3)

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
