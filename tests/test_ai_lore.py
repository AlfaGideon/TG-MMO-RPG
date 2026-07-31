"""AI-мастерская: провайдеры, библия лора, применение черновиков.

python3 tests/test_ai_lore.py

Админ-эндпоинты гоняются настоящим TestClient (когда доступен httpx),
генерация — против локального мок-сервера: реальные сетевые вызовы в
тестах не делаются.
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Тестовая БД — ДО импорта admin.main (тот читает DATABASE_URL на старте).
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DB.name}")
os.environ.setdefault("BOT_TOKEN", "test-token")

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


def _have_modules(*names):
    import importlib.util
    return all(importlib.util.find_spec(n) for n in names)


async def _make_db():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from core.database import Base
    import importlib
    importlib.import_module("core.models")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


# ── офлайн-генератор без сети и ключей ────────────────────────

def test_offline_generator():
    print("\n— Офлайн-генератор (без ключа блок всё равно работает) —")
    from core import ai as AI
    for kind in ("quest", "quest_chain", "npc_dialogue",
                 "location_desc", "lore_note"):
        text = AI.offline_generate(kind, {"tone": "мрачный сказ",
                                          "location_name": "Тёмный Лес"},
                                   dossier="")
        check(isinstance(text, str) and len(text) > 60,
              f"{kind}: правдоподобная заготовка ({len(text)} симв.)")
    a = AI.offline_generate("quest", {"seed_text": "один и тот же seed"}, "")
    b = AI.offline_generate("quest", {"seed_text": "один и тот же seed"}, "")
    check(a == b, "детерминизм по seed-затравке")


def test_key_masking():
    print("\n— Маски ключей —")
    from core import ai as AI
    check(AI.mask_key("gsk_1234567890abcd") == "gsk…abcd", "длинный ключ маскируется")
    check(AI.mask_key("abc") == "•••", "короткий ключ прячется целиком")
    check(AI.mask_key("") == "", "пустой — пусто")


# ── настройки: AppSetting важнее env, маска не затирает ключ ──

async def test_settings_async():
    print("\n— Настройки провайдера —")
    from core import ai as AI
    _engine, sm = await _make_db()
    os.environ.pop("AI_API_KEY", None)
    os.environ.pop("AI_PROVIDER", None)

    async with sm() as s:
        st = await AI.load_settings(s)
        check(st["provider"] == "mistral" and not st["api_key"],
              "по умолчанию — Mistral без ключа")
        await AI.save_settings(s, "groq", "gsk_secret_NNNN",
                               "llama-3.3-70b-versatile", "")
        await s.commit()

    os.environ["AI_PROVIDER"] = "gemini"
    os.environ["AI_API_KEY"] = "env-key"
    async with sm() as s:
        st = await AI.load_settings(s)
        check(st["provider"] == "groq" and st["api_key"] == "gsk_secret_NNNN",
              "AppSetting важнее env")
        status = await AI.provider_status(s)
        check(status["configured"] and status["api_key"] == "gsk…NNNN",
              "статус: настроен, ключ под маской")

    # повторное сохранение с маской-как-вводом не затирает настоящий ключ
    async with sm() as s:
        await AI.save_settings(s, "groq", "gsk…NNNN", "", "")
        await s.commit()
    async with sm() as s:
        st = await AI.load_settings(s)
        check(st["api_key"] == "gsk_secret_NNNN", "маска не перезаписала ключ")
    os.environ.pop("AI_PROVIDER", None)
    os.environ.pop("AI_API_KEY", None)


# ── вызов провайдера: мок-сервер вместо настоящей сети ──────

async def _mock_server(handler):
    from aiohttp import web
    app = web.Application()
    app.router.add_post("/v1/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/v1"


async def test_chat_complete_async():
    print("\n— chat_complete против мок-сервера —")
    from core import ai as AI

    async def ok(req):
        data = await req.json()
        assert data["model"] == "test-model"
        assert data["messages"][0]["role"] == "system"
        from aiohttp import web
        return web.json_response(
            {"choices": [{"message": {"content": " Готово. "}}]})

    runner, base = await _mock_server(ok)
    try:
        out = await AI.chat_complete(base, "k", "test-model",
                                     [{"role": "system", "content": "s"},
                                      {"role": "user", "content": "u"}], 100)
        check(out == "Готово.", "200: текст разобран и подрезан")
    finally:
        await runner.cleanup()

    async def err429(req):
        from aiohttp import web
        return web.json_response({"error": "slow down"}, status=429)

    runner, base = await _mock_server(err429)
    try:
        try:
            await AI.chat_complete(base, "k", "m", [], 100)
            check(False, "429 -> понятная ошибка")
        except AI.AIError as e:
            check("лимит" in str(e).lower(), "429 -> понятная ошибка")
    finally:
        await runner.cleanup()

    async def err401(req):
        from aiohttp import web
        return web.json_response({"error": "bad key"}, status=401)

    runner, base = await _mock_server(err401)
    try:
        try:
            await AI.chat_complete(base, "k", "m", [], 100)
            check(False, "401 -> понятная ошибка")
        except AI.AIError as e:
            check("ключ" in str(e).lower(), "401 -> понятная ошибка")
    finally:
        await runner.cleanup()

    async def garbage(req):
        from aiohttp import web
        return web.Response(text="<html>502</html>")

    runner, base = await _mock_server(garbage)
    try:
        try:
            await AI.chat_complete(base, "k", "m", [], 100)
            check(False, "битый ответ -> понятная ошибка")
        except AI.AIError:
            check(True, "битый ответ -> понятная ошибка")
    finally:
        await runner.cleanup()


# ── библия лора и промпты ─────────────────────────────────────

async def test_dossier_async():
    print("\n— Досье мира и «долгая память» —")
    from core import lore as LORE
    from core.models import (AIGeneration, Cell, Location, Mob, Quest)

    _engine, sm = await _make_db()
    async with sm() as s:
        loc = Location(name="Тёмный Лес", description="Дубы шепчутся.")
        s.add(loc)
        await s.flush()
        s.add(Cell(location_id=loc.id, x=1, y=1, has_npc=True,
                   npc_name="Травница Осока",
                   npc_dialogue="Болото кормит и лечит.", is_passable=True))
        s.add(Mob(name="Ворг", description="", hp=10, damage=1,
                  defense=0, level=2))
        s.add(Quest(name="Волчья напасть", description="...",
                    objective_type="kill", objective_target="Ворг",
                    objective_count=3, min_level=2))
        s.add(AIGeneration(kind="lore_note",
                           title="Договор с лесом",
                           content="Погост кормится щедростью болота по договору.",
                           status="draft"))
        s.add(AIGeneration(kind="lore_note",
                           title="Ночная тишина",
                           content="После катаклизма лес молчит трое суток.",
                           status="bible"))
        await s.commit()

        dossier = await LORE.collect_dossier(s)
        check("Тёмный Лес" in dossier and "Травница Осока" in dossier,
              "локации и NPC попадают в досье")
        check("Волчья напасть" in dossier and "Ворг" in dossier,
              "квесты и мобы попадают в досье")
        check("Ночная тишина" in dossier, "утверждённая библия попадает")
        check("Договор с лесом" not in dossier, "черновики НЕ попадают")

        tight = await LORE.collect_dossier(s, budget=120)
        check(len(tight) <= 140, f"усечение по бюджету ({len(tight)} симв.)")


def test_prompts_and_parsing():
    print("\n— Промпты и разбор квеста —")
    from core import lore as LORE

    for kind in LORE.KINDS:
        msgs = LORE.build_messages(kind, {"location_name": "Погост Костров",
                                          "tone": "искрящий фольклор"}, "ДОСЬЕ")
        check(len(msgs) == 2 and "ДОСЬЕ" in msgs[0]["content"],
              f"{kind}: messages собираются с досье")

    sample = ("НАЗВАНИЕ: «Тишина под полом»\nЗАКАЗЧИК: Гробовщик Сивый\n"
              "ТИП: explore\nЦЕЛЬ: подвал таверны\n"
              "ТЕКСТ: Под таверной опять скребётся. Спустись и убедись, "
              "что это крысы.\nНАГРАДА: 150 золота\nКРЮЧОК: ...")
    f = LORE.parse_quest_fields(sample)
    check(f.get("name") == "Тишина под полом", "название вытащено")
    check(f.get("objective_type") == "explore", "тип вытащен")
    check(f.get("npc_name") == "Гробовщик Сивый", "заказчик вытащен")
    check("скребётся" in (f.get("description") or ""), "текст вытащен")

    title = LORE.guess_title("quest", {}, sample)
    check("Тишина под полом" in title, "подпись черновика строится")


# ── админ-эндпоинты настоящим TestClient ─────────────────────

def test_admin_endpoints():
    print("\n— Админ-эндпоинты (TestClient) —")
    from fastapi.testclient import TestClient
    # admin.main импортируется однажды; DATABASE_URL уже подменён выше
    from admin.main import app

    with TestClient(app) as c:
        r = c.get("/editor/ai")
        check(r.status_code == 200 and "AI-мастерская" in r.text,
              "страница открывается (200)")
        check("офлайн" in r.text, "без ключа честно пишет «офлайн»")

        r = c.post("/editor/ai/generate",
                   data={"kind": "quest", "seed_text": "культ под таверной"})
        j = r.json()
        check(r.status_code == 200 and j["ok"] and j["offline"],
              f"генерация без ключа: offline=True ({j.get('provider')})")
        check(j["prompt_chars"] > 500,
              f"в промпт подано досье ({j['prompt_chars']} симв.)")
        gid = j["id"]

        r = c.post(f"/editor/ai/{gid}/to-bible", follow_redirects=False)
        check(r.status_code == 303, "утверждение в библию: 303")

        r = c.post("/editor/ai/generate", data={"kind": "npc_dialogue",
                                                "npc_name": "Торговец Варн"})
        j2 = r.json()
        check(j2["ok"], "вторая генерация проходит")

        # применить квест в БД
        r = c.post(f"/editor/ai/{gid}/apply-quest",
                   data={"name": "Культ под таверной",
                         "description": "Спустись.", "objective_type": "explore",
                         "objective_target": "Таверна", "objective_count": "1",
                         "reward_gold": "120", "reward_exp": "300",
                         "min_level": "3", "location_id": "", "npc_name": ""},
                   follow_redirects=False)
        check(r.status_code == 303, "apply-quest: 303")
        import sqlite3
        con = sqlite3.connect(_TMP_DB.name)
        row = con.execute(
            "SELECT objective_type, status FROM quests q, ai_generations g "
            "WHERE g.id=? AND q.name='Культ под таверной'", (gid,)).fetchone()
        check(row == ("explore", "applied"),
              f"квест создан, черновик помечен applied {row}")

        # диалог в клетку NPC
        cell_row = con.execute(
            "SELECT id FROM cells WHERE has_npc=1 LIMIT 1").fetchone()
        if cell_row:
            r = c.post(f"/editor/ai/{j2['id']}/apply-dialogue",
                       data={"cell_id": str(cell_row[0]),
                             "dialogue": "Держись троп, странник."},
                       follow_redirects=False)
            dlg = con.execute("SELECT npc_dialogue FROM cells WHERE id=?",
                              (cell_row[0],)).fetchone()[0]
            check(r.status_code == 303 and dlg == "Держись троп, странник.",
                  "диалог записан в клетку NPC")
        else:
            check(True, "клеток с NPC в тестовой БД нет — пропуск")

        # настройки провайдера
        r = c.post("/editor/ai/settings",
                   data={"provider": "mistral", "model": "mistral-large-latest",
                         "api_key": "mis_abcdefgh1234"},
                   follow_redirects=False)
        check(r.status_code == 303, "настройки: 303")
        r = c.get("/editor/ai")
        check("mis…1234" in r.text and "mis_abcdefgh1234" not in r.text,
              "ключ хранится под маской и не светится в HTML")


def main():
    test_offline_generator()
    test_key_masking()
    test_prompts_and_parsing()
    if _have_modules("sqlalchemy", "aiosqlite"):
        asyncio.run(test_settings_async())
        asyncio.run(test_dossier_async())
    else:
        print("⚠ Пропуск БД-части: нет sqlalchemy/aiosqlite")
    if _have_modules("sqlalchemy", "aiosqlite", "aiohttp"):
        asyncio.run(test_chat_complete_async())
    else:
        print("⚠ Пропуск мок-сервера: нет aiohttp")
    if _have_modules("sqlalchemy", "aiosqlite", "fastapi", "jinja2", "httpx"):
        test_admin_endpoints()
    else:
        print("⚠ Пропуск админ-эндпоинтов: нет fastapi/jinja2/httpx")

    try:
        os.unlink(_TMP_DB.name)
    except OSError:
        pass
    print("\n" + "=" * 46)
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}: {', '.join(FAILED)}")
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
