# Движок: опрашивает источники по приоритету и обновляет bio в Telegram.
import asyncio
import threading

from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest

from config import load_config
from providers import build_providers

SESSION_NAME = "tg_session"


def build_bio(config: dict, track: str | None) -> str:
    """Формирует строку bio из шаблона и обрезает по лимиту Telegram."""
    if track:
        bio = config.get("bio_template", "🎧 {track}").format(track=track)
    else:
        bio = config.get("bio_idle", "")
    max_len = config.get("bio_max_len", 70)
    if len(bio) > max_len:
        bio = bio[: max_len - 1] + "…"
    return bio


class Engine:
    """Управляет фоновым потоком, который крутит цикл опроса и обновления bio."""

    def __init__(self):
        self.thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.status = {
            "running": False,
            "track": None,
            "source": None,
            "error": None,
            "tg_user": None,
        }

    def set_status(self, **kw):
        with self._lock:
            self.status.update(kw)

    def get_status(self) -> dict:
        with self._lock:
            return dict(self.status)

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, config: dict):
        if self.is_running():
            return
        self._stop.clear()
        self.set_status(error=None)
        self.thread = threading.Thread(target=self._thread_main, args=(config,), daemon=True)
        self.thread.start()

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=10)

    def _thread_main(self, config: dict):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run(config))
        except Exception as e:
            self.set_status(error=str(e), running=False)
        finally:
            loop.close()

    async def _run(self, config: dict):
        providers = build_providers(config)
        if not providers:
            self.set_status(error="Нет активных источников", running=False)
            return

        tg = config.get("telegram", {})
        client = TelegramClient(SESSION_NAME, tg.get("api_id"), tg.get("api_hash"))
        await client.connect()
        if not await client.is_user_authorized():
            self.set_status(error="Telegram не авторизован", running=False)
            await client.disconnect()
            return

        me = await client.get_me()
        self.set_status(running=True, error=None, tg_user=me.first_name)

        # Discord Rich Presence — отдельный выход (две строки), не влияет на Telegram
        discord = await self._make_discord(config)

        interval = max(10, int(config.get("interval", 20)))
        last_bio = None
        last_discord = object()  # sentinel, чтобы первый трек точно отправился
        try:
            while not self._stop.is_set():
                # перечитываем настройки на лету: правки шаблона bio / текста тишины /
                # интервала применяются без перезапуска движка (раньше это был баг)
                fresh = load_config()
                config["bio_template"] = fresh.get("bio_template", config.get("bio_template", "🎧 {track}"))
                config["bio_idle"] = fresh.get("bio_idle", config.get("bio_idle", ""))
                config["bio_max_len"] = fresh.get("bio_max_len", config.get("bio_max_len", 70))
                interval = max(10, int(fresh.get("interval", interval)))

                track, source = None, None
                # опрашиваем источники по приоритету, берём первый играющий
                for p in providers:
                    t = p.get_now_playing()
                    if t:
                        track, source = t, p.name
                        break

                # --- Telegram (как было: одна строка bio) ---
                bio = build_bio(config, track)
                if bio != last_bio:
                    try:
                        await client(UpdateProfileRequest(about=bio))
                        last_bio = bio
                    except Exception as e:
                        self.set_status(error=f"bio: {e}")

                # --- Discord (две строки, меняются с треком) ---
                if discord and track != last_discord:
                    try:
                        await discord.update(track)
                        last_discord = track
                    except Exception as e:
                        self.set_status(error=f"discord: {e}")

                self.set_status(track=track, source=source)

                # ждём interval, но проверяем флаг остановки каждые 0.5с
                for _ in range(interval * 2):
                    if self._stop.is_set():
                        break
                    await asyncio.sleep(0.5)
        finally:
            if discord:
                await discord.close()
            await client.disconnect()
            self.set_status(running=False)

    async def _make_discord(self, config: dict):
        """Создаёт Discord-presence, если включён. None при ошибке (Telegram продолжит работать)."""
        dcfg = config.get("discord", {})
        if not (dcfg.get("enabled") and dcfg.get("client_id")):
            return None
        try:
            from discord_presence import DiscordPresence
            d = DiscordPresence(dcfg["client_id"])
            await d.connect()
            return d
        except Exception as e:
            self.set_status(error=f"Discord не подключён: {e}")
            return None
