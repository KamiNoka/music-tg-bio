# Источник трека через Spotify Web API (spotipy).
# Облачный — ловит воспроизведение с любого устройства, привязанного к аккаунту.
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .base import Provider

# Достаточно прав только на чтение текущего трека
SCOPE = "user-read-currently-playing"
# redirect_uri должен совпадать с тем, что указан в настройках Spotify-приложения
REDIRECT_URI = "http://127.0.0.1:8765/spotify/callback"


def make_oauth(client_id: str, client_secret: str, open_browser: bool = True) -> SpotifyOAuth:
    """Создаёт SpotifyOAuth. cache_path=None — токен не кэшируем на диск, храним в config.json."""
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        open_browser=open_browser,
        cache_path=None,
    )


class SpotifyProvider(Provider):
    name = "Spotify"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.oauth = make_oauth(client_id, client_secret)
        self.refresh_token = refresh_token
        self._sp: spotipy.Spotify | None = None

    def _client(self) -> spotipy.Spotify:
        # spotipy сам обновит access_token по refresh_token при каждом вызове
        token_info = self.oauth.refresh_access_token(self.refresh_token)
        return spotipy.Spotify(auth=token_info["access_token"])

    def get_now_playing(self) -> str | None:
        try:
            data = self._client().current_user_playing_track()
            if not data or not data.get("is_playing"):
                return None
            item = data.get("item")
            if not item:
                return None

            artists = ", ".join(a["name"] for a in item.get("artists", []))
            title = item.get("name", "")
            if artists and title:
                return f"{artists} — {title}"
            return title or None
        except Exception as e:
            print(f"[spotify] ошибка: {e}")
            return None
