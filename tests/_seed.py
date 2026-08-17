"""Детерминизм наборов: единая точка для random.seed (пункт № 5 IDEAS-100.md).

`AUDIT-BUGS.md`, раздел «Прочее на заметку»: прогон однажды поймал флап в
`test_dungeon.py` — тест зависел от неспинованного `random`. Часть наборов
пинит seed сама (`random.seed(5)` в `test_dungeon.py:120`), часть — нет.

Тонкость, из-за которой нельзя просто дописать `random.seed(N)` везде:
пятнадцать наборов генерируют `telegram_id` пользователя как
`random.randint(100_000_000, 999_999_999)`, а таблица `users` держит
`telegram_id` UNIQUE и база `data/game.db` переживает прогон. Со спинованным
seed второй прогон подряд выдал бы те же id и упал бы на UNIQUE constraint.

Поэтому два разных источника случайности:

* `pin(n)` — пинит ГЛОБАЛЬНЫЙ `random` (игровая логика: дроп, бой, генерация
  подземелий). Константа у каждого набора своя, чтобы наборы не повторяли
  друг другу одну и ту же последовательность;
* `unique_id()` / `unique_name()` — НЕ зависят от seed: берут
  `random.SystemRandom` плюс счётчик процесса. Это «технические» значения
  для уникальных колонок БД, на результат проверок они не влияют.
"""
import itertools
import random

_SYS = random.SystemRandom()
_COUNTER = itertools.count(1)


def pin(seed):
    """Зафиксировать глобальный random. Вызывать в начале набора."""
    random.seed(seed)
    return seed


def unique_id(low=100_000_000, high=999_999_999):
    """Уникальное значение для UNIQUE-колонки (telegram_id и т. п.).

    Намеренно вне спинованного потока: повторный прогон по той же базе
    не должен ловить UNIQUE constraint.
    """
    return _SYS.randint(low, high)


def unique_name(prefix):
    """Уникальное имя для UNIQUE-колонки (название гильдии и т. п.)."""
    return f"{prefix} {next(_COUNTER)}-{_SYS.randint(1000, 9999)}"
