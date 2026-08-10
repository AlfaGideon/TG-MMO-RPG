"""Единая отправка картинок в Telegram и быстрый безопасный fallback.

Telegram принимает уже загруженное изображение по ``file_id`` почти мгновенно.
Раньше каждый переход заново отправлял PNG размером 2–3 МБ через
``FSInputFile`` — из-за этого обычная кнопка могла отвечать 5+ секунд.
Здесь file_id кэшируется в памяти и в ``data/telegram_file_ids.json``; ключ
включает id бота и версию локального файла, поэтому чужой/обновлённый ассет
никогда не будет подставлен случайно.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import logging
import os
from pathlib import Path

from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto

from core.assets import REPO_ROOT, local_asset_path
from core.npc_images import npc_image_url


logger = logging.getLogger(__name__)

_CACHE_PATH = Path(
    os.getenv("TELEGRAM_FILE_ID_CACHE", str(REPO_ROOT / "data" / "telegram_file_ids.json"))
)
_CACHE_MAX = 1200
_MESSAGE_CACHE_MAX = 3000
# Иллюстрации из репозитория часто весят 2–3 МБ в PNG. Telegram всё равно
# пережимает sendPhoto, поэтому заранее делаем небольшой JPEG и экономим
# секунды первой отправки. Маленькие файлы и динамические карты не трогаем.
_OPTIMIZE_ABOVE = 700_000
_MEDIA_CACHE_DIR = REPO_ROOT / "data" / "telegram_media"
_file_ids: OrderedDict[str, str] | None = None
# (chat_id, message_id) -> source key. Даёт самый быстрый путь: если фото
# то же самое, меняем только caption и вообще не вызываем editMessageMedia.
_message_sources: OrderedDict[tuple[int, int], str] = OrderedDict()


def _optimized_upload_path(path: Path) -> Path:
    """Вернуть компактную Telegram-копию большого растра или исходник."""
    try:
        stat = path.stat()
    except OSError:
        return path
    if stat.st_size <= _OPTIMIZE_ABOVE or path.suffix.lower() not in {
        ".png", ".jpg", ".jpeg"
    }:
        return path

    stamp = f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    target = _MEDIA_CACHE_DIR / f"{hashlib.sha256(stamp).hexdigest()[:24]}.jpg"
    if target.is_file():
        return target

    try:
        from PIL import Image

        _MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with Image.open(path) as source:
            image = source.convert("RGBA")
            if max(image.size) > 1280:
                image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            # У игровых артов тёмный фон; прозрачность на sendPhoto всё равно
            # не сохраняет практической пользы, зато PNG весит мегабайты.
            background = Image.new("RGB", image.size, (18, 22, 28))
            background.paste(image, mask=image.getchannel("A"))
            background.save(target, "JPEG", quality=86, optimize=True,
                            progressive=True)
        # Если конкретный JPEG неожиданно не стал меньше — шлём исходник.
        if target.stat().st_size >= stat.st_size:
            target.unlink(missing_ok=True)
            return path
        return target
    except Exception as exc:  # Pillow/диск не должны ломать игровой экран
        logger.debug("Не удалось оптимизировать %s для Telegram: %s", path, exc)
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return path


def get_photo_input(image_url: str | None):
    """Преобразовать URL/локальный путь в формат фото aiogram.

    ``/static/...`` всегда вычисляется от файла проекта, а не от текущей
    рабочей папки процесса. Возвращает ``None``, если путь пуст или файл
    отсутствует. HTTP(S) URL Telegram забирает сам.
    """
    url = (image_url or "").strip()
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url

    path = local_asset_path(url)
    if path and path.is_file():
        return FSInputFile(str(_optimized_upload_path(path)))

    logger.warning("Изображение бота не найдено: %r (путь: %s)", image_url,
                   path or "неподдерживаемый")
    return None


def has_usable_photo(image_url: str | None) -> bool:
    """Есть ли шанс отправить указанное фото без попытки отправки в Telegram."""
    url = (image_url or "").strip()
    if not url:
        return False
    if url.startswith(("http://", "https://")):
        return True
    path = local_asset_path(url)
    return bool(path and path.is_file())


def get_npc_image(npc_name: str | None, npc_type: str | None = None,
                  location_name: str | None = None) -> str:
    """Совместимый фасад для портрета NPC."""
    del npc_type
    return npc_image_url(npc_name, location_name)


def _load_file_ids() -> OrderedDict[str, str]:
    global _file_ids
    if _file_ids is not None:
        return _file_ids
    values: OrderedDict[str, str] = OrderedDict()
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for key, value in raw.items():
                if isinstance(key, str) and isinstance(value, str) and value:
                    values[key] = value
    except FileNotFoundError:
        pass
    except Exception as exc:  # повреждённый кэш не должен ломать бота
        logger.debug("Не удалось прочитать кэш Telegram file_id: %s", exc)
    while len(values) > _CACHE_MAX:
        values.popitem(last=False)
    _file_ids = values
    return values


def _save_file_ids() -> None:
    """Маленькая атомарная запись; ошибка диска не влияет на ответ игроку."""
    values = _load_file_ids()
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_PATH.with_name(f"{_CACHE_PATH.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(values, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        os.replace(tmp, _CACHE_PATH)
    except Exception as exc:
        logger.debug("Не удалось сохранить кэш Telegram file_id: %s", exc)


def _bot_id(event, msg) -> int:
    for obj in (event, msg):
        bot = getattr(obj, "bot", None)
        value = getattr(bot, "id", None)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    return 0


def _source_key(image_url: str | None, bot_id: int) -> str | None:
    url = (image_url or "").strip()
    if not url:
        return None
    path = local_asset_path(url)
    if path and path.is_file():
        try:
            stat = path.stat()
            rel = path.relative_to(REPO_ROOT).as_posix()
            # size + mtime инвалидируют file_id после замены картинки в панели.
            source = f"file:{rel}:{stat.st_size}:{stat.st_mtime_ns}"
        except OSError:
            return None
    else:
        source = f"url:{url}"
    return f"bot:{bot_id}:{source}"


def _cached_file_id(key: str | None) -> str | None:
    if not key:
        return None
    values = _load_file_ids()
    value = values.get(key)
    if value:
        values.move_to_end(key)
    return value


def _forget_file_id(key: str | None) -> None:
    if key and _load_file_ids().pop(key, None) is not None:
        _save_file_ids()


def _remember_file_id(key: str | None, result) -> None:
    if not key or result is None:
        return
    photos = getattr(result, "photo", None)
    if not photos:
        return
    file_id = getattr(photos[-1], "file_id", None)
    if not file_id:
        return
    values = _load_file_ids()
    changed = values.get(key) != str(file_id)
    values[key] = str(file_id)
    values.move_to_end(key)
    while len(values) > _CACHE_MAX:
        values.popitem(last=False)
        changed = True
    if changed:
        _save_file_ids()


def _message_id(msg) -> tuple[int, int] | None:
    try:
        return int(msg.chat.id), int(msg.message_id)
    except (AttributeError, TypeError, ValueError):
        return None


def _remember_message(msg, key: str | None) -> None:
    ident = _message_id(msg)
    if ident is None or not key:
        return
    _message_sources[ident] = key
    _message_sources.move_to_end(ident)
    while len(_message_sources) > _MESSAGE_CACHE_MAX:
        _message_sources.popitem(last=False)


def _same_photo(msg, key: str | None, cached_id: str | None) -> bool:
    ident = _message_id(msg)
    if ident is not None and key and _message_sources.get(ident) == key:
        return True
    if cached_id and getattr(msg, "photo", None):
        return any(getattr(photo, "file_id", None) == cached_id for photo in msg.photo)
    return False


def _inputs(image_url: str | None, key: str | None):
    """Сначала file_id; при его протухании вызывающий повторит с исходником."""
    cached = _cached_file_id(key)
    if cached:
        yield cached, True
    original = get_photo_input(image_url)
    if original is not None:
        yield original, False


async def _edit_caption(msg, text, reply_markup, parse_mode) -> bool:
    try:
        await msg.edit_caption(
            caption=text, reply_markup=reply_markup, parse_mode=parse_mode
        )
        return True
    except Exception as exc:  # noqa: BLE001
        if "message is not modified" in str(exc).lower():
            return True
        logger.debug("edit_caption failed: %s", exc)
        return False


async def send_or_edit_photo(
    event,
    text: str,
    reply_markup=None,
    image_url: str | None = None,
    parse_mode: str = "HTML",
):
    """Отправить/сменить фото, переиспользуя Telegram file_id.

    Если кэшированный file_id устарел, автоматически выполняется ровно одна
    повторная попытка с исходным файлом/URL. При отказе медиа старое сообщение
    не удаляется заранее: игрок в любом случае получает рабочий текст.
    """
    msg = event.message if isinstance(event, CallbackQuery) else event
    key = _source_key(image_url, _bot_id(event, msg)) if image_url else None
    cached_id = _cached_file_id(key)

    if msg and getattr(msg, "photo", None) and key:
        # На большинстве кнопок меняется только текст поверх той же картинки.
        # editMessageCaption не загружает мегабайты повторно.
        if _same_photo(msg, key, cached_id):
            if await _edit_caption(msg, text, reply_markup, parse_mode):
                _remember_message(msg, key)
                return

        for photo_input, was_cached in _inputs(image_url, key):
            try:
                result = await msg.edit_media(
                    media=InputMediaPhoto(media=photo_input, caption=text,
                                           parse_mode=parse_mode),
                    reply_markup=reply_markup,
                )
                _remember_file_id(key, result)
                _remember_message(result if result is not True else msg, key)
                return
            except Exception as exc:  # noqa: BLE001
                logger.debug("edit_media failed (%s): %s",
                             "cached file_id" if was_cached else "source", exc)
                if was_cached:
                    _forget_file_id(key)
                    continue
                break

    elif msg and key:
        # Из текста нельзя превратиться в фото через editMessageText. Сначала
        # успешно шлём новый экран и только потом удаляем старое сообщение.
        for photo_input, was_cached in _inputs(image_url, key):
            try:
                result = await msg.answer_photo(
                    photo=photo_input,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
                _remember_file_id(key, result)
                _remember_message(result, key)
                try:
                    await msg.delete()
                except Exception:
                    pass
                return
            except Exception as exc:  # noqa: BLE001
                logger.debug("answer_photo failed (%s): %s",
                             "cached file_id" if was_cached else "source", exc)
                if was_cached:
                    _forget_file_id(key)
                    continue
                logger.warning("Не удалось отправить фото %r: %s", image_url, exc)
                break

    # Фото отсутствует/сломано/отклонено. Сохраняем старое медиа и меняем
    # caption; если и это невозможно — отправляем отдельный текст.
    if msg and getattr(msg, "photo", None):
        if await _edit_caption(msg, text, reply_markup, parse_mode):
            return
        try:
            await msg.answer(text=text, reply_markup=reply_markup,
                             parse_mode=parse_mode)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить текстовый экран: %s", exc)
    elif msg:
        try:
            await msg.edit_text(text=text, reply_markup=reply_markup,
                                parse_mode=parse_mode)
        except Exception as exc:  # noqa: BLE001
            if "message is not modified" not in str(exc).lower():
                try:
                    await msg.answer(text=text, reply_markup=reply_markup,
                                     parse_mode=parse_mode)
                except Exception as fallback_exc:  # noqa: BLE001
                    logger.warning("Не удалось отправить текстовый экран: %s",
                                   fallback_exc)


def _reset_photo_caches_for_tests(cache_path: Path | None = None,
                                  media_cache_dir: Path | None = None) -> None:
    """Тестовый helper; production-код его не вызывает."""
    global _file_ids, _CACHE_PATH, _MEDIA_CACHE_DIR
    _file_ids = OrderedDict()
    _message_sources.clear()
    if cache_path is not None:
        _CACHE_PATH = Path(cache_path)
    if media_cache_dir is not None:
        _MEDIA_CACHE_DIR = Path(media_cache_dir)
