# Сборка активных провайдеров из конфига в порядке приоритета.
from .mpris import MprisProvider
from .spotify import SpotifyProvider
from .yandex import YandexProvider


def build_providers(config: dict) -> list:
    """Создаёт включённые провайдеры в порядке из config['sources'] (= приоритет)."""
    providers = []
    for src in config.get("sources", []):
        if not src.get("enabled"):
            continue
        try:
            providers.append(_build_one(src))
        except Exception as e:
            print(f"[registry] не удалось создать источник {src.get('type')}: {e}")
    return [p for p in providers if p is not None]


def _build_one(src: dict):
    t = src.get("type")
    if t == "spotify":
        if not (src.get("client_id") and src.get("client_secret") and src.get("refresh_token")):
            return None
        return SpotifyProvider(src["client_id"], src["client_secret"], src["refresh_token"])
    if t == "yandex":
        if not src.get("token"):
            return None
        return YandexProvider(src["token"])
    if t == "mpris":
        return MprisProvider(src.get("player_filter", ""))
    print(f"[registry] неизвестный тип источника: {t}")
    return None
