# Discord Rich Presence через pypresence.
# В отличие от Telegram (одна строка bio), здесь показываем ДВЕ строки:
#   details = название трека, state = исполнитель — обе меняются с каждым треком.
# Работает только при запущенном локальном клиенте Discord (как и MPRIS — это локальная штука).
from pypresence import AioPresence


def _split(track: str) -> tuple[str, str | None]:
    """'Исполнитель — Трек' → (details=Трек, state='Исполнитель'). Discord требует ≥2 символов."""
    if " — " in track:
        artist, title = track.split(" — ", 1)
    else:
        artist, title = "", track
    details = (title or "Музыка")[:128]
    if len(details) < 2:
        details = f"{details} "  # добить до минимума
    state = artist[:128] if artist and len(artist) >= 2 else None
    return details, state


class DiscordPresence:
    name = "Discord"

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.rpc: AioPresence | None = None

    async def connect(self):
        self.rpc = AioPresence(self.client_id)
        await self.rpc.connect()

    async def update(self, track: str | None):
        if not self.rpc:
            return
        if not track:
            try:
                await self.rpc.clear()
            except Exception:
                pass
            return
        details, state = _split(track)
        kwargs = {"details": details, "large_image": "music", "large_text": "🎧"}
        if state:
            kwargs["state"] = state
        await self.rpc.update(**kwargs)

    async def close(self):
        if not self.rpc:
            return
        try:
            await self.rpc.clear()
        except Exception:
            pass
        try:
            await self.rpc.close()
        except Exception:
            pass
        self.rpc = None
