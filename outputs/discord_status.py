# Выход в Discord Custom Status (текст-«мысль» рядом с ником).
# ВНИМАНИЕ: меняется только через user-токен (selfbot) — это против ToS Discord, риск бана.
# Работает по HTTP, поэтому годится и для облака.
import requests

API = "https://discord.com/api/v9/users/@me/settings"


class DiscordStatus:
    def __init__(self, user_token: str):
        self.token = user_token
        self._last = object()  # sentinel

    def update(self, text: str | None):
        if text == self._last:
            return
        custom = {"text": text[:128]} if text else None
        try:
            requests.patch(
                API,
                headers={"Authorization": self.token, "Content-Type": "application/json"},
                json={"custom_status": custom},
                timeout=10,
            )
            self._last = text
        except Exception as e:
            print(f"[discord-status] ошибка: {e}")

    def clear(self):
        self.update(None)
