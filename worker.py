# Воркер: читает настройки из БД каждый тик, опрашивает источники и пишет в выходы.
# Запускается отдельным процессом (Procfile: worker), управляется флагом running в БД.
import asyncio
import json

import settings_store as st
from engine import build_bio
from outputs.discord_status import DiscordStatus
from outputs.telegram import TelegramBio
from providers import build_providers

_SENTINEL = object()


class _State:
    """Кеш живущих между тиками объектов (клиенты, провайдеры, последние значения)."""
    def __init__(self):
        self.providers = []
        self.providers_sig = None
        self.tg: TelegramBio | None = None
        self.discord_status: DiscordStatus | None = None
        self.discord_presence = None
        self.discord_sig = None
        self.last_bio = _SENTINEL
        self.last_track = _SENTINEL


async def _ensure_telegram(state: _State, settings: dict) -> TelegramBio | None:
    if state.tg is not None:
        return state.tg
    tg = settings["telegram"]
    if not (tg.get("api_id") and tg.get("api_hash")):
        return None
    bio = TelegramBio(tg["api_id"], tg["api_hash"])
    if not await bio.connect():
        await bio.close()
        return None
    state.tg = bio
    return bio


async def _ensure_discord(state: _State, settings: dict):
    """Пересобирает Discord-выход при смене режима/токена."""
    d = settings.get("discord", {})
    sig = json.dumps(d, sort_keys=True)
    if sig == state.discord_sig:
        return
    # режим изменился — закрываем старое
    if state.discord_presence:
        try:
            await state.discord_presence.close()
        except Exception:
            pass
    state.discord_presence = None
    state.discord_status = None
    state.discord_sig = sig

    mode = d.get("mode", "off")
    if mode == "status" and d.get("user_token"):
        state.discord_status = DiscordStatus(d["user_token"])
    elif mode == "presence" and d.get("client_id"):
        try:
            from outputs.discord_presence import DiscordPresence
            p = DiscordPresence(d["client_id"])
            await p.connect()
            state.discord_presence = p
        except Exception as e:
            print(f"[worker] Discord presence не подключён: {e}")


async def tick(state: _State):
    """Один проход: опрос источников → выходы → история/состояние."""
    settings = st.get_settings()

    # источники пересобираем только при изменении конфигурации sources
    sig = json.dumps(settings.get("sources", []), sort_keys=True)
    if sig != state.providers_sig:
        state.providers = build_providers(settings)
        state.providers_sig = sig

    track, source = None, None
    for p in state.providers:
        t = p.get_now_playing()
        if t:
            track, source = t, p.name
            break

    # --- Telegram bio ---
    bio = build_bio(settings, track)
    tg = await _ensure_telegram(state, settings)
    if tg and bio != state.last_bio:
        try:
            await tg.set_bio(bio)
            state.last_bio = bio
        except Exception as e:
            print(f"[worker] bio: {e}")

    # --- Discord ---
    await _ensure_discord(state, settings)
    if track != state.last_track:
        if state.discord_status:
            state.discord_status.update(bio if track else None)
        if state.discord_presence:
            try:
                await state.discord_presence.update(track)
            except Exception as e:
                print(f"[worker] discord presence: {e}")

    # --- состояние и история ---
    st.set_current(track, source)
    if track and track != state.last_track:
        st.add_history(track, source)
    state.last_track = track


async def run():
    st.ensure_db()
    print("[worker] запущен")
    state = _State()
    while True:
        try:
            if st.get_running():
                await tick(state)
            else:
                st.heartbeat()
        except Exception as e:
            print(f"[worker] ошибка тика: {e}")
        interval = max(10, int(st.get_settings().get("interval", 20)))
        # если стоим — проверяем чаще, чтобы быстро реагировать на «Старт»
        await asyncio.sleep(interval if st.get_running() else 3)


if __name__ == "__main__":
    asyncio.run(run())
