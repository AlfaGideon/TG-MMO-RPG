"""«Библия лора» и конструктор промптов для AI-мастерской.

«Долгая память» генератора реализована архитектурно: на каждую
генерацию в системный промпт подаётся досье мира — сводка локаций,
NPC, квестов, мобов и боссов из БД + записи, которые админ утвердил в
«библию лора» (AIGeneration.status == "bible"). При контексте
провайдера в 131–256K токенов досье целиком умещается всегда; страхуемся
усечением по бюджету символов.
"""
import json

from sqlalchemy import select

# Бюджет досье: ~4 символа на токен (русский чуть дешевле, запас есть).
DOSSIER_BUDGET = 60_000
BIBLE_BUDGET = 30_000

KINDS = {
    "quest":         ("📜 Квест", "одно задание с целью и наградой"),
    "quest_chain":   ("🕸 Линейка квестов", "3–5 связанных заданий с аркой"),
    "npc_dialogue":  ("💬 Диалог NPC", "реплики жителя: приветствие, слухи, напутствие"),
    "location_desc": ("🗺 Описание места", "атмосфера локации или клетки"),
    "lore_note":     ("📖 Запись в библию лора", "каноничный кусок истории мира"),
}

TONES = ["мрачный сказ", "суровый реализм", "искрящий фольклор",
         "мистика и недомолвки", "героический эпос"]

_SYSTEM = """Ты — ведущий нарративный дизайнер тёмного фэнтези-MMORPG «Shadow Lands»
(Telegram-игра). Пишешь по-русски, плотно и атмосферно, без воды и без
англицизмов. Мир невелик: безопасный Погост Костров, опасные земли
вокруг, катаклизмы, фракции (стража, культ, мусорщики, орден), мировые
боссы. Правила вселенной нерушимы: чудес мало, смерть ощутима, юмор —
чёрный и редкий. Ниже — актуальное досье мира: опирайся на него как на
канон, не противоречь именам и фактам, развивай, а не переписывай.

=== ДОСЬЕ МИРА ===
{dossier}
=== КОНЕЦ ДОСЬЕ ==="""


async def collect_dossier(session, budget: int = DOSSIER_BUDGET) -> str:
    """Сводка мира из БД + утверждённая библия лора."""
    from core.models import (AIGeneration, Cell, Location, Mob, Quest)

    parts = []

    result = await session.execute(select(Location).order_by(Location.id))
    locs = result.scalars().all()
    if locs:
        parts.append("ЛОКАЦИИ: " + "; ".join(
            f"{l.name} ({getattr(l.location_type, 'value', l.location_type)}, "
            f"мин.ур.{l.min_level}) — {l.description}" for l in locs))

    result = await session.execute(
        select(Cell).where(Cell.has_npc == True))  # noqa: E712
    npcs = result.scalars().all()
    if npcs:
        loc_name = {l.id: l.name for l in locs}
        parts.append("NPC: " + "; ".join(
            f"{c.npc_name or 'Безымянный'} [{loc_name.get(c.location_id, '?')}"
            f"{', этаж ' + str(c.floor) if c.floor else ''}"
            f"{', ' + c.npc_type if c.npc_type else ''}]"
            f" — {(c.npc_dialogue or '').strip()[:160]}"
            for c in npcs if c.npc_name or c.npc_dialogue))

    result = await session.execute(select(Quest).order_by(Quest.id))
    quests = result.scalars().all()
    if quests:
        parts.append("КВЕСТЫ: " + "; ".join(
            f"«{q.name}» ({q.objective_type} {q.objective_target}×"
            f"{q.objective_count}, ур.{q.min_level}"
            f"{', от ' + q.npc_name if q.npc_name else ''})"
            for q in quests))

    result = await session.execute(select(Mob).order_by(Mob.level))
    mobs = result.scalars().all()
    if mobs:
        parts.append("МОБЫ: " + "; ".join(
            f"{m.name} (ур.{m.level})" for m in mobs[:40]))

    # Канон браузерного стека — боссы и фракции живут в engine-данных.
    try:
        from engine.worldboss import BOSSES
        parts.append("МИРОВЫЕ БОССЫ: " + "; ".join(
            f"{b['name']} (ур.{b['level']}) — {b['omen']}"
            for b in BOSSES.values()))
    except Exception:
        pass
    try:
        from engine.factions import FACTIONS
        parts.append("ФРАКЦИИ: " + "; ".join(
            f"{f['name']} — {f['desc'][:100]}" for f in FACTIONS.values()))
    except Exception:
        pass

    result = await session.execute(
        select(AIGeneration)
        .where(AIGeneration.status == "bible")
        .order_by(AIGeneration.created_at.desc())
        .limit(120))
    bible = result.scalars().all()
    if bible:
        chunks, used = [], 0
        for row in bible:
            piece = f"• {row.title or row.target_label}: {row.content.strip()}"
            if used + len(piece) > BIBLE_BUDGET:
                break
            chunks.append(piece)
            used += len(piece)
        parts.append("БИБЛИЯ ЛОРА (утверждённый канон):\n" + "\n".join(chunks))

    text = "\n\n".join(p for p in parts if p)
    suffix = "\n… [досье усечено по бюджету]"
    if len(text) > budget > len(suffix):
        text = text[:budget - len(suffix)] + suffix
    return text or "Мир сгенерирован недавно, канон почти пуст — ты задаёшь его первым."


def build_messages(kind: str, params: dict, dossier: str) -> list:
    """messages для chat/completions под конкретный тип генерации."""
    task = _TASKS[kind](params)
    return [
        {"role": "system", "content": _SYSTEM.format(dossier=dossier)},
        {"role": "user", "content": task},
    ]


def _anchor(params: dict) -> str:
    bits = []
    if params.get("location_name"):
        bits.append(f"место действия: {params['location_name']}")
    if params.get("npc_name"):
        bits.append(f"NPC: {params['npc_name']} (роль: {params.get('npc_type') or 'житель'})")
    if params.get("level"):
        bits.append(f"целевой уровень игрока: {params['level']}")
    if params.get("tone"):
        bits.append(f"тон: {params['tone']}")
    if params.get("seed_text"):
        bits.append(f"затравка от гейм-мастера: {params['seed_text']}")
    return ("Привязки: " + "; ".join(bits) + ".\n") if bits else ""


def _TASK_quest(p: dict) -> str:
    return (_anchor(p) +
            "Придумай ОДИН квест. Формат строго:\n"
            "НАЗВАНИЕ: …\n"
            "ЗАКАЗЧИК: (имя NPC из досье или новый)\n"
            "ТИП: kill|collect|explore|talk\n"
            "ЦЕЛЬ: (что и сколько)\n"
            "ТЕКСТ: (2–4 предложения от лица заказчика, живой язык)\n"
            "НАГРАДА: (золото, опыт; предмет — если уместно)\n"
            "КРЮЧОК: (одно предложение — куда эта история может вырасти)")


def _TASK_quest_chain(p: dict) -> str:
    return (_anchor(p) +
            "Придумай ЛИНЕЙКУ из 3–5 связанных квестов с общей аркой: "
            "завязка → развитие → выбор → развязка. Для каждого квеста — "
            "блок формата:\n"
            "НАЗВАНИЕ / ЗАКАЗЧИК / ТИП kill|collect|explore|talk / ЦЕЛЬ / "
            "ТЕКСТ (1–2 предложения) / НАГРАДА.\n"
            "Между блоками проставь номер и связку («потому что…»). Арка "
            "должна менять отношение NPC или участка мира, а не быть "
            "просто «принеси-подай».")


def _TASK_npc_dialogue(p: dict) -> str:
    return (_anchor(p) +
            "Напиши диалоговый набор NPC (текст попадёт прямо в игру):\n"
            "1) ПРИВЕТСТВИЕ (первая встреча, 1–2 фразы)\n"
            "2) ОБЫЧНАЯ РЕПЛИКА (повторный визит)\n"
            "3) СЛУХ (полезная крупица про мир — можно крючок к квесту)\n"
            "4) НАПУТСТВИЕ (короткое, в характере)\n"
            "Говори за персонажа, а не про него. Без ремарок типа «улыбается».")


def _TASK_location_desc(p: dict) -> str:
    return (_anchor(p) +
            "Напиши описание места (2 абзаца по 2–4 предложения): первый — "
            "что видит путник, второй — что здесь случилось/слух/тайна. "
            "Описание должно намекать на возможные события, а не быть "
            "открыткой.")


def _TASK_lore_note(p: dict) -> str:
    return (_anchor(p) +
            "Напиши каноничную лор-запись (3–6 предложений): событие, "
            "договор, проклятие или обычай этого мира. Запись попадёт в "
            "«библию лора» и будет связывать будущие генерации — пиши "
            "фактами, без риторических вопросов.")


_TASKS = {"quest": _TASK_quest, "quest_chain": _TASK_quest_chain,
          "npc_dialogue": _TASK_npc_dialogue,
          "location_desc": _TASK_location_desc, "lore_note": _TASK_lore_note}

# ── Разбор сгенерированного квеста в поля формы ───────────────


def parse_quest_fields(text: str) -> dict:
    """Вытащить НАЗВАНИЕ/ТИП/ЦЕЛЬ/ТЕКСТ из ответа модели (мягко)."""
    out = {}
    for line in text.splitlines():
        up, _, rest = line.partition(":")
        key = up.strip().upper().lstrip("0123456789.-) ").strip()
        rest = rest.strip()
        if not rest:
            continue
        if key.startswith("НАЗВАНИЕ") and not out.get("name"):
            out["name"] = rest.strip("«»\"")[:128]
        elif key.startswith("ТИП") and not out.get("objective_type"):
            low = rest.lower()
            for t in ("kill", "collect", "explore", "talk"):
                if t in low:
                    out["objective_type"] = t
                    break
        elif key.startswith("ЦЕЛЬ") and not out.get("objective_target"):
            out["objective_target"] = rest[:64]
        elif key.startswith("ТЕКСТ") and not out.get("description"):
            out["description"] = rest
        elif key.startswith("НАГРАДА") and not out.get("reward_hint"):
            out["reward_hint"] = rest[:64]
        elif key.startswith("ЗАКАЗЧИК") and not out.get("npc_name"):
            out["npc_name"] = rest.strip()[:128]
    return out


def summarize_params(kind: str, params: dict) -> str:
    """Короткая подпись запроса для журнала генераций."""
    return json.dumps({"kind": kind, **{k: v for k, v in params.items() if v}},
                      ensure_ascii=False)


def guess_title(kind: str, params: dict, content: str) -> str:
    """Подпись черновика: из разбора квеста, привязок или первых слов."""
    if kind in ("quest", "quest_chain"):
        fields = parse_quest_fields(content)
        if fields.get("name"):
            return f"Квест «{fields['name']}»"
    if params.get("npc_name") and kind == "npc_dialogue":
        return f"Диалог: {params['npc_name']}"
    if params.get("location_name"):
        who = KINDS.get(kind, (kind,))[0]
        return f"{who}: {params['location_name']}"
    first = " ".join(content.split())[:80]
    return first or KINDS.get(kind, (kind,))[0]
