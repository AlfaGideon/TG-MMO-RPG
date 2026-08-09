"""Дуэли чести с денежными ставками между игроками."""
import random
from core.models import Character
from core.stats import combat_stats, attack_power, damage_reduction


async def resolve_wager_duel(session, char_a: Character, char_b: Character, wager_bronze: int) -> dict:
    """Проводит дуэль со ставкой между двумя игроками."""
    from engine.currency import total_in_bronze, deduct_currency, add_currency

    if wager_bronze < 0:
        return {"ok": False, "reason": "Ставка не может быть отрицательной."}
    if total_in_bronze(char_a) < wager_bronze:
        return {"ok": False, "reason": f"У {char_a.name} не хватает {wager_bronze - total_in_bronze(char_a)}🟤."}
    if total_in_bronze(char_b) < wager_bronze:
        return {"ok": False, "reason": f"У {char_b.name} не хватает {wager_bronze - total_in_bronze(char_b)}🟤."}

    # Списываем ставки в банк
    deduct_currency(char_a, wager_bronze)
    deduct_currency(char_b, wager_bronze)

    stats_a = await combat_stats(session, char_a)
    stats_b = await combat_stats(session, char_b)

    hp_a = char_a.max_hp or 100
    hp_b = char_b.max_hp or 100
    log = []
    rounds = 0

    while hp_a > 0 and hp_b > 0 and rounds < 20:
        rounds += 1
        dmg_a = max(4, attack_power(stats_a, char_a) + random.randint(-2, 4) - damage_reduction(stats_b) // 2)
        hp_b -= dmg_a
        log.append(f"Раунд {rounds}: {char_a.name} бьёт на {dmg_a} урона.")
        if hp_b <= 0:
            break

        dmg_b = max(4, attack_power(stats_b, char_b) + random.randint(-2, 4) - damage_reduction(stats_a) // 2)
        hp_a -= dmg_b
        log.append(f"Раунд {rounds}: {char_b.name} отвечает ударом на {dmg_b} урона.")

    winner = char_a if hp_a > 0 else char_b
    loser = char_b if hp_a > 0 else char_a

    # Банк победителя (за вычетом 5% комиссии арены)
    total_pot = wager_bronze * 2
    payout = int(total_pot * 0.95)
    add_currency(winner, bronze=payout)

    await session.flush()
    return {
        "ok": True,
        "winner_name": winner.name,
        "loser_name": loser.name,
        "payout": payout,
        "rounds": rounds,
        "log": log,
    }
