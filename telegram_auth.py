# Логин в Telegram через Telethon — для веб-GUI (пошагово) и для CLI (интерактивно).
import asyncio
import threading

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

SESSION_NAME = "tg_session"


class _LoopThread:
    """Фоновый event loop: позволяет звать async-код из синхронного Flask."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)


class TelegramAuth:
    """Пошаговый логин для веба. Клиент живёт между шагами на фоновом loop."""

    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self._lt = _LoopThread()
        self.client: TelegramClient | None = None
        self.phone: str | None = None
        self.phone_code_hash: str | None = None

    def send_code(self, phone: str) -> str:
        """Отправляет код на телефон. Возвращает 'already' | 'code_sent'."""
        self.phone = phone

        async def _():
            self.client = TelegramClient(SESSION_NAME, self.api_id, self.api_hash)
            await self.client.connect()
            if await self.client.is_user_authorized():
                return "already"
            sent = await self.client.send_code_request(phone)
            self.phone_code_hash = sent.phone_code_hash
            return "code_sent"

        return self._lt.run(_())

    def sign_in(self, code: str, password: str = "") -> str:
        """Вводит код (и пароль 2FA при необходимости). Возвращает 'ok:<имя>' | 'need_password'."""

        async def _():
            try:
                await self.client.sign_in(
                    self.phone, code, phone_code_hash=self.phone_code_hash
                )
            except SessionPasswordNeededError:
                if not password:
                    return "need_password"
                await self.client.sign_in(password=password)
            me = await self.client.get_me()
            await self.client.disconnect()
            self.client = None
            return f"ok:{me.first_name}"

        return self._lt.run(_())

    def close(self):
        """Закрывает клиент и фоновый loop. Вызывать перед созданием нового логина,
        чтобы не держать SQLite-сессию открытой двумя клиентами (database is locked)."""
        try:
            if self.client is not None:
                async def _():
                    if self.client.is_connected():
                        await self.client.disconnect()
                self._lt.run(_())
                self.client = None
        except Exception:
            pass
        finally:
            self._lt.stop()


def is_authorized(api_id: int, api_hash: str) -> tuple[bool, str]:
    """Проверяет, авторизована ли файловая сессия. Возвращает (bool, имя). Только когда движок стоит."""
    async def _():
        client = TelegramClient(SESSION_NAME, api_id, api_hash)
        await client.connect()
        ok = await client.is_user_authorized()
        name = ""
        if ok:
            me = await client.get_me()
            name = me.first_name or ""
        await client.disconnect()
        return ok, name

    try:
        return asyncio.run(_())
    except Exception:
        return False, ""


def cli_login(api_id: int, api_hash: str):
    """Интерактивный логин в терминале (Telethon сам спросит телефон/код/пароль через input)."""
    async def _():
        client = TelegramClient(SESSION_NAME, api_id, api_hash)
        await client.start()
        me = await client.get_me()
        await client.disconnect()
        return me

    return asyncio.run(_())
