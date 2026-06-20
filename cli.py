# Консольный визард настройки — для VPS без графики. Пишет в БД (settings_store).
from config import get_source
from providers.spotify import make_oauth
from providers.yandex import device_auth
import settings_store as st
from telegram_auth import cli_login


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    return input(f"{prompt}{suffix}: ").strip() or default


def _ask_yes(prompt: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    val = input(f"{prompt} ({d}): ").strip().lower()
    return default if not val else val in ("y", "yes", "д", "да")


def setup():
    """Интерактивная настройка в терминале (сохраняет в БД)."""
    st.ensure_db()
    config = st.get_settings()
    print("\n=== Настройка Music ===\n")

    # --- Telegram ---
    print("--- Telegram (my.telegram.org → API development tools) ---")
    config["telegram"]["api_id"] = int(_ask("api_id", str(config["telegram"]["api_id"] or "")) or 0)
    config["telegram"]["api_hash"] = _ask("api_hash", config["telegram"]["api_hash"])
    st.save_settings(config)

    if _ask_yes("Войти в Telegram сейчас?", True):
        try:
            me = cli_login(config["telegram"]["api_id"], config["telegram"]["api_hash"])
            print(f"✓ Вошёл как {me.first_name}\n")
        except Exception as e:
            print(f"Ошибка входа: {e}\n")

    # --- Spotify ---
    print("--- Spotify (облако, ловит отовсюду) ---")
    spo = get_source(config, "spotify")
    if _ask_yes("Настроить Spotify?", bool(spo.get("refresh_token"))):
        spo["client_id"] = _ask("client_id", spo.get("client_id", ""))
        spo["client_secret"] = _ask("client_secret", spo.get("client_secret", ""))
        print("Redirect URI в Spotify: http://127.0.0.1:8765/spotify/callback")
        try:
            oauth = make_oauth(spo["client_id"], spo["client_secret"], open_browser=False)
            print("\n1. Открой на своём компе:\n" + oauth.get_authorize_url())
            resp = _ask("\n2. Вставь URL, куда тебя перенаправило (или код)")
            token_info = oauth.get_access_token(oauth.parse_response_code(resp), check_cache=False)
            spo["refresh_token"] = token_info["refresh_token"]
            spo["enabled"] = True
            print("✓ Spotify подключён\n")
        except Exception as e:
            print(f"Ошибка Spotify: {e}\n")
    st.save_settings(config)

    # --- Яндекс ---
    print("--- Яндекс Музыка (облако, Ynison) ---")
    yan = get_source(config, "yandex")
    if _ask_yes("Настроить Яндекс?", bool(yan.get("token"))):
        def on_code(c):
            print(f"\n1. Открой {c.verification_url}\n2. Введи код: {c.user_code}\n   (жду подтверждения...)")
        try:
            yan["token"] = device_auth(on_code)
            yan["enabled"] = True
            print("✓ Яндекс подключён\n")
        except Exception as e:
            print(f"Ошибка Яндекса: {e}\n")
    st.save_settings(config)

    # --- MPRIS ---
    print("--- MPRIS (локально, только дома) ---")
    mp = get_source(config, "mpris")
    mp["enabled"] = _ask_yes("Включить MPRIS?", mp.get("enabled", True))
    if mp["enabled"]:
        mp["player_filter"] = _ask("Фильтр плеера (пусто = любой)", mp.get("player_filter", ""))
    st.save_settings(config)

    # --- Discord ---
    print("--- Discord ---")
    config.setdefault("discord", {"mode": "off", "client_id": "", "user_token": ""})
    print("Режимы: off | status (Custom Status, user-токен, работает в облаке) | presence (RPC, дома)")
    mode = _ask("Режим Discord", config["discord"].get("mode", "off"))
    config["discord"]["mode"] = mode
    if mode == "status":
        print("⚠ Custom Status через user-токен — против правил Discord, риск бана.")
        config["discord"]["user_token"] = _ask("User-токен", config["discord"].get("user_token", ""))
    elif mode == "presence":
        config["discord"]["client_id"] = _ask("Application ID", config["discord"].get("client_id", ""))
    st.save_settings(config)

    # --- Bio ---
    print("--- Bio (Telegram) ---")
    config["bio_template"] = _ask("Шаблон ({track} = трек, можно текст до/после)", config["bio_template"])
    config["bio_idle"] = _ask("Текст при тишине (пусто = убрать)", config.get("bio_idle", ""))
    config["interval"] = int(_ask("Интервал, сек", str(config["interval"])) or 20)
    st.save_settings(config)

    # запустить движок сразу?
    st.set_running(_ask_yes("Запустить сейчас (running=on)?", True))

    print("\n✓ Готово. Запуск воркера: python app.py worker  (веб: python app.py web)\n")
