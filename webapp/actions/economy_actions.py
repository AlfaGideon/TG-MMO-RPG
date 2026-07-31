"""Действия вкладки «Экономика»: экземпляры, лоты аукциона и валюты."""
from engine import adminops, auction, items, money
from webapp import dom
from webapp.pages import economy as page


def register(app, A):
    A("eco-tab", lambda arg: _tab(app, arg))
    A("inst-view", lambda arg: app.modal(page.instance_form(app, arg)))
    A("inst-del", lambda arg: _inst_del(app, arg))
    A("lot-del", lambda arg: _lot_del(app, arg))
    A("instances-page", lambda arg: _set_page(app, arg))
    A("money-page", lambda arg: _money_page(app, arg))
    A("money-save", lambda _="": _money_save(app))
    A("money-gem", lambda arg: _money_gem(app, arg))


def _tab(app, tab):
    app.state["eco_tab"] = tab
    app.render()


def _set_page(app, arg):
    app.state["instances_page"] = int(arg)
    app.render()


def _inst_del(app, uid):
    """Убирает экземпляр из мира — например, дубль после сбоя."""
    try:
        adminops.require(app.actor, "edit_content")
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    inst = items.get(app.store, uid)
    if inst is None:
        dom.toast("Экземпляр не найден", "err")
        return
    name = items.title(inst)
    items.destroy(app.store, uid)
    app.store.save()
    app.close_modal()
    dom.toast(f"Удалено: {name}")
    app.render()


def _lot_del(app, lot_id):
    """Снимает лот с витрины и возвращает вещь продавцу."""
    try:
        adminops.require(app.actor, "edit_content")
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    lot = auction.find(app.store, lot_id)
    if lot is None:
        dom.toast("Лот не найден", "err")
        return
    seller = app.store.players.get(int(lot.get("seller") or 0))
    lot["status"] = "cancelled"
    inst = items.get(app.store, lot.get("uid"))
    if inst is not None and seller is not None:
        inst["owner"] = seller.tg_id
        seller.inventory.append(int(inst.get("idx", 0)))
        items.record(app.store, inst, "expired", seller.tg_id, detail="снят админом")
        app.store.save_player(seller)
    app.store.save()
    dom.toast("Лот снят с витрины")
    app.render()


# ── валюты ──────────────────────────────────────────────────

def _money_page(app, arg):
    app.state["money_page"] = int(arg)
    app.render()


def _money_save(app):
    """Курс кристалла и стартовый премиум — из полей вкладки «Валюты»."""
    try:
        adminops.require(app.actor, "settings")
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    values = {k: dom.value(f"#money_{k}", "") for k in money.TUNABLES}
    saved = money.set_tunables(app.store, values)
    dom.toast(f"Курс кристалла: 1{money.PREMIUM_ICON} = "
              f"{money.fmt(saved['premium_rate'])}")
    app.render()


def _money_gem(app, arg):
    """Выдать или списать кристаллы игроку прямо из таблицы кошельков."""
    try:
        adminops.require(app.actor, "edit_players")
    except adminops.Denied as e:
        dom.toast(str(e), "err")
        return
    tg_id, _, amount = arg.partition(":")
    p = app.store.players.get(int(tg_id))
    if p is None:
        dom.toast("Игрок не найден", "err")
        return
    delta = int(amount or 0)
    money.grant_premium(p, delta)
    app.store.save_player(p)
    sign = "+" if delta >= 0 else ""
    adminops.queue(app.store, p.tg_id,
                   f"{money.PREMIUM_ICON} Кристаллы: {sign}{delta} "
                   f"(теперь {money.premium(p)})")
    dom.toast(f"{p.name}: {sign}{delta}{money.PREMIUM_ICON} → {money.premium(p)}")
    app.render()
