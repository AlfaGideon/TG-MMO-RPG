"""HTTP-транспорт к Telegram Bot API.

Telegram с осени 2025 отклоняет запросы с браузерным User-Agent, а браузер
не даёт его подменить. Поэтому поддерживаются два режима:

  direct — fetch напрямую (работает не во всех браузерах);
  proxy  — через relay-прокси, который сам ходит в Telegram.

Режим и адрес прокси задаются в админке и хранятся в настройках.
"""
import json

TELEGRAM = "https://api.telegram.org"

# Публичные relay-прокси, пробрасывающие произвольный URL.
PRESETS = {
    "direct": "",
    "corsproxy": "https://corsproxy.io/?url=",
    "allorigins": "https://api.allorigins.win/raw?url=",
    "codetabs": "https://api.codetabs.com/v1/proxy/?quest=",
}


class Transport:
    def __init__(self, settings):
        self.settings = settings          # dict из Store.settings

    @property
    def mode(self):
        return self.settings.get("proxy_mode", "direct")

    @property
    def custom(self):
        return self.settings.get("proxy_url", "").strip()

    def prefix(self):
        if self.mode == "custom":
            return self.custom
        return PRESETS.get(self.mode, "")

    def build(self, token, method, query=""):
        """Итоговый URL запроса."""
        target = f"{TELEGRAM}/bot{token}/{method}"
        if query:
            target += "?" + query
        pre = self.prefix()
        if not pre:
            return target
        from js import encodeURIComponent
        return pre + str(encodeURIComponent(target))

    async def call(self, token, method, params):
        """Возвращает dict ответа Telegram (или {'ok': False, ...})."""
        from js import fetch, Object
        from pyodide.ffi import to_js

        payload = {k: v for k, v in params.items() if v is not None}
        # GET-строка: прокси обычно не пропускают POST-тело.
        query = "&".join(
            f"{k}={_enc(v)}" for k, v in payload.items()
        )
        url = self.build(token, method, query)

        opts = to_js({"method": "GET", "headers": {"Accept": "application/json"}},
                     dict_converter=Object.fromEntries)
        try:
            resp = await fetch(url, opts)
            text = await resp.text()
        except Exception as e:
            return {"ok": False, "description": f"сеть недоступна: {e}",
                    "network": True}
        try:
            return json.loads(text)
        except Exception:
            head = text[:160].replace("\n", " ")
            return {"ok": False, "description": f"не JSON от {self.mode}: {head}",
                    "network": True}


def _enc(value):
    from js import encodeURIComponent
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    elif isinstance(value, bool):
        value = "true" if value else "false"
    return str(encodeURIComponent(str(value)))
