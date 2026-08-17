"""Действия вкладки «Экономика»: экземпляры предметов и лоты аукциона."""
from engine import adminops, auction, items
from webapp import dom
from webapp.pages import economy as page


def register(app, A):
    A("eco-tab", lambda arg: _tab(app, arg))
    A("inst-view", lambda arg: app.modal(page.instance_form(app, arg)))
    A("inst-del", lambda arg: _inst_del(app, arg))
    A("lot-del", lambda arg: _lot_del(app, arg))
    A("instances-page", lambda arg: _set_page(app, arg))
    A("eco-dividends", lambda _="": _dividends(app))
    A("eco-sweep", lambda _="": _sweep(app))


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


def _dividends(app):
    """Начислить накопившиеся дивиденды вручную (пункт № 71).

    В браузере нет фонового планировщика, как `bot/runner.py:375` у
    сервера, поэтому у админа должна быть кнопка. Начисление идемпотентно:
    считает пропущенные периоды и двигает отметку времени.
    """
    from engine import shadowecon as E

    payouts = E.accrue_dividends(app.store)
    if not payouts:
        dom.toast("Период ещё не наступил — начислять нечего")
    else:
        total = sum(p["amount"] for p in payouts)
        dom.toast(f"Выплачено {total}🟤 · получателей: {len(payouts)}")
    app.render()


def _sweep(app):
    """Изъять просроченные залоги: они уходят на чёрный рынок."""
    from engine import shadowecon as E

    seized = E.sweep_loans(app.store)
    dom.toast(f"Изъято залогов: {len(seized)}" if seized
              else "Просроченных залогов нет")
    app.render()
