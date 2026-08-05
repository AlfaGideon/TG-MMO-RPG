"""Единая отправка картинок в Telegram и безопасный откат на текст."""
import logging

from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto

from core.assets import local_asset_path
from core.npc_images import npc_image_url
from core.mob_images import mob_image_url


logger = logging.getLogger(__name__)


def get_photo_input(image_url: str | None):
    """Преобразовать URL/локальный путь в формат фото aiogram.

    ``/static/...`` всегда вычисляется от файла проекта, а не от текущей
    рабочей папки процесса. Это критично для Docker, службы Windows и
    запусков ярлыком: раньше такая разница молча превращала экран в текст.
    Возвращает ``None``, если путь пуст или локальный файл не найден.
    """
    url = (image_url or "").strip()
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url

    path = local_asset_path(url)
    if path and path.is_file():
        return FSInputFile(str(path))

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
    """Совместимый фасад для портрета NPC.

    ``npc_type`` оставлен в сигнатуре для старых вызовов; портрет зависит от
    имени и, если отдельного изображения ещё нет, от стороны локации.
    """
    del npc_type
    return npc_image_url(npc_name, location_name)


def get_mob_image(mob_name: str | None) -> str:
    """Путь к стандартному портрету монстра по его имени."""
    return mob_image_url(mob_name)


async def send_or_edit_photo(
    event,
    text: str,
    reply_markup=None,
    image_url: str | None = None,
    parse_mode: str = "HTML",
):
    """Отправить/сменить фото с подписью; при ошибке честно откатиться к тексту."""
    photo_input = get_photo_input(image_url) if image_url else None
    msg = event.message if isinstance(event, CallbackQuery) else event

    if photo_input:
        if msg and msg.photo:
            try:
                await msg.edit_media(
                    media=InputMediaPhoto(media=photo_input, caption=text,
                                           parse_mode=parse_mode),
                    reply_markup=reply_markup,
                )
                return
            except Exception as exc:  # noqa: BLE001
                logger.debug("edit_media failed: %s", exc)

        # Из текста нельзя превратиться в фото через editMessageText.
        # Удаляем старое сообщение и отправляем новый экран.
        if msg:
            try:
                await msg.delete()
            except Exception:  # чужие/старые сообщения Telegram не даст удалить
                pass

            try:
                await msg.answer_photo(
                    photo=photo_input,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Не удалось отправить фото %r: %s", image_url, exc)

    # Фото отсутствует, файл сломан или Telegram отверг медиа/подпись.
    # В любом случае игрок не остаётся с мёртвой кнопкой — получает текст.
    if msg and msg.photo:
        try:
            await msg.delete()
        except Exception:  # noqa: BLE001
            pass
        await msg.answer(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    elif msg:
        try:
            await msg.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception as exc:  # noqa: BLE001
            if "message is not modified" not in str(exc).lower():
                try:
                    await msg.answer(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                    )
                except Exception as fallback_exc:  # noqa: BLE001
                    logger.warning("Не удалось отправить текстовый экран: %s",
                                   fallback_exc)
