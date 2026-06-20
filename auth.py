# Авторизация через Telegram Login Widget.
# Проверка подписи данных виджета по bot-токену; доступ только разрешённым telegram_id.
import hashlib
import hmac
import os
import time
from functools import wraps

from flask import redirect, session

import settings_store as st

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
OWNER_TELEGRAM_ID = os.getenv("OWNER_TELEGRAM_ID", "")
# Для локальной разработки (виджет Telegram не работает на localhost): вход без виджета.
DEV_LOGIN = os.getenv("DEV_LOGIN", "") == "1"


def check_telegram_auth(data: dict) -> bool:
    """Проверяет подпись данных Telegram Login Widget."""
    if not BOT_TOKEN:
        return False
    data = dict(data)
    received = data.pop("hash", None)
    if not received:
        return False
    check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    calc = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return False
    # данные не старше суток
    try:
        if time.time() - int(data.get("auth_date", 0)) > 86400:
            return False
    except (ValueError, TypeError):
        return False
    return True


def _bootstrap_owner(telegram_id: int, name: str = ""):
    """Первый вход застолбляет владельца, если список пуст или задан OWNER_TELEGRAM_ID."""
    if st.allowed_count() == 0:
        st.add_allowed(telegram_id, name)
    if OWNER_TELEGRAM_ID and str(telegram_id) == OWNER_TELEGRAM_ID:
        st.add_allowed(telegram_id, name)


def try_login(data: dict) -> bool:
    """Проверяет данные виджета и логинит. Возвращает True при успехе."""
    if not check_telegram_auth(data):
        return False
    tid = int(data["id"])
    name = data.get("first_name", "") or data.get("username", "")
    _bootstrap_owner(tid, name)
    if not st.is_allowed(tid):
        return False
    session["user_id"] = tid
    session["user_name"] = name
    return True


def dev_login() -> bool:
    """Локальный вход без Telegram (только при DEV_LOGIN=1)."""
    if not DEV_LOGIN:
        return False
    tid = int(OWNER_TELEGRAM_ID or 0)
    _bootstrap_owner(tid, "dev")
    session["user_id"] = tid or "dev"
    session["user_name"] = "dev"
    return True


def logout():
    session.clear()


def is_logged_in() -> bool:
    return bool(session.get("user_id"))


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper
