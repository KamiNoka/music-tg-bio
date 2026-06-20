# Выход в Telegram bio через Telethon со StringSession (сессия хранится в БД, не в файле —
# чтобы переживать рестарты на эфемерной ФС Railway).
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest

import settings_store


class TelegramBio:
    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.client: TelegramClient | None = None

    async def connect(self) -> bool:
        """Подключается по StringSession из БД. Возвращает True, если авторизован."""
        sess = settings_store.get_session_string()
        self.client = TelegramClient(StringSession(sess), self.api_id, self.api_hash)
        await self.client.connect()
        return await self.client.is_user_authorized()

    async def set_bio(self, text: str):
        await self.client(UpdateProfileRequest(about=text))

    async def close(self):
        if self.client:
            await self.client.disconnect()
            self.client = None
