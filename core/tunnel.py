"""Публичный HTTPS для админ-панели через SSH-туннель.

Кнопка Telegram Mini App (web_app) открывается только по HTTPS с публичным
доменом, а панель обычно крутится на домашней машине за NAT.

Модуль поднимает HTTPS-туннель одним из способов (по приоритету):
  1. serveo.net    — `ssh -R 80:localhost:PORT serveo.net`
  2. localhost.run — `ssh -R 80:localhost:PORT nokey@localhost.run`

Оба сервиса бесплатные, без регистрации и требуют только SSH-клиент
(есть в Windows 10+, macOS, Linux).

Выловленный из вывода адрес сохраняется в настройки панели (panel_url) —
бот подхватывает адрес для кнопки «🌐 Открыть панель» автоматически.

Адрес туннеля меняется при каждом перезапуске — поэтому при смене
админа оповещаем личным сообщением с кнопкой Mini App.

Управление: переменная окружения ADMIN_TUNNEL (по умолчанию "1"). Если
публичный адрес уже задан вручную (настройка panel_url или PUBLIC_URL /
ADMIN_PUBLIC_URL — например, на Render), туннель не поднимается.
"""
import asyncio
import logging
import os
import re
import shutil
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

# Регулярки для вылавливания публичного адреса из вывода SSH-туннелей.
# serveo.net:  "Forwarding HTTPS from https://xxxxx.serveo.net to port 8000"
# localhost.run: "https://xxxxx.lhr.life is now available"
_SERVEO_RE = re.compile(
    r"https://([a-z0-9-]+\.serveo\.net)\b", re.IGNORECASE
)
_LOCALHOST_RUN_RE = re.compile(
    r"https://([a-z0-9-]+\.(?:lhr\.life|localhost\.run|ssh\.localhost\.run))\b",
    re.IGNORECASE,
)

_URL_TIMEOUT = 60  # столько ждём публичный адрес от SSH

# ── Список SSH-сервисов в порядке приоритета ───────────────────────────────
# (имя, аргументы ssh, регулярка для URL)
_SSH_TUNNELS = [
    ("serveo.net", ["-o", "StrictHostKeyChecking=no",
                    "-R", "80:localhost:{port}", "serveo.net"],
     _SERVEO_RE),
    ("localhost.run", ["-o", "StrictHostKeyChecking=no",
                       "-R", "80:localhost:{port}", "nokey@localhost.run"],
     _LOCALHOST_RUN_RE),
]


def tunnel_enabled() -> bool:
    val = os.getenv(TUNNEL_ENV, "1").strip().lower()
    return val not in ("0", "false", "no", "off", "")


def is_quick_tunnel_url(value: str) -> bool:
    """Это адрес временного туннеля (serveo.net / localhost.run / trycloudflare).

    Одноразовый: после перезапуска SSH прежний домен уже не ведёт в панель.
    Такие адреса нельзя воспринимать как ручную настройку `panel_url`,
    иначе следующий запуск вообще не создаст туннель.

    Реализация живёт в core.settings_store, чтобы бот и панель судили об
    адресе одинаково; здесь остаётся привычное имя.
    """
    return is_temporary_tunnel_url(value)


def _has_ssh() -> bool:
    """Проверяет наличие SSH-клиента."""
    return shutil.which("ssh") is not None


def _kill_orphan_ssh() -> int:
    """Убить процессы SSH-туннеля, оставшиеся от прошлого запуска сервера.

    Осиротевший ssh продолжает держать СТАРЫЙ домен и упорно отвечает на
    него, поэтому новый запуск получал уже занятый порт/второй туннель, а
    игрокам продолжала уходить прежняя ссылка. Чистим перед стартом.

    Возвращает число завершённых процессов (0 — чисто или нет прав).
    """
    killed = 0
    try:
        if os.name == "nt":
            # taskkill: убиваем все ssh.exe с аргументами serveo/localhost.run
            for pattern in ("ssh.exe.*serveo", "ssh.exe.*localhost.run"):
                out = subprocess_run_safe(
                    ["taskkill", "/F", "/IM", "ssh.exe", "/FI",
                     f"WINDOWTITLE eq *{pattern}*"],
                    timeout=10,
                )
                if out and out.returncode == 0:
                    killed += out.stdout.count("SUCCESS") or 0
            # Более надёжный способ: через wmic ищем нужные процессы
            out = subprocess_run_safe(
                ["wmic", "process", "where",
                 "name='ssh.exe'", "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
                timeout=10,
            )
            if out and out.returncode == 0:
                for line in out.stdout.splitlines():
                    if "serveo" in line.lower() or "localhost.run" in line.lower():
                        parts = line.strip().split(",")
                        if len(parts) >= 2:
                            pid = parts[-1].strip()
                            if pid.isdigit():
                                subprocess_run_safe(
                                    ["taskkill", "/F", "/PID", pid], timeout=5)
                                killed += 1
        else:
            out = subprocess_run_safe(
                ["pkill", "-f", r"ssh.*(?:serveo|localhost\.run)"],
                timeout=10,
            )
            if out and out.returncode == 0:
                killed = 1
    except Exception as e:
        logger.debug(f"ssh: очистка старых процессов не выполнена ({e})")
        return 0
    if killed:
        logger.info("ssh: остановлен туннель от прошлого запуска "
                    "(иначе он продолжал бы держать старый адрес).")
    return killed


def subprocess_run_safe(cmd, **kwargs):
    """subprocess.run с обработкой ошибок."""
    import subprocess
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=kwargs.get("timeout", 15),
        )
    except Exception:
        return None


class SSHTunnel:
    """Фоновый процесс SSH-туннеля: запуск, чтение адреса, остановка."""

    def __init__(self, port: int):
        self.port = port
        self.url = ""
        self.error = ""
        self.provider = ""
        self._process = None
        self._watcher_task = None

    async def start(self) -> str:
        """Запускает туннель и ждёт публичный адрес. "" — не вышло."""
        if not _has_ssh():
            self.error = "SSH-клиент не найден (установите OpenSSH)"
            return ""

        # Осиротевший туннель прошлого запуска держит старый домен
        await asyncio.to_thread(_kill_orphan_ssh)

        # Перебираем сервисы по приоритету
        for name, args_template, url_regex in _SSH_TUNNELS:
            url = await self._try_provider(name, args_template, url_regex)
            if url:
                self.url = url
                self.provider = name
                logger.info(
                    f"🌐 SSH-туннель ({name}) поднят: {self.url}\n"
                    f"   Mini App: {self.url}/tgapp"
                )
                self._watcher_task = asyncio.create_task(self._watch_process())
                return self.url

        self.error = "ни один SSH-сервис не ответил (serveo.net, localhost.run)"
        logger.warning(f"SSH-туннель: {self.error}")
        return ""

    async def _try_provider(self, name: str, args_template: list,
                             url_regex: re.Pattern) -> str:
        """Попытка поднять туннель через конкретный SSH-сервис."""
        args = [a.format(port=self.port) for a in args_template]
        cmd = ["ssh"] + args
        logger.info(f"SSH-туннель: пробую {name}…")
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as e:
            logger.debug(f"SSH-туннель ({name}): не запустился ({e})")
            return ""
        try:
            url = await asyncio.wait_for(
                self._read_url(url_regex), timeout=_URL_TIMEOUT)
            return url
        except asyncio.TimeoutError:
            logger.debug(f"SSH-туннель ({name}): не выдал адрес за {_URL_TIMEOUT} с")
            await self._stop_process()
            return ""

    async def _read_url(self, url_regex: re.Pattern) -> str:
        """Читает вывод SSH и ловит публичный адрес."""
        assert self._process and self._process.stdout
        while True:
            line = await self._process.stdout.readline()
            if not line:
                raise asyncio.TimeoutError()
            decoded = line.decode("utf-8", "ignore")
            # Логируем для отладки
            if "ERR" in decoded or "error" in decoded.lower():
                logger.debug(f"ssh: {decoded.strip()}")
            match = url_regex.search(decoded)
            if match:
                return "https://" + match.group(1)

    async def _watch_process(self):
        """Следит за процессом SSH и логирует его падение."""
        try:
            rc = await self._process.wait()
            if rc is not None:
                logger.warning(
                    f"⚠️ SSH-туннель завершился с кодом {rc}. "
                    f"Туннель {self.url} больше не работает."
                )
                set_active_tunnel_url("")
                try:
                    if is_quick_tunnel_url(await get_setting(PANEL_URL_KEY)):
                        await set_panel_url("")
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    async def _stop_process(self):
        """Остановить процесс SSH."""
        proc = self._process
        self._process = None
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()

    async def stop(self) -> None:
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except (asyncio.CancelledError, Exception):
                pass
            self._watcher_task = None
        await self._stop_process()


_current: SSHTunnel | None = None


async def clear_stale_quick_tunnel_url() -> bool:
    """Удалить URL прошлого туннеля до запуска бота.

    Бот стартует раньше фоновой задачи туннеля. Без этой очистки он успевал
    отдать мёртвую ссылку от прошлого запуска.

    Вызывать нужно ДО старта бота (см. lifespan в admin/main.py): очистка
    и в памяти (`set_active_tunnel_url("")`), и в таблице настроек.
    """
    if tunnel_enabled():
        mark_tunnel_managed(True)
    set_active_tunnel_url("")
    saved = normalize_url(await get_setting(PANEL_URL_KEY))
    if not is_quick_tunnel_url(saved):
        return False
    logger.info(f"Предыдущий туннель устарел ({saved}); очищаю адрес.")
    await set_panel_url("")
    return True


async def verify_tunnel_url(url: str, timeout: float = 20.0) -> bool:
    """Проверить, что адрес правда ведёт в ЭТОТ процесс.

    Туннель поднимается не мгновенно, а бывает и хуже: рядом мог
    остаться незакрытый SSH от прошлого запуска, и тогда старый
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


async def setup_public_url(port: int) -> SSHTunnel | None:
    if not tunnel_enabled():
        mark_tunnel_managed(False)
        logger.info(f"Туннель выключен ({TUNNEL_ENV}=0) — панель локальная.")
        return None

    mark_tunnel_managed(True)
    saved = normalize_url(await get_setting(PANEL_URL_KEY))
    env_url = platform_public_url()

    # URL из окружения хостинга (Render/Replit), обычный panel_url и
    # PUBLIC_URL считаются постоянной конфигурацией (VPS, собственный домен).
    # Временные туннельные адреса (serveo.net, localhost.run, trycloudflare)
    # — это мусор от прошлого запуска, чистим.
    if saved and is_quick_tunnel_url(saved):
        await clear_stale_quick_tunnel_url()
        saved = ""

    manual = env_url or saved
    if manual:
        mark_tunnel_managed(False)
        set_active_tunnel_url(manual)
        logger.info(f"Публичный адрес панели задан вручную ({manual}) — "
                    "туннель не нужен.")
        return None

    # Нет ни ручного адреса, ни хостинга — поднимаем SSH-туннель
    tunnel = SSHTunnel(port)
    url = await tunnel.start()
    if not url:
        logger.warning(f"SSH-туннель не поднялся ({tunnel.error}). "
                       "Панель остаётся на localhost, Mini App-кнопка скрыта.\n"
                       "   Подсказка: задай PUBLIC_URL в .env или "
                       "разверни на Render/Replit.")
        return None

    # Сохраняем адрес ТОЛЬКО после того, как убедились: он ведёт в этот
    # процесс. Иначе игрок получает ссылку, которая отдаёт ошибку.
    if not await verify_tunnel_url(url):
        logger.warning(
            f"Адрес {url} не подтвердился — кнопку Mini App не публикую. "
            "Проверь, что рядом не остался старый процесс сервера/SSH."
        )
        await tunnel.stop()
        return None

    global _current
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

    Адрес туннеля новый при каждом перезапуске: без весточки
    пришлось бы самому лезть в настройки, чтобы его узнать.
    """
    try:
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


# ── Для обратной совместимости с тестами и admin/main.py ────────────────────

def binary_url() -> tuple[str, str]:
    """Оставлено для совместимости тестов — теперь не используется."""
    return "", ""


def kill_orphan_cloudflared() -> int:
    """Оставлено для совместимости — теперь чистит SSH-туннели."""
    return _kill_orphan_ssh()


def find_binary() -> str:
    """Оставлено для совместимости — проверяет наличие SSH."""
    return shutil.which("ssh") or ""


def ensure_binary() -> str:
    """Оставлено для совместимости — проверяет наличие SSH."""
    return shutil.which("ssh") or ""
