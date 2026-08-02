"""Публичный HTTPS для админ-панели через Cloudflare Quick Tunnel.

Кнопка Telegram Mini App (web_app) открывается только по HTTPS с публичным
доменом, а панель обычно крутится на домашней машине за NAT. Quick Tunnel

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
import shutil
import stat
import subprocess
import urllib.request

from sqlalchemy import select

from core.database import async_session
from core.models import User
from core.settings_store import (
    PANEL_URL_KEY, build_miniapp_url, get_setting, is_temporary_tunnel_url,
    mark_tunnel_managed, normalize_url, platform_public_url,
    set_active_tunnel_url, set_panel_url, set_setting,
)

logger = logging.getLogger("tunnel")

TUNNEL_ENV = "ADMIN_TUNNEL"
ANNOUNCED_KEY = "panel_url_announced"

CLOUDFLARED_LATEST = "https://github.com/cloudflare/cloudflared/releases/latest/download/"

_URL_TIMEOUT = 45  # столько ждём публичный адрес от cloudflared


def tunnel_enabled() -> bool:
    # Схема Cloudflare Quick Tunnel удалена — туннель больше не используется.
    return False


def is_quick_tunnel_url(value: str) -> bool:
    """Это адрес, который раньше выдал Cloudflare Quick Tunnel.

    Quick Tunnel одноразовый: после перезапуска cloudflared прежний домен
    уже не ведёт в панель. Такие адреса нельзя воспринимать как ручную
    настройку `panel_url`, иначе следующий запуск вообще не создаст туннель.

    Реализация живёт в core.settings_store, чтобы бот и панель судили об
    адресе одинаково; здесь остаётся привычное имя.
    """
    return is_temporary_tunnel_url(value)


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


def kill_orphan_cloudflared() -> int:
    """Убить процессы cloudflared, оставшиеся от прошлого запуска сервера.

    Зачем. Quick Tunnel — дочерний процесс панели, но он переживает её
    далеко не всегда штатно: закрытие окна run.bat крестиком, `os.execv`
    при «Обновить с GitHub», kill по Ctrl+Break. Осиротевший cloudflared
    продолжает держать СТАРЫЙ домен и упорно отвечает на него, поэтому
    новый запуск получал уже занятый порт/второй туннель, а игрокам
    продолжала уходить прежняя ссылка. Чистим перед стартом.

    Возвращает число завершённых процессов (0 — чисто или нет прав).
    """
    killed = 0
    try:
        if os.name == "nt":
            # /T — вместе с деревом дочерних, /F — принудительно.
            out = subprocess.run(
                ["taskkill", "/F", "/T", "/IM", "cloudflared.exe"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode == 0:
                killed = out.stdout.count("SUCCESS") or 1
        else:
            # pkill -f: ловит и bin/cloudflared, и системный бинарь.
            out = subprocess.run(
                ["pkill", "-f", r"cloudflared.*tunnel.*--url"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode == 0:
                killed = 1
    except Exception as e:
        logger.debug(f"cloudflared: очистка старых процессов не выполнена ({e})")
        return 0
    if killed:
        logger.info("cloudflared: остановлен туннель от прошлого запуска "
                    "(иначе он продолжал бы держать старый адрес).")
    return killed


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
        self._watcher_task = None

    async def start(self) -> str:
        """Запускает туннель и ждёт публичный адрес. "" — не вышло."""
        binary = await asyncio.to_thread(ensure_binary)
        if not binary:
            self.error = "бинарь cloudflared недоступен"
            return ""
        # Осиротевший туннель прошлого запуска держит старый домен — из-за
        # него игрокам и продолжала приходить прежняя ссылка.
        await asyncio.to_thread(kill_orphan_cloudflared)
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
            # Фоновый наблюдатель: если cloudflared упадёт — логируем
            self._watcher_task = asyncio.create_task(self._watch_process())
        except asyncio.TimeoutError:
            self.error = f"cloudflared не выдал адрес за {_URL_TIMEOUT} с"
            logger.warning(f"Quick Tunnel: {self.error}")
            await self.stop()
        return self.url

    async def _watch_process(self):
        """Следит за процессом cloudflared и логирует его падение."""
        try:
            rc = await self._process.wait()
            # Even a zero exit means that this ephemeral Quick Tunnel is gone.
            # Leaving its URL in the database makes Telegram open Cloudflare's
            # 1033 page instead of the panel.
            if rc is not None:
                logger.warning(
                    f"⚠️ cloudflared завершился с кодом {rc}. "
                    f"Туннель {self.url} больше не работает."
                )
                # При падении гасим адрес и в памяти, и в настройках: бот
                # сразу перестаёт показывать мёртвую кнопку Mini App.
                set_active_tunnel_url("")
                try:
                    if is_quick_tunnel_url(await get_setting(PANEL_URL_KEY)):
                        await set_panel_url("")
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    async def _read_url(self) -> str:
        """Больше не используется - туннель отключён."""
        raise asyncio.TimeoutError()

    async def stop(self) -> None:
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except (asyncio.CancelledError, Exception):
                pass
            self._watcher_task = None
        proc, self._process = self._process, None
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()


_current: CloudflareTunnel | None = None


async def clear_stale_quick_tunnel_url() -> bool:
    """Удалить URL прошлого Quick Tunnel до запуска бота.

    Бот стартует раньше фоновой задачи туннеля. Без этой очистки он успевал
    неизбежно отдаёт Cloudflare 1033 после перезапуска процесса.

    Вызывать нужно ДО старта бота (см. lifespan в admin/main.py): очистка
    и в памяти (`set_active_tunnel_url("")`), и в таблице настроек.
    """
    if tunnel_enabled():
        # Туннель поднимает этот процесс: пока нового адреса нет, любой
        mark_tunnel_managed(True)
    set_active_tunnel_url("")
    saved = normalize_url(await get_setting(PANEL_URL_KEY))
    if not is_quick_tunnel_url(saved):
        return False
    logger.info(f"Предыдущий Quick Tunnel устарел ({saved}); очищаю адрес.")
    await set_panel_url("")
    return True


async def verify_tunnel_url(url: str, timeout: float = 20.0) -> bool:
    """Проверить, что адрес правда ведёт в ЭТОТ процесс.

    Quick Tunnel поднимается не мгновенно, а бывает и хуже: рядом мог
    остаться незакрытый cloudflared от прошлого запуска, и тогда старый
    домен отвечает, но чужим сервером. Спрашиваем `/health` и сверяем метку
    экземпляра — только совпадение доказывает, что ссылка рабочая и наша.
    """
    from core.settings_store import INSTANCE_ID

    probe = f"{normalize_url(url)}/health"
    deadline = asyncio.get_event_loop().time() + timeout
    last = ""
    while asyncio.get_event_loop().time() < deadline:
        try:
            def _fetch() -> str:
                req = urllib.request.Request(
                    probe, headers={"User-Agent": "shadow-lands-tunnel-check"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    return resp.read(4096).decode("utf-8", "ignore")

            body = await asyncio.to_thread(_fetch)
            if INSTANCE_ID in body:
                return True
            last = "ответил чужой сервер (метка экземпляра не совпала)"
        except Exception as e:
            last = str(e)
        await asyncio.sleep(2)
    logger.warning(f"Проверка адреса {url} не удалась: {last or 'нет ответа'}")
    return False


async def setup_public_url(port: int) -> CloudflareTunnel | None:
    # Схема Cloudflare Quick Tunnel удалена.
    logger.info("Quick Tunnel отключён (ADMIN_TUNNEL=0) — панель работает напрямую.")
    return None
    if not tunnel_enabled():
        mark_tunnel_managed(False)
        logger.info(f"Quick Tunnel выключен ({TUNNEL_ENV}=0) — панель локальная.")
        return None

    mark_tunnel_managed(True)
    saved = normalize_url(await get_setting(PANEL_URL_KEY))
    env_url = platform_public_url()

    # предыдущего процесса cloudflared. Удаляем его до запуска, чтобы бот
    # не успел отдать игроку мёртвую кнопку Mini App.
    if is_quick_tunnel_url(saved):
        await clear_stale_quick_tunnel_url()
        saved = ""

    # URL из окружения хостинга (Render/Replit), обычный panel_url и
    # PUBLIC_URL считаются постоянной конфигурацией (VPS, собственный домен).
    manual = env_url or saved
    if manual:
        mark_tunnel_managed(False)
        set_active_tunnel_url(manual)
        logger.info(f"Публичный адрес панели задан вручную ({manual}) — "
                    "туннель не нужен.")
        return None

    tunnel = CloudflareTunnel(port)
    url = await tunnel.start()
    if not url:
        logger.warning(f"Quick Tunnel не поднялся ({tunnel.error}). "
                       "Панель остаётся на localhost, Mini App-кнопка скрыта.")
        return None

    # Сохраняем адрес ТОЛЬКО после того, как убедились: он ведёт в этот
    # процесс. Иначе игрок получает ссылку, которая отдаёт ошибку 1033.
    if not await verify_tunnel_url(url):
        logger.warning(
            f"Адрес {url} не подтвердился — кнопку Mini App не публикую. "
            "Проверь, что рядом не остался старый процесс сервера/cloudflared."
        )
        await tunnel.stop()
        return None

    _current = tunnel
    set_active_tunnel_url(url)
    await set_panel_url(url)
    await _announce_url(url)
    return tunnel


async def shutdown_public_url() -> None:
    global _current
    set_active_tunnel_url("")
    if _current:
        await _current.stop()
        _current = None


async def _announce_url(url: str) -> None:
    """Личка веб-админам при смене публичного адреса — с кнопкой Mini App.

    Адрес быстрого туннеля новый при каждом перезапуске: без весточки
    пришлось бы самому лезть в настройки, чтобы его узнать.
    """
    try:
        # Сверяем не только адрес, но и метку запуска: после перезапуска
        # сервера Cloudflare изредка выдаёт тот же домен повторно, и без
        # метки админам не приходило бы никакого письма — они бы жали
        # старую кнопку из прошлой переписки и ловили ошибку 1033.
        from core.settings_store import INSTANCE_ID

        stamp = f"{INSTANCE_ID}|{url}"
        if (await get_setting(ANNOUNCED_KEY)) == stamp:
            return  # этот адрес уже анонсировали — не спамим
        await set_setting(ANNOUNCED_KEY, stamp)

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
