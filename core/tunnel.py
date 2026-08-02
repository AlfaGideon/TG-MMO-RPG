"""Публичный HTTPS для админ-панели через Cloudflare Quick Tunnel.

Кнопка Telegram Mini App (web_app) открывается только по HTTPS с публичным
доменом, а панель обычно крутится на домашней машине за NAT. Quick Tunnel
даёт бесплатный адрес вида *.trycloudflare.com без регистрации и ключей.

Модуль сам скачивает официальный бинарь cloudflared под текущую ОС в bin/,
запускает `cloudflared tunnel --url http://127.0.0.1:PORT`, вылавливает из
его вывода публичный адрес и сохраняет его в настройки панели (panel_url) —
бот подхватывает адрес для кнопки «🌐 Открыть панель» автоматически.

Адрес быстрых туннелей меняется при каждом перезапуске — поэтому при смене
админа оповещаем личным сообщением с кнопкой Mini App.

Управление: переменная окружения ADMIN_TUNNEL (по умолчанию "1"). Если
публичный адрес уже задан вручную (настройка panel_url или PUBLIC_URL /
ADMIN_PUBLIC_URL — например, на Render), туннель не поднимается.
"""
import asyncio
import logging
import os
import platform
import re
import shutil
import stat
import urllib.request
from urllib.parse import urlparse

from sqlalchemy import select

from core.database import async_session
from core.models import User
from core.settings_store import (
    PANEL_URL_KEY, build_miniapp_url, get_setting, normalize_url, set_panel_url,
    set_setting,
)

logger = logging.getLogger("tunnel")

TUNNEL_ENV = "ADMIN_TUNNEL"
ANNOUNCED_KEY = "panel_url_announced"

# В ошибках cloudflared бывает URL API (`https://api.trycloudflare.com/...`).
# Это не адрес туннеля, поэтому его нельзя сохранять как panel_url.
TRYCLOUDFLARE_RE = re.compile(
    r"https://(?!api\.trycloudflare\.com\b)"
    r"[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com\b"
)
CLOUDFLARED_LATEST = "https://github.com/cloudflare/cloudflared/releases/latest/download/"

_URL_TIMEOUT = 45  # столько ждём публичный адрес от cloudflared


def tunnel_enabled() -> bool:
    return os.getenv(TUNNEL_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def is_quick_tunnel_url(value: str) -> bool:
    """Это адрес, который раньше выдал Cloudflare Quick Tunnel.

    Quick Tunnel одноразовый: после перезапуска cloudflared прежний домен
    уже не ведёт в панель. Такие адреса нельзя воспринимать как ручную
    настройку `panel_url`, иначе следующий запуск вообще не создаст туннель.
    """
    try:
        host = (urlparse(normalize_url(value)).hostname or "").lower()
    except ValueError:
        return False
    return host != "api.trycloudflare.com" and host.endswith(".trycloudflare.com")


def binary_url() -> tuple[str, str]:
    """(url, имя файла в bin/) под текущую платформу. ("", "") если платформа
    неизвестна — тогда скачать не выйдет и туннель просто не поднимется."""
    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        return "", ""
    if sys_name == "windows" and arch == "amd64":
        return CLOUDFLARED_LATEST + "cloudflared-windows-amd64.exe", "cloudflared.exe"
    if sys_name == "linux":
        return CLOUDFLARED_LATEST + f"cloudflared-linux-{arch}", "cloudflared"
    if sys_name == "darwin":
        return CLOUDFLARED_LATEST + f"cloudflared-darwin-{arch}.tgz", "cloudflared"
    return "", ""


def _bin_dir() -> str:
    # TG-MMO-RPG/bin — не попадает в снапшоты и не мешает git (игнорируется ниже)
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")


def find_binary() -> str:
    """Путь к cloudflared: сначала проектный bin/, потом системный PATH."""
    here = _bin_dir()
    names = ("cloudflared.exe", "cloudflared") if os.name == "nt" else \
        ("cloudflared", "cloudflared.exe")
    for name in names:
        path = os.path.join(here, name)
        if os.path.isfile(path):
            return path
    return shutil.which("cloudflared") or ""


def ensure_binary() -> str:
    """Путь к бинарю; скачивает официальный релиз при отсутствии.

    Пустая строка — не вышло (нет сети/платформа) — туннель пропускаем.
    """
    path = find_binary()
    if path:
        return path
    url, name = binary_url()
    if not url:
        logger.warning("cloudflared: неизвестная платформа, авто-скачивание невозможно")
        return ""
    os.makedirs(_bin_dir(), exist_ok=True)
    dest = os.path.join(_bin_dir(), name)
    tmp = dest + ".download"
    logger.info(f"cloudflared: скачиваю {url} (один раз, ~17 МБ)…")
    try:
        urllib.request.urlretrieve(url, tmp)
        if url.endswith(".tgz"):
            # Внутри архива один файл «cloudflared» — читаем его сами,
            # чтобы не зависеть от различий tarfile между версиями Python.
            import tarfile
            with tarfile.open(tmp, "r:gz") as tf:
                members = [m for m in tf.getmembers()
                           if m.isfile() and m.name.endswith("cloudflared")]
                with tf.extractfile(members[0]) as fh, open(dest, "wb") as out:
                    out.write(fh.read())
            os.remove(tmp)
        else:
            os.replace(tmp, dest)
        if os.name != "nt":
            os.chmod(dest, os.stat(dest).st_mode
                     | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        logger.info(f"cloudflared: готов ({dest})")
        return dest
    except Exception as e:
        logger.warning(f"cloudflared: не удалось скачать ({e}). Туннель пропущен.")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return ""


class CloudflareTunnel:
    """Фоновый процесс Quick Tunnel: запуск, чтение адреса, остановка."""

    def __init__(self, port: int):
        self.port = port
        self.url = ""
        self.error = ""
        self._process = None

    async def start(self) -> str:
        """Запускает туннель и ждёт публичный адрес. "" — не вышло."""
        binary = await asyncio.to_thread(ensure_binary)
        if not binary:
            self.error = "бинарь cloudflared недоступен"
            return ""
        cmd = [binary, "tunnel", "--no-autoupdate",
               "--url", f"http://127.0.0.1:{self.port}"]
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as e:
            self.error = f"не запустился: {e}"
            return ""
        try:
            self.url = await asyncio.wait_for(self._read_url(), timeout=_URL_TIMEOUT)
            logger.info(
                f"🌐 Quick Tunnel поднят: {self.url}\n"
                f"   Mini App: {self.url}/tgapp"
            )
        except asyncio.TimeoutError:
            self.error = f"cloudflared не выдал адрес за {_URL_TIMEOUT} с"
            logger.warning(f"Quick Tunnel: {self.error}")
            await self.stop()
        return self.url

    async def _read_url(self) -> str:
        assert self._process and self._process.stdout
        while True:
            line = await self._process.stdout.readline()
            if not line:
                raise asyncio.TimeoutError()
            match = TRYCLOUDFLARE_RE.search(line.decode("utf-8", "ignore"))
            if match:
                return match.group(0)

    async def stop(self) -> None:
        proc, self._process = self._process, None
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()


_current: CloudflareTunnel | None = None


async def setup_public_url(port: int) -> CloudflareTunnel | None:
    """Поднять туннель и записать публичный адрес в настройки панели.

    Ничего не делает, если туннель выключен или адрес уже задан вручную.
    Сохранённый panel_url сразу подхватывается ботом для Mini App-кнопки.
    """
    global _current
    if not tunnel_enabled():
        logger.info(f"Quick Tunnel выключен ({TUNNEL_ENV}=0) — панель локальная.")
        return None
    saved = normalize_url(await get_setting(PANEL_URL_KEY))
    env_url = normalize_url(
        os.getenv("PUBLIC_URL", "") or os.getenv("ADMIN_PUBLIC_URL", "")
    )

    # Сохранённый *.trycloudflare.com — это не ручной домен, а адрес
    # предыдущего процесса cloudflared. Удаляем его до запуска, чтобы бот
    # не успел отдать игроку мёртвую кнопку Mini App.
    if is_quick_tunnel_url(saved):
        logger.info(f"Предыдущий Quick Tunnel устарел ({saved}); создаю новый.")
        await set_panel_url("")
        saved = ""

    # PUBLIC_URL/ADMIN_PUBLIC_URL и обычный panel_url считаются постоянной
    # ручной конфигурацией (VPS, Render, собственный домен).
    manual = env_url or saved
    if manual:
        logger.info(f"Публичный адрес панели задан вручную ({manual}) — "
                    "туннель не нужен.")
        return None

    tunnel = CloudflareTunnel(port)
    url = await tunnel.start()
    if not url:
        logger.warning(f"Quick Tunnel не поднялся ({tunnel.error}). "
                       "Панель остаётся на localhost, Mini App-кнопка скрыта.")
        return None

    _current = tunnel
    await set_panel_url(url)
    await _announce_url(url)
    return tunnel


async def shutdown_public_url() -> None:
    global _current
    if _current:
        await _current.stop()
        _current = None


async def _announce_url(url: str) -> None:
    """Личка веб-админам при смене публичного адреса — с кнопкой Mini App.

    Адрес быстрого туннеля новый при каждом перезапуске: без весточки
    пришлось бы самому лезть в настройки, чтобы его узнать.
    """
    try:
        if (await get_setting(ANNOUNCED_KEY)) == url:
            return  # этот адрес уже анонсировали — не спамим
        await set_setting(ANNOUNCED_KEY, url)

        from bot.runner import bot_runner
        # Бот мог стартовать чуть позже туннеля — ждём недолго.
        for _ in range(60):
            if bot_runner.is_running() and bot_runner.bot:
                break
            await asyncio.sleep(1)
        else:
            return

        from aiogram.types import WebAppInfo
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        async with async_session() as session:
            rows = await session.execute(
                select(User).where(User.is_web_admin == True)  # noqa: E712
            )
            admins = rows.scalars().all()

        for admin in admins:
            try:
                builder = InlineKeyboardBuilder()
                builder.button(
                    text="🌐 Открыть панель",
                    web_app=WebAppInfo(url=build_miniapp_url(url, admin.telegram_id)),
                )
                await bot_runner.bot.send_message(
                    chat_id=admin.telegram_id,
                    text=(
                        "🌐 <b>Публичный адрес панели обновился</b>\n\n"
                        f"<code>{url}</code>\n\n"
                        "Панель открывается мини-приложением прямо из Telegram — "
                        "пароль больше не нужен."
                    ),
                    parse_mode="HTML",
                    reply_markup=builder.as_markup(),
                )
            except Exception:
                pass
    except Exception:
        pass  # весточка — дело добровольное, падать из-за неё нельзя
