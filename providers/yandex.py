# Источник трека через Яндекс Музыку (неофициальное API очередей).
# Прямого "now playing" нет, поэтому читаем queues — синхронизацию воспроизведения между
# устройствами. Надёжно работает с мобильного приложения; на десктопе очередь часто пустая.
from yandex_music import Client

from .base import Provider


def device_auth(on_code) -> str:
    """OAuth Device Flow: возвращает access_token. on_code(code) — показать ссылку и код."""
    client = Client()
    token = client.device_auth(on_code=on_code)
    return token.access_token


class YandexProvider(Provider):
    name = "Яндекс Музыка"

    def __init__(self, token: str):
        self.client = Client(token).init()

    def get_now_playing(self) -> str | None:
        try:
            queues = self.client.queues_list()
            if not queues:
                return None

            queue = self.client.queue(queues[0].id)
            if not queue or not queue.tracks:
                return None

            index = queue.current_index or 0
            if index >= len(queue.tracks):
                index = 0

            track = queue.tracks[index].fetch_track()
            artists = ", ".join(a.name for a in track.artists) if track.artists else ""
            title = track.title or ""

            if artists and title:
                return f"{artists} — {title}"
            return title or artists or None
        except Exception as e:
            print(f"[yandex] ошибка: {e}")
            return None
