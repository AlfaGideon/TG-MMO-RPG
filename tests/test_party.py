"""Пати: поиск союзников по фракции/близости, запрет пати врагам кольца,
приглашения и заявки с принятием/отказом, предел состава, уборка заявок
при распаде пати.

python3 tests/test_party.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Временная БД ДО импорта core.* — модуль читает DATABASE_URL при загрузке.
_TMP = tempfile.mkdtemp(prefix="tgmmorpg_party_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_TMP, 'party.db')}"

try:
    from sqlalchemy import select
    from core import factions as core_factions
    from core.database import async_session, init_db
    from core.models import Character, Location, Party, PartyInvite, User
    import bot.handlers.party as pm
except ImportError as e:
    print(f"⚠ Пропуск: нет зависимостей серверного стека ({e})")
    sys.exit(0)

FAILED = []


def check(cond, label):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)


EDITS = []


async def _fake_edit(event, text, reply_markup=None, parse_mode=None):
    EDITS.append(text)


pm.safe_edit_text = _fake_edit  # не ходим в Telegram-API


class FakeCB:
    """Минимальный CallbackQuery: answer лишь запоминает алерты."""

    def __init__(self, tg, data):
        self.from_user = SimpleNamespace(id=tg)
        self.data = data
        self.message = None
        self.alerts = []

    async def answer(self, text=None, show_alert=False, **kw):
        self.alerts.append(text or "")


async def _char_id(tg):
    async with async_session() as s:
        u = (await s.execute(select(User).where(User.telegram_id == tg))).scalar_one()
        return (await s.execute(
            select(Character).where(Character.user_id == u.id))).scalar_one().id


async def seed():
    async with async_session() as s:
        s.add_all([
            Location(id=1, name="Замок Пепла", description="тест"),
            Location(id=2, name="Северный тракт", description="тест"),
        ])
        specs = [
            # tg, имя, фракция, локация, забанен, офлайн-VIP, уровень, этаж
            (101, "Алька", '{"guard": 50}', 1, False, False, 5, 0),
            (102, "Борис", '{"guard": 40}', 2, False, False, 7, 0),
            (103, "Цезарь", '{"cult": 60}', 1, False, False, 9, 0),
            (104, "Добромир", '{"scavengers": 50}', 1, False, False, 3, 0),
            (105, "Евлампий", "", 1, False, False, 1, 0),
            (106, "Ждан", '{"guard": 50}', 1, False, True, 4, 0),
            (107, "Зиновий", '{"guard": 50}', 2, True, False, 2, 0),
            (108, "Ия", '{"order": 50}', 1, False, False, 6, 1),
            (109, "Захар", '{"guard": 50}', 1, False, False, 1, 0),
        ]
        for tg, name, rep, loc, banned, off, lvl, fl in specs:
            u = User(telegram_id=tg, first_name=name, is_banned=banned)
            s.add(u)
            await s.flush()
            s.add(Character(
                user_id=u.id, name=name, character_class="warrior",
                level=lvl, reputation=rep, location_id=loc, floor=fl,
                stats_locked=True, offline_protected=off, is_vip=off,
            ))
        await s.commit()


async def main():
    await init_db()
    await seed()

    print("— Кольцо вражды —")
    check(core_factions.hostile("guard", "scavengers"), "Стража ↔ Гильдия — враги")
    check(core_factions.hostile("scavengers", "guard"), "вражда обоюдна")
    check(core_factions.hostile("order", "guard"), "Орден ↔ Стража — враги")
    check(not core_factions.hostile("guard", "cult"), "Стража + Культ (диагональ) — не враги")
    check(not core_factions.hostile("guard", "guard"), "одна сила — не враги")
    check(not core_factions.hostile("guard", None), "нейтрал — не враг")

    print("— Поиск союзников —")
    async with async_session() as s:
        u = (await s.execute(select(User).where(User.telegram_id == 101))).scalar_one()
        me = (await s.execute(select(Character).where(Character.user_id == u.id))).scalar_one()
        cands = await pm._find_candidates(s, me)
        names = {c.name for c, _ in cands}
        check("Борис" in names, "поиск находит своего по фракции (даже далеко)")
        check("Цезарь" in names, "рядом союзник по диагонали (Культ) — можно")
        check("Евлампий" in names, "нейтральный герой рядом — можно")
        check("Добромир" not in names, "враждующая фракция (Гильдия) рядом — нельзя")
        check("Ждан" not in names, "офлайн-VIP скрыт из поиска")
        check("Зиновий" not in names, "забаненный скрыт из поиска")
        check("Ия" not in names, "другой этаж — не «рядом», а во фракции не своя")
        near_names = [c.name for c, near in cands if near]
        check(cands and cands[0][0].name in near_names, "рядом стоят первыми в выдаче")

    print("— Приглашение создаёт пати и заявку —")
    b_id = await _char_id(102)
    await pm.party_ask(FakeCB(101, f"party_ask:{b_id}"))
    async with async_session() as s:
        inv = (await s.execute(select(PartyInvite))).scalar_one_or_none()
        check(inv is not None and inv.kind == "invite" and inv.status == "pending",
              "приглашение создано (invite/pending)")
        parties = (await s.execute(select(Party))).scalars().all()
        check(len(parties) == 1, "пати автоматически создана")
        me_id = await _char_id(101)
        me = await s.get(Character, me_id)
        check(me.party_id == parties[0].id, "инициатор — в новой пати")
        party1_id = parties[0].id

    cb = FakeCB(101, f"party_ask:{b_id}")
    await pm.party_ask(cb)
    check(any("уже отправлена" in a for a in cb.alerts),
          "повторное приглашение — отказ «уже отправлена»")

    check(not any("party_inv_yes" in t for t in EDITS),
          "уведомление улетает личкой, а не в чат инициатора")

    print("— Принятие и отказ —")
    c_id = await _char_id(103)
    async with async_session() as s:
        inv = (await s.execute(select(PartyInvite))).scalar_one()
        inv_id = inv.id
    cb = FakeCB(105, f"party_inv_yes:{inv_id}")
    await pm.party_inv_accept(cb)
    check(any("не тебе" in a for a in cb.alerts), "чужую заявку принять нельзя")
    await pm.party_inv_accept(FakeCB(102, f"party_inv_yes:{inv_id}"))
    async with async_session() as s:
        size = len((await s.execute(
            select(Character).where(Character.party_id == party1_id))).scalars().all())
        check(size == 2, "после принятия в пати двое")
        check((await s.get(PartyInvite, inv_id)).status == "accepted",
              "статус заявки accepted")

    await pm.party_ask(FakeCB(101, f"party_ask:{c_id}"))
    async with async_session() as s:
        inv2 = (await s.execute(
            select(PartyInvite).where(PartyInvite.status == "pending"))).scalar_one()
    await pm.party_inv_accept(FakeCB(103, f"party_inv_yes:{inv2.id}"))
    async with async_session() as s:
        size = len((await s.execute(
            select(Character).where(Character.party_id == party1_id))).scalars().all())
        check(size == 3, "в пати трое — потолок MAX_SIZE")

    a_id = await _char_id(101)
    cb = FakeCB(105, f"party_ask:{a_id}")
    await pm.party_ask(cb)
    check(any("полная" in a for a in cb.alerts), "в полную пати проситься нельзя")

    cb = FakeCB(104, f"party_ask:{a_id}")
    await pm.party_ask(cb)
    check(any("враждуют" in a for a in cb.alerts),
          "приглашение во враждующую фракцию блокируется")

    cb = FakeCB(102, "party_search")
    await pm.party_search(cb)
    check(any("предводитель" in a for a in cb.alerts),
          "обычный член пати не может звать")

    print("— Заявка на вступление —")
    await pm.party_create(FakeCB(105, "party_create"))
    e_id = await _char_id(105)
    ia_id = await _char_id(108)
    await pm.party_ask(FakeCB(108, f"party_ask:{e_id}"))
    async with async_session() as s:
        invj = (await s.execute(
            select(PartyInvite).where(PartyInvite.kind == "join"))).scalar_one()
        check(invj.status == "pending", "заявка на вступление создана (join/pending)")
        check(invj.to_character_id == e_id, "заявка адресована предводителю")
        invj_id = invj.id
    await pm.party_inv_accept(FakeCB(105, f"party_inv_yes:{invj_id}"))
    async with async_session() as s:
        ia = await s.get(Character, ia_id)
        p2 = (await s.execute(select(Party).where(Party.id != party1_id))).scalar_one()
        check(ia.party_id == p2.id, "предводитель принял — проситель в пати")

    print("— Выход и распад —")
    await pm.party_leave(FakeCB(105, "party_leave"))
    async with async_session() as s:
        p2 = (await s.execute(select(Party).where(Party.id != party1_id))).scalar_one()
        check(p2.leader_id == ia_id, "предводительство передано оставшемуся")

    await pm.party_leave(FakeCB(108, "party_leave"))
    async with async_session() as s:
        p2_gone = await s.get(Party, p2.id)
        check(p2_gone is None, "опустевшая пати удалена")

    await pm.party_create(FakeCB(105, "party_create"))
    z_id = await _char_id(109)
    await pm.party_ask(FakeCB(105, f"party_ask:{z_id}"))
    async with async_session() as s:
        p3 = (await s.execute(select(Party).where(Party.leader_id == e_id))).scalar_one()
        pend = (await s.execute(
            select(PartyInvite).where(PartyInvite.party_id == p3.id)
            .where(PartyInvite.status == "pending"))).scalars().all()
        check(len(pend) == 1, "висящее приглашение есть перед распадом")
        p3_id = p3.id
    await pm.party_leave(FakeCB(105, "party_leave"))
    async with async_session() as s:
        check(await s.get(Party, p3_id) is None, "одинокая пати после выхода лидера удалена")
        zombies = (await s.execute(
            select(PartyInvite).where(PartyInvite.party_id == p3_id)
            .where(PartyInvite.status == "pending"))).scalars().all()
        check(len(zombies) == 0, "висящие приглашения распущенной пати отменены")

    print()
    if FAILED:
        print(f"❌ ПРОВАЛЕНО {len(FAILED)}:")
        for f in FAILED:
            print("   -", f)
        return 1
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
