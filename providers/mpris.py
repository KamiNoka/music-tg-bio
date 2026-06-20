# Источник трека через MPRIS (D-Bus) с помощью playerctl.
# Работает локально на Linux с любым плеером: десктоп-Яндекс, браузер (SoundCloud), Spotify и т.д.
import subprocess

from .base import Provider


def _run(args: list[str]) -> str | None:
    """Запускает playerctl, возвращает stdout или None при ошибке."""
    try:
        r = subprocess.run(
            ["playerctl", *args],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        out = r.stdout.strip()
        return out or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _players() -> list[str]:
    out = _run(["-l"])
    return out.split("\n") if out else []


class MprisProvider(Provider):
    name = "MPRIS (локально)"

    def __init__(self, player_filter: str = ""):
        # Фильтр: брать только плееры, чьё имя содержит строку (напр. "yandex"). Пусто = любой.
        self.player_filter = (player_filter or "").lower()

    def get_now_playing(self) -> str | None:
        for player in _players():
            if self.player_filter and self.player_filter not in player.lower():
                continue
            if _run(["-p", player, "status"]) != "Playing":
                continue

            artist = _run(["-p", player, "metadata", "xesam:artist"]) or ""
            title = _run(["-p", player, "metadata", "xesam:title"]) or ""

            if artist and title:
                return f"{artist} — {title}"
            if title:
                return title
        return None
