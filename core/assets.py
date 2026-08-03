"""Надёжные пути к локальным ассетам серверной части.

Бот может запускаться из Docker, через ярлык Windows, systemd или вручную.
Текущая рабочая папка в этих сценариях не обязана быть корнем репозитория,
поэтому строить путь к ``admin/static`` относительно ``cwd`` нельзя.
"""
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = REPO_ROOT / "admin" / "static"


def local_asset_path(value: str | None) -> Path | None:
    """Вернуть абсолютный путь локального ассета или ``None``.

    Поддерживаются привычные URL панели ``/static/...`` и ``static/...``,
    а также относительные пути внутри репозитория. HTTP(S)-ссылки намеренно
    не превращаются в файлы: Telegram забирает их напрямую.
    """
    raw = (value or "").strip()
    if not raw or raw.startswith(("http://", "https://")):
        return None

    # У загруженных в панели ссылок иногда есть cache-buster ``?v=...``.
    path_text = unquote(urlsplit(raw).path)
    if not path_text:
        return None

    if path_text.startswith("/static/"):
        candidate = STATIC_ROOT / path_text.removeprefix("/static/")
    elif path_text.startswith("static/"):
        candidate = STATIC_ROOT / path_text.removeprefix("static/")
    else:
        candidate = Path(path_text)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate

    try:
        resolved = candidate.resolve()
        # Относительные значения храним только внутри проекта: это и
        # предсказуемо для деплоя, и не даёт ошибочной ссылке прочитать
        # произвольный файл на сервере.
        if not resolved.is_relative_to(REPO_ROOT):
            return None
        return resolved
    except (OSError, RuntimeError):
        return None


def local_asset_exists(value: str | None) -> bool:
    """Существует ли указанная локальная картинка на диске."""
    path = local_asset_path(value)
    return bool(path and path.is_file())
