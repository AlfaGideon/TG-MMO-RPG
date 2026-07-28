import os
import logging
from aiogram.types import CallbackQuery, Message, FSInputFile, InputMediaPhoto

logger = logging.getLogger(__name__)


def get_photo_input(image_url: str):
    """
    Converts image_url (URL or local path) to an aiogram photo input (URL string or FSInputFile).
    Returns None if image_url is empty or local file does not exist.
    """
    if not image_url or not image_url.strip():
        return None

    url = image_url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url

    # Local file path handling
    if url.startswith("/static/"):
        path = "admin" + url
    elif url.startswith("static/"):
        path = "admin/" + url
    else:
        path = url

    if os.path.exists(path) and os.path.isfile(path):
        return FSInputFile(path)

    return None


async def send_or_edit_photo(
    event,
    text: str,
    reply_markup=None,
    image_url: str = None,
    parse_mode: str = "HTML",
):
    """
    Sends or edits a Telegram message with optional photo.
    Falls back gracefully to text if image_url is empty, missing, or fails.
    """
    photo_input = get_photo_input(image_url) if image_url else None
    msg = event.message if isinstance(event, CallbackQuery) else event

    if photo_input:
        if msg and msg.photo:
            try:
                await msg.edit_media(
                    media=InputMediaPhoto(media=photo_input, caption=text, parse_mode=parse_mode),
                    reply_markup=reply_markup,
                )
                return
            except Exception as e:
                logger.debug(f"edit_media failed: {e}")

        # If not already a photo or edit_media failed: try delete & answer photo
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

            try:
                await msg.answer_photo(
                    photo=photo_input,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
                return
            except Exception as e:
                logger.warning(f"answer_photo failed: {e}")

    # Fallback to text message if photo_input is None or answer_photo failed
    if msg and msg.photo:
        try:
            await msg.delete()
        except Exception:
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
        except Exception as e:
            err_str = str(e).lower()
            if "message is not modified" not in err_str:
                try:
                    await msg.answer(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                    )
                except Exception:
                    pass
