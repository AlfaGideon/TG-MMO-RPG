"""Действия вкладки «Жизнь мира»: респавн, характеры тварей, карман и VIP."""
from webapp import dom


def register(app, A):
    A("respawn-save", lambda _="": _respawn_save(app))
    A("respawn-now", lambda _="": _respawn_now(app))
    A("behavior-save", lambda _="": _behavior_save(app))
    A("stash-save", lambda _="": _stash_save(app))
    A("stash-reset", lambda _="": _stash_reset(app))


def _respawn_save(app):
    """Задержки возвращения тварей и сундуков по типам локаций."""
    from engine import respawn
    from webapp.pages.world_living import LOC_TYPES

    app.store.settings[respawn.SETTING_ON] = dom.value("#rspOn", "1") == "1"
    for kind, prefix in (("mob", "rsp_mob_"), ("chest", "rsp_chest_")):
        values = {key: dom.value(f"#{prefix}{key}", "") for key, _ in LOC_TYPES}
        respawn.set_delays(app.store, kind, values)
    dom.toast("Настройки респавна сохранены")
    app.render()


def _stash_save(app):
    """Размер кармана, прибавка VIP, доля потерь и срок VIP."""
    from engine import stash

    values = {key: dom.value(f"#st_{key}", "") for key in stash.TUNABLES}
    stash.set_tunables(app.store, values)
    dom.toast("Настройки инвентаря и VIP сохранены")
    app.render()


def _stash_reset(app):
    from engine import stash

    for key in stash.TUNABLES:
        app.store.settings.pop(key, None)
    app.store.save()
    dom.toast("Возвращены значения по умолчанию")
    app.render()


def _behavior_save(app):
    """Выключатели брожения и самостоятельных нападений."""
    from engine import behavior

    app.store.settings[behavior.WANDER_SETTING] = dom.value("#behWander", "1") == "1"
    app.store.settings[behavior.HUNT_SETTING] = dom.value("#behHunt", "1") == "1"
    app.store.save()
    dom.toast("Поведение тварей сохранено")
    app.render()


def _respawn_now(app):
    """Вернуть всё, что ждёт очереди, немедленно."""
    import time

    from engine import respawn
    for c in app.store.world.values():
        if c.mob_at:
            c.mob_at = time.time() - 1
        if c.chest_at:
            c.chest_at = time.time() - 1
    mobs, chests = respawn.tick(app.store)
    app.bot.game.world = app.store.world
    dom.toast(f"Вернулось: 👾 {mobs} · 📦 {chests}"
              if mobs or chests else "Возвращать было нечего")
    app.render()
