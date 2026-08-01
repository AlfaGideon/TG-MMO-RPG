"""Безопасное редактирование сообщений бота (кнопки на фото-экранах).

Регрессия: экран локации и экран боя — это ФОТО с подписью (карта/моб),
а обработчики кнопок («🔍 Осмотреться», «Атаковать», «Отдых» и др.) звали
edit_text и падали с «Bad Request: there is no text in the message to edit».

python3 tests/test_bot_edit.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _have(*mods):
    import importlib.util
    return all(importlib.util.find_spec(m) for m in mods)


class FakeMessage:
    def __init__(self, text=None, caption=None, photo=None,
                 edit_error=None, caption_error=None):
        self.text = text
        self.caption = caption
        self.photo = photo
        self._edit_error = edit_error
        self._caption_error = caption_error
        self.edits = []
        self.answers = []

    async def edit_text(self, **kw):
        self.edits.append(("edit_text", kw))
        if self._edit_error:
            raise self._edit_error

    async def edit_caption(self, **kw):
        self.edits.append(("edit_caption", kw))
        if self._caption_error:
            raise self._caption_error

    async def answer(self, **kw):
        self.answers.append(kw)


class FakeCallback:
    def __init__(self, msg):
        self.message = msg


def test_safe_edit_text():
    from aiogram.exceptions import TelegramBadRequest
    from bot.utils.edit import safe_edit_text

    async def run():
        # 1. Текстовое сообщение → edit_text, без новых сообщений
        m = FakeMessage(text="старый текст")
        await safe_edit_text(FakeCallback(m), "новый текст",
                             reply_markup="kb", parse_mode="HTML")
        check(
            len(m.edits) == 1 and m.edits[0][0] == "edit_text"
            and m.edits[0][1].get("text") == "новый текст"
            and m.edits[0][1].get("reply_markup") == "kb",
            "текст → edit_text",
        )
        check(m.answers == [], "текст → без fallback-сообщений")

        # 2. Фото с подписью (экран локации/боя) → edit_caption, фото остаётся
        m = FakeMessage(caption="старая подпись", photo=[1])
        await safe_edit_text(FakeCallback(m), "результат осмотра")
        check(
            len(m.edits) == 1 and m.edits[0][0] == "edit_caption"
            and m.edits[0][1].get("text") is None
            and m.edits[0][1].get("caption") == "результат осмотра",
            "фото → edit_caption",
        )
        check(m.answers == [], "фото → без fallback-сообщений")

        # 3. Фото без подписи → edit_caption (подпись появится)
        m = FakeMessage(photo=[1])
        await safe_edit_text(m, "подпись")
        check(m.edits[0][0] == "edit_caption", "фото без подписи → edit_caption")

        # 4. «message is not modified» → тихо, без fallback (не ошибка)
        err = TelegramBadRequest(method=None,
                                 message="Bad Request: message is not modified")
        m = FakeMessage(text="тот же текст", edit_error=err)
        await safe_edit_text(m, "тот же текст")
        check(m.answers == [], "message is not modified → проглатывается")

        # 5. edit_text упал («no text in the message to edit») → новое сообщение
        err = TelegramBadRequest(
            method=None,
            message="Bad Request: there is no text in the message to edit")
        m = FakeMessage(text="x", edit_error=err)
        await safe_edit_text(m, "текст")
        check(len(m.answers) == 1 and m.answers[0]["text"] == "текст",
              "edit_text не смог → отправлено новое сообщение")

        # 6. edit_caption упал → новое сообщение
        err = TelegramBadRequest(method=None, message="Bad Request: не вышло")
        m = FakeMessage(photo=[1], caption_error=err)
        await safe_edit_text(m, "текст")
        check(len(m.answers) == 1, "edit_caption не смог → новое сообщение")

        # 7. Ни текста, ни медиа → сразу новое сообщение
        m = FakeMessage()
        await safe_edit_text(m, "текст")
        check(len(m.answers) == 1, "нет ни текста, ни медиа → новое сообщение")

    asyncio.run(run())


def main():
    if not _have("aiogram"):
        print("⚠️  ПРОПУСК: нет aiogram (проверка safe_edit_text требует aiogram.exceptions)")
        return 0

    test_safe_edit_text()

    print()
    if FAILED:
        print("❌ Провалено: " + ", ".join(FAILED))
        return 1
    print("✅ Все проверки редактирования сообщений пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())
