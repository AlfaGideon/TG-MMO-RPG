"""Генерация контента бесплатными LLM — провайдеры и вызовы.

Выбор провайдеров сделан по реестру
https://github.com/mnfst/awesome-free-llm-apis (перманентные free-тарифы).

Логика выбора под задачу «квесты/лор/диалоги NPC»:
- большой контекст: в промпт подаём «библию лора» (сводку всего мира +
  утверждённые записи), поэтому контекст ≥100K обязателен;
- перманентный бесплатный тариф (не триал-кредиты);
- доступность из ЕС (сервер игрока — в Европе: free-тариф Gemini в
  EU/UK недоступен, поэтому он не main, а опция);
- качество русского языка.

Итоговая цепочка приоритетов:
1. Mistral (La Plateforme, FR): 256K контекст, ~1 млрд токенов/мес free.
2. Groq (US): 131K контекст, 30 RPM / 1000 RPD, очень быстрый.
3. OpenRouter: free-пул моделей с одним ключом (есть 262K контекст).
4. Offline: встроенный шаблонный генератор, чтобы блок работал и без
   ключа (помечается в интерфейсе).

Все провайдеры — OpenAI-совместимые (`POST {base}/chat/completions`).
Настройки: AppSetting в админке (приоритет) или env AI_PROVIDER/AI_API_KEY/
AI_MODEL/AI_BASE_URL.
"""
import json
import os

from sqlalchemy import select

# ── Реестр провайдеров (данные awesome-free-llm-apis, июль 2026) ─────

PROVIDERS = {
    "mistral": {
        "name": "Mistral AI (La Plateforme) 🇫🇷 — рекомендуется",
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-large-latest",
        "models": [
            ("mistral-large-latest", "Mistral Large 3 — 256K ctx, 256K out"),
            ("mistral-medium-latest", "Mistral Medium 3.5 — 256K ctx"),
            ("mistral-small-latest", "Mistral Small 4 — 256K ctx, быстрее"),
            ("ministral-14b-latest", "Ministral 14B — 256K ctx, экономно"),
        ],
        "limits": "free «Experiment»: ~1RPS, 500K TPM, ~1B токенов/мес, без карты",
        "key_url": "https://console.mistral.ai/api-keys",
        "note": "Промпты могут использоваться для улучшения моделей.",
    },
    "groq": {
        "name": "Groq 🇺🇸 — самый быстрый",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "models": [
            ("llama-3.3-70b-versatile", "Llama 3.3 70B — 131K ctx, 32K out"),
            ("openai/gpt-oss-120b", "GPT-OSS 120B — 131K ctx, 65K out"),
            ("llama-3.1-8b-instant", "Llama 3.1 8B — 131K ctx, 14400 RPD"),
        ],
        "limits": "free: 30 RPM, 1000 RPD (14400 у 8B), без карты",
        "key_url": "https://console.groq.com/keys",
        "note": "LPU-инференс: ответ почти мгновенный.",
    },
    "openrouter": {
        "name": "OpenRouter 🇺🇸 — много моделей одним ключом",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "nvidia/nemotron-3-super-120b-a12b:free",
        "models": [
            ("nvidia/nemotron-3-super-120b-a12b:free",
             "Nemotron Super 120B — 262K ctx"),
            ("openai/gpt-oss-20b:free", "GPT-OSS 20B — 131K ctx"),
            ("google/gemma-4-31b-it:free", "Gemma 4 31B — 262K ctx"),
            ("openrouter/free", "Автоматический free-роутер"),
        ],
        "limits": "free-модели: 20 RPM, 50 RPD (1000 RPD при $10+ на счёте)",
        "key_url": "https://openrouter.ai/keys",
        "note": "Модели с суффиксом :free; состав пула меняется.",
    },
    "gemini": {
        "name": "Google Gemini 🇺🇸 — 1M контекст (не для EU/UK)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.5-flash",
        "models": [
            ("gemini-2.5-flash", "Gemini 2.5 Flash — 1M ctx, 65K out"),
            ("gemini-2.5-flash-lite", "Flash-Lite — 1M ctx, 30 RPM"),
            ("gemini-2.5-pro", "Gemini 2.5 Pro — 1M ctx, 5 RPM / 50 RPD"),
        ],
        "limits": "free: 15–30 RPM, 1500 RPD; ⚠ free-тариф НЕ работает из EU/UK/CH",
        "key_url": "https://aistudio.google.com/app/apikey",
        "note": "Макс. контекст; free-промпты идут на обучение Google.",
    },
    "github": {
        "name": "GitHub Models 🇺🇸 — если есть GitHub-аккаунт",
        "base_url": "https://models.github.ai/inference",
        "default_model": "openai/gpt-4.1",
        "models": [
            ("openai/gpt-4.1", "GPT-4.1 — 1M ctx (8K на запрос), 10 RPM/50 RPD"),
            ("openai/gpt-4.1-mini", "GPT-4.1 mini — 15 RPM/150 RPD"),
            ("meta/Llama-3.3-70B-Instruct", "Llama 3.3 70B — 15 RPM/150 RPD"),
        ],
        "limits": "free: 10–15 RPM, 50–150 RPD, лимит ~8K входа на запрос!",
        "key_url": "https://github.com/marketplace/models",
        "note": "Из-за лимита входа библию лора подаём урезанной.",
    },
    "custom": {
        "name": "Свой OpenAI-совместимый endpoint",
        "base_url": "",
        "default_model": "",
        "models": [],
        "limits": "как у вашего endpoint",
        "key_url": "",
        "note": "Любой сервис с API формата chat/completions (Ollama, vLLM…).",
    },
}

# Максимальные токены ответа по типам генерации (скромно — free-тарифы).
MAX_TOKENS = {"quest": 1400, "quest_chain": 3200, "npc_dialogue": 1800,
              "location_desc": 1600, "lore_note": 1200}
TEMPERATURE = 0.85
TIMEOUT_SECONDS = 120


class AIError(Exception):
    """Ошибка вызова провайдера с понятным админу текстом."""


def mask_key(key: str) -> str:
    """Показать ключ безопасно: первые 3 и последние 4 символа."""
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:3] + "…" + key[-4:]


async def load_settings(session) -> dict:
    """Настройки генератора: AppSetting важнее env."""
    result = await session.execute(
        select(_AppSetting).where(_AppSetting.key.like("ai_%")))
    stored = {row.key: row.value for row in result.scalars().all()}

    def pick(name, default=""):
        v = stored.get(name, "").strip()
        if v:
            return v
        return os.environ.get(name.upper(), default).strip()

    provider = pick("ai_provider", "mistral")
    if provider not in PROVIDERS:
        provider = "mistral"
    info = PROVIDERS[provider]
    return {
        "provider": provider,
        "api_key": pick("ai_api_key"),
        "model": pick("ai_model") or info["default_model"],
        "base_url": pick("ai_base_url") or info["base_url"],
    }


async def save_settings(session, provider: str, api_key: str, model: str,
                        base_url: str):
    if provider not in PROVIDERS:
        raise AIError("Неизвестный провайдер")
    values = {"ai_provider": provider, "ai_model": model.strip(),
              "ai_base_url": base_url.strip()}
    if api_key.strip() and "…" not in api_key:      # маску не сохраняем
        values["ai_api_key"] = api_key.strip()
    for key, value in values.items():
        result = await session.execute(
            select(_AppSetting).where(_AppSetting.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(_AppSetting(key=key, value=value))
    await session.flush()


async def provider_status(session) -> dict:
    """Что показать в шапке мастерской (ключ — только маской)."""
    st = await load_settings(session)
    info = PROVIDERS[st["provider"]]
    return {
        **st,
        "api_key": mask_key(st["api_key"]),
        "configured": bool(st["api_key"] and st["base_url"]),
        "limits": info["limits"],
        "key_url": info["key_url"],
        "note": info["note"],
        "name": info["name"],
        "env_only": bool(os.environ.get("AI_API_KEY")),
    }


async def chat_complete(base_url: str, api_key: str, model: str,
                        messages: list, max_tokens: int,
                        temperature: float = TEMPERATURE) -> str:
    """Один вызов OpenAI-совместимого chat/completions."""
    import aiohttp

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": messages,
               "max_tokens": max_tokens, "temperature": temperature}
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(url, json=payload, headers=headers) as resp:
                body = await resp.text()
                if resp.status == 401 or resp.status == 403:
                    raise AIError(
                        "Ключ отклонён (401/403). Проверьте ключ в настройках.")
                if resp.status == 429:
                    raise AIError(
                        "Лимит free-тарифа исчерпан (429). Подождите минуту "
                        "или переключите провайдера в настройках.")
                if resp.status != 200:
                    raise AIError(f"Провайдер ответил {resp.status}: "
                                  f"{body[:300]}")
                data = json.loads(body)
    except AIError:
        raise
    except Exception as e:
        raise AIError(f"Сеть/формат ответа: {e}") from e
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise AIError(f"Нестандартный ответ провайдера: {body[:300]}") from e
    return (text or "").strip()


# ── Офлайн-режим ──────────────────────────────────────────────

_OFFLINE_OPENERS = [
    "Записи Летописца Брана гласят:",
    "У костров Погоста шепчутся:",
    "В архивах Заброшенной Крепости найдено:",
]


def offline_generate(kind: str, params: dict, dossier: str) -> str:
    """Встроенный генератор, чтобы мастерская работала без API-ключа.

    Собирает заготовку из живого контента игры (engine.data), честно
    помеченную как офлайн-режим: для полноценной генерации нужен ключ.
    """
    from engine import data as eng_data
    from engine.content import MOBS, NPCS, QUESTS

    import random
    rnd = random.Random(params.get("seed_text", "") or None)
    seed_hint = (params.get("seed_text") or "").strip()
    tone = params.get("tone") or "мрачный сказ"
    loc = params.get("location_name") or "Тёмный Лес"

    def npc():
        return rnd.choice(NPCS)

    def mob():
        same = [m for m in MOBS if eng_data.LOCATIONS[m[8]][0] == loc]
        return rnd.choice(same or MOBS)

    opener = rnd.choice(_OFFLINE_OPENERS)
    if kind == "npc_dialogue":
        n = npc()
        return (f"[основано на {n[0]}, роль {n[2]}]\n"
                f"{n[0]}: «{seed_hint or n[1]}»\n"
                f"{opener} {loc} снова неспокоен. {n[0]} оглядывается, "
                f"прежде чем продолжить: «Держись троп и не отвечай на "
                f"зов из чащи. Расскажу больше — когда принесёшь вести "
                f"от стражи.»")
    if kind == "quest_chain":
        m = mob()
        return (f"Цепочка из трёх заданий ({tone}):\n"
                f"1. «Первые следы» — {opener} зачистить {m[0]} "
                f"({rnd.randint(2, 4)} шт.) у {loc}.\n"
                f"2. «То, что они стерегут» — найти и принести стражнику "
                f"улику с тел.\n"
                f"3. «Корень зла» — вернуться ночью и закончить начатое. "
                f"{('Затравка: ' + seed_hint) if seed_hint else ''}")
    if kind == "location_desc":
        st = rnd.choice(eng_data.STORIES)
        saying = seed_hint or "камни здесь помнят шаги тех, кто не вернулся"
        sign = rnd.choice(["туман", "пепел", "роса"])
        return (f"{opener} {loc} — {st[0]}. {st[1]} "
                f"Путники говорят: {saying}. При ночном свете {sign} "
                f"складывается в знаки.")
    if kind == "lore_note":
        n = npc()
        return (f"{opener} до Тьмы {loc} держался на договоре с лесом. "
                f"{n[0]} вспоминает: «{n[1]}». "
                f"{('Связка: ' + seed_hint) if seed_hint else ''}")
    # quest
    m = mob()
    q = rnd.choice(QUESTS)
    return (f"{opener} {loc} «{q[1]}-2» (по мотивам «{q[1]}»).\n"
            f"Заказчик: {npc()[0]}. Задача: истребить {m[0]} — "
            f"{rnd.randint(3, 6)} особей. {m[1]} "
            f"Награда: {rnd.randint(80, 260)}🟤 и слава. "
            f"Тон: {tone}. {('Затравка: ' + seed_hint) if seed_hint else ''}")


async def generate(session, kind: str, params: dict, dossier: str,
                   messages: list) -> dict:
    """Сгенерировать: с ключом — через провайдера, без — офлайн."""
    st = await load_settings(session)
    max_tokens = MAX_TOKENS.get(kind, 1400)
    if st["api_key"] and st["base_url"]:
        text = await chat_complete(st["base_url"], st["api_key"], st["model"],
                                   messages, max_tokens)
        return {"content": text, "provider": st["provider"],
                "model": st["model"], "offline": False,
                "prompt_chars": sum(len(m["content"]) for m in messages)}
    return {"content": offline_generate(kind, params, dossier),
            "provider": "offline", "model": "builtin-templates",
            "offline": True,
            "prompt_chars": sum(len(m["content"]) for m in messages)}


# Импорт внизу, чтобы core.ai можно было читать без моделей (тесты).
from core.models import AppSetting as _AppSetting  # noqa: E402
