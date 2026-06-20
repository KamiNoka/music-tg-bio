# Источник трека через Яндекс Музыку по протоколу Ynison (realtime-синхронизация устройств).
# В отличие от queues, Ynison видит, что играет на ЛЮБОМ устройстве (телефон, десктоп, веб) —
# это «где бы ни слушал» для Яндекса.
#
# Особенности окружения (РКН): домены Яндекс-музыки часто заблокированы в системном DNS,
# а IPv6-связности может не быть. Поэтому резолвим хосты сами через DoH (DNS-over-HTTPS)
# и форсируем IPv4. Если до ynison-бэкенда нет сети (DPI режет) — нужен активный обход/VPN.
import socket

import requests
import urllib3
from yandex_music import Client
from yandex_music.ynison import simple

from .base import Provider

# DoH идёт на IP 1.1.1.1 без проверки сертификата по hostname — глушим предупреждение
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# DoH-резолвер (Cloudflare по IP, в обход заблокированного системного DNS)
_DOH_URL = "https://1.1.1.1/dns-query"
_dns_cache: dict[str, list[str]] = {}


def _doh_v4(host: str) -> list[str]:
    """Резолвит host в IPv4 через DoH, с кешем. Пусто при неудаче."""
    if host in _dns_cache:
        return _dns_cache[host]
    ips: list[str] = []
    try:
        r = requests.get(
            _DOH_URL, params={"name": host, "type": "A"},
            headers={"accept": "application/dns-json"}, timeout=8, verify=False,
        )
        ips = [a["data"] for a in r.json().get("Answer", []) if a.get("type") == 1]
    except Exception:
        ips = []
    _dns_cache[host] = ips
    return ips


def _is_ip(host: str) -> bool:
    return all(c.isdigit() or c == "." for c in host)


class _V4DoHResolver:
    """Контекст: на время блока подменяет socket.getaddrinfo на DoH IPv4-only.
    Нужен, чтобы обойти DNS-блокировку доменов Яндекса и отсутствие IPv6."""

    def __enter__(self):
        self._orig = socket.getaddrinfo

        def patched(host, port, family=0, type=0, proto=0, flags=0):
            if not host or _is_ip(host):
                return self._orig(host, port, socket.AF_INET, type, proto, flags)
            ips = _doh_v4(host)
            if not ips:
                # нет DoH-ответа — пробуем системный резолвер (только IPv4)
                return self._orig(host, port, socket.AF_INET, type, proto, flags)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

        socket.getaddrinfo = patched
        return self

    def __exit__(self, *exc):
        socket.getaddrinfo = self._orig


def device_auth(on_code) -> str:
    """OAuth Device Flow: возвращает access_token. on_code(code) — показать ссылку и код."""
    client = Client()
    token = client.device_auth(on_code=on_code)
    return token.access_token


class YandexProvider(Provider):
    name = "Яндекс Музыка"

    def __init__(self, token: str, device_id: str = "musictgbio0001"):
        self.token = token
        self.device_id = device_id
        self._client: Client | None = None  # для дозапроса исполнителя по id

    def _artists_for(self, track_id: str) -> str:
        """Дозапрашивает исполнителя по id трека (Ynison отдаёт только название)."""
        try:
            if self._client is None:
                self._client = Client(self.token).init()
            tracks = self._client.tracks([track_id])
            if tracks and tracks[0].artists:
                return ", ".join(a.name for a in tracks[0].artists)
        except Exception:
            pass
        return ""

    def get_now_playing(self) -> str | None:
        try:
            with _V4DoHResolver():
                pl = simple.get_current_track(self.token, device_id=self.device_id, timeout=10)
                if not pl or not pl.title:
                    return None
                title = pl.title
                artists = self._artists_for(pl.playable_id) if pl.playable_id else ""
            if artists and title:
                return f"{artists} — {title}"
            return title
        except Exception as e:
            print(f"[yandex] ошибка: {e}")
            return None
